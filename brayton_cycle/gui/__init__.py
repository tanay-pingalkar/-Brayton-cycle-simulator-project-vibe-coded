"""Tkinter front end (REQ-U01), MVC split:

    controller.py  GuiController: parses entry text, calls solver/sweep/plotter/report,
                   returns outcome objects, maps errors. No tkinter, no formulas.
    app.py         BraytonApp: layout and event binding only.

Design rule (tests/test_architecture.py): no thermodynamic expressions in gui/,
and no direct imports of components/ or properties/.
Tkinter is imported only when ``launch()`` is called.
"""

from __future__ import annotations


def launch() -> None:
    """Open the GUI. Raises ImportError if this Python has no Tk support."""
    from brayton_cycle.gui.app import launch as _launch

    _launch()


__all__ = ["launch"]
