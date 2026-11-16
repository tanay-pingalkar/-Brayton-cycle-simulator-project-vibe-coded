"""BraytonConfig: immutable, validated description of one cycle case (SI units)."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brayton_cycle.components import CombustorMode
from brayton_cycle.components._validation import (
    optional_positive,
    require_efficiency,
    require_positive,
    require_pressure_loss,
    require_pressure_ratio,
)
from brayton_cycle.core.constants import LHV_KEROSENE
from brayton_cycle.core.exceptions import InputValidationError

#: Default location of the independent reference data (repository checkout).
DEFAULT_REFERENCE_FILE = Path(__file__).resolve().parents[2] / "validation_reference_data.json"

#: Short provider names accepted everywhere (CLI, JSON) -> registry names.
PROVIDER_ALIASES: dict[str, str] = {"constant": "constant-cp", "variable": "variable-cp"}

#: Alternative input keys (reference JSON / user files) -> field names.
_KEY_ALIASES: dict[str, str] = {
    "rp": "pressure_ratio", "r_p": "pressure_ratio", "mdot": "mass_flow",
    "m_dot": "mass_flow", "mode": "combustor_mode", "f": "fuel_air_ratio",
}
#: Keys that are provider options rather than cycle fields.
_PROVIDER_OPTION_KEYS: dict[str, str] = {"cp": "cp", "k": "gamma", "gamma": "gamma"}

#: Reference case short names.
CASE_ALIASES: dict[str, str] = {"A": "A_ideal_cold_air", "B": "B_irreversible_variable_cp"}


@dataclass(frozen=True)
class BraytonConfig:
    """All inputs of one steady-state Brayton cycle.

    Attributes (SI):
        T1 [K], P1 [Pa]: compressor inlet (station 1).
        pressure_ratio: r_p = P2/P1 > 1.
        eta_c, eta_t, eta_comb: efficiencies in (0, 1].
        dp_comb: fractional combustor pressure loss in [0, 1).
        combustor_mode: "target_T3" (needs T3) or "fuel_air_ratio" (needs fuel_air_ratio).
        T3 [K], fuel_air_ratio [-]: exactly one, according to the mode.
        lhv [J/kg]: fuel lower heating value, default kerosene [7].
        mass_flow [kg/s]: air mass flow, default 1 (per-kg results).
        provider: property backend name (registry name or alias "constant"/"variable").
        provider_options: keyword arguments for the backend (e.g. cp, gamma).
        T_source, T_sink [K]: reservoir temperatures for s_gen (defaults T3, T1).
        name: free-text case label.
    """

    T1: float
    P1: float
    pressure_ratio: float
    eta_c: float = 1.0
    eta_t: float = 1.0
    eta_comb: float = 1.0
    dp_comb: float = 0.0
    combustor_mode: str = CombustorMode.TARGET_T3.value
    T3: float | None = None
    fuel_air_ratio: float | None = None
    lhv: float = LHV_KEROSENE
    mass_flow: float = 1.0
    provider: str = "variable-cp"
    provider_options: Mapping[str, Any] = field(default_factory=dict)
    T_source: float | None = None
    T_sink: float | None = None
    name: str = ""

    def __post_init__(self) -> None:
        set_ = lambda k, v: object.__setattr__(self, k, v)  # noqa: E731 (frozen)
        set_("T1", require_positive("T1", self.T1))
        set_("P1", require_positive("P1", self.P1))
        set_("pressure_ratio", require_pressure_ratio("pressure_ratio", self.pressure_ratio))
        for k in ("eta_c", "eta_t", "eta_comb"):
            set_(k, require_efficiency(k, getattr(self, k)))
        set_("dp_comb", require_pressure_loss("dp_comb", self.dp_comb))
        set_("lhv", require_positive("lhv", self.lhv))
        set_("mass_flow", require_positive("mass_flow", self.mass_flow))
        set_("T_source", optional_positive("T_source", self.T_source))
        set_("T_sink", optional_positive("T_sink", self.T_sink))
        try:
            mode = CombustorMode(self.combustor_mode)
        except ValueError:
            raise InputValidationError(
                f"combustor_mode must be one of {[m.value for m in CombustorMode]}, "
                f"got {self.combustor_mode!r}") from None
        set_("combustor_mode", mode.value)
        if mode is CombustorMode.TARGET_T3 and (self.T3 is None or self.fuel_air_ratio is not None):
            raise InputValidationError("combustor_mode 'target_T3' needs T3 and no fuel_air_ratio")
        if mode is CombustorMode.FUEL_AIR_RATIO and (self.fuel_air_ratio is None or self.T3 is not None):
            raise InputValidationError("combustor_mode 'fuel_air_ratio' needs fuel_air_ratio and no T3")
        key = str(self.provider).strip().lower()
        set_("provider", PROVIDER_ALIASES.get(key, key))
        set_("provider_options", dict(self.provider_options))

    # ------------------------------------------------------------ builders
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BraytonConfig:
        """Build from a mapping. Accepts field names plus aliases (rp, mdot, cp, k, ...).

        Args:
            data: Mapping with field names or aliases (rp, mdot, cp, k, mode, f).

        Returns:
            Validated ``BraytonConfig``.

        Raises:
            InputValidationError: unknown key or invalid value.
        """
        fields = {f.name for f in dataclasses.fields(cls)}
        kwargs: dict[str, Any] = {}
        options: dict[str, Any] = dict(data.get("provider_options", {}))
        for raw_key, value in data.items():
            if raw_key == "provider_options":
                continue
            if raw_key in _PROVIDER_OPTION_KEYS:
                options[_PROVIDER_OPTION_KEYS[raw_key]] = value
                continue
            key = _KEY_ALIASES.get(raw_key, raw_key)
            if key not in fields:
                raise InputValidationError(f"unknown configuration key {raw_key!r}")
            kwargs[key] = value
        kwargs["provider_options"] = options
        return cls(**kwargs)

    @classmethod
    def from_json(cls, path: str | Path) -> BraytonConfig:
        """Load a JSON file containing one configuration object.

        Args:
            path: JSON file containing one configuration object.

        Returns:
            Validated ``BraytonConfig``.
        """
        with Path(path).open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @classmethod
    def from_reference_case(cls, case: str,
                            path: str | Path = DEFAULT_REFERENCE_FILE) -> BraytonConfig:
        """Load case ``"A"``/``"B"`` (or its full name) from validation_reference_data.json.

        Args:
            case: ``"A"``, ``"B"`` or a full case name.
            path: Location of validation_reference_data.json.

        Returns:
            Validated ``BraytonConfig`` with the matching backend.
        """
        name = CASE_ALIASES.get(case.upper() if len(case) == 1 else case, case)
        with Path(path).open(encoding="utf-8") as fh:
            cases = json.load(fh)["cases"]
        if name not in cases:
            raise InputValidationError(f"unknown reference case {case!r}; available: {sorted(cases)}")
        entry = cases[name]
        provider = "constant-cp" if entry["property_model"].startswith("constant-cp") else "variable-cp"
        return cls.from_dict({**entry["inputs"], "provider": provider, "name": name})

    # ------------------------------------------------------------- helpers
    def replace(self, **changes: Any) -> BraytonConfig:
        """Return a validated copy with some fields changed (used by sweeps)."""
        return dataclasses.replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable mapping; ``from_dict(to_dict())`` round-trips."""
        d = dataclasses.asdict(self)
        d["provider_options"] = dict(self.provider_options)
        return d
