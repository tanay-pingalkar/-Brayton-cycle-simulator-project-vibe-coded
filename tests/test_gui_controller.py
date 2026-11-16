"""GUI controller tests: parsing, error mapping, solve round-trip. No display needed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from matplotlib.figure import Figure

from brayton_cycle.core.exceptions import (
    BackendUnavailable,
    ConservationError,
    CycleClosureError,
    SecondLawViolation,
)
from brayton_cycle.gui.controller import (
    FIELDS,
    MODES,
    PROVIDERS,
    ErrorInfo,
    GuiController,
    GuiInputError,
    map_error,
)
from brayton_cycle.solver import BraytonConfig, BraytonSolver

ROOT = Path(__file__).resolve().parents[1]
REF_B = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))[
    "cases"]["B_irreversible_variable_cp"]["expected"]
VAR = "Variable cp (Table A-2c)"
T3_MODE, F_MODE = "Target T3", "Fuel-air ratio f"


@pytest.fixture
def ctl() -> GuiController:
    return GuiController()


def test_controller_module_has_no_tkinter() -> None:
    import brayton_cycle.gui.controller as c

    assert "tkinter" not in sys.modules or not hasattr(c, "tk")
    assert "import tkinter" not in Path(c.__file__).read_text(encoding="utf-8")


# ------------------------------------------------------------------ parsing
def test_defaults_are_case_B_in_display_units(ctl: GuiController) -> None:
    d = ctl.defaults()
    assert d["P1"] == "101.325" and d["lhv"] == "43" and d["pressure_ratio"] == "14"
    assert set(d) == {f.key for f in FIELDS}


def test_parse_converts_display_units_to_si(ctl: GuiController) -> None:
    cfg = ctl.parse(ctl.defaults(), VAR, T3_MODE)
    assert cfg == BraytonConfig.from_reference_case("B").replace(name="GUI case")
    assert cfg.P1 == 101325.0 and cfg.lhv == 43.0e6 and cfg.provider == "variable-cp"


def test_parse_accepts_comma_decimal_and_whitespace(ctl: GuiController) -> None:
    cfg = ctl.parse(dict(ctl.defaults(), eta_c=" 0,85 "), VAR, T3_MODE)
    assert cfg.eta_c == 0.85


def test_mode_toggle_selects_T3_or_f(ctl: GuiController) -> None:
    assert "fuel_air_ratio" not in ctl.enabled_fields(T3_MODE)
    assert "T3" not in ctl.enabled_fields(F_MODE)
    cfg = ctl.parse(dict(ctl.defaults(), T3="not used"), VAR, F_MODE)
    assert cfg.combustor_mode == "fuel_air_ratio" and cfg.T3 is None


@pytest.mark.parametrize(("key", "text", "fragment"), [
    ("eta_c", "", "is empty"),
    ("eta_c", "abc", "must be a number"),
    ("pressure_ratio", "0.8", "pressure_ratio must be > 1"),
    ("eta_t", "1.2", "0 < eta_t <= 1"),
    ("dp_comb", "1", "0 <= dp_comb < 1"),
    ("mass_flow", "-3", "mass_flow must be > 0"),
])
def test_parse_errors_name_the_field(ctl: GuiController, key: str, text: str, fragment: str) -> None:
    with pytest.raises(GuiInputError, match=fragment) as exc:
        ctl.parse(dict(ctl.defaults(), **{key: text}), VAR, T3_MODE)
    assert exc.value.field == key


def test_unknown_mode_rejected(ctl: GuiController) -> None:
    with pytest.raises(GuiInputError):
        ctl.parse(ctl.defaults(), VAR, "warp drive")


def test_all_provider_labels_map_to_known_backends() -> None:
    assert set(PROVIDERS.values()) == {"variable", "constant", "coolprop", "cantera"}
    assert set(MODES.values()) == {"target_T3", "fuel_air_ratio"}


# ------------------------------------------------------------- error mapping
@pytest.mark.parametrize(("exc", "kind", "title"), [
    (GuiInputError("T1", "bad"), "input", "Invalid input"),
    (ConservationError("residual"), "conservation", "Conservation check failed"),
    (SecondLawViolation("s_gen < 0"), "conservation", "Conservation check failed"),
    (BackendUnavailable("pip install CoolProp"), "backend", "Property backend not installed"),
    (CycleClosureError("T4 <= T1"), "calculation", "Calculation error"),
    (ValueError("T = 2500 K outside validity range"), "range", "Outside property range"),
    (RuntimeError("boom"), "internal", "Unexpected error"),
])
def test_map_error(exc: Exception, kind: str, title: str) -> None:
    info = map_error(exc)
    assert isinstance(info, ErrorInfo) and info.kind == kind and info.title == title
    assert str(exc) in info.message


def test_input_error_keeps_field(ctl: GuiController) -> None:
    out = ctl.run(dict(ctl.defaults(), T1="cold"), VAR, T3_MODE)
    assert not out.ok and out.error is not None and out.error.field == "T1"


def test_run_maps_conservation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = GuiController(solver=BraytonSolver(residual_tol=0.0))
    out = ctl.run(ctl.defaults(), VAR, T3_MODE, make_figures=False)
    assert not out.ok and out.error is not None and out.error.kind == "conservation"


def test_run_maps_missing_backend(ctl: GuiController, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "cantera", None)
    out = ctl.run(ctl.defaults(), "Cantera (optional)", T3_MODE, make_figures=False)
    assert out.error is not None and out.error.kind == "backend"


def test_run_maps_property_range_error(ctl: GuiController) -> None:
    out = ctl.run(dict(ctl.defaults(), T3="2500"), VAR, T3_MODE, make_figures=False)
    assert out.error is not None and out.error.kind == "range"


# ---------------------------------------------------------------- round-trip
def test_solve_round_trip_matches_reference(ctl: GuiController) -> None:
    out = ctl.run(ctl.defaults(), VAR, T3_MODE)
    assert out.ok and out.result is not None
    assert out.result.w_net == pytest.approx(REF_B["w_net"], rel=1e-8)
    assert [r[0] for r in out.station_rows] == ["1", "2s", "2", "3", "4s", "4"]
    assert dict(out.kpi_rows)["Thermal efficiency"] == "37.315 %"
    assert set(out.figures) == {"T-s", "P-v", "Energy audit"}
    assert all(isinstance(f, Figure) for f in out.figures.values())
    assert "37.315 %" in out.summary and ctl.last_result is out.result


def test_fuel_air_ratio_mode_round_trip(ctl: GuiController) -> None:
    values = dict(ctl.defaults(), fuel_air_ratio=repr(REF_B["fuel_air_ratio"]))
    out = ctl.run(values, VAR, F_MODE, make_figures=False)
    assert out.ok and out.result is not None
    assert out.result.states["3"].T == pytest.approx(1500.0, abs=1e-6)


def test_sweep_outcome(ctl: GuiController) -> None:
    out = ctl.sweep(ctl.defaults(), VAR, T3_MODE, "2", "40", "12")
    assert out.ok and len(out.table) == 12 and isinstance(out.figure, Figure)
    assert [r[0] for r in out.optimum_rows] == ["w_net", "eta_th"]
    assert float(out.optimum_rows[0][1]) == pytest.approx(13.8466, rel=1e-3)


@pytest.mark.parametrize(("lo", "hi", "n"), [("5", "3", "10"), ("0.5", "10", "10"),
                                             ("2", "40", "1"), ("2", "x", "10")])
def test_sweep_rejects_bad_range(ctl: GuiController, lo: str, hi: str, n: str) -> None:
    out = ctl.sweep(ctl.defaults(), VAR, T3_MODE, lo, hi, n)
    assert not out.ok and out.error is not None and out.error.kind == "input"


def test_export_requires_a_run(ctl: GuiController, tmp_path: Path) -> None:
    out = ctl.export_report(tmp_path)
    assert not out.ok and out.error is not None and out.error.title == "Nothing to export"


def test_export_writes_reports(ctl: GuiController, tmp_path: Path) -> None:
    assert ctl.run(ctl.defaults(), VAR, T3_MODE, make_figures=False).ok
    out = ctl.export_report(tmp_path, figures=False)
    assert out.ok and set(out.paths) == {"json", "markdown"}
    assert json.loads(Path(out.paths["json"]).read_text(encoding="utf-8"))["provider"] == "variable-cp"
