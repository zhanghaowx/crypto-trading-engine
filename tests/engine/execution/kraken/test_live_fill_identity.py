"""Regression coverage for issue #64, using captured-shape REST responses."""

import asyncio
import copy
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from jolteon.engine.core.event.signal_recorder import SignalRecorder
from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.fill_identity import fill_identity
from jolteon.engine.execution.kraken.execution_service import ExecutionService
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import Order, OrderType
from jolteon.engine.post_trade.post_trade_service import PostTradeService


@pytest.fixture
def venue(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "test")
    monkeypatch.setenv("KRAKEN_API_SECRET", "dGVzdA==")
    service = ExecutionService(dry_run=False)
    order = Order(
        client_order_id="123",
        order_type=OrderType.MARKET_ORDER,
        symbol="BTC/USD",
        side=MarketSide.BUY,
        price=100,
        quantity=1,
        creation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    orders = {}
    executions = {}
    fills = []

    def receive(_, trade):
        fills.append(trade)

    service.order_fill_event.connect(receive)

    def request(endpoint, payload):
        if endpoint.endswith("QueryOrders"):
            assert payload["trades"] is True
            assert payload["consolidate_taker"] is False
            source = orders
        else:
            assert endpoint.endswith("QueryTrades")
            source = executions
        result = {
            key: source[key]
            for key in payload["txid"].split(",")
            if key in source
        }
        return MagicMock(
            status_code=200, json=lambda: {"error": [], "result": result}
        )

    service._client.send_request = MagicMock(side_effect=request)
    # Keep the weak signal receiver alive for the fixture's duration.
    yield service, order, orders, executions, fills
    service.order_fill_event.disconnect(receive)


def execution(order_id, *, volume="0.5", time=1704067200.0):
    return {
        "ordertxid": order_id,
        "trade_id": 7,
        "type": "buy",
        "price": "100",
        "fee": "0.1",
        "vol": volume,
        "time": time,
    }


def order_status(trade_ids, *, volume="1", status="closed"):
    return {
        "descr": {"type": "buy"},
        "status": status,
        "vol_exec": volume,
        "trades": trade_ids,
    }


def test_identical_fills_on_separate_orders_have_distinct_stable_ids(venue):
    service, order, orders, executions, fills = venue
    for index in (1, 2):
        orders[f"O{index}"] = order_status([f"T{index}"], volume="0.5")
        executions[f"T{index}"] = execution(f"O{index}")
        service._get_fills(
            [f"O{index}"], replace(order, client_order_id=str(index))
        )
    assert len({fill.fill_id for fill in fills}) == 2
    assert [fill.client_order_id for fill in fills] == ["1", "2"]
    assert [fill.exchange_order_id for fill in fills] == ["O1", "O2"]
    assert [fill.exchange_trade_id for fill in fills] == ["T1", "T2"]
    assert fills[0].price == fills[1].price
    assert fills[0].quantity == fills[1].quantity
    assert fills[0].transaction_time == fills[1].transaction_time
    assert fills[0].trade_id == fills[1].trade_id == 7

    restarted = ExecutionService(dry_run=False)
    restarted._client = service._client
    restarted._get_fills(["O1"], replace(order, client_order_id="1"))
    assert fills[2] == fills[0]


def test_partial_fills_arrive_once_with_their_own_price_fee_and_time(venue):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1"], volume="0.5", status="open")
    executions["T1"] = execution("O1")
    for _ in range(2):
        with pytest.raises(RuntimeError, match="still open"):
            service._get_fills(["O1"], order)
    assert len(fills) == 1
    orders["O1"] = order_status(["T1", "T2"])
    executions["T2"] = {
        **execution("O1", time=1704067201.0),
        "price": "101",
        "fee": "0.2",
    }
    service._get_fills(["O1"], order)
    service._get_fills(["O1"], order)
    assert len(fills) == 2
    assert len({fill.fill_id for fill in fills}) == 2
    assert [fill.price for fill in fills] == [100, 101]
    assert [fill.fee for fill in fills] == [0.1, 0.2]
    assert sum(fill.quantity for fill in fills) == 1
    requests = service._client.send_request.call_args_list
    assert [
        call.args[1]["txid"]
        for call in requests
        if call.args[0].endswith("QueryTrades")
    ] == ["T1", "T2"]


@pytest.mark.parametrize("status", ["canceled", "expired"])
def test_terminal_orders_preserve_partial_fills_and_stop_polling(
    venue, status
):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1"], volume="0.5", status=status)
    executions["T1"] = execution("O1")
    service._get_fills(["O1"], order)
    assert [fill.quantity for fill in fills] == [0.5]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_order",
        "missing_trade",
        "wrong_order",
        "wrong_side",
        "wrong_volume",
    ],
)
def test_incomplete_or_mismatched_responses_publish_nothing_and_can_retry(
    venue, fault
):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1", "T2"])
    executions.update({"T1": execution("O1"), "T2": execution("O1")})
    good_orders, good_executions = (
        copy.deepcopy(orders),
        copy.deepcopy(executions),
    )
    if fault == "missing_order":
        orders.clear()
    elif fault == "missing_trade":
        del executions["T2"]
    elif fault == "wrong_order":
        executions["T2"]["ordertxid"] = "other"
    elif fault == "wrong_side":
        executions["T2"]["type"] = "sell"
    else:
        executions["T2"]["vol"] = "0.4"
    with pytest.raises((RuntimeError, ValueError)):
        service._get_fills(["O1"], order)
    assert not fills
    orders.clear()
    orders.update(good_orders)
    executions.clear()
    executions.update(good_executions)
    service._get_fills(["O1"], order)
    assert len(fills) == 2


def test_trade_lookup_respects_twenty_id_limit(venue):
    service, order, orders, executions, fills = venue
    ids = [f"T{i}" for i in range(21)]
    orders["O1"] = order_status(ids, volume="10.5")
    executions.update({key: execution("O1") for key in ids})
    service._get_fills(["O1"], replace(order, quantity=10.5))
    queries = [
        call
        for call in service._client.send_request.call_args_list
        if call.args[0].endswith("QueryTrades")
    ]
    assert [len(call.args[1]["txid"].split(",")) for call in queries] == [
        20,
        1,
    ]
    assert len(fills) == 21


@pytest.mark.parametrize("same_order", [True, False])
def test_markouts_and_existing_sqlite_primary_key_keep_fills_separate(
    venue, tmp_path, same_order
):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1", "T2"])
    executions.update({"T1": execution("O1"), "T2": execution("O1")})
    service._get_fills(["O1"], order)
    if not same_order:
        fills.clear()
        service._reported_fills.clear()
        orders["O1"] = order_status(["T1"], volume="0.5")
        orders["O2"] = order_status(["T2"], volume="0.5")
        executions["T2"]["ordertxid"] = "O2"
        service._get_fills(["O1", "O2"], order)
    db = str(tmp_path / "existing.sqlite")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE decorated_order_fill "
            "(trade_id PRIMARY KEY, fill_qty)"
        )
        connection.execute("INSERT INTO decorated_order_fill VALUES (0, 3)")

    async def measure():
        post_trade = PostTradeService()
        records = []

        def receive(_, decorated_order_fill):
            records.append(copy.copy(decorated_order_fill))

        post_trade.decorated_order_fill_event.connect(receive)
        recorder = SignalRecorder(db)
        recorder.start_recording()
        try:
            bbo = BBO(
                symbol="BTC/USD",
                bid_price=99,
                ask_price=101,
                bid_quantity=1,
                ask_quantity=1,
            )
            post_trade.on_bbo("test", bbo)
            loop = asyncio.get_running_loop()
            with patch.object(loop, "call_later") as schedule:
                for fill in fills:
                    post_trade.on_fill("test", fill)
            assert len(post_trade._pending_fills) == 2
            callbacks = schedule.call_args_list
            assert len(callbacks) == 8
            # Execute each fill's callbacks at different prices. No sleeps.
            for index, call in enumerate(callbacks):
                price = 110 + index
                post_trade.on_bbo(
                    "test",
                    replace(bbo, bid_price=price - 1, ask_price=price + 1),
                )
                _, callback, key, field = call.args
                callback(key, field)
            assert not post_trade._pending_fills
            latest = {record.fill_id: record for record in records}
            assert latest[fills[0].fill_id].fair_price_30s == 113
            assert latest[fills[1].fill_id].fair_price_30s == 117
            assert latest[fills[0].fill_id].fair_price_100ms == 110
            assert latest[fills[1].fill_id].fair_price_100ms == 114
        finally:
            recorder.close()
            post_trade.decorated_order_fill_event.disconnect(receive)

    asyncio.run(measure())
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT trade_id, fill_id, exchange, exchange_order_id, "
            "exchange_trade_id, client_order_id, fair_price_30s "
            "FROM decorated_order_fill WHERE trade_id != 0 "
            "ORDER BY exchange_trade_id"
        ).fetchall()
        assert len(rows) == 2
        for index, row in enumerate(rows):
            fill = fills[index]
            assert row == (
                fill.fill_id,
                fill.fill_id,
                "Kraken",
                fill.exchange_order_id,
                f"T{index + 1}",
                "123",
                113 + 4 * index,
            )
        assert connection.execute(
            "SELECT fill_qty FROM decorated_order_fill WHERE trade_id=0"
        ).fetchone() == (3,)


def test_identity_encoding_has_no_separator_collisions():
    assert fill_identity("A:B", "C", "D") != fill_identity("A", "B:C", "D")
    with pytest.raises(ValueError):
        fill_identity("Kraken", "", "T1")


@pytest.mark.parametrize(
    "http_status,errors", [(503, []), (200, ["EGeneral:Temporary lockout"])]
)
def test_trade_query_failure_does_not_suppress_fills_on_retry(
    venue, http_status, errors
):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1", "T2"])
    executions.update({"T1": execution("O1"), "T2": execution("O1")})
    request = service._client.send_request.side_effect

    def fail_details(endpoint, payload):
        if endpoint.endswith("QueryTrades"):
            return MagicMock(
                status_code=http_status, json=lambda: {"error": errors}
            )
        return request(endpoint, payload)

    service._client.send_request.side_effect = fail_details
    with pytest.raises(RuntimeError, match="error on fetching trades"):
        service._get_fills(["O1"], order)
    assert not fills
    service._client.send_request.side_effect = request
    service._get_fills(["O1"], order)
    assert len(fills) == 2


def test_closed_order_fill_is_reported_while_another_order_is_open(venue):
    service, order, orders, executions, fills = venue
    orders["O1"] = order_status(["T1"], volume="0.5")
    orders["O2"] = order_status([], volume="0", status="open")
    executions["T1"] = execution("O1")
    with pytest.raises(RuntimeError, match="still open"):
        service._get_fills(["O1", "O2"], order)
    assert [fill.exchange_trade_id for fill in fills] == ["T1"]
    orders["O2"]["status"] = "canceled"
    service._get_fills(["O1", "O2"], order)
    assert len(fills) == 1
