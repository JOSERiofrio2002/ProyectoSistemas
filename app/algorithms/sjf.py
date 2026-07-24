"""Non-preemptive SJF scheduler."""

from __future__ import annotations

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class SJFQueueScheduler(BaseQueueScheduler):
    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        selected = min(
            self.ready,
            key=lambda process: (process.current_cpu_remaining(), process.arrival_time, process.name),
        )
        self.remove(selected)
        return selected

    def snapshot(self) -> list[Process]:
        return sorted(
            self.ready,
            key=lambda process: (process.current_cpu_remaining(), process.arrival_time, process.name),
        )
