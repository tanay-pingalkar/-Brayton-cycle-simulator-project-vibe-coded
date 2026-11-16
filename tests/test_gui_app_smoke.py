"""Wiring smoke test for gui/app.py using a stand-in tkinter.

The real Tk is often absent in CI (headless Python builds). Here a fake
``tkinter`` package built from MagicMock plus a working StringVar lets
``BraytonApp`` construct its layout and run its event handlers. That proves the
view's wiring to the controller (Run, Sweep, Export, errors, mode toggle)
without a display. It does not check pixels; launching the real window is a
manual check (``python main.py --gui``).
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest


class FakeVar:
    """Minimal tk.StringVar replacement."""

    def __init__(self, master: object = None, value: str = "") -> None:
        self._v = value

    def get(self) -> str:
        return self._v

    def set(self, value: str) -> None:
        self._v = value


@pytest.fixture
def app_module(monkeypatch: pytest.MonkeyPatch):
    tk = MagicMock(name="tkinter")
    tk.StringVar = FakeVar
    ttk, messagebox, filedialog = MagicMock(), MagicMock(), MagicMock()
    ttk.Entry.side_effect = lambda *a, **k: MagicMock(name="Entry")  # distinct widget per call
    tk.ttk, tk.messagebox, tk.filedialog = ttk, messagebox, filedialog
    backend = types.ModuleType("matplotlib.backends.backend_tkagg")
    backend.FigureCanvasTkAgg = MagicMock(name="FigureCanvasTkAgg")  # type: ignore[attr-defined]
    backend.NavigationToolbar2Tk = MagicMock(name="NavigationToolbar2Tk")  # type: ignore[attr-defined]
    for name, mod in {"tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": messagebox,
                      "tkinter.filedialog": filedialog,
                      "matplotlib.backends.backend_tkagg": backend}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "brayton_cycle.gui.app", raising=False)
    mod = importlib.import_module("brayton_cycle.gui.app")
    yield mod, messagebox, filedialog, backend
    sys.modules.pop("brayton_cycle.gui.app", None)


def test_app_builds_and_runs(app_module) -> None:
    mod, messagebox, _fd, backend = app_module
    app = mod.BraytonApp(MagicMock(name="root"))
    assert set(app.vars) >= {"P1", "T1", "pressure_ratio", "T3", "fuel_air_ratio", "lhv"}
    app._on_run()
    messagebox.showerror.assert_not_called()
    assert set(app.canvases) == {"T-s", "P-v", "Energy audit"}
    assert "37.315 %" in app.status.get()
    assert app.ctl.last_result is not None


def test_app_sweep_fills_sweep_tab(app_module) -> None:
    mod, messagebox, _fd, _b = app_module
    app = mod.BraytonApp(MagicMock())
    app.sweep_vars["points"].set("8")
    app._on_sweep()
    messagebox.showerror.assert_not_called()
    assert "Sweep" in app.canvases and "optimal r_p" in app.status.get()


def test_app_invalid_input_shows_dialog_and_focuses_field(app_module) -> None:
    mod, messagebox, _fd, _b = app_module
    app = mod.BraytonApp(MagicMock())
    app.vars["eta_c"].set("1.7")
    app._on_run()
    title, message = messagebox.showerror.call_args.args
    assert title == "Invalid input" and "eta_c" in message
    app.entries["eta_c"].focus_set.assert_called()


def test_app_export_flow(app_module, tmp_path) -> None:
    mod, messagebox, filedialog, _b = app_module
    app = mod.BraytonApp(MagicMock())
    app._on_export()  # before any run -> friendly error, no folder dialog
    assert messagebox.showerror.call_args.args[0] == "Nothing to export"
    filedialog.askdirectory.assert_not_called()
    app._on_run()
    filedialog.askdirectory.return_value = str(tmp_path)
    app._on_export()
    messagebox.showinfo.assert_called()
    assert (tmp_path / "report.md").exists() and (tmp_path / "ts.png").exists()


def test_app_mode_toggle_disables_other_entry(app_module) -> None:
    mod, _m, _f, _b = app_module
    app = mod.BraytonApp(MagicMock())
    app.mode.set("Fuel-air ratio f")
    app._on_mode_change()
    app.entries["T3"].state.assert_called_with(["disabled"])
    app.entries["fuel_air_ratio"].state.assert_called_with(["!disabled"])
