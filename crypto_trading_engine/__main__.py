"""Entry point for crypto_trading_engine."""

import asyncio

from crypto_trading_engine.cli import main

if __name__ == "__main__":
    asyncio.run(main())
