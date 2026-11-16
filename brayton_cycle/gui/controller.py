"""GUI controller (MVC "C"): widget strings in, display-ready results out.

Has no tkinter import, so it is fully testable without a display. It contains
no thermodynamics: it parses text, builds a ``BraytonConfig``, calls the
solver / sweep engine / plotter / report generator, and packages the answers
into immutable outcome objects for the view. Every exception becomes an
``ErrorInfo`` with a friendly title and message.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure

from brayton_cycle.analysis import ParametricSweepEngine
from brayton_cycle.core.exceptions import (
    BackendUnavailable,
    BraytonError,
    ConservationError,
    InputValidationError,
    SecondLawViolation,
)
from brayton_cycle.reporting import (
    STATION_HEADERS,
    CyclePlotter,
    ReportGenerator,
    kpi_rows,
    optimum_rows,
    station_rows,
)
from brayton_cycle.solver import BraytonConfig, BraytonResult, BraytonSolver


# ------------------------------------------------------------------ inputs
@dataclass(frozen=True)
class InputField:
    """One numeric entry: config key, label, display unit, display -> SI factor."""

    key: str
    label: str
    unit: str
    scale: float = 1.0

    def to_si(self, value: float) -> float:
        """Convert a display-unit value to SI.

        Args:
            value: Value in display units.

        Returns:
            Value in SI units.
        """
        return value * self.scale

    def from_si(self, value: float) -> float:
        """Convert an SI value to display units.

        Args:
            value: Value in SI units.

        Returns:
            Value in display units.
        """
        return value / self.scale


FIELDS: tuple[InputField, ...] = (
    InputField("P1", "Inlet pressure P1", "kPa", 1e3),
    InputField("T1", "Inlet temperature T1", "K"),
    InputField("pressure_ratio", "Pressure ratio r_p", "-"),
    InputField("T3", "Turbine inlet T3", "K"),
    InputField("fuel_air_ratio", "Fuel-air ratio f", "-"),
    InputField("eta_c", "Compressor η_c", "-"),
    InputField("eta_t", "Turbine η_t", "-"),
    InputField("eta_comb", "Combustion η_comb", "-"),
    InputField("dp_comb", "Combustor loss ΔP/P2", "-"),
    InputField("mass_flow", "Mass flow ṁ", "kg/s"),
    InputField("lhv", "Fuel LHV", "MJ/kg", 1e6),
)
FIELD_BY_KEY: dict[str, InputField] = {f.key: f for f in FIELDS}

#: Display label -> provider name accepted by BraytonConfig.
PROVIDERS: dict[str, str] = {"Variable cp (Table A-2c)": "variable",
                             "Constant cp (cold air)": "constant",
                             "CoolProp (optional)": "coolprop",
                             "Cantera (optional)": "cantera"}
#: Display label -> combustor mode.
MODES: dict[str, str] = {"Target T3": "target_T3", "Fuel-air ratio f": "fuel_air_ratio"}
#: Fields disabled in each combustor mode.
_MODE_EXCLUDES: dict[str, str] = {"target_T3": "fuel_air_ratio", "fuel_air_ratio": "T3"}
DEFAULT_FUEL_AIR_RATIO = "0.0228"  # about Case B's value, for the mode toggle


class GuiInputError(InputValidationError):
    """A specific entry could not be parsed; ``field`` names the config key."""

    def __init__(self, field_key: str | None, message: str) -> None:
        super().__init__(message)
        self.field = field_key


# ------------------------------------------------------------------ outcomes
@dataclass(frozen=True)
class ErrorInfo:
    """Friendly error description for a dialog."""

    title: str
    message: str
    kind: str  # "input" | "conservation" | "backend" | "range" | "calculation" | "internal"
    field: str | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Result of a single solve, ready for display."""

    ok: bool
    error: ErrorInfo | None = None
    result: BraytonResult | None = None
    station_headers: tuple[str, ...] = STATION_HEADERS
    station_rows: list[tuple[str, ...]] = field(default_factory=list)
    kpi_rows: list[tuple[str, str]] = field(default_factory=list)
    figures: dict[str, Figure] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class SweepOutcome:
    """Result of a pressure-ratio sweep plus optimum search."""

    ok: bool
    error: ErrorInfo | None = None
    table: Any = None  # pandas.DataFrame
    figure: Figure | None = None
    optimum_rows: list[tuple[str, str, str, str]] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class ExportOutcome:
    """Paths written by a report export."""

    ok: bool
    error: ErrorInfo | None = None
    paths: dict[str, str] = field(default_factory=dict)


def map_error(exc: BaseException) -> ErrorInfo:
    """Translate any exception into a user-facing ``ErrorInfo``.

    Args:
        exc: Any exception raised while handling a GUI action.

    Returns:
        ``ErrorInfo`` for a dialog.
    """
    if isinstance(exc, GuiInputError):
        return ErrorInfo("Invalid input", str(exc), "input", exc.field)
    if isinstance(exc, InputValidationError):
        return ErrorInfo("Invalid input", str(exc), "input")
    if isinstance(exc, (ConservationError, SecondLawViolation)):
        return ErrorInfo("Conservation check failed",
                         f"{exc}\n\nThe result was rejected because an energy, mass or "
                         "entropy audit failed. Please report this case.", "conservation")
    if isinstance(exc, BackendUnavailable):
        return ErrorInfo("Property backend not installed", str(exc), "backend")
    if isinstance(exc, BraytonError):
        return ErrorInfo("Calculation error", str(exc), "calculation")
    if isinstance(exc, ValueError):  # e.g. a backend's temperature validity range
        return ErrorInfo("Outside property range",
                         f"{exc}\n\nTry temperatures inside the backend's validity range "
                         "or choose another property backend.", "range")
    return ErrorInfo("Unexpected error", f"{type(exc).__name__}: {exc}", "internal")


# ------------------------------------------------------------------ controller
class GuiController:
    """Mediates between the Tkinter view and the simulation API."""

    fields = FIELDS
    providers = PROVIDERS
    modes = MODES

    def __init__(self, solver: BraytonSolver | None = None,
                 plotter: CyclePlotter | None = None,
                 reporter: ReportGenerator | None = None) -> None:
        self.solver = solver or BraytonSolver()
        self.engine = ParametricSweepEngine(self.solver)
        self.plotter = plotter or CyclePlotter()
        self.reporter = reporter or ReportGenerator()
        self.last_result: BraytonResult | None = None

    # --------------------------------------------------------- defaults
    def defaults(self) -> dict[str, str]:
        """Initial entry texts (display units), from reference Case B when available."""
        try:
            cfg = BraytonConfig.from_reference_case("B")
        except (OSError, BraytonError):
            cfg = BraytonConfig(T1=288.15, P1=101325.0, pressure_ratio=14.0, T3=1500.0,
                                eta_c=0.86, eta_t=0.89, eta_comb=0.99, dp_comb=0.03,
                                lhv=43.0e6, mass_flow=25.0)
        out = {f.key: f"{f.from_si(getattr(cfg, f.key)):g}" for f in FIELDS
               if getattr(cfg, f.key) is not None}
        out.setdefault("fuel_air_ratio", DEFAULT_FUEL_AIR_RATIO)
        return out

    def enabled_fields(self, mode: str) -> set[str]:
        """Entry keys that should be editable in ``mode`` (label or value).

        Args:
            mode: Combustor mode (display label or value).

        Returns:
            Set of config keys.
        """
        excluded = _MODE_EXCLUDES[MODES.get(mode, mode)]
        return {f.key for f in FIELDS if f.key != excluded}

    # --------------------------------------------------------- parsing
    def parse(self, values: Mapping[str, str], provider: str, mode: str) -> BraytonConfig:
        """Turn entry texts into a validated ``BraytonConfig`` (raises GuiInputError).

        Args:
            values: Entry key -> text, in display units.
            provider: Property backend (display label or name).
            mode: Combustor mode (display label or value).

        Returns:
            Validated ``BraytonConfig``.

        Raises:
            GuiInputError: an entry is empty, not a number, or out of range.
        """
        mode_value = MODES.get(mode, mode)
        if mode_value not in _MODE_EXCLUDES:
            raise GuiInputError(None, f"Unknown combustor mode {mode!r}.")
        kwargs: dict[str, Any] = {}
        for key in sorted(self.enabled_fields(mode_value)):
            kwargs[key] = self._number(FIELD_BY_KEY[key], values.get(key, ""))
        kwargs.update(combustor_mode=mode_value, provider=PROVIDERS.get(provider, provider),
                      name="GUI case")
        try:
            return BraytonConfig(**kwargs)
        except InputValidationError as exc:
            raise GuiInputError(self._field_in(str(exc)), str(exc)) from exc

    @staticmethod
    def _number(spec: InputField, text: str) -> float:
        raw = str(text).strip().replace(",", ".")
        if not raw:
            raise GuiInputError(spec.key, f"'{spec.label}' is empty.")
        try:
            number = float(raw)
        except ValueError:
            raise GuiInputError(spec.key, f"'{spec.label}' must be a number, got {text!r}.") from None
        return spec.to_si(number)

    @staticmethod
    def _field_in(message: str) -> str | None:
        return next((f.key for f in FIELDS if message.startswith(f.key)), None)

    # --------------------------------------------------------- actions
    def run(self, values: Mapping[str, str], provider: str, mode: str,
            make_figures: bool = True) -> RunOutcome:
        """Solve one cycle; never raises.

        Args:
            values: Entry key -> text, in display units.
            provider: Property backend (display label or name).
            mode: Combustor mode (display label or value).
            make_figures: Also build the T-s, P-v and energy-audit figures.

        Returns:
            ``RunOutcome`` (never raises).
        """
        try:
            result = self.solver.solve(self.parse(values, provider, mode))
            figures = ({"T-s": self.plotter.ts_diagram(result),
                        "P-v": self.plotter.pv_diagram(result),
                        "Energy audit": self.plotter.energy_audit(result)}
                       if make_figures else {})
        except Exception as exc:  # noqa: BLE001 - every error becomes a dialog
            return RunOutcome(ok=False, error=map_error(exc))
        self.last_result = result
        kpis = kpi_rows(result)
        lookup = dict(kpis)
        return RunOutcome(ok=True, result=result, station_rows=station_rows(result),
                          kpi_rows=kpis, figures=figures,
                          summary=(f"Solved with {result.provider_name}: η_th = "
                                   f"{lookup['Thermal efficiency']}, w_net = "
                                   f"{lookup['Net work w_net']}"))

    def sweep(self, values: Mapping[str, str], provider: str, mode: str,
              rp_min: str = "2", rp_max: str = "40", points: str = "30") -> SweepOutcome:
        """1-D r_p sweep and optimal r_p for w_net and eta_th; never raises.

        Args:
            values: Entry key -> text, in display units.
            provider: Property backend (display label or name).
            mode: Combustor mode (display label or value).
            rp_min: Lowest pressure ratio (text).
            rp_max: Highest pressure ratio (text).
            points: Number of sweep points (text).

        Returns:
            ``SweepOutcome`` (never raises).
        """
        try:
            cfg = self.parse(values, provider, mode)
            lo = self._number(InputField("rp_min", "Sweep r_p min", "-"), rp_min)
            hi = self._number(InputField("rp_max", "Sweep r_p max", "-"), rp_max)
            n = int(self._number(InputField("points", "Sweep points", "-"), points))
            if not (1.0 < lo < hi and 2 <= n <= 500):
                raise GuiInputError("rp_min", "Sweep needs 1 < r_p min < r_p max and 2-500 points.")
            table = self.engine.sweep_rp(cfg, lo, hi, n)
            optima = {o: self.engine.optimal_pressure_ratio(cfg, o, bounds=(lo, hi))
                      for o in ("w_net", "eta_th")}
            fig = self.plotter.sweep_1d(table, optima={k: v.pressure_ratio
                                                       for k, v in optima.items()})
        except Exception as exc:  # noqa: BLE001
            return SweepOutcome(ok=False, error=map_error(exc))
        rows = optimum_rows(optima)
        return SweepOutcome(ok=True, table=table, figure=fig, optimum_rows=rows,
                            summary="; ".join(f"optimal r_p ({r[0]}) = {r[1]} → {r[2]}"
                                              for r in rows))

    def export_report(self, out_dir: str | Path, figures: bool = True) -> ExportOutcome:
        """Write JSON/Markdown (and PNG) reports of the last run; never raises.

        Args:
            out_dir: Destination folder.
            figures: Also write PNG figures.

        Returns:
            ``ExportOutcome`` (never raises).
        """
        if self.last_result is None:
            return ExportOutcome(ok=False, error=ErrorInfo(
                "Nothing to export", "Run a case first, then export the report.", "input"))
        try:
            paths = self.reporter.write_all(self.last_result, out_dir, figures=figures)
        except Exception as exc:  # noqa: BLE001
            return ExportOutcome(ok=False, error=map_error(exc))
        return ExportOutcome(ok=True, paths={k: str(v) for k, v in paths.items()})
