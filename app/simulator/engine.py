
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

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
    burst_index: int = 0
    info_value: int = 0

    @property
    def duration(self) -> int:
        return self.end - self.start


class MultilevelQueueEngine:
    """
    Motor principal de simulacion por eventos discretos.
    Coordina 4 colas (SJF, Prioridades, RR, FCFS) con jerarquia fija.
    Gestiona llegadas, desalojos, E/S, y genera estadisticas.
    """

    def __init__(self, default_quantum: int = 3) -> None:
        self.default_quantum = default_quantum
        self.processes: List[Process] = []
        self.time: int = 0
        self.finished: bool = False
        self.current_process: Process | None = None
        self.current_queue: int | None = None
        self.blocked: list[BlockedItem] = []
        self.execution_segments: list[ExecutionSegment] = []
        self.cpu_timeline_segments: list[ExecutionSegment] = []
        self.queue_entry_segments: list[ExecutionSegment] = []
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
        self.queue_arrival_history: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
        self.io_execution_history: list[str] = []
        self.force_new_segment: bool = True
        self.queue_ready_order: list[tuple[int, str, int]] = []

  
    def set_processes(self, processes: list[Process]) -> None:
        self.processes = processes
        self.reset()

    def reset(self) -> None:
        """Reinicia el motor: limpia estado, recrea colas y lanza llegada inicial."""
        self.time = 0
        self.finished = False
        self.current_process = None          # Proceso actualmente en CPU
        self.current_queue = None            # Indice de la cola del proceso en CPU
        self.blocked = []                    # Lista de procesos bloqueados (E/S)
        self.execution_segments = []         # Segmentos de ejecucion (Gantt algoritmos)
        self.cpu_timeline_segments = []      # Segmentos para la linea de CPU
        self.queue_entry_segments = []       # Segmentos de entrada a cola (Gantt)
        self.io_segments = []                # Segmentos de operaciones E/S
        self.recent_transitions = []         # Transiciones recientes (UI)
        self.log_lines = []                  # Historial de logs
        self.context_switches = 0            # Contador de cambios de contexto
        self.cpu_busy_time = 0               # Tiempo que la CPU estuvo ocupada
        self.total_idle_time = 0             # Tiempo que la CPU estuvo inactiva
        # 4 colas de planificacion con prioridad fija (0 = mas alta)
        self.schedulers = {
            0: SJFQueueScheduler(),          # Cola 0: SJF Apropiativo (Sistema)
            1: PriorityQueueScheduler(),     # Cola 1: Prioridades (Multimedia)
            2: RoundRobinQueueScheduler(self.default_quantum),  # Cola 2: RR (Interactivos)
            3: FCFSScheduler(),              # Cola 3: FCFS (Lotes)
        }
        self.queue_execution_history = {0: [], 1: [], 2: [], 3: []}  # Historial por cola
        self.queue_arrival_history = {0: [], 1: [], 2: [], 3: []}    # Llegadas por cola
        self.io_execution_history = []       # Historial de operaciones E/S
        self.force_new_segment = True        # Forzar nuevo segmento en Gantt
        self.queue_ready_order = []          # Orden de entrada a colas (para Gantt SJF)
        for process in self.processes:
            process.reset_runtime()          # Restaurar estado inicial de cada proceso
        self._handle_arrivals()              # Registrar llegadas en tiempo 0
        self._handle_unblocks()              # Verificar desbloqueos en tiempo 0
        if self.current_process is None:
            self._try_dispatch()             # Si CPU libre, despachar el primero

    def set_default_quantum(self, quantum: int) -> None:
        self.default_quantum = quantum
        self.schedulers[2].default_quantum = quantum

    def queue_snapshot(self, queue_index: int) -> list[Process]:
        return self.schedulers[queue_index].snapshot()

    def blocked_snapshot(self) -> list[tuple[Process, int]]:
        return [(item.process, max(0, item.unblock_time - self.time)) for item in self.blocked]

    def io_snapshot(self) -> list[tuple[Process, int]]:
        return self.blocked_snapshot()

    def queue_history(self, queue_index: int) -> list[str]:
        return self.queue_execution_history[queue_index][:]

    def io_history(self) -> list[str]:
        return self.io_execution_history[:]

  
    def _log(self, message: str) -> None:
        self.log_lines.append(f"Tiempo {self.time}: {message}")

    def _queue_algorithm_name(self, queue_index: int) -> str:
        names = {0: "SJF (Sistema)", 1: "Prioridades (Multimedia)", 2: "Round Robin (Interactivos)", 3: "FCFS (Lotes)"}
        return names.get(queue_index, f"Cola {queue_index}")

    def _highest_ready_queue(self) -> int | None:
        for index in range(4):
            if self.schedulers[index].has_ready():
                return index
        return None


    def _remove_from_all_ready_queues(self, process: Process) -> None:
       
        for sched in self.schedulers.values():
            sched.remove(process)

    def _remove_from_blocked(self, process: Process) -> None:
        self.blocked = [item for item in self.blocked if item.process is not process]

    def _is_in_any_ready_queue(self, process: Process) -> bool:
        return any(sched._contains(process) for sched in self.schedulers.values())

    def _is_in_blocked(self, process: Process) -> bool:
        return any(item.process is process for item in self.blocked)

 

    def _transition_to_ready(
        self,
        process: Process,
        *,
        at_front: bool = False,
        from_io: bool = False,
        from_quantum_expiry: bool = False,
        from_preemption: bool = False,
    ) -> None:
      
        queue_index = process.queue_index
        algo_name = self._queue_algorithm_name(queue_index)

        if self._is_in_any_ready_queue(process):
            return

     
        if self.current_process is process:
            self.current_process = None
            self.current_queue = None

   
        if from_io:
            self._remove_from_blocked(process)

     
        if queue_index == 2 and not at_front:
            process.remaining_quantum = process.quantum or self.default_quantum

        process.state = ProcessState.READY
        process.ready_since = self.time

        if (process.current_burst is not None
                and process.current_burst.kind == BurstType.CPU
                and process.remaining_in_burst <= 0):
            process.remaining_in_burst = process.current_burst.duration

  
        if at_front and queue_index != 1:
       
            self.schedulers[queue_index].add_front(process)
        else:
            self.schedulers[queue_index].add(process)

      
        burst = process.current_burst
        if queue_index == 2:
            info_val = process.current_cpu_remaining()
        else:
            info_val = burst.duration if (burst is not None and burst.kind == BurstType.CPU) else 0
        self.queue_entry_segments.append(ExecutionSegment(
            process.name, self.time, self.time + 1,
            queue_index=queue_index,
            priority=process.priority,
            burst_index=process.current_burst_index,
            info_value=info_val,
        ))

    
        if process.name not in self.queue_arrival_history[queue_index]:
            self.queue_arrival_history[queue_index].append(process.name)
        self.queue_ready_order.append((queue_index, process.name, process.current_burst_index))

   
        if from_io:
            self.recent_transitions.append(
                f"{process.name} finaliza E/S → abandona cola E/S → vuelve a cola {algo_name}"
            )
            self._log(f"{process.name} finaliza Entrada/Salida")
            self._log(f"{process.name} abandona la cola E/S")
            self._log(f"{process.name} vuelve a la cola {algo_name}")
        elif from_quantum_expiry:
            self._log(f"{process.name} agota Quantum → vuelve al FINAL de la cola Round Robin (RR)")
        elif at_front:
            if queue_index == 1:
                prio = process.priority if process.priority is not None else '?'
                self._log(f"{process.name} desalojado → reinserción ordenada en cola {algo_name} (prioridad {prio})")
            else:
                self._log(f"{process.name} desalojado → mantiene posición al frente en cola {algo_name}")
        elif from_preemption:
           
            prio = process.priority if process.priority is not None else '?'
            self._log(f"{process.name} desalojado → reinserción ordenada en cola {algo_name} (prioridad {prio})")
        else:
            self._log(f"{process.name} llega al sistema → entra a cola {algo_name}")

    def _transition_to_running(self, process: Process, queue_index: int) -> None:
      
        self._remove_from_all_ready_queues(process)
        self._remove_from_blocked(process)

        process.state = ProcessState.RUNNING
        if process.first_response_time is None:
            process.first_response_time = self.time - process.arrival_time
        if process.start_time is None:
            process.start_time = self.time

        self.current_process = process
        self.current_queue = queue_index

    

       
        if queue_index == 2 or not self.execution_segments or self.execution_segments[-1].process_name != process.name:
            self.force_new_segment = True

        self._log(f"{process.name} ocupa CPU desde cola {self._queue_algorithm_name(queue_index)}")

    def _transition_to_blocked(self, process: Process, io_duration: int) -> None:
      
        self._remove_from_all_ready_queues(process)

        if self.current_process is process:
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True

        process.state = ProcessState.BLOCKED
        process.blocked_until = self.time + io_duration

        if not self._is_in_blocked(process):
            self.blocked.append(BlockedItem(process, process.blocked_until))
            self.io_execution_history.append(process.name)
            self.io_segments.append(ExecutionSegment(
                process.name, self.time, self.time + io_duration
            ))

        self._log(f"{process.name} sale de CPU → entra a la cola de Entrada/Salida por {io_duration} u.t.")

    def _transition_to_finished(self, process: Process) -> None:
       
        self._remove_from_all_ready_queues(process)
        self._remove_from_blocked(process)

        if self.current_process is process:
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True

        process.state = ProcessState.FINISHED
        process.completion_time = self.time
        process.remaining_in_burst = 0
        process.remaining_quantum = 0
        self._log(f"{process.name} finaliza todo su recorrido en el sistema")


    def _handle_arrivals(self) -> None:
        for process in self.processes:
            if process.state == ProcessState.NEW and process.arrival_time <= self.time:
                self._transition_to_ready(process)

    def _handle_unblocks(self, log_continue: bool = True) -> None:
        still_blocked: list[BlockedItem] = []
        for item in self.blocked:
            if item.unblock_time <= self.time:
                process = item.process
                process.blocked_until = None
                process.advance_to_next_burst()
                if process.current_burst is None:
                
                    self._transition_to_finished(process)
                else:
                    self._transition_to_ready(process, from_io=True)
            else:
                still_blocked.append(item)
                if log_continue:
                    remaining_time = item.unblock_time - self.time
                    self._log(f"{item.process.name} continúa en Entrada/Salida (Restan {remaining_time} u.t.)")
        self.blocked = still_blocked

    def _should_preempt(self) -> tuple[bool, int | None]:
        if self.current_process is None or self.current_queue is None:
            return False, None
        highest_queue = self._highest_ready_queue()
        if highest_queue is None:
            return False, None

   
        if highest_queue < self.current_queue:
            return True, highest_queue

     
        if self.current_queue == 0 and highest_queue == 0 and self.schedulers[0].ready:
            best = min(self.schedulers[0].ready, key=lambda p: p.remaining_total_cpu())
            if best is not None:
                curr_remaining = self.current_process.remaining_total_cpu()
                best_remaining = best.remaining_total_cpu()
                if best_remaining < curr_remaining:
                    return True, 0

        if self.current_queue == 1 and highest_queue == 1:
            top = self.schedulers[1].ready[0] if self.schedulers[1].ready else None
            if top is not None:
                curr_prio = self.current_process.priority if self.current_process.priority is not None else 10_000
                top_prio = top.priority if top.priority is not None else 10_000
                if top_prio < curr_prio:
                    return True, 1
        return False, None

    def _preempt_current(self, higher_priority_queue: int | None = None) -> None:
        if self.current_process is None or self.current_queue is None:
            return
        preempted_process = self.current_process
        preempted_queue = self.current_queue
        cause_name = (
            self._queue_algorithm_name(higher_priority_queue)
            if higher_priority_queue is not None
            else "cola de mayor prioridad"
        )
        self._log(
            f"{preempted_process.name} es desplazado de {self._queue_algorithm_name(preempted_queue)}"
            f" por proceso de mayor prioridad en {cause_name}"
        )
    
        self.current_process = None
        self.current_queue = None
        if preempted_queue == 2:
            self.force_new_segment = True

        # RR (cola 2) y Prioridades (cola 1): van al FINAL de la cola
        # SJF (cola 0) y FCFS (cola 3): van al FRENTE
        self._transition_to_ready(
            preempted_process,
            at_front=(preempted_queue not in (1, 2)),
            from_preemption=True,
        )

  
    def _try_dispatch(self) -> None:
  
        if self.current_process is not None:
            return
        queue_index = self._highest_ready_queue()
        if queue_index is None:
            return
        process = self.schedulers[queue_index].pop_next()
        if process is None:
            return
        self.context_switches += 1
        process.context_switches += 1
        # Record execution order
        # RR (cola 2): registra cada despacho (alternancia P1,P2,P1,P2...)
        # FCFS/SJF/Prioridades (colas 0,1,3): cada proceso aparece UNA SOLA vez
        if queue_index == 2:
            self.queue_execution_history[queue_index].append(process.name)
        elif process.name not in self.queue_execution_history[queue_index]:
            self.queue_execution_history[queue_index].append(process.name)
        self._transition_to_running(process, queue_index)


    def _record_execution(self, process: Process, start: int) -> None:
        q_idx = process.queue_index
        prio = process.priority
        burst_idx = process.current_burst_index

     
        last_tl = self.cpu_timeline_segments[-1] if self.cpu_timeline_segments else None
        can_merge_tl = (
            last_tl is not None and
            last_tl.process_name == process.name and
            last_tl.end == start and
            last_tl.queue_index == q_idx and
            (q_idx != 2 or not self.force_new_segment)
        )
        if can_merge_tl:
            self.cpu_timeline_segments[-1].end += 1
        else:
            self.cpu_timeline_segments.append(ExecutionSegment(process.name, start, start + 1, q_idx, prio, burst_idx))

  
        if q_idx == 2:
        
            if (not self.force_new_segment
                    and self.execution_segments
                    and self.execution_segments[-1].process_name == process.name
                    and self.execution_segments[-1].end == start
                    and self.execution_segments[-1].queue_index == q_idx):
                self.execution_segments[-1].end += 1
            else:
                self.execution_segments.append(ExecutionSegment(process.name, start, start + 1, q_idx, prio, burst_idx))
                self.force_new_segment = False
        else:
           
            last_seg = self.execution_segments[-1] if self.execution_segments else None
            can_merge = (
                last_seg is not None and
                last_seg.process_name == process.name and
                last_seg.queue_index == q_idx and
                getattr(last_seg, 'burst_index', 0) == burst_idx and
                last_seg.end == start
            )
            if can_merge:
                last_seg.end += 1
            else:
                self.execution_segments.append(ExecutionSegment(process.name, start, start + 1, q_idx, prio, burst_idx))
            self.force_new_segment = False


    def _finish_current_burst(self, process: Process) -> None:
       
        queue_index = process.queue_index
        process.advance_to_next_burst()

        if process.current_burst is None:
            self._transition_to_finished(process)
            return

        if process.current_burst.kind == BurstType.IO:
            io_duration = process.current_burst.duration
            self._transition_to_blocked(process, io_duration)
        else:
          
            process.remaining_in_burst = process.current_burst.duration
            if queue_index == 2:
              
                self._transition_to_ready(process, from_quantum_expiry=False)
            
            else:
                
                process.state = ProcessState.RUNNING
                self.current_process = process
                self.current_queue = queue_index
                self._log(
                    f"{process.name} continúa siguiente ráfaga CPU en "
                    f"{self._queue_algorithm_name(queue_index)}"
                )

 
    def _update_waiting_times(self) -> None:
        for process in self.processes:
            if process.state == ProcessState.READY:
                process.total_wait_time += 1
            elif process.state == ProcessState.BLOCKED:
                process.total_blocked_time += 1

  
    def step(self) -> list[str]:
        """
        Ejecuta UN paso de simulacion (1 unidad de tiempo).
        
        Fases del paso:
        1. LLEGADAS: procesos nuevos entran a su cola
        2. DESBLOQUEOS: procesos que terminaron E/S vuelven a su cola
        3. DESALOJO: si hay un proceso de mayor prioridad, desaloja al actual
        4. DESPACHO: si CPU libre, tomar el mejor proceso listo
        5. IDLE: si no hay procesos listos, avanza tiempo y pre-carga siguiente estado
        6. EJECUCION: proceso actual ejecuta 1 unidad de tiempo
        7. POST-EJECUCION: decidir si termino rafaga, expiro quantum, o sigue
        """
        if self.finished:
            return [f"Tiempo {self.time}: simulación finalizada"]

        self.recent_transitions.clear()

        # --- FASE 1: Llegadas ---
        # Procesos con arrival_time <= tiempo actual pasan de NEW a READY
        self._handle_arrivals()

        # --- FASE 2: Desbloqueos ---
        # Procesos en E/S cuyo blocked_until <= tiempo actual vuelven a READY
        self._handle_unblocks()

        # --- FASE 3: Verificacion de desalojo ---
        # Si un proceso de mayor prioridad esta listo, desaloja al actual
        if self.current_process is not None:
            should_preempt, higher_queue = self._should_preempt()
            if should_preempt:
                self._preempt_current(higher_priority_queue=higher_queue)

        # --- FASE 4: Despacho ---
        # Si CPU libre, tomar el proceso de la cola mas prioritaria con procesos
        if self.current_process is None:
            self._try_dispatch()

        # --- FASE 5: Tick idle ---
        # Si CPU sigue libre (no hay procesos listos), registrar idle y avanzar
        if self.current_process is None:
            self._log("CPU queda libre (sin procesos listos)")
            self.total_idle_time += 1
            self._update_waiting_times()
            self.time += 1
            # Pre-cargar llegadas/desbloqueos en el nuevo tiempo para UI
            self._handle_arrivals()
            self._handle_unblocks(log_continue=False)
            self._try_dispatch()
            self.finished = all(p.is_finished for p in self.processes)
            return list(self.log_lines[-4:])

        # --- FASE 6: Ejecutar 1 unidad de tiempo ---
        process = self.current_process
        queue_index = self.current_queue if self.current_queue is not None else process.queue_index

        if process.remaining_in_burst <= 0 and process.current_burst is not None:
            process.remaining_in_burst = process.current_burst.duration

        process.remaining_in_burst -= 1
        process.executed_cpu_time += 1
        self.cpu_busy_time += 1
        self._record_execution(process, self.time)
        self._update_waiting_times()
        self._log(
            f"{process.name} ejecuta 1 u.t. en CPU"
            f" (Restan {process.remaining_in_burst} u.t. de ráfaga)"
        )
        if queue_index == 2:
            process.remaining_quantum -= 1
            self._log(f"{process.name} [RR] quantum residual: {process.remaining_quantum} u.t.")

        self.time += 1

        # Llegadas/Desbloqueos en el nuevo instante de tiempo
        self._handle_arrivals()
        self._handle_unblocks(log_continue=False)

        # --- FASE 7: Decisiones post-ejecucion ---
        # Caso A: La rafaga actual termino -> ver que sigue (IO, otra CPU, o finalizar)
        if process.remaining_in_burst <= 0:
            # Liberar CPU y procesar fin de rafaga
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True
            self._finish_current_burst(process)
            self._try_dispatch()  # Despachar inmediatamente si hay procesos listos

        # Caso B: Round Robin - el quantum expiro -> proceso va al final de la cola RR
        elif queue_index == 2 and process.remaining_quantum <= 0:
            # Liberar CPU, re-encolar al final, y despachar el siguiente
            self.current_process = None
            self.current_queue = None
            self.force_new_segment = True
            self._transition_to_ready(process, from_quantum_expiry=True)
            self._try_dispatch()

        # Caso C: El proceso sigue ejecutando -> verificar si debe ser desalojado
        else:
            # El proceso aun tiene rafaga y quantum. Verificar si llego uno mas prioritario
            if self.current_process is not None:
                should_preempt, higher_queue = self._should_preempt()
                if should_preempt:
                    self._preempt_current(higher_priority_queue=higher_queue)
                    self._try_dispatch()

        self.finished = all(p.is_finished for p in self.processes)
        if self.finished:
            self._log("La simulación ha finalizado completamente")
        return list(self.log_lines[-6:])

    # ------------------------------------------------------------------
    def run_until_end(self, max_steps: int = 10_000) -> list[str]:
        output: list[str] = []
        for _ in range(max_steps):
            if self.finished:
                break
            output.extend(self.step())
        return output

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
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
        completed = [p for p in self.processes if p.is_finished]
        count = max(1, len(completed))
        metrics = {p.name: self._process_metrics(p) for p in self.processes}
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
        for idx, p in enumerate(self.processes):
            if p.name == name:
                return PROCESS_COLORS[idx % len(PROCESS_COLORS)]
        return PROCESS_COLORS[abs(hash(name)) % len(PROCESS_COLORS)]
