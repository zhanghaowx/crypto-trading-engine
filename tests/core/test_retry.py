import unittest
from unittest.mock import AsyncMock, patch

from jolteon.core.retry import Retry


class TestRetryClass(unittest.IsolatedAsyncioTestCase):
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_execution(self, mock_sleep):
        async def successful_coroutine():
            return "Success!"

        async with Retry(max_retries=2, delay_seconds=1) as retry_instance:
            result = await retry_instance.execute(successful_coroutine)

        self.assertEqual(result, "Success!")
        self.assertEqual(
            mock_sleep.call_count, 0
        )  # No retries, so sleep should not be called

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_execution_with_regular_func(self, mock_sleep):
        def successful_function():
            return "Success!"

        async with Retry(max_retries=2, delay_seconds=1) as retry_instance:
            result = await retry_instance.execute(successful_function)

        self.assertEqual(result, "Success!")
        self.assertEqual(
            mock_sleep.call_count, 0
        )  # No retries, so sleep should not be called

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_failure_with_retries(self, mock_sleep):
        async def failing_coroutine():
            raise ValueError("Simulated failure")

        async with Retry(
            max_retries=2, delay_seconds=1, retry_exceptions=(ValueError,)
        ) as retry_instance:
            with self.assertRaises(RuntimeError) as context:
                await retry_instance.execute(failing_coroutine)

        self.assertIn(
            "failing_coroutine failed after 3 attempts",
            str(context.exception),
        )
        self.assertEqual(
            mock_sleep.call_count, 2
        )  # Two retries, so sleep should be called twice

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_failure_without_retries(self, mock_sleep):
        async def failing_coroutine():
            raise ValueError("Simulated failure")

        async with Retry(
            max_retries=0, delay_seconds=1, retry_exceptions=(ValueError,)
        ) as retry_instance:
            with self.assertRaises(RuntimeError) as context:
                await retry_instance.execute(failing_coroutine)

        self.assertIn(
            "failing_coroutine failed after 1 attempts", str(context.exception)
        )
        self.assertEqual(mock_sleep.call_count, 0)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_multiple_exceptions(self, mock_sleep):
        async def failing_coroutine():
            raise ValueError("Simulated failure")

        async with Retry(
            max_retries=2, delay_seconds=1, retry_exceptions=(TypeError,)
        ) as retry_instance:
            with self.assertRaises(ValueError) as context:
                await retry_instance.execute(failing_coroutine)

        self.assertIn("Simulated failure", str(context.exception))
        self.assertEqual(mock_sleep.call_count, 0)
        # No retries for the specified exception, so sleep should not be called
