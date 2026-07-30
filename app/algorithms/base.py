"""Contrato base del planificador para el simulador de colas múltiples."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Deque

from app.models.process import Process


class BaseQueueScheduler(ABC):
   

    def __init__(self) -> None:
        self.ready: Deque[Process] = deque()


    def _contains(self, process: Process) -> bool:
        return any(p is process for p in self.ready)

    def add(self, process: Process) -> None:
      
        if self._contains(process):
            return
        self.ready.append(process)

    def add_front(self, process: Process) -> None:
        if self._contains(process):
            return
        self.ready.appendleft(process)

    def remove(self, process: Process) -> None:
     
        self.ready = deque(p for p in self.ready if p is not process)

    def has_ready(self) -> bool:
        return bool(self.ready)

    @abstractmethod
    def pop_next(self) -> Process | None:
        """Retorna el siguiente proceso según la regla de planificación."""

    def snapshot(self) -> list[Process]:
        return list(self.ready)
