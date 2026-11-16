"""Parametric sweeps and optimal pressure ratio (REQ-A01).

``ParametricSweepEngine`` provides:
    * ``sweep_1d``      any numeric config field;
    * ``sweep_rp``      1-D pressure-ratio sweep (default 30 points);
    * ``sweep_2d``      coarse r_p x T3 grid (default 12 x 8), long format;
    * ``optimal_pressure_ratio``  maximise w_net or eta_th with
      ``scipy.optimize.minimize_scalar(method="bounded")``.

Infeasible points (``InputValidationError``, e.g. T3 <= T2 at very high r_p, or
``CycleClosureError``, e.g. T4 <= T1) are kept as rows with ``status`` = the message and NaN KPIs. Audit failures
(``ConservationError``, ``SecondLawViolation``) are never caught: they are bugs,
not infeasible designs.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from brayton_cycle.core.exceptions import CycleClosureError, InputValidationError
from brayton_cycle.solver import BraytonConfig, BraytonResult, BraytonSolver

#: Config fields that may be swept (numeric cycle inputs).
SWEEPABLE: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(BraytonConfig)
    if f.name not in {"combustor_mode", "provider", "provider_options", "name"}
)
KPI_COLUMNS: tuple[str, ...] = ("w_net", "eta_th", "bwr", "fuel_air_ratio", "sfc_kg_per_kWh",
                                "net_power_W", "first_law_residual", "s_gen_total")
Objective = Literal["w_net", "eta_th"]

DEFAULT_RP_RANGE: tuple[float, float] = (2.0, 40.0)
DEFAULT_T3_RANGE: tuple[float, float] = (1100.0, 1700.0)  # inside Table A-2c validity [1]
DEFAULT_OPT_BOUNDS: tuple[float, float] = (1.05, 60.0)
#: Exceptions that mark a design point as physically infeasible (not a bug).
INFEASIBLE: tuple[type[Exception], ...] = (InputValidationError, CycleClosureError)
#: Points of the coarse, geometrically spaced pre-scan used to bracket the optimum.
_SCAN_POINTS: int = 41


@dataclass(frozen=True)
class OptimumResult:
    """Outcome of an optimal-r_p search.

    Attributes:
        objective: "w_net" [J/kg] or "eta_th" [-].
        pressure_ratio: Optimal r_p.
        value: Objective value at the optimum.
        result: Full solved cycle at the optimum.
        bounds: Search interval for r_p.
        at_bound: True if the optimum sits within xatol of a bound, so the
            maximum may lie outside the interval (typical for eta_th of the ideal cycle).
        n_evaluations: Number of cycle solves used.
        converged: scipy's success flag.
    """

    objective: str
    pressure_ratio: float
    value: float
    result: BraytonResult
    bounds: tuple[float, float]
    at_bound: bool
    n_evaluations: int
    converged: bool


class ParametricSweepEngine:
    """Sweeps and optimisation over ``BraytonConfig`` (stateless apart from the solver)."""

    def __init__(self, solver: BraytonSolver | None = None) -> None:
        self.solver = solver or BraytonSolver()

    # ------------------------------------------------------------- 1-D
    def sweep_1d(self, config: BraytonConfig, parameter: str,
                 values: Iterable[float]) -> pd.DataFrame:
        """Solve once per value; columns [parameter, *KPI_COLUMNS, "status"] (SI).

        Args:
            config: Cycle configuration (SI units).
            parameter: Name of the ``BraytonConfig`` field to vary.
            values: Values to assign to the swept field.

        Returns:
            DataFrame with columns [parameter, *KPI_COLUMNS, "status"] (SI).
        """
        if parameter not in SWEEPABLE:
            raise InputValidationError(f"cannot sweep {parameter!r}; choose from {sorted(SWEEPABLE)}")
        rows = [self._row(config, {parameter: float(v)}) for v in values]
        return pd.DataFrame(rows, columns=[parameter, *KPI_COLUMNS, "status"])

    def sweep_rp(self, config: BraytonConfig, rp_min: float = DEFAULT_RP_RANGE[0],
                 rp_max: float = DEFAULT_RP_RANGE[1], n: int = 30) -> pd.DataFrame:
        """1-D pressure-ratio sweep with ``n`` evenly spaced points.

        Args:
            config: Cycle configuration (SI units).
            rp_min: Lowest pressure ratio.
            rp_max: Highest pressure ratio.
            n: Number of evenly spaced points.

        Returns:
            DataFrame with columns ["pressure_ratio", *KPI_COLUMNS, "status"].
        """
        return self.sweep_1d(config, "pressure_ratio", np.linspace(rp_min, rp_max, n))

    # ------------------------------------------------------------- 2-D
    def sweep_2d(self, config: BraytonConfig, rp_values: Sequence[float] | None = None,
                 T3_values: Sequence[float] | None = None) -> pd.DataFrame:
        """r_p x T3 grid (default 12 x 8), long format: one row per (r_p, T3).

        The combustor is run in target-T3 mode for every point, whatever the
        mode of ``config``.

        Args:
            config: Cycle configuration (SI units).
            rp_values: Pressure ratios of the grid (default: 12 points over 2-40).
            T3_values: Turbine inlet temperatures of the grid [K] (default: 8 points over 1100-1700 K).

        Returns:
            Long-format DataFrame ["pressure_ratio", "T3", *KPI_COLUMNS, "status"].
        """
        rps = np.linspace(*DEFAULT_RP_RANGE, 12) if rp_values is None else rp_values
        T3s = np.linspace(*DEFAULT_T3_RANGE, 8) if T3_values is None else T3_values
        base = config.replace(combustor_mode="target_T3", fuel_air_ratio=None,
                              T3=float(T3s[0]))
        rows = [self._row(base, {"pressure_ratio": float(rp), "T3": float(T3)})
                for T3 in T3s for rp in rps]
        return pd.DataFrame(rows, columns=["pressure_ratio", "T3", *KPI_COLUMNS, "status"])

    # ------------------------------------------------------------ optimum
    def optimal_pressure_ratio(self, config: BraytonConfig, objective: Objective = "w_net",
                               bounds: tuple[float, float] = DEFAULT_OPT_BOUNDS,
                               xatol: float = 1e-5) -> OptimumResult:
        """Maximise ``objective`` over r_p in ``bounds``.

        A 41-point geometric scan brackets the best feasible point, then
        ``minimize_scalar(method="bounded")`` refines inside that bracket.
        Raises ``InputValidationError`` if no r_p in ``bounds`` is feasible.

        Args:
            config: Cycle configuration (SI units).
            objective: ``"w_net"`` or ``"eta_th"``.
            bounds: Search interval (lo, hi) for r_p, with 1 < lo < hi.
            xatol: Absolute tolerance on r_p for the bounded Brent refinement.

        Returns:
            ``OptimumResult`` with the optimal r_p, value and solved cycle.

        Raises:
            InputValidationError: bad objective/bounds, or no feasible r_p.
        """
        if objective not in ("w_net", "eta_th"):
            raise InputValidationError(f"objective must be 'w_net' or 'eta_th', got {objective!r}")
        lo, hi = bounds
        if not 1.0 < lo < hi:
            raise InputValidationError(f"bounds must satisfy 1 < lo < hi, got {bounds}")
        count = [0]

        def value(rp: float) -> float:
            count[0] += 1
            try:
                return float(getattr(self.solver.solve(config.replace(pressure_ratio=rp)), objective))
            except INFEASIBLE:
                return -np.inf

        # 1) coarse scan: robust to infeasible regions and flat penalties
        grid = np.geomspace(lo, hi, _SCAN_POINTS)
        scan = np.array([value(float(rp)) for rp in grid])
        if not np.isfinite(scan).any():
            raise InputValidationError(f"no feasible pressure ratio in {bounds}")
        i = int(np.nanargmax(scan))
        a, b = float(grid[max(i - 1, 0)]), float(grid[min(i + 1, len(grid) - 1)])
        # 2) bounded Brent refinement inside the bracketing grid cell
        def neg(rp: float) -> float:
            v = value(rp)
            return -v if np.isfinite(v) else 1e30

        res = minimize_scalar(neg, bounds=(a, b), method="bounded",
                              options={"xatol": xatol, "maxiter": 500})
        rp_opt = float(res.x) if value(float(res.x)) >= scan[i] else float(grid[i])
        best = self.solver.solve(config.replace(pressure_ratio=rp_opt))
        return OptimumResult(
            objective=objective, pressure_ratio=rp_opt, value=float(getattr(best, objective)),
            result=best, bounds=(lo, hi),
            at_bound=min(rp_opt - lo, hi - rp_opt) <= 10 * xatol * max(1.0, rp_opt),
            n_evaluations=count[0] + 1, converged=bool(res.success),
        )

    # ------------------------------------------------------------ helpers
    def _row(self, config: BraytonConfig, changes: dict[str, float]) -> dict[str, object]:
        row: dict[str, object] = dict(changes)
        try:
            k = self.solver.solve(config.replace(**changes)).kpis
            row.update({c: k[c] for c in KPI_COLUMNS}, status="ok")
        except INFEASIBLE as exc:
            row.update({c: float("nan") for c in KPI_COLUMNS}, status=f"infeasible: {exc}")
        return row


def sweep_1d(config: BraytonConfig, parameter: str, values: Iterable[float],
             solver: BraytonSolver | None = None) -> pd.DataFrame:
    """Functional shortcut for ``ParametricSweepEngine(solver).sweep_1d`` (kept from Day 4).

    Args:
        config: Cycle configuration (SI units).
        parameter: Name of the ``BraytonConfig`` field to vary.
        values: Values to assign to the swept field.
        solver: Solver to use (a default ``BraytonSolver`` if None).

    Returns:
        Same as ``ParametricSweepEngine.sweep_1d``.
    """
    return ParametricSweepEngine(solver).sweep_1d(config, parameter, values)
