"""Tests for process duplication prevention, priority preemption, and queue behaviors."""

import unittest
from app.models.enums import BurstType, ProcessType
from app.models.process import Burst, Process
from app.simulator.engine import MultilevelQueueEngine
from app.algorithms.priorities import PriorityQueueScheduler
from app.algorithms.rr import RoundRobinQueueScheduler
from app.algorithms.fcfs import FCFSScheduler


class TestQueueDuplicationAndPriority(unittest.TestCase):
    def test_no_duplicate_in_ready_queues(self):
        """Test that BaseQueueScheduler, FCFS, RR, Priority don't duplicate processes in ready queue."""
        p = Process("P1", 0, [Burst(BurstType.CPU, 5)], ProcessType.BATCH)
        scheduler = FCFSScheduler()
        scheduler.add(p)
        scheduler.add(p)
        self.assertEqual(len(scheduler.ready), 1)

        prio_sch = PriorityQueueScheduler()
        prio_p = Process("P2", 0, [Burst(BurstType.CPU, 5)], ProcessType.MULTIMEDIA, priority=2)
        prio_sch.add(prio_p)
        prio_sch.add(prio_p)
        prio_sch.add_front(prio_p)
        self.assertEqual(len(prio_sch.ready), 1)

        rr_sch = RoundRobinQueueScheduler(3)
        rr_p = Process("P3", 0, [Burst(BurstType.CPU, 5)], ProcessType.INTERACTIVE)
        rr_sch.add(rr_p)
        rr_sch.add(rr_p)
        self.assertEqual(len(rr_sch.ready), 1)

    def test_priority_preemption_p8_p9(self):
        """Test user's scenario: P9 prio=5 starts at t=0. At t=3, P8 prio=1 arrives. P8 must preempt P9 immediately."""
        p9 = Process("P9", 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=5)
        p8 = Process("P8", 3, [Burst(BurstType.CPU, 4)], ProcessType.MULTIMEDIA, priority=1)

        engine = MultilevelQueueEngine(default_quantum=3)
        engine.set_processes([p9, p8])

        # Step 1 (t=0->1), Step 2 (t=1->2), Step 3 (t=2->3): P9 executes
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.time, 3)

      
        engine.step()
        self.assertEqual(engine.time, 4)
        self.assertEqual(engine.current_process.name, "P8")
        
        q1_names = [p.name for p in engine.queue_snapshot(1)]
        self.assertIn("P9", q1_names)

        # Step 5 (t=4->5), Step 6 (t=5->6)
        engine.step()
        engine.step()
        self.assertEqual(engine.current_process.name, "P8")

        # Step 7 (t=6->7): P8 completes its 4 u.t. burst
        engine.step()
        self.assertEqual(engine.time, 7)

        # Step 8 (t=7->8): P9 is dispatched and executes
        engine.step()
        self.assertEqual(engine.current_process.name, "P9")

    def test_rr_quantum_expired_vs_preemption(self):
        """Test RR: process only goes to end of queue when quantum expires, not when preempted mid-quantum."""
        p1 = Process("P1", 0, [Burst(BurstType.CPU, 6)], ProcessType.INTERACTIVE, quantum=3)
        p2 = Process("P2", 0, [Burst(BurstType.CPU, 6)], ProcessType.INTERACTIVE, quantum=3)

        engine = MultilevelQueueEngine(default_quantum=3)
        engine.set_processes([p1, p2])

        # Step 1 (t=0->1): P1 running, P2 in RR queue
        engine.step()
        self.assertEqual(engine.current_process.name, "P1")
        self.assertEqual([p.name for p in engine.queue_snapshot(2)], ["P2"])

        # Step 2 (t=1->2), Step 3 (t=2->3): P1 completes quantum 3 at t=3
        engine.step()
        engine.step()
        self.assertEqual(engine.time, 3)
        # At t=3, P1 quantum expired -> P1 al final, P2 despachado inmediatamente
        self.assertEqual([p.name for p in engine.queue_snapshot(2)], ["P1"])

        # Step 4 (t=3->4): P2 continua ejecutando, P1 espera
        engine.step()
        self.assertEqual(engine.current_process.name, "P2")
        self.assertEqual([p.name for p in engine.queue_snapshot(2)], ["P1"])


if __name__ == "__main__":
    unittest.main()
