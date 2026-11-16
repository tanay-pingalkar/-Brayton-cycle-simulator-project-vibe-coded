"""CLI tests (REQ-U01): in-process via main(argv) plus one real subprocess."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from brayton_cycle.cli import EXIT_AUDIT, EXIT_BACKEND, EXIT_INPUT, EXIT_OK, EXIT_USAGE, main
from brayton_cycle.solver import BraytonConfig, BraytonSolver

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))["cases"]


def run(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    code = main(list(argv), out=buf)
    return code, buf.getvalue()


def test_single_case_B_table() -> None:
    code, text = run("--case", "B")
    assert code == EXIT_OK
    assert "Thermal efficiency     37.315 %" in text
    assert "variable-cp" in text and "2s" in text


def test_output_dir_writes_json(tmp_path: Path) -> None:
    code, _ = run("--case", "A", "--provider", "constant", "--output-dir", str(tmp_path))
    assert code == EXIT_OK
    d = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert d["kpis"]["eta_th"] == pytest.approx(REF["A_ideal_cold_air"]["expected"]["eta_th"], rel=1e-9)


def test_config_file(tmp_path: Path) -> None:
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"T1": 300, "P1": 101325, "rp": 8, "T3": 1300,
                               "eta_c": 0.85, "eta_t": 0.9, "provider": "variable"}),
                   encoding="utf-8")
    code, text = run("--config", str(cfg))
    assert code == EXIT_OK and "Net work" in text


def test_sweep_mode_writes_csv(tmp_path: Path) -> None:
    code, text = run("--case", "B", "--mode", "sweep", "--sweep-start", "2",
                     "--sweep-stop", "30", "--sweep-num", "8", "--output-dir", str(tmp_path))
    assert code == EXIT_OK and "pressure_ratio" in text
    df = pd.read_csv(tmp_path / "sweep.csv")
    assert len(df) == 8 and (df["status"] == "ok").all()


def test_sweep_marks_infeasible_points() -> None:
    # Case A: T3 = 1400 K; above r_p ~ 219 the compressor exit exceeds T3 -> infeasible, not a crash
    code, text = run("--case", "A", "--mode", "sweep", "--sweep-start", "10",
                     "--sweep-stop", "400", "--sweep-num", "4")
    assert code == EXIT_OK and "infeasible" in text


@pytest.mark.parametrize("argv", [
    ("--case", "Z"),
    ("--config", "does_not_exist.json"),
    ("--case", "B", "--mode", "sweep", "--sweep-param", "provider"),
])
def test_invalid_input_exit_code(argv: tuple[str, ...]) -> None:
    assert run(*argv)[0] == EXIT_INPUT


def test_validation_failure_in_config(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"T1": 300, "P1": 101325, "rp": 8, "T3": 1300, "eta_c": 1.2}),
                   encoding="utf-8")
    assert run("--config", str(cfg))[0] == EXIT_INPUT


def test_conservation_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    orig = BraytonSolver.__init__
    monkeypatch.setattr(BraytonSolver, "__init__",
                        lambda self, provider=None, residual_tol=0.0: orig(self, provider, 0.0))
    code, _ = run("--case", "B")
    assert code == EXIT_AUDIT


def test_missing_backend_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "cantera", None)
    assert run("--case", "B", "--provider", "cantera")[0] == EXIT_BACKEND


def test_provider_override_drops_foreign_options() -> None:
    assert run("--case", "A", "--provider", "variable")[0] == EXIT_OK


def test_gui_flag_launches_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    import brayton_cycle.gui as gui

    calls: list[bool] = []
    monkeypatch.setattr(gui, "launch", lambda: calls.append(True))
    assert run("--gui")[0] == EXIT_OK and calls == [True]


def test_gui_flag_without_tk_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    import brayton_cycle.gui as gui

    def no_tk() -> None:
        raise ImportError("No module named 'tkinter'")

    monkeypatch.setattr(gui, "launch", no_tk)
    assert run("--gui")[0] == EXIT_USAGE


def test_plots_flag_writes_figures_and_reports(tmp_path: Path) -> None:
    code, _ = run("--case", "B", "--output-dir", str(tmp_path), "--plots")
    assert code == EXIT_OK
    for name in ("result.json", "report.json", "report.md", "ts.png", "pv.png",
                 "energy_audit.png"):
        assert (tmp_path / name).exists(), name
    code, text = run("--case", "B", "--mode", "sweep", "--sweep-num", "6",
                     "--output-dir", str(tmp_path), "--plots")
    assert code == EXIT_OK and (tmp_path / "sweep.png").exists()
    assert "optimal r_p for w_net" in text


def test_usage_error_from_argparse() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--provider", "unobtainium"])
    assert exc.value.code == EXIT_USAGE


def test_subprocess_main_py() -> None:
    proc = subprocess.run([sys.executable, str(ROOT / "main.py"), "--case", "B"],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "First-Law residual" in proc.stdout


def test_subprocess_nonzero_on_bad_input() -> None:
    proc = subprocess.run([sys.executable, str(ROOT / "main.py"), "--case", "nope"],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == EXIT_INPUT and "INVALID INPUT" in proc.stderr


def test_reference_case_alias_matches_full_name() -> None:
    assert BraytonConfig.from_reference_case("b") == BraytonConfig.from_reference_case(
        "B_irreversible_variable_cp")
