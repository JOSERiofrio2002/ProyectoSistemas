"""Priority scheduler for queue 1."""

from __future__ import annotations

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class PriorityQueueScheduler(BaseQueueScheduler):
    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        selected = min(
            self.ready,
            key=lambda process: (
                process.priority if process.priority is not None else 10_000,
                process.arrival_time,
                process.name,
            ),
        )
        self.remove(selected)
        return selected

    def snapshot(self) -> list[Process]:
        return sorted(
            self.ready,
            key=lambda process: (
                process.priority if process.priority is not None else 10_000,
                process.arrival_time,
                process.name,
            ),
        )
