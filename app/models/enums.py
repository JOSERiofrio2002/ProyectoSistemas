"""Shared enums used by the simulator."""

from __future__ import annotations

from enum import Enum


class ProcessType(str, Enum):
    SYSTEM = "Sistema"
    MULTIMEDIA = "Multimedia"
    INTERACTIVE = "Interactivo"
    BATCH = "Lotes"


class ProcessState(str, Enum):
    NEW = "Nuevo"
    READY = "Listo"
    RUNNING = "Ejecutando"
    BLOCKED = "Bloqueado"
    FINISHED = "Finalizado"


class BurstType(str, Enum):
    CPU = "CPU"
    IO = "IO"
