import tempfile
import unittest

from jolteon.app.base import ApplicationBase
from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    FairPriceContext,
    IFairPriceModel,
)


class SubscribingFairPriceModel(IFairPriceModel, SignalSubscriber):
    """A minimal stand-in for AdjustedFairPriceModel: an IFairPriceModel
    that is also a SignalSubscriber, to check connect_all() discovers
    it."""

    def __init__(self):
        super().__init__()
        self.ticks_seen = 0

    def _calculate(self, context: FairPriceContext) -> FairPrice:
        return FairPrice(bid=0.0, ask=0.0)

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.ticks_seen += 1


class TestApplicationBaseFairPriceModel(unittest.TestCase):
    def _make_app(self, fair_price_model):
        return ApplicationBase(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_base.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_base.log",
            fair_price_model=fair_price_model,
        )

    def test_connect_all_wires_a_subscribing_fair_price_model(self):
        model = SubscribingFairPriceModel()
        app = self._make_app(model)

        app.connect_all()
        signal("ticker_feed").send(
            "mock_sender",
            bbo=BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=1.0,
                ask_price=102.0,
                ask_quantity=1.0,
            ),
        )

        self.assertEqual(1, model.ticks_seen)
        app.disconnect_all()

    def test_connect_all_tolerates_a_non_subscribing_fair_price_model(self):
        app = self._make_app(fair_price_model=None)

        app.connect_all()
        app.disconnect_all()


if __name__ == "__main__":
    unittest.main()
