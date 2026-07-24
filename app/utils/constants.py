"""UI and simulation constants."""

from __future__ import annotations

from app.models.enums import ProcessState, ProcessType

STATE_COLORS = {
    ProcessState.NEW: "#5f6b7a",
    ProcessState.READY: "#3b82f6",
    ProcessState.RUNNING: "#22c55e",
    ProcessState.BLOCKED: "#f59e0b",
    ProcessState.FINISHED: "#ef4444",
}

PROCESS_COLORS = [
    "#3b82f6",  # P1: Azul
    "#22c55e",  # P2: Verde
    "#ef4444",  # P3: Rojo
    "#8b5cf6",  # P4: Morado
    "#f97316",  # P5: Naranja
    "#06b6d4",  # P6: Turquesa
    "#ec4899",  # P7: Rosa
    "#eab308",  # P8: Amarillo
    "#6366f1",  # P9: Índigo
    "#10b981",  # P10: Menta
    "#f43f5e",  # P11: Carmesí
    "#a855f7",  # P12: Violeta
]

PROCESS_TYPE_LABELS = [t.value for t in ProcessType]

QUEUE_LABELS = {
    0: "COLA 0 | SJF (Sistema)",
    1: "COLA 1 | Prioridades (Multimedia)",
    2: "COLA 2 | Round Robin (Interactivos)",
    3: "COLA 3 | FCFS (Lotes)",
}

DEFAULT_THEME = "darkly"
