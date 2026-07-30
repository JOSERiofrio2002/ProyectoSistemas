"""Diálogo modal para agregar o editar un proceso."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb

from app.models.enums import ProcessType
from app.models.process import Process
from app.utils.validators import (
    build_bursts_from_cpu_and_io,
    get_next_process_name,
    is_priority_algorithm,
    is_round_robin_algorithm,
    parse_dash_int_list,
    parse_positive_int,
    process_type_display_label,
    process_type_from_label,
    validate_process_name,
)


class ProcessDialog:
    def __init__(self, master: tk.Misc, existing_names: list[str], process: Process | None = None) -> None:
        self.master = master
        self.existing_names = existing_names
        self.process = process
        self.result: Process | None = None
        self.field_widgets: dict[str, tk.Misc] = {}
        self.field_labels: dict[str, tb.Label] = {}

        self.window = tb.Toplevel(master)
        self.window.title("Definir Proceso")
        self.window.geometry("760x760")
        self.window.transient(master)
        self.window.grab_set()
        self.window.minsize(700, 620)
        self.window.resizable(True, True)

        auto_name = process.name if process else get_next_process_name(existing_names)
        self.name_var = tk.StringVar(value=auto_name)
        self.arrival_var = tk.StringVar(value=str(process.arrival_time) if process else "")
        initial_type_label = process_type_display_label(process.process_type) if process else process_type_display_label(ProcessType.SYSTEM)
        self.type_var = tk.StringVar(value=initial_type_label)
        self.priority_var = tk.StringVar(value="" if process is None or process.priority is None else str(process.priority))
        self.quantum_var = tk.StringVar(value="" if process is None or process.quantum is None else str(process.quantum))

        if process is not None:
            cpu_value = str(process.cpu_total())
            io_ops = process.io_operation_points()
            io_durations = process.io_durations()
            io_ops_text = "-".join(str(value) for value in io_ops)
            io_duration_text = "-".join(str(value) for value in io_durations)
        else:
            cpu_value = ""
            io_ops_text = ""
            io_duration_text = ""

        self.cpu_var = tk.StringVar(value=cpu_value)
        self.io_ops_var = tk.StringVar(value=io_ops_text)
        self.io_duration_var = tk.StringVar(value=io_duration_text)

        self._build_ui()
        self._on_type_changed()
        self.type_var.trace_add("write", lambda *args: self._on_type_changed())
        self.window.wait_window()

    def _build_ui(self) -> None:
        container = tb.Frame(self.window, padding=18)
        container.pack(fill="both", expand=True)
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)

        header = tb.Label(container, text="Definición del proceso", font=("Segoe UI", 16, "bold"))
        header.grid(row=0, column=0, sticky="w", pady=(0, 12))

        body = tb.Frame(container)
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        canvas = tk.Canvas(body, highlightthickness=0, bg=self.window.cget("background"))
        scrollbar = tb.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.form_content = tb.Frame(canvas)
        self.form_window = canvas.create_window((0, 0), window=self.form_content, anchor="nw")

        def update_scrollregion(_: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(self.form_window, width=event.width)

        self.form_content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", sync_width)

        form = self.form_content
        type_options = ["SJF (Sistema)", "Prioridades (Multimedia)", "Round Robin (Interactivos)", "FCFS (Lotes)"]
        lbl_name, widget_name = self._add_row(form, 0, "name", "Nombre de Proceso (Auto)", tb.Entry, self.name_var)
        widget_name.configure(state="readonly")

        self._add_row(form, 1, "arrival", "Llegada", tb.Entry, self.arrival_var)
        type_lbl, type_widget = self._add_row(form, 2, "type", "Tipo de proceso", tb.Combobox, self.type_var, values=type_options)

        if isinstance(type_widget, tb.Combobox):
            type_widget.bind("<<ComboboxSelected>>", lambda e: self._on_type_changed())

        self._add_row(form, 3, "priority", "Prioridad", tb.Entry, self.priority_var)
        self._add_row(form, 4, "quantum", "Quantum", tb.Entry, self.quantum_var)
        self._add_row(form, 5, "cpu", "CPU (único)", tb.Entry, self.cpu_var)
        self._add_row(form, 6, "io_ops", "Operaciones E/S", tb.Entry, self.io_ops_var)
        self._add_row(form, 7, "io_dur", "Duraciones E/S", tb.Entry, self.io_duration_var)

        hint = tb.Label(
            form,
            text="Usa '-' para separar múltiples valores. Ejemplo: Operaciones E/S=2-5-9, Duraciones E/S=1-3-2",
            foreground="#93a4b8",
        )
        hint.grid(row=8, column=1, sticky="w", pady=(4, 8))

        form.columnconfigure(1, weight=1)

        buttons = tb.Frame(container)
        buttons.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        buttons.columnconfigure(0, weight=1)
        action_box = tb.Frame(buttons)
        action_box.pack(side="right")
        tb.Button(action_box, text="Guardar", bootstyle="success", command=self._save).pack(side="right", padx=(8, 0))
        tb.Button(action_box, text="Cancelar", bootstyle="secondary", command=self.window.destroy).pack(side="right")

    def _add_row(self, parent: tk.Misc, row: int, key: str, label_text: str, widget_cls, variable, values=None) -> tuple[tb.Label, tk.Misc]:
        label = tb.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
        if widget_cls is tb.Combobox:
            widget = widget_cls(parent, textvariable=variable, values=values, state="readonly", width=44)
        else:
            widget = widget_cls(parent, textvariable=variable, width=48)
        widget.grid(row=row, column=1, sticky="ew", pady=6)

        self.field_labels[key] = label
        self.field_widgets[key] = widget
        return label, widget

    def _on_type_changed(self, event=None) -> None:
        selected_type_text = self.type_var.get()
        is_priority = is_priority_algorithm(selected_type_text)
        is_rr = is_round_robin_algorithm(selected_type_text)

        p_widget = self.field_widgets.get("priority")
        p_label = self.field_labels.get("priority")
        if is_priority:
            if p_widget:
                p_widget.configure(state="normal")
            if p_label:
                p_label.configure(foreground="#dce6f2", text="Prioridad *")
        else:
            self.priority_var.set("")
            if p_widget:
                p_widget.configure(state="disabled")
            if p_label:
                p_label.configure(foreground="#64748b", text="Prioridad")

        q_widget = self.field_widgets.get("quantum")
        q_label = self.field_labels.get("quantum")
        if is_rr:
            if q_widget:
                q_widget.configure(state="normal")
            if q_label:
                q_label.configure(foreground="#dce6f2", text="Quantum *")
        else:
            self.quantum_var.set("")
            if q_widget:
                q_widget.configure(state="disabled")
            if q_label:
                q_label.configure(foreground="#64748b", text="Quantum")

    def _save(self) -> None:
        try:
            validate_process_name(self.name_var.get(), self.existing_names, self.process.name if self.process else None)
            arrival = parse_positive_int(self.arrival_var.get(), "Tiempo de llegada", allow_zero=True)
            process_type = process_type_from_label(self.type_var.get())

            if is_priority_algorithm(process_type):
                if not self.priority_var.get().strip():
                    raise ValueError("Debe ingresar la prioridad para el algoritmo de Prioridades.")
            if is_round_robin_algorithm(process_type):
                if not self.quantum_var.get().strip():
                    raise ValueError("Debe ingresar el quantum para el algoritmo Round Robin.")

            cpu_total = parse_positive_int(self.cpu_var.get(), "CPU")
            io_points = parse_dash_int_list(self.io_ops_var.get(), "Operaciones E/S")
            io_durations = parse_dash_int_list(self.io_duration_var.get(), "Duraciones E/S")
            priority = None
            quantum = None

            if is_priority_algorithm(process_type) and self.priority_var.get().strip():
                priority = parse_positive_int(self.priority_var.get(), "Prioridad")
            if is_round_robin_algorithm(process_type) and self.quantum_var.get().strip():
                quantum = parse_positive_int(self.quantum_var.get(), "Quantum")

            bursts = build_bursts_from_cpu_and_io(cpu_total, io_points, io_durations)
            self.result = Process(
                name=self.name_var.get().strip(),
                arrival_time=arrival,
                bursts=bursts,
                process_type=process_type,
                priority=priority,
                quantum=quantum,
            )
            self.window.destroy()
        except ValueError as exc:
            messagebox.showerror("Validación", str(exc), parent=self.window)

