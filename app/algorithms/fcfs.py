"""Planificador First-Come, First-Served (FCFS) para la cola 3."""

from __future__ import annotations

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class FCFSScheduler(BaseQueueScheduler):
    """Cola FIFO. Unicidad garantizada por BaseQueueScheduler."""

    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        return self.ready.popleft()
