"""Static architecture checks: layering, MVC, and no thermodynamics in gui/.

The GUI scanner is itself tested against known-bad and known-good snippets,
so it cannot silently pass because of a broken rule.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "brayton_cycle"
GUI_FILES = sorted((PKG / "gui").glob("*.py"))

# ----------------------------------------------------------------- GUI rules
FORBIDDEN_GUI_IMPORTS: tuple[str, ...] = (
    "brayton_cycle.components", "brayton_cycle.properties", "brayton_cycle.core.constants",
    "math", "cmath", "numpy", "scipy", "CoolProp", "cantera",
)
#: Identifiers that indicate thermodynamic quantities when used in arithmetic.
THERMO_IDENT = re.compile(
    r"^(cp|cv|gamma|k|R|R_AIR|R_u|R_UNIVERSAL|rho|h\d?s?|s\d?s?|u\d?|v\d?|T\d?s?|P\d?s?|"
    r"eta(_\w+)?|w(_\w+)?|q(_\w+)?|rp|r_p|pressure_ratio|lhv|LHV|f|far|fuel_air_ratio|"
    r"mdot|m_dot|mass_flow|enthalpy|entropy|temperature|pressure|s_gen\w*|bwr|sfc\w*|"
    r"dh\w*|ds\w*|dT\w*|dp\w*|work\w*|heat\w*)$"
)
MATH_FUNCS = frozenset({"log", "log10", "log2", "exp", "sqrt", "ln", "power", "pow"})
ARITH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)


def _names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def find_thermo_violations(source: str) -> list[str]:
    """Return human-readable violations of the 'no thermodynamics in gui/' rule."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        else:
            mods = []
        for m in mods:
            if any(m == bad or m.startswith(bad + ".") for bad in FORBIDDEN_GUI_IMPORTS):
                problems.append(f"line {node.lineno}: forbidden import {m}")
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Pow):
            problems.append(f"line {node.lineno}: power operator")
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ARITH_OPS):
            hits = sorted(x for x in _names(node) if THERMO_IDENT.match(x))
            if hits:
                problems.append(f"line {node.lineno}: arithmetic on thermodynamic names {hits}")
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if name in MATH_FUNCS:
                problems.append(f"line {node.lineno}: math function {name}()")
    return problems


@pytest.mark.parametrize("snippet", [
    "w_c = cp * (T2 - T1)",
    "eta = 1 - rp ** (-0.4 / 1.4)",
    "x = self.result.h3 - self.result.h2",
    "s = cp * log(T / 298.15)",
    "import math",
    "from brayton_cycle.properties import VariableCpProvider",
    "from brayton_cycle.components import Compressor",
    "import numpy as np",
    "total += heat_rate",
])
def test_scanner_detects_thermodynamics(snippet: str) -> None:
    assert find_thermo_violations(snippet), snippet


@pytest.mark.parametrize("snippet", [
    "x = value * self.scale",
    "row = row + 1",
    "label = f'{name}: {text}'",
    "from brayton_cycle.solver import BraytonConfig",
])
def test_scanner_accepts_presentation_code(snippet: str) -> None:
    assert not find_thermo_violations(snippet), snippet


@pytest.mark.parametrize("path", GUI_FILES, ids=lambda p: p.name)
def test_gui_has_no_thermodynamics(path: Path) -> None:
    assert find_thermo_violations(path.read_text(encoding="utf-8")) == []


def test_gui_view_talks_only_to_controller() -> None:
    """MVC: app.py imports tkinter/matplotlib and gui.controller, nothing else from the package."""
    tree = ast.parse((PKG / "gui" / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("brayton_cycle"):
            assert node.module == "brayton_cycle.gui.controller", node.module


def test_gui_files_exist() -> None:
    assert {p.name for p in GUI_FILES} >= {"__init__.py", "app.py", "controller.py"}


# ------------------------------------------------------------ package layering
#: Allowed direction: core <- properties <- components <- solver <- analysis
#: <- reporting <- {cli, gui}; extensibility depends on core only.
LAYER_FORBIDS: dict[str, tuple[str, ...]] = {
    "core": ("properties", "components", "solver", "analysis", "reporting", "gui",
             "extensibility", "cli"),
    "properties": ("components", "solver", "analysis", "reporting", "gui", "cli"),
    "components": ("properties", "solver", "analysis", "reporting", "gui", "cli"),
    "solver": ("analysis", "reporting", "gui", "cli"),
    "analysis": ("reporting", "gui", "cli"),
    "reporting": ("gui", "cli"),
    "extensibility": ("properties", "components", "solver", "analysis", "reporting", "gui", "cli"),
}


def _package_imports(path: Path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
    return {m.split(".")[1] for m in mods if m.startswith("brayton_cycle.") and m.count(".") >= 1}


@pytest.mark.parametrize("layer", sorted(LAYER_FORBIDS))
def test_layering(layer: str) -> None:
    for f in (PKG / layer).glob("*.py"):
        bad = _package_imports(f) & set(LAYER_FORBIDS[layer])
        assert not bad, f"{layer}/{f.name} imports upper layer(s) {sorted(bad)}"
