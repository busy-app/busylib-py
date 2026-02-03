from unittest.mock import MagicMock

from examples.bc.runner import AsyncRunner


def test_async_runner_runs_coroutine():
    """
    Verify the async runner executes a coroutine and returns its result.

    The test uses a mock task to keep execution isolated.
    """
    runner = AsyncRunner()
    runner.start(MagicMock())

    async def sample() -> int:
        return 42

    result = runner.run(sample())
    assert result == 42

    runner.stop()
