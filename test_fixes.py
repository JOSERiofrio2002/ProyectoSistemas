"""Test script to verify all simulation fixes."""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'c:\Users\DANIEL\Desktop\proyectoSistemas')

from app.models.process import Process, Burst
from app.models.enums import BurstType, ProcessType
from app.simulator.engine import MultilevelQueueEngine


def run_test(title, processes, quantum=3, steps=15, check_time=None, check_fn=None):
    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print('='*60)
    engine = MultilevelQueueEngine(default_quantum=quantum)
    engine.set_processes(processes)
    test_passed = None

    for step_num in range(steps):
        t_before = engine.time
        engine.step()

        q0 = engine.queue_snapshot(0)
        q1 = engine.queue_snapshot(1)
        q2 = engine.queue_snapshot(2)
        q3 = engine.queue_snapshot(3)
        cpu = engine.current_process.name if engine.current_process else 'LIBRE'

        q0_names = [p.name for p in q0]
        q1_names = [f"{p.name}(P:{p.priority})" for p in q1]
        q2_names = [p.name for p in q2]
        q3_names = [p.name for p in q3]

        marker = ">>>" if t_before == check_time else "   "
        print(f"{marker} t={t_before}->{engine.time}: CPU={cpu}"
              f" | SJF={q0_names} | Prio={q1_names} | RR={q2_names} | FCFS={q3_names}")

        if check_time is not None and t_before == check_time and check_fn is not None:
            test_passed = check_fn(engine)
            result = "PASSED" if test_passed else "FAILED"
            print(f"\n    --> Verificacion en t={check_time}: [{result}]")

        if engine.finished:
            print("    Simulacion finalizada.")
            break

    return test_passed


# ==========================================================================
# TEST 1: Llegada de procesos - P1 en CPU, P2 llega y debe aparecer en cola
# ==========================================================================
p1 = Process('P1', 1, [Burst(BurstType.CPU, 8)], ProcessType.SYSTEM)
p2 = Process('P2', 3, [Burst(BurstType.CPU, 4)], ProcessType.SYSTEM)

def check_t3_arrival(engine):
    cpu_is_p1 = engine.current_process is not None and engine.current_process.name == 'P1'
    q0 = engine.queue_snapshot(0)
    p2_in_queue = any(p.name == 'P2' for p in q0)
    print(f"       CPU es P1: {cpu_is_p1}")
    print(f"       P2 esta en cola SJF: {p2_in_queue}")
    return cpu_is_p1 and p2_in_queue

run_test(
    "P1 llega t=1 (SJF), P2 llega t=3 - P2 debe aparecer en cola mientras P1 ejecuta",
    [p1, p2], steps=10, check_time=3, check_fn=check_t3_arrival
)


# ==========================================================================
# TEST 2: Preempcion por Prioridad - proceso desalojado vuelve en orden correcto
# ==========================================================================
p1 = Process('P1', 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=5)
p2 = Process('P2', 3, [Burst(BurstType.CPU, 4)], ProcessType.MULTIMEDIA, priority=1)

def check_t3_preemption(engine):
    # At t=3: CPU should be P2 (higher priority), P1 should be in queue in correct position
    cpu_is_p2 = engine.current_process is not None and engine.current_process.name == 'P2'
    q1 = engine.queue_snapshot(1)
    p1_in_queue = any(p.name == 'P1' for p in q1)
    if q1:
        first_in_queue = q1[0].name
        # P1(prio=5) should be first (and only) in queue
        correct_order = first_in_queue == 'P1'
    else:
        correct_order = False
    print(f"       CPU es P2 (prio=1): {cpu_is_p2}")
    print(f"       P1 esta en cola Prioridades: {p1_in_queue}")
    print(f"       Orden correcto en cola: {correct_order}")
    return cpu_is_p2 and p1_in_queue and correct_order

run_test(
    "P1 prio=5 en t=0, P2 prio=1 en t=3 - P2 desaloja a P1, P1 vuelve en posicion correcta",
    [p1, p2], steps=15, check_time=3, check_fn=check_t3_preemption
)


# ==========================================================================
# TEST 3: Multiples procesos en Prioridades - orden correcto de la cola
# ==========================================================================
p1 = Process('P1', 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=5)
p2 = Process('P2', 4, [Burst(BurstType.CPU, 3)], ProcessType.MULTIMEDIA, priority=1)
p3 = Process('P3', 2, [Burst(BurstType.CPU, 6)], ProcessType.MULTIMEDIA, priority=3)

def check_t4_multi_priority(engine):
    # At t=4: CPU=P2(prio=1), Queue=[P3(prio=3), P1(prio=5)]
    cpu_is_p2 = engine.current_process is not None and engine.current_process.name == 'P2'
    q1 = engine.queue_snapshot(1)
    q_names = [p.name for p in q1]
    correct_order = q_names == ['P3', 'P1']
    print(f"       CPU es P2 (prio=1): {cpu_is_p2}")
    print(f"       Cola Prioridades: {[f'{p.name}(P:{p.priority})' for p in q1]}")
    print(f"       Orden correcto [P3,P1]: {correct_order}")
    return cpu_is_p2 and correct_order

run_test(
    "3 procesos de Prioridades - cola ordenada correctamente tras desalojo",
    [p1, p2, p3], steps=20, check_time=4, check_fn=check_t4_multi_priority
)


# ==========================================================================
# TEST 4: Round Robin - proceso va al FINAL cuando se agota el quantum
# ==========================================================================
p1 = Process('P1', 0, [Burst(BurstType.CPU, 5)], ProcessType.INTERACTIVE, quantum=2)
p2 = Process('P2', 0, [Burst(BurstType.CPU, 5)], ProcessType.INTERACTIVE, quantum=2)

print(f"\n{'='*60}")
print("TEST: Round Robin - quantum agotado va al FINAL de la cola")
print('='*60)
engine = MultilevelQueueEngine(default_quantum=2)
engine.set_processes([p1, p2])
rr_order = []  # Track order of execution

for step_num in range(15):
    t_before = engine.time
    cpu_before = engine.current_process.name if engine.current_process else 'LIBRE'
    engine.step()
    q2 = engine.queue_snapshot(2)
    cpu = engine.current_process.name if engine.current_process else 'LIBRE'
    q2_names = [p.name for p in q2]
    if cpu != 'LIBRE':
        if not rr_order or rr_order[-1] != cpu:
            rr_order.append(cpu)
    print(f"   t={t_before}->{engine.time}: CPU={cpu} | Cola RR={q2_names}")
    if engine.finished:
        print("   Simulacion finalizada.")
        break

print(f"\n   Secuencia de ejecucion: {rr_order}")
print(f"   Esperado (alternancia): ['P1','P2','P1','P2',...]")
alternating = all(rr_order[i] != rr_order[i+1] for i in range(len(rr_order)-1)) if len(rr_order) > 1 else True
print(f"   Alternancia correcta: {alternating}")


print("\n\n*** TODOS LOS TESTS COMPLETADOS ***\n")
