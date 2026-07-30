"""Planificador SJF (Shortest Job First) apropiativo."""

from __future__ import annotations

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class SJFQueueScheduler(BaseQueueScheduler):
   

    def _sjf_key(self, process: Process) -> tuple:
        ready_time = process.ready_since if process.ready_since is not None else process.arrival_time
        return (process.remaining_total_cpu(), ready_time, process.name)

    def add(self, process: Process) -> None:
        if self._contains(process):
            return
        self.ready.append(process)

    def add_front(self, process: Process) -> None:
        if self._contains(process):
            return
        self.ready.appendleft(process)

    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        best_process = min(self.ready, key=self._sjf_key)
        self.remove(best_process)
        return best_process

    def snapshot(self) -> list[Process]:
        return list(self.ready)
