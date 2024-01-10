"""CLI interface for crypto_trading_engine project.

Be creative! do whatever you want!

- Install click or typer and create a CLI app
- Use builtin argparse
- Start a web application
- Import things from your .base module
"""
import logging

from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    CoinbasePublicFeed,
)


async def main():  # pragma: no cover
    """
    The main function executes on commands:
    `python -m crypto_trading_engine` and `$ crypto_trading_engine `.

    This is your program's entry point.

    You can change this function to do whatever you want.
    Examples:
        * Run a test suite
        * Run a server
        * Do some other stuff
        * Run a command line application (Click, Typer, ArgParse)
        * List all available tasks
        * Run an application (Flask, FastAPI, Django, etc.)
    """
    logging.basicConfig(
        filename="crypto.log",
        filemode="w",
        format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
        level=logging.INFO,
    )
    md = CoinbasePublicFeed(CoinbaseEnvironment.PRODUCTION)
    await md.connect(["ETH-USD"])
