"""Documentation checks (REQ-D01): docstrings and constant citations."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "brayton_cycle"
REFS = (ROOT / "docs" / "references.md").read_text(encoding="utf-8")
CONST_SRC = (PKG / "core" / "constants.py").read_text(encoding="utf-8")

#: Constants that are numerical requirements or unit definitions, not physical data.
NON_PHYSICAL = {"FIRST_LAW_RESIDUAL_TOL": "REQ-N01", "S_GEN_TOL": "REQ-T02",
                "J_PER_KWH": "Definitional"}


def _constants() -> list[tuple[str, str]]:
    body = ast.parse(CONST_SRC).body
    out = []
    for i, node in enumerate(body):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nxt = body[i + 1] if i + 1 < len(body) else None
            doc = (nxt.value.value if isinstance(nxt, ast.Expr) and isinstance(nxt.value, ast.Constant)
                   else "")
            out.append((node.target.id, str(doc)))
    return out


@pytest.mark.parametrize(("name", "doc"), _constants(), ids=lambda v: v if len(v) < 40 else "")
def test_constant_reference_tag_resolves(name: str, doc: str) -> None:
    """Every constant cites [n] present in references.md, or is a flagged/non-physical value."""
    tags = re.findall(r"\[(\d+)\]", doc)
    if name in NON_PHYSICAL:
        assert NON_PHYSICAL[name] in doc, name
        return
    if tags:
        for t in tags:
            assert re.search(rf"^\[{t}\] ", REFS, re.MULTILINE), f"{name}: [{t}] not in references.md"
    else:
        assert "[FLAG:" in doc, f"{name}: no reference tag and not flagged"
        assert name in REFS, f"{name}: flagged but missing from the flagged-values table"
    if "[FLAG" in doc:
        assert name in REFS or name.endswith("_DEFAULT"), \
            f"{name}: flagged but missing from the flagged-values table"


def test_constants_found() -> None:
    assert len(_constants()) >= 20


# ----------------------------------------------------------------- docstrings
def _public_callables() -> list[tuple[str, ast.AST]]:
    out: list[tuple[str, ast.AST]] = []
    for f in sorted(PKG.rglob("*.py")):
        if f.name.startswith("_") and f.name != "__init__.py":
            continue  # private helper modules
        tree = ast.parse(f.read_text(encoding="utf-8"))

        def visit(node: ast.AST, prefix: str) -> None:
            for n in ast.iter_child_nodes(node):
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
                    out.append((f"{f.relative_to(ROOT)}::{prefix}{n.name}", n))
                    if isinstance(n, ast.ClassDef):
                        visit(n, prefix + n.name + ".")

        visit(tree, "")
    return out


CALLABLES = _public_callables()


def test_every_module_has_docstring() -> None:
    missing = [str(f.relative_to(ROOT)) for f in PKG.rglob("*.py")
               if not ast.get_docstring(ast.parse(f.read_text(encoding="utf-8")))]
    assert not missing, missing


def test_every_public_callable_has_docstring() -> None:
    missing = [q for q, n in CALLABLES if not ast.get_docstring(n)]
    assert not missing, missing


def test_google_style_args_sections() -> None:
    """Public functions with parameters document them in an ``Args:`` section.

    Exemptions: overrides that point to the documented base method ("See ``...``"),
    and properties.
    """
    offenders = []
    for q, n in CALLABLES:
        if not isinstance(n, ast.FunctionDef):
            continue
        doc = ast.get_docstring(n) or ""
        params = [a.arg for a in n.args.args + n.args.kwonlyargs if a.arg not in ("self", "cls")]
        is_property = any(isinstance(d, ast.Name) and d.id == "property" for d in n.decorator_list)
        if params and not is_property and "Args:" not in doc and "See ``" not in doc:
            offenders.append(q)
            continue
        if "Args:" in doc:
            for p in params:
                if not re.search(rf"^\s+{re.escape(p)}( \(.*\))?:", doc, re.MULTILINE):
                    offenders.append(f"{q} (param {p!r} undocumented)")
    assert not offenders, offenders


def test_docs_exist() -> None:
    for name in ("README.md", "docs/architecture.md", "docs/user_guide.md",
                 "docs/validation_report.md", "docs/physics_formulation.md", "docs/references.md"):
        assert (ROOT / name).is_file(), name


def test_architecture_examples_run() -> None:
    """The worked examples in docs/architecture.md execute and behave as described."""
    from brayton_cycle.properties import VariableCpProvider, unregister_provider
    from brayton_cycle.solver import BraytonConfig, BraytonSolver

    md = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", md, re.S)
    assert len(blocks) == 3
    ns: dict = {}
    try:
        exec(blocks[0], ns)  # registers "nasa-n2"
        r = BraytonSolver().solve(BraytonConfig(T1=300, P1=101325, pressure_ratio=4, T3=950,
                                                provider="nasa-n2"))
        assert r.first_law_residual < 1e-6
        assert ns["NasaN2Provider"]().cp(300.0) == pytest.approx(1039.7, rel=2e-3)
    finally:
        unregister_provider("nasa-n2")
    ns2: dict = {}
    exec(blocks[2], ns2)
    gas = VariableCpProvider()
    res = ns2["Intercooler"](gas, 300.0, 0.8, 0.02).process(gas.state(450.0, 4e5, "1a"))
    assert res.outlet.T == pytest.approx(330.0) and res.heat < 0 < res.s_gen
    assert res.energy_residual == pytest.approx(0.0, abs=1e-9)


def test_rtm_test_names_exist() -> None:
    """Every ``test_x.py::test_name`` cited in the traceability matrix exists."""
    brief = (ROOT / "PROJECT_BRIEF.md").read_text(encoding="utf-8")
    rtm = brief[brief.index("## 5. Requirements Traceability Matrix"):]
    cited = set(re.findall(r"(test_\w+\.py)::(test_\w+)", rtm))
    assert len(cited) >= 30
    missing = []
    for fname, test in sorted(cited):
        src = (ROOT / "tests" / fname).read_text(encoding="utf-8")
        if not re.search(rf"^def {test}\(", src, re.MULTILINE):
            missing.append(f"{fname}::{test}")
    assert not missing, missing
    for req in ("F01", "F02", "T01", "T02", "N01", "N02", "A01", "R01", "U01", "E01", "V01", "D01"):
        assert f"| REQ-{req} |" in rtm, req
