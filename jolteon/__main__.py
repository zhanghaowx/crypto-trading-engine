"""Entry point for jolteon."""

import asyncio

from jolteon.engine.runner import main


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
