"""Shared adiabatic compression/expansion logic for Compressor and Turbine.

Both machines use the same three steps:
    1. isentropic end state:  s(T_s, P_out) = s_in
    2. actual enthalpy:       compression  h_out = h_in + (h_s - h_in) / eta
                              expansion    h_out = h_in - eta (h_in - h_s)
    3. SFEE (q = 0):          w = h_in - h_out   (> 0 for a turbine)
       entropy balance:       s_gen = s_out - s_in  (adiabatic, [9])
"""

from __future__ import annotations

from brayton_cycle.core.interfaces import ComponentResult, PropertyProvider
from brayton_cycle.core.state import State


def adiabatic_process(
    provider: PropertyProvider,
    inlet: State,
    P_out: float,
    eta: float,
    *,
    compression: bool,
    name: str,
    outlet_label: str,
    mass_flow: float,
) -> ComponentResult:
    """Adiabatic, steady-flow compression or expansion with isentropic efficiency ``eta``.

    Args:
        provider: Property backend (display label or name).
        inlet: Inlet state of the control volume.
        P_out: Outlet pressure [Pa].
        eta: Isentropic efficiency (0, 1].
        compression: True for compression, False for expansion.
        name: Parameter or backend name (used in messages / as registry key).
        outlet_label: Label of the outlet state.
        mass_flow: Mass flow [kg/s].

    Returns:
        ``ComponentResult`` including the isentropic end state.
    """
    ideal = provider.state_from_s_P(inlet.s, P_out, label=f"{outlet_label}s")
    dh_s = ideal.h - inlet.h
    dh = dh_s / eta if compression else dh_s * eta
    outlet = provider.state_from_h_P(inlet.h + dh, P_out, label=outlet_label)
    return ComponentResult(
        component=name,
        inlet=inlet,
        outlet=outlet,
        work=inlet.h - outlet.h,
        heat=0.0,
        s_gen=outlet.s - inlet.s,
        isentropic_outlet=ideal,
        mass_flow=mass_flow,
    )
