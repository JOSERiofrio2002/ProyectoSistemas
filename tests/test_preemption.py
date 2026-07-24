"""Unit tests for multilevel queue scheduler preemption and Round Robin behavior."""

import unittest
from app.models.process import Process, Burst
from app.models.enums import ProcessType, BurstType
from app.simulator.engine import MultilevelQueueEngine


class TestMultilevelPreemption(unittest.TestCase):
    def test_preemption_on_arrival(self):
        """Test that arrival of process in higher-priority queue preempts currently running process immediately."""
        # P2 in RR (Queue 2), arrives at t=0, CPU=10, quantum=4
        # P1 in Priority (Queue 1), arrives at t=6, CPU=4
        p2 = Process("P2", 0, [Burst(BurstType.CPU, 10)], ProcessType.INTERACTIVE, quantum=4)
        p1 = Process("P1", 6, [Burst(BurstType.CPU, 4)], ProcessType.MULTIMEDIA, priority=1)

        engine = MultilevelQueueEngine(default_quantum=4)
        engine.set_processes([p2, p1])

        # Step until t=6
        while engine.time < 6:
            engine.step()

        # At t=6, step() executes arrival of P1 and preemption of P2
        engine.step()

        # P1 should now be running
        self.assertIsNotNone(engine.current_process)
        self.assertEqual(engine.current_process.name, "P1")
        self.assertEqual(engine.current_queue, 1)

        # P2 should be back in Queue 2 with remaining quantum 2 and remaining burst 4
        self.assertEqual(p2.remaining_quantum, 2)
        self.assertEqual(p2.remaining_in_burst, 4)

    def test_preemption_on_io_unblock(self):
        """Test that unblocking of higher-priority process from I/O preempts lower-priority running process."""
        # P1 in Priority (Queue 1), CPU=1, IO=3, CPU=2
        # P2 in RR (Queue 2), CPU=10, quantum=4
        p1 = Process("P1", 0, [Burst(BurstType.CPU, 1), Burst(BurstType.IO, 3), Burst(BurstType.CPU, 2)], ProcessType.MULTIMEDIA, priority=1)
        p2 = Process("P2", 0, [Burst(BurstType.CPU, 10)], ProcessType.INTERACTIVE, quantum=4)

        engine = MultilevelQueueEngine(default_quantum=4)
        engine.set_processes([p1, p2])

        # Step until t=4 (when P1 finishes IO)
        while engine.time < 4:
            engine.step()

        engine.step()

        # At t=4, P1 unblocks from IO and preempts P2
        self.assertIsNotNone(engine.current_process)
        self.assertEqual(engine.current_process.name, "P1")
        self.assertEqual(p2.remaining_quantum, 1)

    def test_quantum_preserved_and_resumed(self):
        """Test that preempted RR process retains its quantum and resumes after higher-priority process finishes."""
        p2 = Process("P2", 0, [Burst(BurstType.CPU, 10)], ProcessType.INTERACTIVE, quantum=4)
        p1 = Process("P1", 2, [Burst(BurstType.CPU, 3)], ProcessType.SYSTEM)

        engine = MultilevelQueueEngine(default_quantum=4)
        engine.set_processes([p2, p1])

        engine.run_until_end()

        # Check log contains preemption message
        logs_text = "\n".join(engine.log_lines)
        self.assertIn("P2 es desplazado de Round Robin", logs_text)
        self.assertIn("quantum residual: 2 u.t.", logs_text)
        self.assertTrue(engine.finished)

    def test_intra_queue_priority_preemption(self):
        """Test that arrival of a process with higher process priority within Queue 1 preempts current process."""
        p_low = Process("P_low", 0, [Burst(BurstType.CPU, 10)], ProcessType.MULTIMEDIA, priority=5)
        p_high = Process("P_high", 2, [Burst(BurstType.CPU, 3)], ProcessType.MULTIMEDIA, priority=1)

        engine = MultilevelQueueEngine()
        engine.set_processes([p_low, p_high])

        while engine.time < 2:
            engine.step()

        engine.step()

        self.assertIsNotNone(engine.current_process)
        self.assertEqual(engine.current_process.name, "P_high")


if __name__ == "__main__":
    unittest.main()
