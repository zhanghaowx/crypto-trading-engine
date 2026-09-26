"""The token sheet says what the prototype says.

The prototype's stylesheet is the executable reference for every colour
and measure; `tokens.css` repeats the Slate values for the dashboard's own
CSS, and a value stated twice is a value that can drift. The guidelines
record exactly that happening once. This is what catches it.
"""

import re
from pathlib import Path

STATIC = (
    Path(__file__).resolve().parents[3] / "jolteon" / "dashboard" / "static"
)

_DECLARATION = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _root_tokens(css: str) -> dict[str, str]:
    """The custom properties of the first `:root` block - the prototype's
    Slate palette, before its Sage and Morandi overrides."""
    block = css.split(":root", 1)[1].split("}", 1)[0]
    return {
        name: value.strip().lower()
        for name, value in _DECLARATION.findall(block)
    }


def test_every_shared_token_carries_the_prototypes_value():
    prototype = _root_tokens(
        (STATIC / "prototype" / "styles.css").read_text(encoding="utf-8")
    )
    ours = _root_tokens((STATIC / "tokens.css").read_text(encoding="utf-8"))

    shared = {name: ours[name] for name in ours if name in prototype}
    assert shared, "the token sheet shares no names with the prototype"
    drifted = {
        name: (value, prototype[name])
        for name, value in shared.items()
        if value != prototype[name]
    }
    assert not drifted, f"tokens differ from the prototype: {drifted}"


def test_the_token_sheet_carries_the_roles_the_guidelines_name():
    ours = _root_tokens((STATIC / "tokens.css").read_text(encoding="utf-8"))

    for role in (
        "--canvas",
        "--surface",
        "--ink",
        "--muted",
        "--line",
        "--accent",
        "--positive",
        "--positive-soft",
        "--negative",
        "--negative-soft",
        "--warning",
        "--warning-soft",
        "--info",
        "--info-soft",
    ):
        assert role in ours, role


def test_no_stylesheet_of_ours_spells_a_slate_colour_by_hand():
    """A colour named as a hex in a stylesheet is one a palette change
    cannot reach. The prototype's own sheet defines the tokens, so it is
    the one place a hex belongs."""
    spelled = {}
    for sheet in STATIC.glob("*.css"):
        if sheet.name == "tokens.css":
            continue
        hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", sheet.read_text("utf-8"))
        if hexes:
            spelled[sheet.name] = sorted(set(hexes))
    assert not spelled, f"hex colours outside the token sheet: {spelled}"
