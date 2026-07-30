"""Planificador Round Robin para la cola 2."""

from __future__ import annotations

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class RoundRobinQueueScheduler(BaseQueueScheduler):
    

    def __init__(self, default_quantum: int) -> None:
        super().__init__()
        self.default_quantum = default_quantum

    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        return self.ready.popleft()
