"""Modelo de proceso y helpers de ráfagas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.enums import BurstType, ProcessState, ProcessType


@dataclass(slots=True)
class Burst:
    """Representa una ráfaga de CPU o E/S."""

    kind: BurstType
    duration: int


@dataclass
class Process:
    """Modelo de proceso en tiempo de ejecución usado por el simulador y la UI."""

    name: str
    arrival_time: int
    bursts: List[Burst]
    process_type: ProcessType
    priority: Optional[int] = None
    quantum: Optional[int] = None
    state: ProcessState = ProcessState.NEW
    current_burst_index: int = 0
    remaining_in_burst: int = 0
    remaining_quantum: int = 0
    ready_since: Optional[int] = None
    first_response_time: Optional[int] = None
    start_time: Optional[int] = None
    completion_time: Optional[int] = None
    total_wait_time: int = 0
    total_blocked_time: int = 0
    executed_cpu_time: int = 0
    context_switches: int = 0
    blocked_until: Optional[int] = None
    gantt_segments: List[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reset_runtime()

    def reset_runtime(self) -> None:
        """Restaura el proceso a su estado inicial antes de una simulación."""

        self.state = ProcessState.NEW
        self.current_burst_index = 0
        self.remaining_in_burst = self.bursts[0].duration if self.bursts else 0
        self.remaining_quantum = 0
        self.ready_since = None
        self.first_response_time = None
        self.start_time = None
        self.completion_time = None
        self.total_wait_time = 0
        self.total_blocked_time = 0
        self.executed_cpu_time = 0
        self.context_switches = 0
        self.blocked_until = None
        self.gantt_segments = []

    @property
    def queue_index(self) -> int:
        mapping = {
            ProcessType.SYSTEM: 0,
            ProcessType.MULTIMEDIA: 1,
            ProcessType.INTERACTIVE: 2,
            ProcessType.BATCH: 3,
        }
        return mapping[self.process_type]

    @property
    def current_burst(self) -> Burst | None:
        if 0 <= self.current_burst_index < len(self.bursts):
            return self.bursts[self.current_burst_index]
        return None

    @property
    def is_finished(self) -> bool:
        return self.state == ProcessState.FINISHED

    def has_more_bursts(self) -> bool:
        return self.current_burst_index < len(self.bursts)

    def current_cpu_remaining(self) -> int:
        burst = self.current_burst
        if not burst or burst.kind != BurstType.CPU:
            return 0
        return self.remaining_in_burst

    def remaining_total_cpu(self) -> int:
        """Retorna la duración total restante de CPU en todas las ráfagas futuras de este proceso."""
        total = 0
        for i in range(self.current_burst_index, len(self.bursts)):
            b = self.bursts[i]
            if b.kind == BurstType.CPU:
                if i == self.current_burst_index:
                    total += max(0, self.remaining_in_burst)
                else:
                    total += b.duration
        return total

    def advance_to_next_burst(self) -> None:
        self.current_burst_index += 1
        if self.current_burst_index < len(self.bursts):
            self.remaining_in_burst = self.bursts[self.current_burst_index].duration
        else:
            self.remaining_in_burst = 0

    def cpu_total(self) -> int:
        return sum(b.duration for b in self.bursts if b.kind == BurstType.CPU)

    def io_total(self) -> int:
        return sum(b.duration for b in self.bursts if b.kind == BurstType.IO)

    def io_count(self) -> int:
        return sum(1 for b in self.bursts if b.kind == BurstType.IO)

    def io_operation_points(self) -> list[int]:
        """Retorna los instantes de CPU donde comienza cada operación de E/S."""

        points: list[int] = []
        cpu_elapsed = 0
        for burst in self.bursts:
            if burst.kind == BurstType.CPU:
                cpu_elapsed += burst.duration
            else:
                points.append(cpu_elapsed)
        return points

    def io_durations(self) -> list[int]:
        """Retorna todas las duraciones de las ráfagas de E/S."""

        return [burst.duration for burst in self.bursts if burst.kind == BurstType.IO]
