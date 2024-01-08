"""Entry point for crypto_trading_engine."""

import asyncio

from crypto_trading_engine.cli import main  # pragma: no cover

if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
