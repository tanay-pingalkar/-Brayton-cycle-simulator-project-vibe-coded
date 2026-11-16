"""BraytonResult: immutable outcome of one solved cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brayton_cycle.core.interfaces import ComponentResult, PropertyProvider
from brayton_cycle.core.state import State
from brayton_cycle.solver.config import BraytonConfig

#: Station order used for reports and plots.
STATION_ORDER: tuple[str, ...] = ("1", "2s", "2", "3", "4s", "4")


@dataclass(frozen=True)
class BraytonResult:
    """States, component results and KPIs of a solved cycle (SI units).

    Attributes:
        config: The configuration that produced the result.
        provider_name: Property backend actually used.
        states: Station label -> State, in ``STATION_ORDER``.
        components: Component name -> ComponentResult, in flow order.
        w_c, w_t, w_net, q_in, q_out: specific energies [J/kg], all positive by
            definition except w_net, which is negative if the cycle absorbs work.
        bwr: back-work ratio w_c / w_t [-].
        eta_th: thermal efficiency w_net / q_in [-].
        fuel_air_ratio: f [-].
        sfc: specific fuel consumption [kg/kWh]; ``None`` when w_net <= 0.
        net_power: W_dot_net = m_dot w_net [W].
        fuel_flow: m_dot_f = m_dot f [kg/s].
        first_law_residual: |(q_in - q_out) - w_net| / q_in [-] (REQ-N01).
        s_gen: component name -> s_gen [J/(kg K)].
        s_gen_total: sum of s_gen [J/(kg K)].
        provider: The backend instance used (for plotting process paths);
            excluded from equality, repr and ``to_dict``.
    """

    config: BraytonConfig
    provider_name: str
    states: dict[str, State]
    components: dict[str, ComponentResult]
    w_c: float
    w_t: float
    w_net: float
    q_in: float
    q_out: float
    bwr: float
    eta_th: float
    fuel_air_ratio: float
    sfc: float | None
    net_power: float
    fuel_flow: float
    first_law_residual: float
    s_gen: dict[str, float]
    s_gen_total: float
    provider: PropertyProvider | None = field(default=None, repr=False, compare=False)

    @property
    def kpis(self) -> dict[str, float | None]:
        """Key performance indicators as a flat mapping (SI)."""
        return {
            "w_c": self.w_c, "w_t": self.w_t, "w_net": self.w_net,
            "q_in": self.q_in, "q_out": self.q_out, "bwr": self.bwr,
            "eta_th": self.eta_th, "fuel_air_ratio": self.fuel_air_ratio,
            "sfc_kg_per_kWh": self.sfc, "net_power_W": self.net_power,
            "fuel_flow_kg_per_s": self.fuel_flow,
            "first_law_residual": self.first_law_residual,
            "s_gen_total": self.s_gen_total,
        }

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (SI units; see ``units``)."""
        return {
            "units": {"T": "K", "P": "Pa", "h": "J/kg", "s": "J/(kg*K)", "w,q": "J/kg",
                      "power": "W", "sfc": "kg/kWh", "s_gen": "J/(kg*K)"},
            "provider": self.provider_name,
            "config": self.config.to_dict(),
            "states": [self.states[k].as_dict() for k in STATION_ORDER],
            "components": [
                {"name": n, "work": r.work, "heat": r.heat, "s_gen": r.s_gen,
                 "power": r.power, "heat_rate": r.heat_rate,
                 "fuel_air_ratio": r.fuel_air_ratio, "mass_flow": r.mass_flow}
                for n, r in self.components.items()
            ],
            "kpis": self.kpis,
            "s_gen": dict(self.s_gen),
        }
