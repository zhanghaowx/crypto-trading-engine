from unittest.mock import Mock

from jolteon.engine.market_data.binance_us.rest_client import (
    BinanceUsPublicRestClient,
)


def test_gets_exchange_info_and_depth_with_bounded_requests():
    response = Mock()
    response.json.side_effect = [{"symbols": []}, {"lastUpdateId": 1}]
    session = Mock()
    session.get.return_value = response
    client = BinanceUsPublicRestClient(session)

    assert client.exchange_info("BTCUSD") == {"symbols": []}
    assert client.depth("BTCUSD", 1000) == {"lastUpdateId": 1}
    assert session.get.call_args_list[0].kwargs == {
        "params": {"symbol": "BTCUSD", "showPermissionSets": "false"},
        "timeout": 10,
    }
    assert session.get.call_args_list[1].kwargs == {
        "params": {"symbol": "BTCUSD", "limit": 1000},
        "timeout": 10,
    }
    assert response.raise_for_status.call_count == 2
