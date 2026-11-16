"""BraytonSolver: assembles components 1 -> 2 -> 3 -> 4 -> 1 and audits the result."""

from __future__ import annotations

import math

from brayton_cycle.components import Combustor, Compressor, HeatRejection, Turbine
from brayton_cycle.core.constants import FIRST_LAW_RESIDUAL_TOL, J_PER_KWH
from brayton_cycle.core.exceptions import ConservationError, MassConservationError
from brayton_cycle.core.interfaces import ComponentResult, PropertyProvider
from brayton_cycle.properties import get_property_provider
from brayton_cycle.solver.config import BraytonConfig
from brayton_cycle.solver.result import BraytonResult


class BraytonSolver:
    """Solve a ``BraytonConfig`` for states, KPIs and audits.

    Args:
        provider: Optional backend instance. If given, it overrides
            ``config.provider`` (useful for tests and custom backends).
        residual_tol: Maximum allowed relative First-Law residual (REQ-N01).

    Audits run on every solve:
        * per-component SFEE residual |dh - (q - w)| / q_in < residual_tol;
        * cycle residual |(q_in - q_out) - w_net| / q_in < residual_tol;
        * mass flow identical through all components (air-standard);
        * Second Law: enforced by ``ComponentResult`` (s_gen >= 0).
    Any failure raises ``ConservationError`` (or ``SecondLawViolation``).
    """

    def __init__(self, provider: PropertyProvider | None = None,
                 residual_tol: float = FIRST_LAW_RESIDUAL_TOL) -> None:
        self._provider = provider
        self.residual_tol = residual_tol

    def provider_for(self, config: BraytonConfig) -> PropertyProvider:
        """Backend used for ``config``.

        Args:
            config: Configuration whose backend is requested.

        Returns:
            ``PropertyProvider`` instance.
        """
        if self._provider is not None:
            return self._provider
        return get_property_provider(config.provider, **dict(config.provider_options))

    def solve(self, config: BraytonConfig) -> BraytonResult:
        """Run 1 -> 2 -> 3 -> 4 -> 1 and return an audited ``BraytonResult``.

        Args:
            config: Cycle configuration (SI units).

        Returns:
            Audited ``BraytonResult``.

        Raises:
            ConservationError: an energy or mass audit failed.
            SecondLawViolation: a component reports s_gen < 0.
            InputValidationError: physically infeasible inputs (e.g. T3 <= T2).
        """
        gas = self.provider_for(config)
        m = config.mass_flow
        mode_kw = ({"T3": config.T3} if config.combustor_mode == "target_T3"
                   else {"fuel_air_ratio": config.fuel_air_ratio})
        st1 = gas.state(config.T1, config.P1, "1")
        r_c = Compressor(gas, config.pressure_ratio, config.eta_c, m).process(st1)
        r_b = Combustor(gas, config.combustor_mode, eta_comb=config.eta_comb,
                        dp_comb=config.dp_comb, lhv=config.lhv, mass_flow=m,
                        T_source=config.T_source, **mode_kw).process(r_c.outlet)
        r_t = Turbine(gas, config.P1, config.eta_t, m).process(r_b.outlet)
        r_r = HeatRejection(gas, config.T1, config.P1, m, T_sink=config.T_sink).process(
            r_t.outlet, mass_flow_in=r_t.mass_flow)
        comps = {"compressor": r_c, "combustor": r_b, "turbine": r_t, "heat_rejection": r_r}

        w_c, w_t = -r_c.work, r_t.work
        q_in, q_out = r_b.heat, -r_r.heat
        w_net = w_t - w_c
        residual = abs((q_in - q_out) - w_net) / q_in
        self._audit(comps, q_in, residual, m)

        f = float(r_b.fuel_air_ratio)  # type: ignore[arg-type]
        s_gen = {n: r.s_gen for n, r in comps.items()}
        states = {"1": st1, "2s": r_c.isentropic_outlet, "2": r_c.outlet, "3": r_b.outlet,
                  "4s": r_t.isentropic_outlet, "4": r_t.outlet}
        return BraytonResult(
            config=config, provider_name=gas.name, states=states,  # type: ignore[arg-type]
            components=comps, w_c=w_c, w_t=w_t, w_net=w_net, q_in=q_in, q_out=q_out,
            bwr=w_c / w_t, eta_th=w_net / q_in, fuel_air_ratio=f,
            sfc=J_PER_KWH * f / w_net if w_net > 0.0 else None,
            net_power=m * w_net, fuel_flow=m * f, first_law_residual=residual,
            s_gen=s_gen, s_gen_total=math.fsum(s_gen.values()), provider=gas,
        )

    def _audit(self, comps: dict[str, ComponentResult], q_in: float,
               residual: float, m: float) -> None:
        for name, r in comps.items():
            if not math.isclose(r.mass_flow, m, rel_tol=1e-12):
                raise MassConservationError(f"{name}: m_dot = {r.mass_flow} != {m} kg/s")
            eps = abs(r.energy_residual) / q_in
            if eps >= self.residual_tol:
                raise ConservationError(f"{name}: SFEE residual {eps:.3e} >= {self.residual_tol:.1e}")
        if not residual < self.residual_tol:
            raise ConservationError(
                f"cycle First-Law residual {residual:.3e} >= {self.residual_tol:.1e} (REQ-N01)")
