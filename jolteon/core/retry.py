import asyncio
import inspect
import logging
from typing import Callable


class Retry:
    def __init__(
        self, max_retries=3, delay_seconds=1, retry_exceptions=(Exception,)
    ):
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds
        self.retry_exceptions = retry_exceptions
        self.retries = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    async def execute(self, user_function: Callable, *args, **kwargs):
        is_coroutine = inspect.iscoroutinefunction(user_function)
        while self.retries <= self.max_retries:
            try:
                if is_coroutine:
                    return await user_function(*args, **kwargs)
                else:
                    return user_function(*args, **kwargs)
            except self.retry_exceptions as e:
                logging.info(
                    f"Attempt {user_function.__name__} "
                    f"{self.retries + 1}/{self.max_retries + 1} "
                    f"failed: {e}"
                )
                if self.retries < self.max_retries:
                    logging.info(
                        f"Retrying {user_function.__name__} "
                        f"in {self.delay_seconds} seconds..."
                    )
                    await asyncio.sleep(self.delay_seconds)
                self.retries += 1
        raise RuntimeError(
            f"{user_function.__name__} failed "
            f"after {self.max_retries + 1} attempts"
        )
