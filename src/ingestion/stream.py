from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np


@dataclass
class Frame:
    data: np.ndarray
    camera_id: str
    timestamp: float
    frame_number: int


class StreamReader(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def read_frames(self) -> AsyncIterator[Frame]: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...
