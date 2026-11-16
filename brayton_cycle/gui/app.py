"""Tkinter view (MVC "V"): layout and event binding only.

All parsing, solving, plotting and error mapping happen in
``gui.controller.GuiController``. This module never imports the solver,
components or properties (enforced by tests/test_architecture.py).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from brayton_cycle.gui.controller import ErrorInfo, GuiController

PLOT_TABS: tuple[str, ...] = ("T-s", "P-v", "Energy audit", "Sweep")


class BraytonApp:
    """Single-window Brayton cycle GUI."""

    def __init__(self, root: tk.Tk, controller: GuiController | None = None) -> None:
        self.root = root
        self.ctl = controller or GuiController()
        root.title("Brayton Cycle Simulator")
        root.minsize(1100, 680)
        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.canvases: dict[str, FigureCanvasTkAgg] = {}
        self.provider = tk.StringVar(value=next(iter(self.ctl.providers)))
        self.mode = tk.StringVar(value=next(iter(self.ctl.modes)))
        self.sweep_vars = {k: tk.StringVar(value=v)
                           for k, v in (("rp_min", "2"), ("rp_max", "40"), ("points", "30"))}
        self.status = tk.StringVar(value="Enter inputs and press Run.")

        main = ttk.Frame(root, padding=8)
        main.pack(fill="both", expand=True)
        self._build_inputs(main)
        self._build_outputs(main)
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 2)).pack(fill="x")
        self._on_mode_change()

    # ------------------------------------------------------------ layout
    def _build_inputs(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="Inputs", padding=8)
        box.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(box, text="Property backend").grid(row=0, column=0, sticky="w")
        ttk.Combobox(box, textvariable=self.provider, values=list(self.ctl.providers),
                     state="readonly", width=24).grid(row=0, column=1, columnspan=2, sticky="ew")
        ttk.Label(box, text="Combustor mode").grid(row=1, column=0, sticky="w", pady=(6, 0))
        for i, label in enumerate(self.ctl.modes):
            ttk.Radiobutton(box, text=label, value=label, variable=self.mode,
                            command=self._on_mode_change).grid(row=2 + i, column=1,
                                                               columnspan=2, sticky="w")
        defaults = self.ctl.defaults()
        row = 4
        for spec in self.ctl.fields:
            row += 1
            self.vars[spec.key] = tk.StringVar(value=defaults.get(spec.key, ""))
            ttk.Label(box, text=spec.label).grid(row=row, column=0, sticky="w", pady=1)
            entry = ttk.Entry(box, textvariable=self.vars[spec.key], width=12)
            entry.grid(row=row, column=1, sticky="ew", pady=1)
            ttk.Label(box, text=spec.unit, foreground="#52514e").grid(row=row, column=2, sticky="w")
            self.entries[spec.key] = entry
        buttons = ttk.Frame(box)
        buttons.grid(row=row + 1, column=0, columnspan=3, pady=(10, 4), sticky="ew")
        ttk.Button(buttons, text="Run", command=self._on_run).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="Sweep", command=self._on_sweep).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="Export report",
                   command=self._on_export).pack(side="left", expand=True, fill="x")
        sweep = ttk.LabelFrame(box, text="Sweep r_p", padding=4)
        sweep.grid(row=row + 2, column=0, columnspan=3, sticky="ew")
        for i, (key, label) in enumerate((("rp_min", "min"), ("rp_max", "max"),
                                          ("points", "points"))):
            ttk.Label(sweep, text=label).grid(row=0, column=2 * i, padx=(4, 2))
            ttk.Entry(sweep, textvariable=self.sweep_vars[key], width=6).grid(row=0, column=2 * i + 1)

    def _build_outputs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(side="left", fill="both", expand=True)
        results = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(results, text="Results")
        self.states_tree = self._tree(results, ("Station", "T [K]", "P [kPa]", "h [kJ/kg]",
                                                "s [kJ/(kg·K)]"), height=7)
        self.kpi_tree = self._tree(results, ("Quantity", "Value"), height=12)
        self.opt_tree = self._tree(results, ("Objective", "r_p,opt", "Value", "Note"), height=3)
        self.plot_frames: dict[str, ttk.Frame] = {}
        for name in PLOT_TABS:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=name)
            self.plot_frames[name] = frame

    @staticmethod
    def _tree(parent: ttk.Frame, columns: tuple[str, ...], height: int) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor="e" if col != columns[0] else "w", width=130)
        tree.pack(fill="x", pady=4)
        return tree

    # ------------------------------------------------------------ helpers
    def _values(self) -> dict[str, str]:
        return {k: v.get() for k, v in self.vars.items()}

    @staticmethod
    def _fill(tree: ttk.Treeview, rows: list[tuple[str, ...]]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=row)

    def _show_figure(self, tab: str, fig: object) -> None:
        frame = self.plot_frames[tab]
        for child in frame.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        toolbar = NavigationToolbar2Tk(canvas, frame, pack_toolbar=False)
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()
        self.canvases[tab] = canvas

    def _show_error(self, info: ErrorInfo) -> None:
        messagebox.showerror(info.title, info.message, parent=self.root)
        self.status.set(f"{info.title}.")
        if info.field in self.entries:
            self.entries[info.field].focus_set()
            self.entries[info.field].select_range(0, "end")

    # ------------------------------------------------------------ events
    def _on_mode_change(self) -> None:
        enabled = self.ctl.enabled_fields(self.mode.get())
        for key, entry in self.entries.items():
            entry.state(["!disabled"] if key in enabled else ["disabled"])

    def _on_run(self) -> None:
        out = self.ctl.run(self._values(), self.provider.get(), self.mode.get())
        if not out.ok:
            self._show_error(out.error)  # type: ignore[arg-type]
            return
        self._fill(self.states_tree, out.station_rows)
        self._fill(self.kpi_tree, out.kpi_rows)
        for tab, fig in out.figures.items():
            self._show_figure(tab, fig)
        self.notebook.select(0)
        self.status.set(out.summary)

    def _on_sweep(self) -> None:
        sv = {k: v.get() for k, v in self.sweep_vars.items()}
        out = self.ctl.sweep(self._values(), self.provider.get(), self.mode.get(),
                             sv["rp_min"], sv["rp_max"], sv["points"])
        if not out.ok:
            self._show_error(out.error)  # type: ignore[arg-type]
            return
        self._fill(self.opt_tree, out.optimum_rows)
        self._show_figure("Sweep", out.figure)
        self.notebook.select(len(PLOT_TABS))
        self.status.set(out.summary)

    def _on_export(self) -> None:
        if self.ctl.last_result is None:
            self._show_error(ErrorInfo("Nothing to export", "Run a case first.", "input"))
            return
        folder = filedialog.askdirectory(parent=self.root, title="Export report to folder")
        if not folder:
            return
        out = self.ctl.export_report(folder)
        if not out.ok:
            self._show_error(out.error)  # type: ignore[arg-type]
            return
        messagebox.showinfo("Report exported", "\n".join(out.paths.values()), parent=self.root)
        self.status.set(f"Report written to {folder}")


def launch() -> None:
    """Create the main window and run the Tk event loop."""
    root = tk.Tk()
    BraytonApp(root)
    root.mainloop()
