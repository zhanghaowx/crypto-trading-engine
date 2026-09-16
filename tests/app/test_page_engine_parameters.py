import sqlite3
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from jolteon import paths
from jolteon.app.app_pages import engine_parameters
from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_change_result import (
    REJECTED,
    TAKEN,
    UNKNOWN,
    change_key,
)
from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
    parameter,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
    change_of,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)


def _key(group_name: str, field_name: str, symbol: str = ALL_SYMBOLS) -> str:
    return engine_parameters._widget_key((symbol, group_name, field_name))


QUOTE_SIZE = _key("MarketMakingParameters", "quote_size")
BOOK_DEPTH = _key("MarketMakingParameters", "book_depth")


def _script():
    from jolteon.app.app_pages import engine_parameters

    engine_parameters.render()


def _page(params_db_path, missing_db_path, root=None) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["params_db_path"] = params_db_path
    at.session_state["db_path"] = missing_db_path
    # A root nothing has run under, so no symbol is on offer unless the
    # test points the page at engines of its own. Left at its default it
    # would find whatever engines the machine really has running.
    at.session_state["root"] = root or str(
        Path(missing_db_path).parent / "no-engine"
    )
    return at


def test_renders_a_widget_for_every_declared_parameter(
    params_db_path, missing_db_path
):
    """
    The page is built from the catalog, so a parameter added to the
    engine has to appear here without anyone editing this page. If it
    cannot be rendered, that fails here rather than going unnoticed.
    """
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    kinds = (at.number_input, at.checkbox, at.selectbox, at.text_input)
    rendered = {widget.key for kind in kinds for widget in kind}
    expected = {
        _key(group.__name__, definition.name)
        for group in GROUPS
        for definition in definitions(group)
    }
    assert expected == rendered & expected


def test_seeds_each_widget_from_its_declared_default(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    assert at.number_input(key=QUOTE_SIZE).value == 0.0005
    assert at.number_input(key=BOOK_DEPTH).value == 10


def test_takes_its_bounds_from_the_declaration(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    quote_size = at.number_input(key=QUOTE_SIZE)
    declared = {d.name: d for d in definitions(MarketMakingParameters)}
    assert quote_size.min == declared["quote_size"].minimum
    assert quote_size.max == declared["quote_size"].maximum
    assert quote_size.step == declared["quote_size"].step


def test_a_field_explains_itself_where_its_name_is(
    params_db_path, missing_db_path
):
    """
    The tooltip belongs to the label, and the label is on a row of its
    own now so the field's state can sit beside it.
    """
    at = _page(params_db_path, missing_db_path).run()

    declared = {d.name: d for d in definitions(MarketMakingParameters)}
    quote_size = declared["quote_size"]
    labels = {m.proto.body: m.proto.help for m in at.markdown}

    assert (
        labels[engine_parameters._field_label(quote_size)]
        == quote_size.description
    )


def test_an_edit_reaches_no_file_until_it_is_pushed(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

    assert not at.exception
    assert not Path(params_db_path).exists()
    assert ParameterStore(params_db_path).read() == []


def test_an_edit_shows_what_it_would_change(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

    assert not at.exception
    assert not at.button[0].disabled
    summary = at.markdown[-1].value
    assert (
        "| Market Making · Quote Size | All Symbols | 0.00050 | 0.02000 |"
        in summary
    )


def test_an_edit_shows_the_value_it_is_replacing(
    params_db_path, missing_db_path
):
    """
    What a field is changing from is what an engine reads today, which is
    the stored value once one has been pushed rather than the value the
    parameter declares.
    """
    ParameterStore(params_db_path).push(
        [change_of("MarketMakingParameters", "quote_size", 0.01)]
    )
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

    assert not at.exception
    assert (
        "| Market Making · Quote Size | All Symbols | 0.01000 | 0.02000 |"
        in at.markdown[-1].value
    )


def test_pushing_writes_every_staged_change(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.number_input(key=BOOK_DEPTH).set_value(4).run()
    at.button[0].click().run()

    assert not at.exception
    stored = {
        o.field_name: o.value for o in ParameterStore(params_db_path).read()
    }
    assert stored == {"quote_size": 0.02, "book_depth": 4}


def test_a_pushed_int_stays_an_int(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=BOOK_DEPTH).set_value(4).run()
    at.button[0].click().run()

    stored = ParameterStore(params_db_path).read()
    assert isinstance(stored[0].value, int)
    assert stored[0].symbol == ALL_SYMBOLS


def test_pushing_clears_what_was_staged(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["_staged_parameters"] == {}
    assert at.button[0].disabled
    assert "| Market Making · Quote Size |" not in at.markdown[-1].value


def test_reverting_drops_the_edit_and_writes_nothing(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[1].click().run()

    assert not at.exception
    assert at.session_state["_staged_parameters"] == {}
    assert ParameterStore(params_db_path).read() == []


def test_a_pushed_value_comes_back_as_the_widgets_value(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[0].click().run()

    fresh = _page(params_db_path, missing_db_path).run()
    assert fresh.number_input(key=QUOTE_SIZE).value == 0.02


def test_says_nothing_about_a_parameter_left_at_its_default(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    assert not at.caption


def test_reports_a_stored_value_no_engine_has_read(
    params_db_path, missing_db_path
):
    """
    A pushed value with no engine behind it has to say so. Showing it in
    the widget and nothing else reads as though it were in force.
    """
    ParameterStore(params_db_path).push(
        [change_of("MarketMakingParameters", "quote_size", 0.02)]
    )
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    assert any(
        "no engine has reported" in caption.value for caption in at.caption
    )


def test_a_fields_state_sits_on_the_row_with_its_name(
    params_db_path, missing_db_path
):
    """
    Under the widget, a badge reads as though it belonged to whatever
    came next; beside the name it is about, it reads as part of the
    field.
    """
    ParameterStore(params_db_path).push(
        [change_of("MarketMakingParameters", "quote_size", 0.02)]
    )
    at = _page(params_db_path, missing_db_path).run()

    declared = {d.name: d for d in definitions(MarketMakingParameters)}
    label = engine_parameters._field_label(declared["quote_size"])
    bodies = [m.proto.body for m in at.markdown]

    assert bodies[bodies.index(label) + 1].endswith("-badge[Not picked up]")


class TestAStoreThePageCannotRender:
    """
    A store can hold a value no widget will take: a field's bounds may
    have been tightened after it was pushed, or something may have
    written to the store directly. The engine refuses such a value and
    keeps running, and the page has to stay up the same way - one bad
    field used to raise and take every other field down with it.
    """

    def test_a_value_above_the_maximum_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=QUOTE_SIZE).value == 10.0

    def test_a_value_below_the_minimum_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "quote_size", -5.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=QUOTE_SIZE).value == 0.00001

    def test_a_value_of_the_wrong_type_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "book_depth", "ten")]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=BOOK_DEPTH).value == 10

    def test_says_what_is_really_stored_and_that_it_is_refused(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        captions = " ".join(caption.value for caption in at.caption)
        assert "Stored as 99.0" in captions
        assert "refuses it" in captions
        # Its declared minimum is 0.00001, which str() renders as 1e-05.
        assert "Allowed: 0.00001 to 10.00000." in captions

    def test_every_other_field_still_renders(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        expected = sum(len(definitions(group)) for group in GROUPS)
        kinds = (at.number_input, at.checkbox, at.selectbox, at.text_input)
        assert sum(len(kind) for kind in kinds) == expected

    def test_it_is_not_quietly_corrected_on_the_users_behalf(
        self, params_db_path, missing_db_path
    ):
        """
        Showing a clamped value must not stage or push one. The bad value
        stays in the store until someone decides what it should be.
        """
        store = ParameterStore(params_db_path)
        store.push([change_of("MarketMakingParameters", "quote_size", 99.0)])
        at = _page(params_db_path, missing_db_path).run()

        assert at.session_state["_staged_parameters"] == {}
        assert store.read()[0].value == 99.0


@dataclass(frozen=True)
class DemoParameters(ParameterGroup):
    """
    A group declaring the two field kinds no catalogued group happens to
    use yet. The page is built from what a group declares, so both have
    to render for a later group that does use them.
    """

    mode: str = parameter("fast", choices=("fast", "slow"))
    label: str = parameter("alpha")


MODE = _key("DemoParameters", "mode")
LABEL = _key("DemoParameters", "label")


@pytest.fixture
def demo_catalog():
    """The page holds its own reference to GROUPS, so patching the
    catalog module it came from would not reach it."""
    with patch.object(engine_parameters, "GROUPS", (DemoParameters,)):
        yield


def _reported(root, traded="BTC/USD", exchange=None, **row) -> str:
    """One engine's recording, holding the report it made about a pushed
    parameter, as SQLiteWriter would have recorded it. Returns the root
    the engine trading `traded` recorded under."""
    columns = {
        "key": change_key(
            "MarketMakingParameters",
            "quote_size",
            row.get("symbol", ALL_SYMBOLS),
        ),
        "group_name": "MarketMakingParameters",
        "field_name": "quote_size",
        "symbol": ALL_SYMBOLS,
        "stored_value": "0.02",
        "current_revision": 1,
        "last_read_revision": 1,
        "status": TAKEN,
        "reason": "",
        **row,
    }
    db_path = (
        paths.recording(root, exchange, traded)
        if exchange
        else paths.recording(root, traded)
    )
    paths.prepare(db_path)
    with sqlite3.connect(db_path) as conn:
        current_revision = columns.pop("current_revision")
        last_read_revision = columns.pop("last_read_revision")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS parameter_change_result ("
            "key TEXT PRIMARY KEY, group_name TEXT, field_name TEXT, "
            "symbol TEXT, stored_value TEXT, status TEXT, reason TEXT)"
        )
        conn.execute(
            "INSERT INTO parameter_change_result VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(columns.values()),
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS parameter_group_revision ("
            "group_name TEXT PRIMARY KEY, current_revision INTEGER, "
            "last_read_revision INTEGER)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO parameter_group_revision VALUES (?, ?, ?)",
            (columns["group_name"], current_revision, last_read_revision),
        )
    conn.close()
    return root


class TestFieldKindsBeyondNumbers:
    def test_a_field_with_choices_renders_as_a_selectbox(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.selectbox(key=MODE).options == ["fast", "slow"]
        assert at.selectbox(key=MODE).value == "fast"

    def test_a_plain_string_field_renders_as_a_text_input(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.text_input(key=LABEL).value == "alpha"

    def test_choosing_another_option_stages_it(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        at = _page(params_db_path, missing_db_path).run()
        at.selectbox(key=MODE).select("slow").run()
        at.button[0].click().run()

        assert not at.exception
        stored = {
            o.field_name: o.value
            for o in ParameterStore(params_db_path).read()
        }
        assert stored == {"mode": "slow"}

    def test_typing_a_string_stages_it(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        at = _page(params_db_path, missing_db_path).run()
        at.text_input(key=LABEL).set_value("beta").run()
        at.button[0].click().run()

        assert not at.exception
        assert ParameterStore(params_db_path).read()[0].value == "beta"

    def test_a_stored_value_outside_the_choices_does_not_break_the_page(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("DemoParameters", "mode", "sideways")]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.selectbox(key=MODE).value == "fast"

    def test_says_which_options_a_refused_value_should_have_been_one_of(
        self, demo_catalog, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [change_of("DemoParameters", "mode", "sideways")]
        )
        at = _page(params_db_path, missing_db_path).run()

        captions = " ".join(caption.value for caption in at.caption)
        assert "Stored as sideways" in captions
        assert "Allowed: fast, slow." in captions


class TestWhatTheEngineSaidItDid:
    """
    A pushed value is only half the story: the page has to say what the
    engine reported back, or a stored value reads as one in force.
    """

    def _pushed(self, params_db_path):
        ParameterStore(params_db_path).push(
            [change_of("MarketMakingParameters", "quote_size", 0.02)]
        )

    @staticmethod
    def _badges(at) -> str:
        # st.badge reaches AppTest as markdown, as ":green-badge[applied]".
        return " ".join(m.value for m in at.markdown if "-badge[" in m.value)

    def test_a_change_whose_group_was_read_says_nothing(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        An accepted change needs no badge once its group has been read.
        """
        self._pushed(params_db_path)
        at = _page(
            params_db_path,
            missing_db_path,
            _reported(str(tmp_path), current_revision=3, last_read_revision=3),
        ).run()

        assert not at.exception
        assert not self._badges(at)

    def test_a_value_no_component_has_looked_at_says_so(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        The change was accepted, but its current group has not been read.
        """
        self._pushed(params_db_path)
        at = _page(
            params_db_path,
            missing_db_path,
            _reported(str(tmp_path), current_revision=3, last_read_revision=1),
        ).run()

        captions = " ".join(c.value for c in at.caption)
        assert "no component has read the current parameter group" in captions
        assert "Not read yet" in self._badges(at)

    def test_a_group_never_read_is_not_reported_as_read(
        self, params_db_path, missing_db_path, tmp_path
    ):
        self._pushed(params_db_path)
        root = _reported(str(tmp_path), last_read_revision=None)
        at = _page(params_db_path, missing_db_path, root).run()
        assert not at.exception
        assert "Not read yet" in self._badges(at)

    @pytest.mark.parametrize("missing", ["table", "group"])
    def test_missing_revision_information_is_not_reported_as_read(
        self, params_db_path, missing_db_path, tmp_path, missing
    ):
        self._pushed(params_db_path)
        root = _reported(str(tmp_path))
        with sqlite3.connect(paths.recording(root, "BTC/USD")) as conn:
            if missing == "table":
                conn.execute("DROP TABLE parameter_group_revision")
            else:
                conn.execute(
                    "UPDATE parameter_group_revision "
                    "SET group_name = 'AnotherGroup'"
                )
        conn.close()
        at = _page(params_db_path, missing_db_path, root).run()
        assert not at.exception
        assert "Not read yet" in self._badges(at)

    def test_group_revisions_are_joined_within_each_engine(
        self, params_db_path, missing_db_path, tmp_path
    ):
        self._pushed(params_db_path)
        root = str(tmp_path)
        _reported(
            root, traded="BTC/USD", current_revision=2, last_read_revision=1
        )
        _reported(
            root, traded="ETH/USD", current_revision=10, last_read_revision=10
        )
        at = _page(params_db_path, missing_db_path, root).run()
        assert not at.exception
        assert "Not read yet" in self._badges(at)

    def test_a_refused_value_reports_the_engines_own_reason(
        self, params_db_path, missing_db_path, tmp_path
    ):
        self._pushed(params_db_path)
        at = _page(
            params_db_path,
            missing_db_path,
            _reported(
                str(tmp_path), status=REJECTED, reason="must be at most 10.0"
            ),
        ).run()

        captions = " ".join(c.value for c in at.caption)
        assert "must be at most 10.0" in captions
        assert "Rejected" in self._badges(at)

    def test_a_status_the_page_does_not_know_is_shown_as_it_came(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        The engine decides what statuses exist, so one this page has
        never heard of is passed through rather than swallowed.
        """
        self._pushed(params_db_path)
        at = _page(
            params_db_path,
            missing_db_path,
            _reported(str(tmp_path), status=UNKNOWN),
        ).run()

        assert not at.exception
        assert UNKNOWN in self._badges(at)

    def test_the_engine_trading_a_symbol_is_the_one_asked_about_it(
        self, params_db_path, tmp_path
    ):
        """
        A value set for one symbol is read by the engine trading that
        symbol and by no other, so asking whichever recording happens to
        be on screen reported on the wrong process - a value ETH had
        picked up read as "not picked up" while BTC was being viewed.
        """
        eth = "ETH/USD"
        ParameterStore(params_db_path).push(
            [
                ParameterChange(
                    "MarketMakingParameters", "quote_size", eth, 0.01
                )
            ]
        )
        root = str(tmp_path)
        paths.prepare(paths.recording(root, "BTC/USD"))
        _reported(root, traded=eth, symbol=eth)

        at = _page(params_db_path, paths.recording(root, "BTC/USD"), root)
        at.session_state[engine_parameters._SCOPE] = eth
        at.run()

        assert not at.exception
        # Read by the engine trading it, so there is nothing to report -
        # which is exactly what "not picked up" would have contradicted.
        assert not self._badges(at)

    def test_one_engine_refusing_a_shared_value_is_what_is_shown(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        A value set for every symbol is read by every engine, and it is
        not in force while any one of them refuses it - so the least
        settled of their answers is the one that gets shown.
        """
        self._pushed(params_db_path)
        root = str(tmp_path)
        _reported(root, traded="BTC/USD")
        _reported(
            root,
            traded="ETH/USD",
            status=REJECTED,
            reason="must be at most 10.0",
        )

        at = _page(params_db_path, missing_db_path, root).run()

        assert "Rejected" in self._badges(at)
        assert "must be at most 10.0" in " ".join(c.value for c in at.caption)

    def test_ignores_parameter_reports_from_another_exchange(
        self, params_db_path, missing_db_path, tmp_path
    ):
        self._pushed(params_db_path)
        root = str(tmp_path)
        _reported(root, traded="BTC/USD", exchange="Kraken")
        _reported(
            root,
            traded="BTC/USD",
            exchange="Binance.US",
            status=REJECTED,
            reason="another venue",
        )

        at = _page(params_db_path, missing_db_path, root)
        at.session_state["exchange"] = "Kraken"
        at.run()

        assert "Rejected" not in self._badges(at)
        assert "another venue" not in " ".join(c.value for c in at.caption)

    def test_a_status_the_page_does_not_know_outranks_a_settled_one(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        The engine decides what statuses exist, so one this page has
        never heard of cannot be assumed to mean the value is running -
        it has to survive being read alongside an engine that took it.
        """
        self._pushed(params_db_path)
        root = str(tmp_path)
        _reported(root, traded="BTC/USD")
        _reported(root, traded="ETH/USD", status=UNKNOWN)

        at = _page(params_db_path, missing_db_path, root).run()

        assert UNKNOWN in self._badges(at)

    def test_a_settled_answer_does_not_displace_an_unsettled_one(
        self, params_db_path, missing_db_path, tmp_path
    ):
        """
        The same as above with the engines the other way round, since
        they are read in the order their symbols sort in.
        """
        self._pushed(params_db_path)
        root = str(tmp_path)
        _reported(root, traded="BTC/USD", status=REJECTED, reason="too big")
        _reported(root, traded="ETH/USD")

        at = _page(params_db_path, missing_db_path, root).run()

        assert "Rejected" in self._badges(at)


class TestTuningOneSymbol:
    """
    A size or an edge that suits one instrument suits no other, so a
    value can be set for one symbol without disturbing the rest. The page
    has to resolve a symbol exactly as the engine does, or it shows a
    number the engine is not running on.
    """

    ETH = "ETH/USD"

    def _eth_quote_size(self) -> str:
        return _key("MarketMakingParameters", "quote_size", self.ETH)

    def _seeded(self, params_db_path, changes):
        ParameterStore(params_db_path).push(changes)

    def _page_for(self, params_db_path, missing_db_path, symbol=None):
        at = _page(params_db_path, missing_db_path)
        if symbol is not None:
            at.session_state[engine_parameters._SCOPE] = symbol
        return at.run()

    def test_offers_no_choice_until_a_symbol_is_known(
        self, params_db_path, missing_db_path
    ):
        at = _page(params_db_path, missing_db_path).run()
        assert not at.exception
        assert len(at.segmented_control) == 0

    def test_offers_every_symbol_the_store_has_heard_of(
        self, params_db_path, missing_db_path
    ):
        self._seeded(
            params_db_path,
            [
                ParameterChange(
                    "MarketMakingParameters", "quote_size", self.ETH, 0.01
                )
            ],
        )
        at = self._page_for(params_db_path, missing_db_path)

        assert not at.exception
        # AppTest reports the labels, not the values behind them.
        assert ["All Symbols", self.ETH] == at.segmented_control[0].options

    def test_offers_a_symbol_an_engine_has_actually_traded(
        self, params_db_path, missing_db_path, tmp_path, recordings
    ):
        """
        The usual way a symbol becomes tunable: an engine ran on it and
        recorded its ticks, so nobody has to register it here first.
        """
        at = _page(params_db_path, missing_db_path, str(tmp_path)).run()

        assert not at.exception
        assert [
            "All Symbols",
            "BTC/USD",
            "ETH/USD",
        ] == at.segmented_control[0].options

    def test_offers_every_running_engines_symbol_not_just_the_one_shown(
        self, params_db_path, recordings, tmp_path
    ):
        """
        Tuning a symbol must not wait on the Live page being switched to
        it: the page reads one engine's recording, but a value pushed for
        any symbol is read by the engine trading it.
        """
        at = _page(params_db_path, recordings["BTC/USD"], str(tmp_path)).run()

        assert not at.exception
        assert "ETH/USD" in at.segmented_control[0].options

    def test_a_symbol_shows_what_it_would_inherit(
        self, params_db_path, missing_db_path
    ):
        """
        A field a symbol has no value for is not on its declared default:
        it is on whatever every symbol uses.
        """
        self._seeded(
            params_db_path,
            [
                change_of("MarketMakingParameters", "quote_size", 0.02),
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                ),
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)

        assert not at.exception
        assert 0.02 == at.number_input(key=self._eth_quote_size()).value

    def test_a_symbols_own_value_wins(self, params_db_path, missing_db_path):
        self._seeded(
            params_db_path,
            [
                change_of("MarketMakingParameters", "quote_size", 0.02),
                ParameterChange(
                    "MarketMakingParameters", "quote_size", self.ETH, 0.01
                ),
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)

        assert 0.01 == at.number_input(key=self._eth_quote_size()).value

    def test_says_which_values_a_symbol_is_only_inheriting(
        self, params_db_path, missing_db_path
    ):
        self._seeded(
            params_db_path,
            [
                change_of("MarketMakingParameters", "quote_size", 0.02),
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                ),
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)

        badges = " ".join(m.value for m in at.markdown if "-badge[" in m.value)
        assert "Inherited" in badges

    def test_an_edit_is_stored_against_the_symbol_chosen(
        self, params_db_path, missing_db_path
    ):
        self._seeded(
            params_db_path,
            [
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                )
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)
        at.number_input(key=self._eth_quote_size()).set_value(0.01).run()
        at.button[0].click().run()

        assert not at.exception
        stored = {
            (o.symbol, o.field_name): o.value
            for o in ParameterStore(params_db_path).read()
        }
        assert 0.01 == stored[(self.ETH, "quote_size")]

    def test_editing_a_symbol_leaves_every_other_symbol_alone(
        self, params_db_path, missing_db_path
    ):
        self._seeded(
            params_db_path,
            [
                change_of("MarketMakingParameters", "quote_size", 0.02),
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                ),
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)
        at.number_input(key=self._eth_quote_size()).set_value(0.01).run()
        at.button[0].click().run()

        shared = _page(params_db_path, missing_db_path).run()
        assert 0.02 == shared.number_input(key=QUOTE_SIZE).value

    def test_a_staged_edit_names_the_symbol_it_applies_to(
        self, params_db_path, missing_db_path
    ):
        self._seeded(
            params_db_path,
            [
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                )
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)
        at.number_input(key=self._eth_quote_size()).set_value(0.01).run()

        assert f"| {self.ETH} |" in at.markdown[-1].value

    def test_each_symbol_keeps_its_own_widget(
        self, params_db_path, missing_db_path
    ):
        """
        Widgets are keyed by scope as well as by name. Keyed by name
        alone, Streamlit would carry one symbol's edit over to the next
        symbol selected.
        """
        self._seeded(
            params_db_path,
            [
                ParameterChange(
                    "MarketMakingParameters", "quote_size", self.ETH, 0.01
                )
            ],
        )
        at = self._page_for(params_db_path, missing_db_path, self.ETH)

        assert self._eth_quote_size() in {
            widget.key for widget in at.number_input
        }
        assert QUOTE_SIZE not in {widget.key for widget in at.number_input}

    def test_a_symbol_follows_a_shared_edit_before_it_is_committed(
        self, params_db_path, missing_db_path
    ):
        """
        Staging a change for every symbol and then looking at one of them
        has to show the change, not the value it is about to replace.
        """
        self._seeded(
            params_db_path,
            [
                ParameterChange(
                    "MarketMakingParameters", "book_depth", self.ETH, 4
                )
            ],
        )
        at = self._page_for(params_db_path, missing_db_path)
        at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

        at.session_state[engine_parameters._SCOPE] = self.ETH
        at.run()

        assert not at.exception
        assert 0.02 == at.number_input(key=self._eth_quote_size()).value
