"""Unit tests for non-preemptive SJF (Shortest Job First) scheduling."""

import unittest
from app.models.process import Process, Burst
from app.models.enums import ProcessType, BurstType
from app.simulator.engine import MultilevelQueueEngine


class TestSJFNonPreemptive(unittest.TestCase):
    def test_sjf_preemptive_execution_order(self):
        """
        Preemptive SJF (SRTF) test:
        P1: arrival=1, CPU=5
        P2: arrival=2, CPU=4
        P3: arrival=3, CPU=2

        Expected timeline:
        - t=1: P1 arrives and starts running on CPU (remaining=5).
        - t=2: P2 arrives (burst=4). P1 remaining=4. 4 < 4? No. P1 continues.
        - t=3: P3 arrives (burst=2). P1 remaining=3. 2 < 3? YES -> P3 preempts P1!
        - t=3-5: P3 runs and finishes 2 ut.
        - t=5: P1 resumes (remaining=3).
        - t=8: P1 finishes 3 ut. CPU picks P2.
        - t=12: P2 finishes 4 ut.

        Final execution order: P1 -> P3 -> P1 -> P2.
        """
        p1 = Process("P1", 1, [Burst(BurstType.CPU, 5)], ProcessType.SYSTEM)
        p2 = Process("P2", 2, [Burst(BurstType.CPU, 4)], ProcessType.SYSTEM)
        p3 = Process("P3", 3, [Burst(BurstType.CPU, 2)], ProcessType.SYSTEM)

        engine = MultilevelQueueEngine()
        engine.set_processes([p1, p2, p3])

        # Step t=0 -> t=1 (CPU idle, waiting for arrival at t=1)
        engine.step()
        self.assertEqual(engine.time, 1)

        # Step t=1 -> t=2 (P1 starts running, remaining=5)
        engine.step()
        self.assertEqual(engine.time, 2)
        self.assertEqual(engine.current_process.name, "P1")

        # Step t=2 -> t=3: P2 llega(t=2), P1 ejecuta. time=3: P3 llega y desaloja a P1!
        engine.step()
        self.assertEqual(engine.time, 3)
        self.assertEqual(engine.current_process.name, "P3")

        # Step t=3 -> t=4: P3 ejecuta 1 ut (burst 2->1)
        engine.step()
        self.assertEqual(engine.time, 4)
        self.assertEqual(engine.current_process.name, "P3")

        # Step t=4 -> t=5: P3 ejecuta ultima ut y finaliza
        engine.step()
        self.assertEqual(engine.time, 5)

        # t=5: P3 finalizado. P1(restante=3) vs P2(4). P1 mas corto → P1 reanuda.
        engine.step()
        self.assertEqual(engine.current_process.name, "P1")

        # Steps t=6->t=8: P1 termina sus 3 ut restantes
        engine.step()
        engine.step()
        self.assertEqual(engine.time, 8)

        # t=8: P1 finalizado. P2 ejecuta a continuacion.
        engine.step()
        self.assertEqual(engine.current_process.name, "P2")

        # Run remaining simulation
        engine.run_until_end()

        # Check total execution sequence in CPU timeline segments
        cpu_order = []
        for seg in engine.cpu_timeline_segments:
            if not cpu_order or cpu_order[-1] != seg.process_name:
                cpu_order.append(seg.process_name)

        self.assertEqual(cpu_order, ["P1", "P3", "P1", "P2"])


if __name__ == "__main__":
    unittest.main()
