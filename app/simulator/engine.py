"""Discrete-event simulation engine for the multilevel queue scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.algorithms.fcfs import FCFSScheduler
from app.algorithms.priorities import PriorityQueueScheduler
from app.algorithms.rr import RoundRobinQueueScheduler
from app.algorithms.sjf import SJFQueueScheduler
from app.models.enums import BurstType, ProcessState
from app.models.process import Process
from app.utils.constants import PROCESS_COLORS


@dataclass
class BlockedItem:
    process: Process
    unblock_time: int


@dataclass
class ExecutionSegment:
    process_name: str
    start: int
    end: int
    queue_index: int = 0
    priority: Optional[int] = None

    @property
    def duration(self) -> int:
        return self.end - self.start


class MultilevelQueueEngine:
    """Coordinates arrivals, dispatching, IO blocks and statistics."""

    def __init__(self, default_quantum: int = 3) -> None:
        self.default_quantum = default_quantum
        self.processes: List[Process] = []
        self.time: int = 0
        self.finished: bool = False
        self.current_process: Process | None = None
        self.current_queue: int | None = None
        self.blocked: list[BlockedItem] = []
        self.execution_segments: list[ExecutionSegment] = []
        self.io_segments: list[ExecutionSegment] = []
        self.recent_transitions: list[str] = []
        self.log_lines: list[str] = []
        self.context_switches: int = 0
        self.cpu_busy_time: int = 0
        self.total_idle_time: int = 0
        self.schedulers = {
            0: SJFQueueScheduler(),
            1: PriorityQueueScheduler(),
            2: RoundRobinQueueScheduler(default_quantum),
            3: FCFSScheduler(),
        }
        self.queue_execution_history: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
        self.io_execution_history: list[str] = []
        self.force_new_segment: bool = True

    def set_processes(self, processes: list[Process]) -> None:
        self.processes = processes
        self.reset()

    def reset(self) -> None:
        self.time = 0
        self.finished = False
        self.current_process = None
        self.current_queue = None
        self.blocked = []
        self.execution_segments = []
        self.io_segments = []
        self.recent_transitions = []
        self.log_lines = []
        self.context_switches = 0
        self.cpu_busy_time = 0
        self.total_idle_time = 0
        self.schedulers = {
            0: SJFQueueScheduler(),
            1: PriorityQueueScheduler(),
            2: RoundRobinQueueScheduler(self.default_quantum),
            3: FCFSScheduler(),
        }
        self.queue_execution_history = {0: [], 1: [], 2: [], 3: []}
        self.io_execution_history = []
        self.force_new_segment = True
        for process in self.processes:
            process.reset_runtime()

    def set_default_quantum(self, quantum: int) -> None:
        self.default_quantum = quantum
        self.schedulers[2].default_quantum = quantum

    def queue_snapshot(self, queue_index: int) -> list[Process]:
        return self.schedulers[queue_index].snapshot()

    def blocked_snapshot(self) -> list[tuple[Process, int]]:
        return [(item.process, max(0, item.unblock_time - self.time)) for item in self.blocked]

    def io_snapshot(self) -> list[tuple[Process, int]]:
        """Expose the E/S queue to the UI."""
        return self.blocked_snapshot()

    def queue_history(self, queue_index: int) -> list[str]:
        """Return the sequence of processes executed from one queue."""
        return self.queue_execution_history[queue_index][:]

    def io_history(self) -> list[str]:
        """Return the sequence of processes executed in E/S."""
        return self.io_execution_history[:]

    def _log(self, message: str) -> None:
        self.log_lines.append(f"Tiempo {self.time}: {message}")

    def _highest_ready_queue(self) -> int | None:
        for index in range(4):
            if self.schedulers[index].has_ready():
                return index
        return None

    def _queue_algorithm_name(self, queue_index: int) -> str:
        names = {0: "SJF (Sistema)", 1: "Prioridades (Multimedia)", 2: "Round Robin (Interactivos)", 3: "FCFS (Lotes)"}
        return names.get(queue_index, f"Cola {queue_index}")

    def _enqueue_process(self, process: Process) -> None:
        queue_index = process.queue_index
        process.state = ProcessState.READY
        process.ready_since = self.time
        if process.current_burst is not None and process.current_burst.kind == BurstType.CPU and process.remaining_in_burst == 0:
            process.remaining_in_burst = process.current_burst.duration
        self.schedulers[queue_index].add(process)
        self._log(f"{process.name} entra a cola {self._queue_algorithm_name(queue_index)}")

    def _dispatch_next(self) -> tuple[Process | None, int | None]:
        queue_index = self._highest_ready_queue()
        if queue_index is None:
            return None, None
        process = self.schedulers[queue_index].pop_next()
        if process is None:
            return None, None
        self._log(f"{process.name} sale de cola {self._queue_algorithm_name(queue_index)}")
        self.queue_execution_history[queue_index].append(process.name)
        process.state = ProcessState.RUNNING
        if process.first_response_time is None:
            process.first_response_time = self.time - process.arrival_time
        if process.start_time is None:
            process.start_time = self.time
        if queue_index == 2 and process.remaining_quantum <= 0:
            process.remaining_quantum = process.quantum or self.default_quantum
        self.force_new_segment = True
        return process, queue_index

    def _preempt_current(self) -> None:
        if self.current_process is None or self.current_queue is None:
            return
        self.schedulers[self.current_queue].add_front(self.current_process)
        self.current_process.state = ProcessState.READY
        self.current_process.ready_since = self.time
        self._log(f"{self.current_process.name} es desplazado por una cola de mayor prioridad ({self._queue_algorithm_name(self.current_queue)})")
        self.current_process = None
        self.current_queue = None
        self.force_new_segment = True

    def _handle_arrivals(self) -> None:
        for process in self.processes:
            if process.state == ProcessState.NEW and process.arrival_time == self.time:
                self._log(f"Llega {process.name} al sistema")
                self._enqueue_process(process)

    def _handle_unblocks(self) -> None:
        remaining: list[BlockedItem] = []
        for item in self.blocked:
            if item.unblock_time <= self.time:
                process = item.process
                process.blocked_until = None
                process.advance_to_next_burst()
                process.state = ProcessState.READY
                process.ready_since = self.time
                process.remaining_in_burst = process.current_burst.duration if process.current_burst else 0
                algo_name = self._queue_algorithm_name(process.queue_index)
                self.schedulers[process.queue_index].add(process)
                self.recent_transitions.append(f"{process.name} finaliza E/S -> abandona cola E/S -> vuelve a cola {algo_name}")
                self._log(f"{process.name} finaliza Entrada/Salida")
                self._log(f"{process.name} abandona la cola E/S")
                self._log(f"{process.name} vuelve a la cola {algo_name}")
            else:
                remaining.append(item)
                remaining_time = item.unblock_time - self.time
                self._log(f"{item.process.name} continúa en Entrada/Salida (Restan {remaining_time} u.t.)")
        self.blocked = remaining

    def _update_waiting_times(self) -> None:
        for process in self.processes:
            if process.state == ProcessState.READY:
                process.total_wait_time += 1
            elif process.state == ProcessState.BLOCKED:
                process.total_blocked_time += 1

    def _record_execution(self, process: Process, start: int) -> None:
        q_idx = process.queue_index
        prio = process.priority
        if self.force_new_segment:
            self.execution_segments.append(ExecutionSegment(process.name, start, start + 1, q_idx, prio))
            self.force_new_segment = False
        elif (self.execution_segments and
              self.execution_segments[-1].process_name == process.name and
              self.execution_segments[-1].end == start and
              self.execution_segments[-1].queue_index == q_idx):
            self.execution_segments[-1].end += 1
        else:
            self.execution_segments.append(ExecutionSegment(process.name, start, start + 1, q_idx, prio))

    def _io_sort_key(self, item: "BlockedItem") -> tuple:
        """Sort key that mirrors the CPU scheduling policy for I/O queue ordering."""
        p = item.process
        q = p.queue_index
        if q == 0:   # SJF: shortest remaining CPU burst first
            secondary = p.remaining_in_burst
        elif q == 1: # Prioridades: lower priority number = higher priority
            secondary = (p.priority if p.priority is not None else 999)
        else:        # RR (q=2) and FCFS (q=3): arrival order
            secondary = (p.arrival_time, p.ready_since or 0)
        return (q, secondary)

    def _record_io_execution(self, start: int) -> None:
        # El registro de E/S se realiza al entrar a la ráfaga de E/S en _send_to_io
        pass

    def _finalize_process(self, process: Process) -> None:
        process.state = ProcessState.FINISHED
        process.completion_time = self.time
        process.remaining_in_burst = 0
        process.remaining_quantum = 0
        self._log(f"{process.name} finaliza todo su recorrido en el sistema")

    def _send_to_io(self, process: Process) -> None:
        io_burst = process.current_burst
        if io_burst is None:
            self._finalize_process(process)
            return
        process.state = ProcessState.BLOCKED
        process.blocked_until = self.time + io_burst.duration
        self.blocked.append(BlockedItem(process, process.blocked_until))
        self.io_execution_history.append(process.name)
        self.io_segments.append(ExecutionSegment(process.name, self.time, self.time + io_burst.duration))
        self._log(f"{process.name} sale de CPU -> entra a la cola de Entrada/Salida por {io_burst.duration} u.t.")

    def _finish_current_burst(self, process: Process) -> None:
        process.advance_to_next_burst()
        if process.current_burst is None:
            self._finalize_process(process)
            return
        if process.current_burst.kind == BurstType.IO:
            self._send_to_io(process)
        else:
            process.state = ProcessState.READY
            process.ready_since = self.time
            process.remaining_in_burst = process.current_burst.duration
            algo_name = self._queue_algorithm_name(process.queue_index)
            self.schedulers[process.queue_index].add(process)
            self._log(f"{process.name} vuelve a cola {algo_name} para ejecutar CPU")

    def step(self) -> list[str]:
        if self.finished:
            return [f"Tiempo {self.time}: simulación finalizada"]

        self.recent_transitions.clear()
        self._handle_arrivals()
        self._handle_unblocks()
        self._record_io_execution(self.time)

        if self.current_process is not None:
            highest_ready = self._highest_ready_queue()
            if highest_ready is not None and highest_ready < (self.current_queue or 0):
                self._preempt_current()

        if self.current_process is None:
            self.current_process, self.current_queue = self._dispatch_next()
            if self.current_process is not None and self.current_queue is not None:
                self.context_switches += 1
                self.current_process.context_switches += 1
                self._log(f"{self.current_process.name} ocupa CPU desde cola {self._queue_algorithm_name(self.current_queue)}")

        if self.current_process is None:
            self._log("CPU queda libre (sin procesos listos)")
            self.total_idle_time += 1
            self._update_waiting_times()
            self.time += 1
            self.finished = all(process.is_finished for process in self.processes)
            return list(self.log_lines[-4:])

        process = self.current_process
        queue_index = self.current_queue or process.queue_index

        if process.remaining_in_burst <= 0 and process.current_burst is not None:
            process.remaining_in_burst = process.current_burst.duration

        process.remaining_in_burst -= 1
        process.executed_cpu_time += 1
        self.cpu_busy_time += 1
        self._record_execution(process, self.time)
        self._update_waiting_times()
        self._log(f"{process.name} ejecuta 1 u.t. en CPU (Restan {process.remaining_in_burst} u.t. de ráfaga)")
        if queue_index == 2:
            process.remaining_quantum -= 1

        self.time += 1

        if process.remaining_in_burst <= 0:
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True
            self._finish_current_burst(process)
        elif queue_index == 2 and process.remaining_quantum <= 0:
            process.state = ProcessState.READY
            process.ready_since = self.time
            process.remaining_quantum = process.quantum or self.default_quantum
            self.schedulers[2].add(process)
            self._log(f"{process.name} agota Quantum y vuelve al final de Cola Round Robin (RR)")
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True

        self.finished = all(process.is_finished for process in self.processes)
        if self.finished:
            self._log("La simulación ha finalizado completamente")
        return list(self.log_lines[-5:])

    def run_until_end(self, max_steps: int = 10_000) -> list[str]:
        output: list[str] = []
        for _ in range(max_steps):
            if self.finished:
                break
            output.extend(self.step())
        return output

    def _process_metrics(self, process: Process) -> dict[str, int]:
        completion = 0 if process.completion_time is None else process.completion_time
        execution_time = completion - process.arrival_time if process.completion_time is not None else 0
        waiting_time = execution_time - process.cpu_total() - process.io_total()
        if waiting_time < 0:
            waiting_time = 0
        response = 0 if process.first_response_time is None else process.first_response_time
        return {
            "llegada": process.arrival_time,
            "finalizacion": completion,
            "cpu_total": process.cpu_total(),
            "io_total": process.io_total(),
            "ejecucion": execution_time,
            "espera": waiting_time,
            "retorno": execution_time,
            "respuesta": response,
            "bloqueado": process.total_blocked_time,
            "total": execution_time,
        }

    def statistics(self) -> dict:
        completed = [process for process in self.processes if process.is_finished]
        count = max(1, len(completed))
        metrics = {process.name: self._process_metrics(process) for process in self.processes}
        total_wait = sum(item["espera"] for item in metrics.values())
        total_execution = sum(item["ejecucion"] for item in metrics.values())
        total_return = sum(item["retorno"] for item in metrics.values())
        average_wait = total_wait / count if completed else 0
        average_execution = total_execution / count if completed else 0
        average_return = total_return / count if completed else 0
        cpu_utilization = (self.cpu_busy_time / max(1, self.time)) * 100
        throughput = len(completed) / max(1, self.time)
        return {
            "per_process": metrics,
            "average_wait": average_wait,
            "average_execution": average_execution,
            "average_return": average_return,
            "cpu_utilization": cpu_utilization,
            "throughput": throughput,
            "context_switches": self.context_switches,
            "total_time": self.time,
        }

    def process_color(self, name: str) -> str:
        import re
        match = re.search(r"P(\d+)", name, re.IGNORECASE)
        if match:
            num = int(match.group(1)) - 1
            if 0 <= num < len(PROCESS_COLORS):
                return PROCESS_COLORS[num]
            return PROCESS_COLORS[num % len(PROCESS_COLORS)]
        for idx, process in enumerate(self.processes):
            if process.name == name:
                return PROCESS_COLORS[idx % len(PROCESS_COLORS)]
        index = abs(hash(name)) % len(PROCESS_COLORS)
        return PROCESS_COLORS[index]

