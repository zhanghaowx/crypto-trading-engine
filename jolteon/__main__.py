"""Entry point for jolteon."""

import asyncio

from jolteon.cli import main


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
