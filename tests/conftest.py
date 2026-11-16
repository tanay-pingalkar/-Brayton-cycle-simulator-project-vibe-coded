"""Shared pytest configuration: make the repo root importable without install."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
