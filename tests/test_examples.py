"""The README demo script runs end to end (REQ-D01)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script_runs(tmp_path: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(ROOT), MPLBACKEND="Agg")
    proc = subprocess.run([sys.executable, str(ROOT / "examples" / "demo.py")], cwd=tmp_path,
                          env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "eta_th = 37.31%" in proc.stdout and "best r_p = 37.7" in proc.stdout
    assert (tmp_path / "demo_output" / "report.md").exists()


def test_demo_is_ten_lines() -> None:
    lines = [ln for ln in (ROOT / "examples" / "demo.py").read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    assert len(lines) == 10
