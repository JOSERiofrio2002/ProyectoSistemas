"""Validación de entrada y helpers de análisis."""

from __future__ import annotations

import re
from typing import Sequence

from app.models.enums import BurstType, ProcessType
from app.models.process import Burst, Process


def parse_positive_int(value: str, field_name: str, allow_zero: bool = False) -> int:
    """Analiza un entero positivo, lanzando ValueError con mensaje legible."""

    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} debe ser un número entero.") from exc

    if allow_zero and number < 0:
        raise ValueError(f"{field_name} no puede ser negativo.")
    if not allow_zero and number <= 0:
        raise ValueError(f"{field_name} debe ser mayor que cero.")
    return number


def parse_burst_sequence(sequence_text: str, cpu_value: int | None = None, io_value: int | None = None) -> list[Burst]:
    """Analiza una secuencia flexible de CPU/E/S."""

    text = sequence_text.strip()
    if not text:
        if cpu_value is None:
            raise ValueError("Debes definir una secuencia de ráfagas o al menos una ráfaga CPU.")
        bursts = [Burst(BurstType.CPU, cpu_value)]
        if io_value is not None and io_value > 0:
            bursts.extend([Burst(BurstType.IO, io_value), Burst(BurstType.CPU, cpu_value)])
        return bursts

    tokens = re.findall(r"(?:\b(cpu|io|e/s)\b)?\s*(\d+)", text, flags=re.IGNORECASE)
    if not tokens:
        raise ValueError("La secuencia de ráfagas no es válida.")

    bursts: list[Burst] = []
    expected_kind = BurstType.CPU
    for raw_kind, raw_value in tokens:
        duration = int(raw_value)
        if duration <= 0:
            raise ValueError("Todas las ráfagas deben ser mayores que cero.")

        if raw_kind:
            kind_token = raw_kind.lower()
            if kind_token in {"cpu"}:
                kind = BurstType.CPU
            else:
                kind = BurstType.IO
        else:
            kind = expected_kind

        if bursts and bursts[-1].kind == kind:
            raise ValueError("La secuencia debe alternar CPU y E/S.")

        bursts.append(Burst(kind, duration))
        expected_kind = BurstType.IO if kind == BurstType.CPU else BurstType.CPU

    if bursts[0].kind != BurstType.CPU:
        raise ValueError("La secuencia debe comenzar con CPU.")
    return bursts


def parse_burst_rows(rows: Sequence[tuple[str, str]]) -> list[Burst]:
    """Analiza lista de ráfagas explícitas desde la UI."""

    bursts: list[Burst] = []
    expected_kind = BurstType.CPU

    for raw_kind, raw_duration in rows:
        kind_label = raw_kind.strip().upper()
        if kind_label in {"CPU", "C"}:
            kind = BurstType.CPU
        elif kind_label in {"IO", "E/S", "ES", "E S", "ENTRADA/SALIDA"}:
            kind = BurstType.IO
        else:
            raise ValueError("Cada ráfaga debe ser de tipo CPU o E/S.")

        duration = parse_positive_int(raw_duration, "Duración de ráfaga")
        if bursts and bursts[-1].kind == kind:
            raise ValueError("Las ráfagas deben alternar CPU y E/S.")
        if not bursts and kind != BurstType.CPU:
            raise ValueError("La primera ráfaga debe ser CPU.")

        bursts.append(Burst(kind, duration))
        expected_kind = BurstType.IO if kind == BurstType.CPU else BurstType.CPU

    if not bursts:
        raise ValueError("Debes agregar al menos una ráfaga.")
    if bursts[0].kind != BurstType.CPU:
        raise ValueError("La primera ráfaga debe ser CPU.")
    return bursts


def parse_dash_int_list(value: str, field_name: str) -> list[int]:
    """Analiza lista de enteros separados por guión como `2-5-7`."""

    text = value.strip()
    if not text:
        return []
    parts = [part.strip() for part in text.split("-") if part.strip()]
    if not parts:
        return []

    result: list[int] = []
    for part in parts:
        result.append(parse_positive_int(part, field_name))
    return result


def build_bursts_from_cpu_and_io(cpu_total: int, io_points: list[int], io_durations: list[int]) -> list[Burst]:
    """Build alternating CPU/IO bursts from a single CPU total and IO specs.

    `io_points` are CPU progress instants where the process requests IO.
    Example: CPU=10, points=2-7, io=3-2 -> CPU2,IO3,CPU5,IO2,CPU3.
    """

    if len(io_points) != len(io_durations):
        raise ValueError("La cantidad de operaciones E/S y duraciones E/S debe coincidir.")

    if not io_points:
        return [Burst(BurstType.CPU, cpu_total)]

    points = io_points[:]
    if any(point >= cpu_total for point in points):
        raise ValueError("Cada operación E/S debe ocurrir antes de terminar el CPU total.")
    if points != sorted(points):
        raise ValueError("Las operaciones E/S deben estar en orden ascendente.")
    if any(point <= 0 for point in points):
        raise ValueError("Las operaciones E/S deben ser mayores que cero.")
    if len(set(points)) != len(points):
        raise ValueError("No repitas tiempos de operación E/S.")

    bursts: list[Burst] = []
    previous = 0
    for point, io_duration in zip(points, io_durations):
        cpu_slice = point - previous
        if cpu_slice <= 0:
            raise ValueError("Las operaciones E/S deben avanzar en el tiempo de CPU.")
        bursts.append(Burst(BurstType.CPU, cpu_slice))
        bursts.append(Burst(BurstType.IO, io_duration))
        previous = point

    tail_cpu = cpu_total - previous
    if tail_cpu <= 0:
        raise ValueError("Debe existir CPU restante después de la última E/S.")
    bursts.append(Burst(BurstType.CPU, tail_cpu))
    return bursts


PROCESS_TYPE_LABELS = {
    ProcessType.SYSTEM: "SJF (Sistema)",
    ProcessType.MULTIMEDIA: "Prioridades (Multimedia)",
    ProcessType.INTERACTIVE: "Round Robin (Interactivos)",
    ProcessType.BATCH: "FCFS (Lotes)",
}

LABEL_TO_PROCESS_TYPE = {
    "SJF (Sistema)": ProcessType.SYSTEM,
    "Prioridades (Multimedia)": ProcessType.MULTIMEDIA,
    "Round Robin (Interactivos)": ProcessType.INTERACTIVE,
    "FCFS (Lotes)": ProcessType.BATCH,
    "Sistema": ProcessType.SYSTEM,
    "Multimedia": ProcessType.MULTIMEDIA,
    "Interactivo": ProcessType.INTERACTIVE,
    "Lotes": ProcessType.BATCH,
}


def process_type_display_label(process_type: ProcessType) -> str:
    """Retorna etiqueta visible del desplegable para tipo de proceso."""
    return PROCESS_TYPE_LABELS.get(process_type, process_type.value)


def process_type_from_label(label: str) -> ProcessType:
    """Convierte etiqueta visible en tipo de proceso."""
    clean_label = label.strip()
    if clean_label in LABEL_TO_PROCESS_TYPE:
        return LABEL_TO_PROCESS_TYPE[clean_label]

    for process_type in ProcessType:
        if process_type.value.lower() in clean_label.lower():
            return process_type
    raise ValueError("Tipo de proceso inválido.")


def is_priority_algorithm(type_value: str | ProcessType) -> bool:
    """Retorna True si el algoritmo es basado en prioridades."""
    if isinstance(type_value, ProcessType):
        return type_value == ProcessType.MULTIMEDIA
    val = str(type_value).lower()
    return "prioridad" in val or "multimedia" in val


def is_round_robin_algorithm(type_value: str | ProcessType) -> bool:
    """Retorna True si el algoritmo es Round Robin."""
    if isinstance(type_value, ProcessType):
        return type_value == ProcessType.INTERACTIVE
    val = str(type_value).lower()
    return "round" in val or "interactivo" in val or "rr" in val




def get_next_process_name(existing_names: Sequence[str]) -> str:
    """Calcula el siguiente nombre automático (P1, P2, P3...)."""
    nums: list[int] = []
    for name in existing_names:
        match = re.search(r"P(\d+)", name, re.IGNORECASE)
        if match:
            nums.append(int(match.group(1)))
    next_num = max(nums) + 1 if nums else len(existing_names) + 1
    return f"P{next_num}"


def validate_process_name(name: str, existing_names: Sequence[str], current_name: str | None = None) -> None:
    """Evita nombres duplicados y vacíos."""

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("El nombre del proceso es obligatorio.")

    duplicates = {n.strip().lower() for n in existing_names}
    if current_name is not None:
        duplicates.discard(current_name.strip().lower())
    if clean_name.lower() in duplicates:
        raise ValueError("No se permiten nombres repetidos.")


def process_summary_values(process: Process) -> tuple[str, str, str, str, str, str, str, str]:
    """Retorna los valores mostrados en la tabla de procesos."""

    priority = "-" if process.priority is None else str(process.priority)
    quantum = "-" if process.quantum is None else str(process.quantum)
    io_points = process.io_operation_points()
    io_durations = process.io_durations()
    io_points_text = "-".join(str(value) for value in io_points) if io_points else "-"
    io_durations_text = "-".join(str(value) for value in io_durations) if io_durations else "-"
    return (
        process.name,
        str(process.arrival_time),
        str(process.cpu_total()),
        priority,
        quantum,
        io_points_text,
        io_durations_text,
        process.process_type.value,
    )
