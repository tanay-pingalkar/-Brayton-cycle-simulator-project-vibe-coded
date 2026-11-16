"""Display-unit tables shared by the CLI, the GUI and the Markdown report.

This is the only place where SI results are converted to display units
(kPa, kJ/kg, kJ/(kg K), MW), so every front end shows identical numbers.
"""

from __future__ import annotations

from collections.abc import Mapping

from brayton_cycle.analysis import OptimumResult
from brayton_cycle.solver import STATION_ORDER, BraytonResult

STATION_HEADERS: tuple[str, ...] = ("Station", "T [K]", "P [kPa]", "h [kJ/kg]", "s [kJ/(kg·K)]")


def station_rows(r: BraytonResult) -> list[tuple[str, str, str, str, str]]:
    """One formatted row per station, in ``STATION_ORDER``.

    Args:
        r: Solved cycle result.

    Returns:
        List of formatted rows.
    """
    rows = []
    for k in STATION_ORDER:
        s = r.states[k]
        rows.append((k, f"{s.T:.2f}", f"{s.P / 1e3:.3f}", f"{s.h / 1e3:.3f}", f"{s.s / 1e3:.5f}"))
    return rows


def kpi_rows(r: BraytonResult) -> list[tuple[str, str]]:
    """(label, formatted value with unit) pairs for the KPIs and audits.

    Args:
        r: Solved cycle result.

    Returns:
        List of (label, value) pairs.
    """
    sfc = "n/a (w_net <= 0)" if r.sfc is None else f"{r.sfc:.4f} kg/kWh"
    return [
        ("Compressor work w_c", f"{r.w_c / 1e3:.3f} kJ/kg"),
        ("Turbine work w_t", f"{r.w_t / 1e3:.3f} kJ/kg"),
        ("Net work w_net", f"{r.w_net / 1e3:.3f} kJ/kg"),
        ("Heat input q_in", f"{r.q_in / 1e3:.3f} kJ/kg"),
        ("Heat rejected q_out", f"{r.q_out / 1e3:.3f} kJ/kg"),
        ("Back-work ratio", f"{r.bwr:.4f}"),
        ("Thermal efficiency", f"{100 * r.eta_th:.3f} %"),
        ("Fuel-air ratio f", f"{r.fuel_air_ratio:.5f}"),
        ("SFC", sfc),
        ("Net power", f"{r.net_power / 1e6:.4f} MW  (m_dot = {r.config.mass_flow:g} kg/s)"),
        ("First-Law residual", f"{r.first_law_residual:.2e}  (limit 1e-6)"),
        ("Total s_gen", f"{r.s_gen_total / 1e3:.5f} kJ/(kg·K)"),
    ]


def input_rows(r: BraytonResult) -> list[tuple[str, str]]:
    """(label, formatted value) pairs describing the configuration.

    Args:
        r: Solved cycle result.

    Returns:
        List of (label, value) pairs.
    """
    c = r.config
    heat = (f"T3 = {c.T3:.2f} K" if c.combustor_mode == "target_T3"
            else f"f = {c.fuel_air_ratio:.5f}")
    return [
        ("Property backend", r.provider_name),
        ("T1", f"{c.T1:.2f} K"), ("P1", f"{c.P1 / 1e3:.3f} kPa"),
        ("Pressure ratio r_p", f"{c.pressure_ratio:.4g}"),
        ("Combustor mode", f"{c.combustor_mode} ({heat})"),
        ("eta_c / eta_t / eta_comb", f"{c.eta_c:.4g} / {c.eta_t:.4g} / {c.eta_comb:.4g}"),
        ("Combustor pressure loss", f"{100 * c.dp_comb:.3g} %"),
        ("LHV", f"{c.lhv / 1e6:.4g} MJ/kg"),
        ("Mass flow", f"{c.mass_flow:g} kg/s"),
    ]


def optimum_rows(optima: Mapping[str, OptimumResult]) -> list[tuple[str, str, str, str]]:
    """(objective, r_p,opt, value with unit, note) rows for optimal-r_p results.

    Args:
        optima: Objective -> ``OptimumResult``.

    Returns:
        List of formatted rows.
    """
    rows = []
    for key, o in optima.items():
        value = f"{o.value / 1e3:.3f} kJ/kg" if key == "w_net" else f"{100 * o.value:.3f} %"
        rows.append((key, f"{o.pressure_ratio:.4f}", value,
                     "at search bound" if o.at_bound else "interior"))
    return rows
