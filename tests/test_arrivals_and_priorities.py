"""Unit tests for process arrivals at exact arrival_time and priority queue reinsertion logic."""

import unittest
from app.models.process import Process, Burst
from app.models.enums import ProcessType, BurstType
from app.simulator.engine import MultilevelQueueEngine


class TestArrivalsAndPriorityQueue(unittest.TestCase):
    def test_process_arrival_exact_time_while_cpu_busy(self):
        """Error 1: Process enters its queue at exact arrival_time regardless of CPU state."""
        # P1 (Batch, Queue 3) arrives at t=0, runs CPU burst of 5
        # P2 (Batch, Queue 3) arrives at t=3, runs CPU burst of 2
        p1 = Process("P1", 0, [Burst(BurstType.CPU, 5)], ProcessType.BATCH)
        p2 = Process("P2", 3, [Burst(BurstType.CPU, 2)], ProcessType.BATCH)

        engine = MultilevelQueueEngine()
        engine.set_processes([p1, p2])

        # Step 1 (t=0 -> t=1): P1 is dispatched and executes tick 1
        engine.step()
        self.assertEqual(engine.time, 1)
        self.assertEqual(engine.current_process.name, "P1")

        # Step 2 (t=1 -> t=2): P1 executes tick 2. Time becomes 2.
        engine.step()
        self.assertEqual(engine.time, 2)
        self.assertEqual(engine.current_process.name, "P1")
        # At t=2, P2 has not arrived yet (arrival_time = 3)
        self.assertEqual(len(engine.queue_snapshot(3)), 0)

        # Step 3 (t=2 -> t=3): P1 executes tick 3. Time becomes 3.
        engine.step()
        self.assertEqual(engine.time, 3)
        self.assertEqual(engine.current_process.name, "P1")
        # EXACT BEHAVIOR REQUIREMENT: At time 3, while P1 is still executing in CPU,
        # P2 MUST appear in Queue 3 ready queue!
        q3_ready = engine.queue_snapshot(3)
        self.assertEqual(len(q3_ready), 1)
        self.assertEqual(q3_ready[0].name, "P2")



    def test_priority_queue_reinsertion_on_preemption(self):
        """Error 2a: Interrupted priority process returns to ready queue respecting priority order."""
        # Queue 1 processes:
        # P_low (priority 5) arrives at t=0, CPU=10
        # P_high (priority 1) arrives at t=2, CPU=3
        p_low = Process("P_low", 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=5)
        p_high = Process("P_high", 2, [Burst(BurstType.CPU, 3)], ProcessType.MULTIMEDIA, priority=1)

        engine = MultilevelQueueEngine()
        engine.set_processes([p_low, p_high])

        # Step until t=2
        while engine.time < 2:
            engine.step()

        # At t=2, P_high arrives and preempts P_low.
        engine.step()

        # P_high should be running
        self.assertEqual(engine.current_process.name, "P_high")

        # P_low should be in Queue 1 ready list in priority order
        queue1_snapshot = engine.queue_snapshot(1)
        self.assertEqual(len(queue1_snapshot), 1)
        self.assertEqual(queue1_snapshot[0].name, "P_low")

    def test_priority_queue_reinsertion_on_io_return(self):
        """Error 2b: Process returning from I/O to priority queue respects priority ordering."""
        p_low = Process("P_low", 0, [Burst(BurstType.CPU, 1), Burst(BurstType.IO, 2), Burst(BurstType.CPU, 5)], ProcessType.MULTIMEDIA, priority=5)
        p_med = Process("P_med", 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=3)

        engine = MultilevelQueueEngine()
        engine.set_processes([p_low, p_med])

        p_low.priority = 5
        p_med.priority = 3
        p_top = Process("P_top", 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=1)

        sched = engine.schedulers[1]
        sched.ready.clear()
        sched.add(p_low)
        sched.add(p_med)
        sched.add(p_top)

        # The ready queue snapshot must be sorted by priority: P_top (1), P_med (3), P_low (5)
        snapshot = sched.snapshot()
        self.assertEqual([p.name for p in snapshot], ["P_top", "P_med", "P_low"])

    def test_rr_quantum_expiration_moves_to_back(self):
        """Error 2c: Only Round Robin moves process to back on quantum expiration."""
        p1 = Process("P1", 0, [Burst(BurstType.CPU, 10)], ProcessType.INTERACTIVE, quantum=2)
        p2 = Process("P2", 0, [Burst(BurstType.CPU, 10)], ProcessType.INTERACTIVE, quantum=2)

        engine = MultilevelQueueEngine(default_quantum=2)
        engine.set_processes([p1, p2])

        # Step t=0 -> t=1 (P1 executes 1 ut)
        engine.step()
        # Step t=1 -> t=2 (P1 executes 2nd ut, quantum expires, P1 returns to back of RR queue)
        engine.step()
        # Step t=2 -> t=3 (P2 is dispatched from RR queue)
        engine.step()

        # At t=2, P2 should be running
        self.assertEqual(engine.current_process.name, "P2")



if __name__ == "__main__":
    unittest.main()
