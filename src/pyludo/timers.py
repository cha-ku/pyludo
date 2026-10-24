import asyncio
from collections.abc import Awaitable, Callable


class TurnTimer:
    def __init__(self, seconds: float, on_expiry: Callable[[], Awaitable[None]]) -> None:
        self.seconds = seconds
        self._on_expiry = on_expiry
        self._expiry_time: float | None = None
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        await asyncio.sleep(self.seconds)
        self._task = None
        self._expiry_time = None
        await self._on_expiry()

    def start(self) -> None:
        self._expiry_time = asyncio.get_running_loop().time() + self.seconds
        if self._task is not None:
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._task = None
        self._expiry_time = None

    @property
    def seconds_left(self) -> float | None:
        if self._expiry_time is None:
            return None
        return max(0.0, self._expiry_time - asyncio.get_running_loop().time())
