import asyncio
from dataclasses import dataclass

from app.core.errors import DeadlineExceededError


@dataclass(frozen=True)
class Deadline:
    expires_at: float

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        return cls(asyncio.get_running_loop().time() + seconds)

    def remaining(self) -> float:
        return max(0.0, self.expires_at - asyncio.get_running_loop().time())

    def require(self, minimum: float = 0.05) -> float:
        remaining = self.remaining()
        if remaining < minimum:
            raise DeadlineExceededError()
        return remaining

    async def run(self, awaitable):
        try:
            return await asyncio.wait_for(awaitable, timeout=self.require(0.001))
        except TimeoutError as exc:
            raise DeadlineExceededError() from exc
