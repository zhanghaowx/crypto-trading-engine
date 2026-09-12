import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Callable

from jolteon.engine.core.parameter.parameter_service import parameter_service
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class RetryParameters(ParameterGroup):
    max_retries: int = parameter(
        3,
        minimum=0,
        maximum=100,
        step=1,
        unit="attempts",
        description="How many times to retry before giving up.",
    )
    delay_seconds: float = parameter(
        1.0,
        minimum=0.0,
        maximum=300.0,
        step=0.5,
        number_format="%.1f",
        unit="s",
        description=(
            "How long to wait between attempts. The delay is flat, not "
            "backed off, so a long one holds up whatever is retrying."
        ),
    )


class Retry:
    def __init__(
        self,
        max_retries=None,
        delay_seconds=None,
        retry_exceptions=(Exception,),
    ):
        params = parameter_service().get(RetryParameters)
        self.max_retries = (
            params.max_retries if max_retries is None else max_retries
        )
        self.delay_seconds = (
            params.delay_seconds if delay_seconds is None else delay_seconds
        )
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
                logging.warning(
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
