"""Entry point. See ``brayton_cycle/cli.py`` for options and exit codes.

    python main.py --case B
    python main.py --help
"""

from __future__ import annotations

from brayton_cycle.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
