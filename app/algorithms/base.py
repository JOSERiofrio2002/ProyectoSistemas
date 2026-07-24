"""Base scheduler contract for the multilevel queue simulator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Deque

from app.models.process import Process


class BaseQueueScheduler(ABC):
    """Abstract ready-queue scheduler."""

    def __init__(self) -> None:
        self.ready: Deque[Process] = deque()

    def add(self, process: Process) -> None:
        self.ready.append(process)

    def add_front(self, process: Process) -> None:
        self.ready.appendleft(process)

    def remove(self, process: Process) -> None:
        self.ready = deque(item for item in self.ready if item is not process)

    def has_ready(self) -> bool:
        return bool(self.ready)

    @abstractmethod
    def pop_next(self) -> Process | None:
        """Return the next process according to the scheduling rule."""

    def snapshot(self) -> list[Process]:
        return list(self.ready)
