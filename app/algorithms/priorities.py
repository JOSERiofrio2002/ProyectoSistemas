"""Planificador por Prioridades para la cola 1."""

from __future__ import annotations

from collections import deque

from app.algorithms.base import BaseQueueScheduler
from app.models.process import Process


class PriorityQueueScheduler(BaseQueueScheduler):
  

    def _priority_key(self, process: Process) -> tuple:
        prio = process.priority if process.priority is not None else 10_000
        ready_time = process.ready_since if process.ready_since is not None else process.arrival_time
        return (prio, ready_time, process.name)

    def add(self, process: Process) -> None:
        if self._contains(process):
            return
        ready_list = list(self.ready)
        ready_list.append(process)
        ready_list.sort(key=self._priority_key)
        self.ready = deque(ready_list)

    def add_front(self, process: Process) -> None:
      
        self.add(process)

    def pop_next(self) -> Process | None:
        if not self.ready:
            return None
        return self.ready.popleft()

    def snapshot(self) -> list[Process]:
        return list(self.ready)
