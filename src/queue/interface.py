from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class FrameQueue(ABC):
    @abstractmethod
    async def push(self, camera_id: str, data: bytes) -> None: ...

    @abstractmethod
    async def consume(self, camera_id: str) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def backlog_size(self, camera_id: str) -> int: ...

    @abstractmethod
    async def ack(self, camera_id: str, message_id: str) -> None: ...
