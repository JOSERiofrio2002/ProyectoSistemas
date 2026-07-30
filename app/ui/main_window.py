"""Ventana principal con todos los componentes visuales."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import ttkbootstrap as tb

from app.models.enums import BurstType, ProcessType
from app.models.enums import ProcessState
from app.models.process import Burst, Process
from app.simulator.engine import ExecutionSegment, MultilevelQueueEngine
from app.ui.process_dialog import ProcessDialog
from app.utils.constants import DEFAULT_THEME, QUEUE_LABELS, STATE_COLORS
from app.utils.validators import (
    build_bursts_from_cpu_and_io,
    is_priority_algorithm,
    is_round_robin_algorithm,
    parse_dash_int_list,
    parse_positive_int,
    process_summary_values,
    process_type_display_label,
    process_type_from_label,
    validate_process_name,
)


class MainWindow:
    def __init__(self) -> None:
        self.root = tb.Window(themename=DEFAULT_THEME)
        self.root.title("Simulador de Colas de Múltiples Niveles")
        self.root.geometry("1680x980")
        self.root.minsize(1500, 900)

        self.processes: list[Process] = []
        self.engine = MultilevelQueueEngine(default_quantum=3)
        self.auto_running = False
        self.timer_id: str | None = None
        self.step_delay_ms = tk.IntVar(value=1000)

        self._configure_styles()
        self._build_layout()
        self.refresh_all()

    def _configure_styles(self) -> None:
        style = self.root.style
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#dce6f2")
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), foreground="#dce6f2")
        style.configure("Muted.TLabel", foreground="#9fb0c2")
        style.configure("TButton", padding=8)
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        main = tb.Frame(self.root, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self.left_panel = tb.Frame(main, width=370)
        self.left_panel.grid(row=0, column=0, sticky="nswe", padx=(0, 12))
        self.left_panel.grid_propagate(False)
        self._build_left_panel(self.left_panel)

        right = tb.Frame(main)
        right.grid(row=0, column=1, sticky="nswe")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.table_frame = tb.Frame(right, padding=8)
        self.table_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        right.rowconfigure(0, weight=1)

        bottom_tabs = tb.Notebook(right)
        bottom_tabs.grid(row=1, column=0, sticky="nsew")

        self.gantt_tab = tb.Frame(bottom_tabs, padding=8)
        self.console_tab = tb.Frame(bottom_tabs, padding=8)
        self.stats_tab = tb.Frame(bottom_tabs, padding=8)

        bottom_tabs.add(self.gantt_tab, text="Ejecución de Colas y CPU")
        bottom_tabs.add(self.console_tab, text="Consola")
        bottom_tabs.add(self.stats_tab, text="Tiempos de Espera y Ejecución")

        self._build_process_table(self.table_frame)
        self._build_gantt_panel(self.gantt_tab)
        self._build_console_panel(self.console_tab)
        self._build_stats_panel(self.stats_tab)

    def _build_left_panel(self, parent: tk.Misc) -> None:
        title = tb.Label(parent, text="Procesos", style="Title.TLabel")
        title.pack(anchor="w", pady=(0, 10))

    def _build_left_panel(self, parent: tk.Misc) -> None:
        title = tb.Label(parent, text="Procesos", style="Title.TLabel")
        title.pack(anchor="w", pady=(0, 10))

        form = tb.Labelframe(parent, text="Vista previa / Información del proceso", padding=10)
        form.pack(fill="x", pady=(0, 12))

        tb.Label(form, text="Los campos marcados con * son obligatorios", foreground="#38bdf8", font=("Segoe UI", 9, "italic")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.new_process_fields = {
            "name": tk.StringVar(),
            "arrival": tk.StringVar(value="0"),
            "cpu": tk.StringVar(value="8"),
            "priority": tk.StringVar(),
            "quantum": tk.StringVar(),
            "io_ops": tk.StringVar(value="2-5"),
            "io_dur": tk.StringVar(value="1-2"),
            "type": tk.StringVar(value="SJF (Sistema)"),
        }

        self.form_field_widgets: dict[str, tk.Misc] = {}
        self.form_field_labels: dict[str, tb.Label] = {}

        type_options = ["SJF (Sistema)", "Prioridades (Multimedia)", "Round Robin (Interactivos)", "FCFS (Lotes)"]

        field_specs = [
            ("Proceso",        "name",     False),
            ("Llegada",        "arrival",  False),
            ("CPU",            "cpu",      False),
            ("Prioridad",      "priority", False),
            ("Quantum",        "quantum",  False),
            ("E/S (puntos)",   "io_ops",   False),
            ("Duración E/S",   "io_dur",   False),
            ("Tipo de proceso","type",     True),
        ]
        for index, (label_text, key, is_combo) in enumerate(field_specs):
            row_idx = index + 1
            lbl = tb.Label(form, text=label_text)
            lbl.grid(row=row_idx, column=0, sticky="w", pady=3, padx=(0, 8))
            self.form_field_labels[key] = lbl

            if is_combo:
                widget = tb.Combobox(form, textvariable=self.new_process_fields[key], values=type_options, state="disabled", width=28)
            else:
                widget = tb.Entry(form, textvariable=self.new_process_fields[key], state="readonly", width=32)
            widget.grid(row=row_idx, column=1, sticky="ew", pady=3)
            self.form_field_widgets[key] = widget

        tb.Label(form, text="(E/S: separar valores con '-'. Ej: 2-5  /  1-3)",
                 foreground="#9fb0c2", font=("Segoe UI", 8)).grid(
                 row=len(field_specs) + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        form.columnconfigure(1, weight=1)

        controls = tb.Labelframe(parent, text="Acciones", padding=10)
        controls.pack(fill="x", pady=(0, 12))

        # Grupo 1: Gestión de procesos
        group_mgmt = tb.Labelframe(controls, text="Gestión de procesos", padding=8)
        group_mgmt.pack(fill="x", pady=(0, 8))
        group_mgmt.columnconfigure(0, weight=1, uniform="mgmt")
        group_mgmt.columnconfigure(1, weight=1, uniform="mgmt")

        tb.Button(group_mgmt, text="Agregar", bootstyle="success", command=self.add_process).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        tb.Button(group_mgmt, text="Editar", bootstyle="warning", command=self.edit_process).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        tb.Button(group_mgmt, text="Eliminar", bootstyle="danger", command=self.delete_process).grid(row=1, column=0, sticky="ew", padx=3, pady=3)
        tb.Button(group_mgmt, text="Nuevo ejercicio", bootstyle="secondary", command=self.new_exercise).grid(row=1, column=1, sticky="ew", padx=3, pady=3)
        tb.Button(group_mgmt, text="Cargar ejemplo", bootstyle="info", command=self.load_sample).grid(row=2, column=0, columnspan=2, sticky="ew", padx=3, pady=3)

        # Grupo 2: Control de ejecución
        group_exec = tb.Labelframe(controls, text="Control de ejecución", padding=8)
        group_exec.pack(fill="x")
        group_exec.columnconfigure(0, weight=1, uniform="exec")
        group_exec.columnconfigure(1, weight=1, uniform="exec")

        tb.Button(group_exec, text="Iniciar", bootstyle="primary", command=self.start_auto).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        tb.Button(group_exec, text="Pausar", bootstyle="warning", command=self.pause_auto).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        tb.Button(group_exec, text="Continuar", bootstyle="success", command=self.resume_auto).grid(row=1, column=0, sticky="ew", padx=3, pady=3)
        tb.Button(group_exec, text="Reiniciar", bootstyle="secondary", command=self.reset_simulation).grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        self._on_left_panel_type_changed()
        self.new_process_fields["type"].trace_add("write", lambda *args: self._on_left_panel_type_changed())


        speed_box = tb.Labelframe(parent, text="Velocidad de simulación", padding=10)
        speed_box.pack(fill="x")
        tb.Label(speed_box, text="Milisegundos por paso").pack(anchor="w")
        tb.Spinbox(speed_box, from_=100, to=5000, textvariable=self.step_delay_ms, width=12).pack(anchor="w", pady=(4, 0))

    def _build_process_table(self, parent: tk.Misc) -> None:
        header = tb.Label(parent, text="Tabla de procesos", style="Section.TLabel")
        header.pack(anchor="w", pady=(0, 8))

        columns = ("Proceso", "Llegada", "CPU", "Prioridad", "Quantum", "E/S", "Duración", "Tipo")
        self.process_tree = ttk.Treeview(parent, columns=columns, show="headings", height=13)
        for column in columns:
            self.process_tree.heading(column, text=column)
            self.process_tree.column(column, anchor="center", width=95)
        self.process_tree.column("Proceso", width=100, anchor="w")
        self.process_tree.column("Tipo", width=170)
        self.process_tree.pack(fill="both", expand=True)
        self.process_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _build_queue_panel(self, parent: tk.Misc) -> None:
        header = tb.Label(parent, text="Colas de planificación y E/S", style="Section.TLabel")
        header.pack(anchor="w", pady=(0, 8))

        body = tb.Frame(parent)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        queue_canvas = tk.Canvas(body, bg="#0f1720", highlightthickness=0)
        queue_scroll = tb.Scrollbar(body, orient="vertical", command=queue_canvas.yview)
        queue_canvas.configure(yscrollcommand=queue_scroll.set)
        queue_canvas.grid(row=0, column=0, sticky="nsew")
        queue_scroll.grid(row=0, column=1, sticky="ns")

        self.queue_content = tb.Frame(queue_canvas)
        self.queue_window = queue_canvas.create_window((0, 0), window=self.queue_content, anchor="nw")

        def _update_queue_scroll(_: tk.Event | None = None) -> None:
            queue_canvas.configure(scrollregion=queue_canvas.bbox("all"))

        def _sync_queue_width(event: tk.Event) -> None:
            queue_canvas.itemconfigure(self.queue_window, width=event.width)

        self.queue_content.bind("<Configure>", _update_queue_scroll)
        queue_canvas.bind("<Configure>", _sync_queue_width)

        self.queue_boxes: dict[int, dict[str, tk.Misc]] = {}
        for queue_index in range(4):
            box = tb.Labelframe(self.queue_content, text=QUEUE_LABELS[queue_index], padding=8)
            box.pack(fill="x", pady=6)

            order_label = tb.Label(box, text="Orden actual: (vacía)", foreground="#9fb0c2")
            order_label.pack(anchor="w", pady=(0, 4))

            # Contenedor con scroll horizontal para tarjetas de la cola
            lane_container = tb.Frame(box)
            lane_container.pack(fill="x", pady=(0, 4))

            lane_canvas = tk.Canvas(lane_container, height=72, bg="#0f1720", highlightthickness=0)
            lane_scroll = tb.Scrollbar(lane_container, orient="horizontal", command=lane_canvas.xview)
            lane_canvas.configure(xscrollcommand=lane_scroll.set)

            lane_frame = tb.Frame(lane_canvas)
            lane_win = lane_canvas.create_window((0, 0), window=lane_frame, anchor="nw")

            def _on_lane_cfg(event: tk.Event, c=lane_canvas) -> None:
                c.configure(scrollregion=c.bbox("all"))

            lane_frame.bind("<Configure>", _on_lane_cfg)

            lane_canvas.pack(side="top", fill="x", expand=True)
            lane_scroll.pack(side="bottom", fill="x")

            tb.Label(box, text="Secuencia ejecutada", foreground="#9fb0c2").pack(anchor="w")
            sequence_label = tb.Label(box, text="-", foreground="#dce6f2", wraplength=520, justify="left")
            sequence_label.pack(anchor="w", pady=(2, 0), fill="x")

            tb.Label(box, text="Procesos de la cola", foreground="#9fb0c2").pack(anchor="w", pady=(6, 2))
            members = tb.Frame(box)
            members.pack(fill="x")

            self.queue_boxes[queue_index] = {
                "order": order_label,
                "lane": lane_frame,
                "lane_canvas": lane_canvas,
                "sequence": sequence_label,
                "members": members,
            }

        self.blocked_box = tb.Labelframe(self.queue_content, text="COLA DE ENTRADA / SALIDA (E/S)", padding=8)
        self.blocked_box.pack(fill="x", pady=(8, 0))

        self.io_order_label = tb.Label(self.blocked_box, text="Orden actual en E/S: (vacía)", foreground="#9fb0c2")
        self.io_order_label.pack(anchor="w", pady=(0, 4))

        io_container = tb.Frame(self.blocked_box)
        io_container.pack(fill="x", pady=(0, 4))

        self.io_lane_canvas = tk.Canvas(io_container, height=72, bg="#0f1720", highlightthickness=0)
        io_scroll = tb.Scrollbar(io_container, orient="horizontal", command=self.io_lane_canvas.xview)
        self.io_lane_canvas.configure(xscrollcommand=io_scroll.set)

        self.io_lane = tb.Frame(self.io_lane_canvas)
        self.io_win = self.io_lane_canvas.create_window((0, 0), window=self.io_lane, anchor="nw")

        def _on_io_cfg(event: tk.Event, c=self.io_lane_canvas) -> None:
            c.configure(scrollregion=c.bbox("all"))

        self.io_lane.bind("<Configure>", _on_io_cfg)

        self.io_lane_canvas.pack(side="top", fill="x", expand=True)
        io_scroll.pack(side="bottom", fill="x")

        tb.Label(self.blocked_box, text="Secuencia ejecutada en E/S", foreground="#9fb0c2").pack(anchor="w")
        self.io_sequence_label = tb.Label(self.blocked_box, text="-", foreground="#dce6f2", wraplength=520, justify="left")
        self.io_sequence_label.pack(anchor="w", pady=(2, 0), fill="x")

        tb.Label(self.blocked_box, text="Procesos del sistema con E/S", foreground="#9fb0c2").pack(anchor="w", pady=(6, 2))
        self.io_members = tb.Frame(self.blocked_box)
        self.io_members.pack(fill="x")

    def _build_gantt_panel(self, parent: tk.Misc) -> None:
        top = tb.Frame(parent)
        top.pack(fill="both", expand=True)
        top.rowconfigure(0, weight=4)
        top.rowconfigure(1, weight=2)
        top.rowconfigure(2, weight=2)
        top.columnconfigure(0, weight=1)

        algo_frame = tb.Labelframe(top, text="Historial de Ejecución por Algoritmo (SJF, Prioridades, RR, FCFS)", padding=6)
        algo_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        
        algo_container = tb.Frame(algo_frame)
        algo_container.pack(fill="both", expand=True)
        algo_container.rowconfigure(0, weight=1)
        algo_container.columnconfigure(0, weight=1)

        self.algo_canvas = tk.Canvas(algo_container, bg="#0f1720", highlightthickness=0)
        h_scroll = tb.Scrollbar(algo_container, orient="horizontal", command=self.algo_canvas.xview)
        v_scroll = tb.Scrollbar(algo_container, orient="vertical", command=self.algo_canvas.yview)
        self.algo_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.algo_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        io_diag_frame = tb.Labelframe(top, text="O E/S (Diagrama de Entrada / Salida)", padding=6)
        io_diag_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        self.io_canvas = tk.Canvas(io_diag_frame, height=95, bg="#0f1720", highlightthickness=0)
        self.io_canvas.pack(fill="both", expand=True)

        timeline_frame = tb.Labelframe(top, text="CPU (Línea de Ejecución)", padding=6)
        timeline_frame.grid(row=2, column=0, sticky="nsew")

        timeline_container = tb.Frame(timeline_frame)
        timeline_container.pack(fill="both", expand=True)
        timeline_container.rowconfigure(0, weight=1)
        timeline_container.columnconfigure(0, weight=1)

        self.timeline_canvas = tk.Canvas(timeline_container, height=115, bg="#0f1720", highlightthickness=0)
        t_scroll = tb.Scrollbar(timeline_container, orient="horizontal", command=self.timeline_canvas.xview)
        self.timeline_canvas.configure(xscrollcommand=t_scroll.set)
        self.timeline_canvas.grid(row=0, column=0, sticky="nsew")
        t_scroll.grid(row=1, column=0, sticky="ew")

    def _build_console_panel(self, parent: tk.Misc) -> None:
        self.console_text = tk.Text(parent, height=16, bg="#0f1720", fg="#dce6f2", insertbackground="#dce6f2", relief="flat")
        self.console_text.pack(fill="both", expand=True)
        self.console_text.configure(state="disabled")

    def _build_stats_panel(self, parent: tk.Misc) -> None:
        # Two side-by-side columns: Espera | Ejecucion
        cols_frame = tb.Frame(parent)
        cols_frame.pack(fill="both", expand=True, pady=4)
        cols_frame.columnconfigure(0, weight=1)
        cols_frame.columnconfigure(1, weight=1)

        # ---- Tiempo de Espera ----
        left_lf = tb.Labelframe(cols_frame, text="Tiempo de Espera Promedio", padding=10)
        left_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.espera_avg_label = tb.Label(left_lf, text="Promedio → --",
                                         font=("Segoe UI", 11, "bold"), bootstyle="success")
        self.espera_avg_label.pack(anchor="w", pady=(0, 8))
        self.espera_text = tk.Text(
            left_lf, height=20, bg="#0f1720", fg="#dce6f2",
            font=("Consolas", 10), relief="flat", state="disabled",
            insertbackground="#dce6f2", selectbackground="#1e3a5f"
        )
        self.espera_text.pack(fill="both", expand=True)

        # ---- Tiempo de Ejecucion ----
        right_lf = tb.Labelframe(cols_frame, text="Tiempo de Ejecución Promedio", padding=10)
        right_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.ejec_avg_label = tb.Label(right_lf, text="Promedio → --",
                                        font=("Segoe UI", 11, "bold"), bootstyle="info")
        self.ejec_avg_label.pack(anchor="w", pady=(0, 8))
        self.ejec_text = tk.Text(
            right_lf, height=20, bg="#0f1720", fg="#dce6f2",
            font=("Consolas", 10), relief="flat", state="disabled",
            insertbackground="#dce6f2", selectbackground="#1e3a5f"
        )
        self.ejec_text.pack(fill="both", expand=True)

    def run(self) -> None:
        self.root.mainloop()

    def _selected_process(self) -> Process | None:
        selection = self.process_tree.selection()
        if not selection:
            return None
        index = int(selection[0])
        if 0 <= index < len(self.processes):
            return self.processes[index]
        return None

    def _on_left_panel_type_changed(self, event=None) -> None:
        selected_type = self.new_process_fields["type"].get()
        is_priority = is_priority_algorithm(selected_type)
        is_rr = is_round_robin_algorithm(selected_type)

        p_label = self.form_field_labels.get("priority")
        if p_label:
            p_label.configure(foreground="#dce6f2" if is_priority else "#64748b", text="Prioridad *" if is_priority else "Prioridad")
        if not is_priority:
            self.new_process_fields["priority"].set("")

        q_label = self.form_field_labels.get("quantum")
        if q_label:
            q_label.configure(foreground="#dce6f2" if is_rr else "#64748b", text="Quantum *" if is_rr else "Quantum")
        if not is_rr:
            self.new_process_fields["quantum"].set("")

    def add_process(self) -> None:
        dialog = ProcessDialog(self.root, [process.name for process in self.processes])
        if dialog.result is None:
            return
        self.processes.append(dialog.result)
        self._sync_engine()
        if self.processes:
            new_idx = str(len(self.processes) - 1)
            self.process_tree.selection_set(new_idx)
            self._on_tree_select(None)


    def edit_process(self) -> None:
        selected = self._selected_process()
        if selected is None:
            messagebox.showinfo("Editar", "Selecciona un proceso de la tabla.")
            return
        dialog = ProcessDialog(self.root, [process.name for process in self.processes], selected)
        if dialog.result is None:
            return
        index = self.processes.index(selected)
        self.processes[index] = dialog.result
        self._sync_engine()

    def delete_process(self) -> None:
        selected = self._selected_process()
        if selected is None:
            messagebox.showinfo("Eliminar", "Selecciona un proceso de la tabla.")
            return
        self.processes.remove(selected)
        self._sync_engine()

    def new_exercise(self) -> None:
        self.pause_auto()
        self.processes = []
        self.engine.set_processes([])
        self.refresh_all()

    def load_sample(self) -> None:
        self.pause_auto()
        self.processes = [
            Process("P1", 0, [Burst(BurstType.CPU, 4), Burst(BurstType.IO, 2), Burst(BurstType.CPU, 3)], ProcessType.SYSTEM),
            Process("P2", 1, [Burst(BurstType.CPU, 5)], ProcessType.MULTIMEDIA, priority=2),
            Process("P3", 2, [Burst(BurstType.CPU, 6), Burst(BurstType.IO, 3), Burst(BurstType.CPU, 2)], ProcessType.INTERACTIVE, quantum=4),
            Process("P4", 3, [Burst(BurstType.CPU, 7)], ProcessType.BATCH),
        ]
        self._sync_engine()

    def _sync_engine(self) -> None:
        self.engine.set_processes(self.processes)
        self.refresh_all()

    def start_auto(self) -> None:
        if not self.processes:
            messagebox.showinfo("Simulación", "Primero agrega procesos.")
            return
        if self.engine.finished:
            self.reset_simulation()
        self.auto_running = True
        self._schedule_next_step()

    def _schedule_next_step(self) -> None:
        if not self.auto_running:
            return
        if self.engine.finished:
            self.auto_running = False
            return
        self.engine.step()
        self.refresh_all()
        if not self.engine.finished:
            self.timer_id = self.root.after(self.step_delay_ms.get(), self._schedule_next_step)
        else:
            self.auto_running = False
            messagebox.showinfo("Simulación", "¡Simulación finalizada!")

    def pause_auto(self) -> None:
        self.auto_running = False
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def resume_auto(self) -> None:
        if not self.processes:
            return
        self.auto_running = True
        self._schedule_next_step()

    def reset_simulation(self) -> None:
        self.pause_auto()
        self.engine.set_processes(self.processes)
        self.refresh_all()


    def refresh_all(self) -> None:
        self._refresh_table()
        self._refresh_gantt()
        self._refresh_stats()
        self._refresh_console()

    def _refresh_table(self) -> None:
        for item in self.process_tree.get_children():
            self.process_tree.delete(item)
        for index, process in enumerate(self.processes):
            values = process_summary_values(process)
            self.process_tree.insert("", "end", iid=str(index), values=values)

    def _refresh_queues(self) -> None:
        for queue_index, controls in self.queue_boxes.items():
            lane = controls["lane"]
            order_label = controls["order"]
            sequence_label = controls["sequence"]
            members = controls["members"]

            for child in list(lane.winfo_children()):
                child.destroy()
            for child in list(members.winfo_children()):
                child.destroy()

            snapshot = self.engine.queue_snapshot(queue_index)

            order_parts: list[str] = []
            if self.engine.current_process is not None and self.engine.current_queue == queue_index:
                p = self.engine.current_process
                p_str = f" CPU:  {p.name} (P:{p.priority})" if p.priority is not None else f" CPU:  {p.name}"
                order_parts.append(p_str)
            
            queue_parts: list[str] = []
            for idx_p, process in enumerate(snapshot, start=1):
                p_str = f"#{idx_p} {process.name} (P:{process.priority})" if process.priority is not None else f"#{idx_p} {process.name}"
                queue_parts.append(p_str)

            if queue_parts:
                order_parts.append("Cola: [" + ", ".join(queue_parts) + "]")

            if order_parts:
                order_label.configure(text="Estado actual: " + " | ".join(order_parts), foreground="#dce6f2")
            else:
                order_label.configure(text="Estado actual: (vacía)", foreground="#9fb0c2")

            # 1. Proceso ejecutándose actualmente en CPU (distinto visualmente)
            if self.engine.current_process is not None and self.engine.current_queue == queue_index:
                running = self.engine.current_process
                card = tb.Frame(lane, width=135, height=64)
                card.pack_propagate(False)
                card.pack(side="left", padx=4, pady=2)

                tb.Label(
                    card,
                    text=" EN CPU",
                    font=("Segoe UI", 8, "bold"),
                    background="#0284c7",
                    foreground="#ffffff",
                    anchor="center",
                ).pack(fill="x")

                tb.Label(
                    card,
                    text=f"▶ {running.name}",
                    font=("Segoe UI", 10, "bold"),
                    background=self.engine.process_color(running.name),
                    foreground="#ffffff",
                    anchor="center",
                ).pack(fill="both", expand=True)

                prio_txt = f"P:{running.priority} | " if running.priority is not None else ""
                tb.Label(
                    card,
                    text=f"{prio_txt}Rest: {running.remaining_in_burst}",
                    font=("Segoe UI", 8),
                    background="#0f1720",
                    foreground="#9fb0c2",
                    anchor="center",
                ).pack(fill="x")

            # 2. Procesos esperando en la Cola de Listos (numerados 1), 2), 3)...)
            for idx, process in enumerate(snapshot, start=1):
                card = tb.Frame(lane, width=130, height=64)
                card.pack_propagate(False)
                card.pack(side="left", padx=4, pady=2)

                if process.priority is not None:
                    tb.Label(
                        card,
                        text=f"★ PRIORIDAD: {process.priority}",
                        font=("Segoe UI", 8, "bold"),
                        background="#1e293b",
                        foreground="#38bdf8",
                        anchor="center",
                    ).pack(fill="x")

                tb.Label(
                    card,
                    text=f"Cola #{idx}: {process.name}",
                    font=("Segoe UI", 10, "bold"),
                    background=self.engine.process_color(process.name),
                    foreground="#ffffff",
                    anchor="center",
                ).pack(fill="both", expand=True)

                tb.Label(
                    card,
                    text=f"CPU rest: {process.remaining_in_burst} u.t.",
                    font=("Segoe UI", 8),
                    background="#0f1720",
                    foreground="#9fb0c2",
                    anchor="center",
                ).pack(fill="x")

            if not snapshot and not (self.engine.current_process is not None and self.engine.current_queue == queue_index):
                tb.Label(lane, text="(sin procesos en esta cola)", foreground="#9fb0c2").pack(anchor="w")

          
            queue_members = [
                process for process in self.processes
                if process.queue_index == queue_index
                and process.state not in (ProcessState.RUNNING, ProcessState.BLOCKED, ProcessState.FINISHED)
            ]
            for pos, process in enumerate(queue_members, start=1):
                mem_text = f"{pos}. {process.name} (P:{process.priority})" if process.priority is not None else f"{pos}. {process.name}"
                chip = tb.Label(
                    members,
                    text=mem_text,
                    padding=(8, 3),
                    background=self.engine.process_color(process.name),
                    foreground="#ffffff",
                )
                chip.grid(row=(pos - 1) // 4, column=(pos - 1) % 4, padx=4, pady=3, sticky="w")

            sequence = self.engine.queue_history(queue_index)
            sequence_label.configure(text=" -> ".join(sequence) if sequence else "-")

        for child in list(self.io_lane.winfo_children()):
            child.destroy()
        for child in list(self.io_members.winfo_children()):
            child.destroy()

        blocked_items = self.engine.io_snapshot()

        if blocked_items:
            names = [f"{proc.name} ({rem} u.t.)" for proc, rem in blocked_items]
            self.io_order_label.configure(text="Orden actual en E/S: " + " | ".join(names), foreground="#dce6f2")
        else:
            self.io_order_label.configure(text="Orden actual en E/S: (vacía)", foreground="#9fb0c2")

        for idx, (process, remaining) in enumerate(blocked_items, start=1):
            card = tb.Frame(self.io_lane, width=135, height=64)
            card.pack_propagate(False)
            card.pack(side="left", padx=4, pady=2)

            tb.Label(
                card,
                text=f"{idx}) ❖ {process.name}",
                font=("Segoe UI", 10, "bold"),
                background=self.engine.process_color(process.name),
                foreground="#ffffff",
                anchor="center",
            ).pack(fill="both", expand=True)

            tb.Label(
                card,
                text=f"E/S rest: {remaining} u.t.",
                font=("Segoe UI", 8),
                background="#0f1720",
                foreground="#9fb0c2",
                anchor="center",
            ).pack(fill="x")

        if not blocked_items:
            tb.Label(self.io_lane, text="(sin procesos ejecutando E/S actualmente)", foreground="#9fb0c2").pack(anchor="w")

        io_history = self.engine.io_history()
        self.io_sequence_label.configure(text=" -> ".join(io_history) if io_history else "-")

        io_processes = [p for p in self.processes if p.io_count() > 0]
        for pos, process in enumerate(io_processes, start=1):
            chip = tb.Label(
                self.io_members,
                text=f"{pos}. {process.name}",
                padding=(8, 3),
                background=STATE_COLORS.get(process.state, "#3b82f6"),
                foreground="#ffffff",
            )
            chip.grid(row=(pos - 1) // 4, column=(pos - 1) % 4, padx=4, pady=3, sticky="w")

    def _refresh_gantt(self) -> None:
        for canvas in (self.algo_canvas, self.io_canvas, self.timeline_canvas):
            canvas.delete("all")

        cpu_segments  = self.engine.queue_entry_segments
        io_segments   = self.engine.io_segments
        process_by_name = {p.name: p for p in self.processes}

        # ──────────────────────────────────────────────────────────────
        # 1. HISTORIAL POR ALGORITMO 
        #
        #  Todos los algoritmos (SJF, Prioridades, RR, FCFS) dibujan sus
        #  bloques de forma CONSECUTIVA y SECUENCIAL desde el inicio (start_x),
        #  sin líneas de tiempo verticales ni espacios en blanco.
        #  En Round Robin, cada quantum ejecutado se muestra como un bloque
        #  independiente consecutivo ([P3 4ut] [P3 2ut] [P3 2ut]).
        # ──────────────────────────────────────────────────────────────
        queue_names = {0: "SJF", 1: "Prioridades", 2: "RR", 3: "FCFS"}
        row_h    = 95     # altura total por fila
        box_w    = 64     # ancho del bloque
        box_h    = 44     # alto del bloque
        box_gap  = 10     # hueco entre bloques
        label_x  = 10
        start_x  = 155
        max_right = start_x

        cpu_proc  = self.engine.current_process
        cpu_queue = self.engine.current_queue
        blocked_names = {item.process.name for item in self.engine.blocked}

        for q_idx in range(4):
            y_top     = 10 + q_idx * row_h
            y_box_top = y_top + 22
            q_name    = queue_names[q_idx]

            # Etiqueta del algoritmo
            self.algo_canvas.create_text(
                label_x, y_box_top + box_h // 2, anchor="w",
                fill="#38bdf8", font=("Segoe UI", 11, "bold"),
                text=f"{q_name}  ➔"
            )

            # Obtener segmentos ejecutados para esta cola
            q_segs = [s for s in cpu_segments if s.queue_index == q_idx]
            waiting_snap = self.engine.queue_snapshot(q_idx)

            block_index = 0
            if not q_segs and not waiting_snap and not (cpu_proc is not None and cpu_queue == q_idx):
                self.algo_canvas.create_text(
                    start_x, y_box_top + box_h // 2, anchor="w",
                    fill="#64748b", font=("Segoe UI", 9, "italic"),
                    text="(ningún proceso ha ingresado a esta cola)"
                )
                continue

            # ----------------------------------------------------------------
            # For SJF (queue 0):
            # block (cada proceso aparece una sola vez).
            # ----------------------------------------------------------------
            if q_idx == 0:
              
                seg_lookup: dict[tuple[str, int], object] = {}
                for seg in q_segs:
                    key = (seg.process_name, getattr(seg, 'burst_index', 0))
                    seg_lookup[key] = seg

                drawn_keys: set[tuple[str, int]] = set()
                ordered_segs = []
                for (qi, pname, bidx) in self.engine.queue_ready_order:
                    if qi != 0:
                        continue
                    key = (pname, bidx)
                    if key in drawn_keys:
                        continue
                    drawn_keys.add(key)
                    if key in seg_lookup:
                        ordered_segs.append(seg_lookup[key])

                for seg in q_segs:
                    key = (seg.process_name, getattr(seg, 'burst_index', 0))
                    if key not in drawn_keys:
                        drawn_keys.add(key)
                        ordered_segs.append(seg)

                segs_to_draw = ordered_segs
            elif q_idx == 2:
                # RR: cada ronda de quantum = 1 bloque (individual, sin fusionar)
                segs_to_draw = q_segs
            else:
                # Prioridades (1) & FCFS (3): aggregate by (name, burst_index)
                # Misma rafaga (desalojo) -> se fusiona en 1 bloque
                # Distinta rafaga (retorno E/S) -> bloque separado
                burst_totals: dict[tuple[str, int], int] = {}
                for seg in q_segs:
                    key = (seg.process_name, seg.burst_index)
                    burst_totals[key] = burst_totals.get(key, 0) + seg.duration
              
                seen_keys: set[tuple[str, int]] = set()
                merged_segs: list[ExecutionSegment] = []
                for seg in q_segs:
                    key = (seg.process_name, seg.burst_index)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        total_dur = burst_totals[key]
                        merged_segs.append(ExecutionSegment(
                            seg.process_name, 0, total_dur,
                            queue_index=seg.queue_index,
                            priority=seg.priority,
                            burst_index=seg.burst_index,
                            info_value=seg.info_value,
                        ))
                segs_to_draw = merged_segs

            for seg in segs_to_draw:
                proc = process_by_name.get(seg.process_name)
                color = self.engine.process_color(seg.process_name)
                dur = seg.end - seg.start
                x1  = start_x + block_index * (box_w + box_gap)
                x2  = x1 + box_w
                cx  = (x1 + x2) / 2

                is_active = (cpu_proc is not None and cpu_queue == q_idx and cpu_proc.name == seg.process_name and seg is segs_to_draw[-1])
                outline_c = "#38bdf8" if is_active else "#0f1720"
                outline_w = 3 if is_active else 1.5

                if is_active:
                    self.algo_canvas.create_text(
                        cx, y_box_top - 5, anchor="s",
                        text="▶ CPU", fill="#38bdf8", font=("Segoe UI", 8, "bold")
                    )

                # Número de prioridad arriba (solo cola 1 - Prioridades)
                if q_idx == 1 and seg.priority is not None:
                    self.algo_canvas.create_text(
                        cx, y_box_top - 2, anchor="s",
                        text=str(seg.priority), fill="#38bdf8",
                        font=("Segoe UI", 8, "bold")
                    )

                self.algo_canvas.create_rectangle(
                    x1, y_box_top, x2, y_box_top + box_h,
                    fill=color, outline=outline_c, width=outline_w
                )
                self.algo_canvas.create_text(
                    cx, y_box_top + box_h // 2,
                    text=seg.process_name, fill="#ffffff", font=("Segoe UI", 10, "bold")
                )

                # Valor fijo debajo del bloque (info_value del segmento)
                if seg.info_value > 0:
                    self.algo_canvas.create_text(
                        cx, y_box_top + box_h + 2, anchor="n",
                        text=str(seg.info_value), fill="#dce6f2",
                        font=("Segoe UI", 8)
                        )

                max_right = max(max_right, x2 + 20)
                block_index += 1

        algo_w = max(900, max_right + 40)
        algo_h = 10 + 4 * row_h + 30
        self.algo_canvas.configure(scrollregion=(0, 0, algo_w, algo_h))


        # ---- 2. DIAGRAMA DE E/S ----
        box_offset_x = 40
        box_width = 54
        box_gap_io = 8

        if not io_segments:
            self.io_canvas.create_text(20, 20, anchor="nw", fill="#9fb0c2", text="Sin operaciones de Entrada/Salida en ejecución.")
        else:
            for idx, segment in enumerate(io_segments):
                x1 = box_offset_x + idx * (box_width + box_gap_io)
                x2 = x1 + box_width
                duration = segment.end - segment.start
                exit_time = segment.end

                io_color = self.engine.process_color(segment.process_name)
                self.io_canvas.create_rectangle(x1, 10, x2, 38, fill=io_color, outline="#0f1720", width=1.5)
                self.io_canvas.create_text((x1 + x2) / 2, 24, text=segment.process_name, fill="#ffffff", font=("Segoe UI", 10, "bold"))

                self.io_canvas.create_line(x1, 8, x1, 76, fill="#475569")
                self.io_canvas.create_line(x2, 8, x2, 76, fill="#475569")

                self.io_canvas.create_text((x1 + x2) / 2, 47, text=str(duration), fill="#dce6f2", font=("Segoe UI", 9, "bold"))

                cx = (x1 + x2) / 2
                cy = 66
                r = 10
                self.io_canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#38bdf8", width=1.5)
                self.io_canvas.create_text(cx, cy, text=str(exit_time), fill="#38bdf8", font=("Segoe UI", 9, "bold"))

            io_width = max(800, box_offset_x + len(io_segments) * (box_width + box_gap_io) + 60)
            self.io_canvas.configure(scrollregion=(0, 0, io_width, 95))

        # ---- 3. CPU LÍNEA DE EJECUCIÓN (cronológica, eje del tiempo) ----
        tl_segments = self.engine.cpu_timeline_segments
        if not tl_segments:
            self.timeline_canvas.create_text(20, 20, anchor="nw", fill="#9fb0c2", text="La línea de ejecución de CPU se mostrará aquí.")
        else:
            unit_width = 55
            offset_x_cpu = 160

            for i, segment in enumerate(tl_segments):
                x1 = offset_x_cpu + segment.start * unit_width
                is_last = (i == len(tl_segments) - 1)
                # Dejar 2px de separacion entre bloques para que se vea el limite
                x2 = offset_x_cpu + segment.end * unit_width - (0 if is_last else 2)
                color = self.engine.process_color(segment.process_name)
                self.timeline_canvas.create_rectangle(x1, 10, x2, 40, fill=color, outline="#0f1720", width=1.5)
                self.timeline_canvas.create_text((x1 + x2) / 2, 25, text=segment.process_name, fill="#ffffff", font=("Segoe UI", 10, "bold"))

            # Ticks solo al INICIO de cada segmento + final del ultimo
            cpu_boundary_times = sorted(set([0] + [s.start for s in tl_segments] + [tl_segments[-1].end]))
            last_x = -100
            alt_toggle = False

            for tick in cpu_boundary_times:
                x = offset_x_cpu + tick * unit_width
                self.timeline_canvas.create_line(x, 8, x, 42, fill="#475569", width=1.5)

                if x - last_x < 34:
                    alt_toggle = not alt_toggle
                else:
                    alt_toggle = False

                text_y = 74 if alt_toggle else 58
                if alt_toggle:
                    self.timeline_canvas.create_line(x, 42, x, 66, fill="#334155", dash=(2, 2))

                self.timeline_canvas.create_text(x, text_y, text=str(tick), fill="#ffffff", font=("Segoe UI", 10, "bold"))
                last_x = x

            max_time_cpu = max(s.end for s in tl_segments)
            timeline_width = max(800, offset_x_cpu + max_time_cpu * unit_width + 80)
            self.timeline_canvas.configure(scrollregion=(0, 0, timeline_width, 100))

    def _refresh_algo_history(self) -> None:
        self._refresh_gantt()

    def _refresh_console(self) -> None:
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", tk.END)
        self.console_text.insert(tk.END, "\n".join(self.engine.log_lines))
        self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")

    def append_console(self, events: list[str]) -> None:
        if not events:
            return
        self.console_text.configure(state="normal")
        for event in events:
            self.console_text.insert(tk.END, event + "\n")
        self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")

    def _refresh_stats(self) -> None:
        stats = self.engine.statistics()
        per = stats.get("per_process", {})

        espera_lines: list[str] = []
        ejec_lines: list[str] = []
        sum_espera = 0
        sum_ejec = 0
        count = 0

        for pname, data in per.items():
            llegada   = data["llegada"]
            tfinal    = data["finalizacion"]
            cpu_total = data["cpu_total"]
            io_total  = data["io_total"]

            te  = tfinal - llegada                      # Tiempo Ejecucion
            tep = tfinal - llegada - cpu_total - io_total  # Tiempo Espera

            sum_ejec   += te
            sum_espera += tep
            count      += 1

            # Formato
            ejec_lines.append(
                f"  ( {tfinal} - {llegada} )  =  {te}"
            )
            espera_lines.append(
                f"  ( {tfinal} - {llegada} - {cpu_total} - {io_total} )  =  {tep}"
            )

        if count > 0:
            prom_ejec   = sum_ejec   / count
            prom_espera = sum_espera / count
        else:
            prom_ejec = prom_espera = 0.0

        # Actualizar Tiempo Ejecucion
        ejec_footer = f"\n  {sum_ejec} / {count}  =  {prom_ejec:.1f} ms"
        self.ejec_avg_label.configure(text=f"Promedio → {prom_ejec:.1f} ms")
        self.ejec_text.configure(state="normal")
        self.ejec_text.delete("1.0", tk.END)
        self.ejec_text.insert(tk.END, "\n".join(ejec_lines) + ejec_footer)
        self.ejec_text.configure(state="disabled")

        # Actualizar Tiempo Espera
        espera_footer = f"\n  {sum_espera} / {count}  =  {prom_espera:.1f} ms"
        self.espera_avg_label.configure(text=f"Promedio → {prom_espera:.1f} ms")
        self.espera_text.configure(state="normal")
        self.espera_text.delete("1.0", tk.END)
        self.espera_text.insert(tk.END, "\n".join(espera_lines) + espera_footer)
        self.espera_text.configure(state="disabled")

    def _on_tree_select(self, event: tk.Event) -> None:
        selected = self._selected_process()
        if selected is None:
            return
        self.new_process_fields["name"].set(selected.name)
        self.new_process_fields["arrival"].set(str(selected.arrival_time))
        self.new_process_fields["cpu"].set(str(selected.cpu_total()))
        self.new_process_fields["priority"].set("" if selected.priority is None else str(selected.priority))
        self.new_process_fields["quantum"].set("" if selected.quantum is None else str(selected.quantum))
        io_ops = selected.io_operation_points()
        io_durs = selected.io_durations()
        self.new_process_fields["io_ops"].set("-".join(str(v) for v in io_ops))
        self.new_process_fields["io_dur"].set("-".join(str(v) for v in io_durs))
        self.new_process_fields["type"].set(process_type_display_label(selected.process_type))
        self._on_left_panel_type_changed()



def run_app() -> None:
    MainWindow().run()
