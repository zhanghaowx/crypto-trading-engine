"""CLI interface for crypto_trading_engine project.

Be creative! do whatever you want!

- Install click or typer and create a CLI app
- Use builtin argparse
- Start a web application
- Import things from your .base module
"""
import asyncio

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.health_monitor.heartbeat_monitor import HeartbeatMonitor


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
    heartbeater = Heartbeater(1)
    monitor = HeartbeatMonitor()
    heartbeater.heartbeat_signal().connect(monitor.on_heartbeat)
    while True:
        await asyncio.sleep(1)  # Keep the main thread alive
