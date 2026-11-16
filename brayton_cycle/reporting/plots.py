"""CyclePlotter: T-s, P-v, energy audit, 1-D sweep and 2-D contour figures (REQ-R01).

Every method returns a ``matplotlib.figure.Figure`` built without pyplot, so
there is no global state and no ``plt.show()``. The CLI saves figures with
``fig.savefig``, and the GUI embeds them with ``FigureCanvasTkAgg``.

Process paths are sampled through the result's own ``PropertyProvider``: along
each process, P is interpolated geometrically and s linearly, and
T = T_from_s_P(s, P). For the isobars 2-3 (with pressure loss) and 4-1 this
traces the exact isobar. For the irreversible compression and expansion it
draws a smooth path between the true end states (only the end states are
thermodynamically meaningful).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from brayton_cycle.core.interfaces import PropertyProvider
from brayton_cycle.core.state import State
from brayton_cycle.solver import BraytonResult, BraytonSolver

# Categorical slots 1-3 of the dataviz reference palette (validated, light mode).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
SEQUENTIAL_CMAP = "Blues"  # single hue, light -> dark (magnitude)

KPI_LABELS: dict[str, str] = {
    "w_net": "Net specific work w_net [kJ/kg]",
    "eta_th": "Thermal efficiency η_th [%]",
    "bwr": "Back-work ratio [-]",
    "sfc_kg_per_kWh": "SFC [kg/kWh]",
    "net_power_W": "Net power [MW]",
}
#: Multiply SI values by these factors for display.
KPI_SCALE: dict[str, float] = {"w_net": 1e-3, "eta_th": 100.0, "net_power_W": 1e-6}
PARAM_LABELS: dict[str, str] = {"pressure_ratio": "Pressure ratio r_p [-]", "T3": "T3 [K]",
                                "T1": "T1 [K]", "eta_c": "η_c [-]", "eta_t": "η_t [-]"}


def _name(key: str, table: Mapping[str, str] = PARAM_LABELS) -> str:
    """Axis label without its unit, e.g. 'Pressure ratio r_p'."""
    return table.get(key, key).split(" [")[0]


def _style(ax: Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED)


class CyclePlotter:
    """Build figures from ``BraytonResult`` objects and sweep DataFrames.

    Args:
        n_points: Samples per process path.
        figsize: Default figure size in inches.
    """

    def __init__(self, n_points: int = 40, figsize: tuple[float, float] = (6.4, 4.4)) -> None:
        self.n_points = n_points
        self.figsize = figsize

    # --------------------------------------------------------- helpers
    @staticmethod
    def _provider(r: BraytonResult) -> PropertyProvider:
        return r.provider if r.provider is not None else BraytonSolver().provider_for(r.config)

    def _path(self, gas: PropertyProvider, a: State, b: State) -> tuple[np.ndarray, np.ndarray]:
        """Sample (T, P) along a -> b; returns arrays of T [K] and P [Pa]."""
        u = np.linspace(0.0, 1.0, self.n_points)
        P = a.P * (b.P / a.P) ** u
        s = a.s + (b.s - a.s) * u
        T = np.array([gas.T_from_s_P(si, Pi) for si, Pi in zip(s, P)])
        T[0], T[-1] = a.T, b.T
        return T, P

    def _cycle_paths(self, r: BraytonResult) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
        gas, st = self._provider(r), r.states
        out = []
        for a, b in (("1", "2"), ("2", "3"), ("3", "4"), ("4", "1")):
            T, P = self._path(gas, st[a], st[b])
            s = np.array([gas.s(Ti, Pi) for Ti, Pi in zip(T, P)])
            out.append((T, P, s))
        return out

    def _new(self, nrows: int = 1, ncols: int = 1, **kw: object) -> tuple[Figure, object]:
        fig = Figure(figsize=kw.pop("figsize", self.figsize), layout="constrained")  # type: ignore[arg-type]
        axes = fig.subplots(nrows, ncols, **kw)  # type: ignore[arg-type]
        return fig, axes

    # --------------------------------------------------------- diagrams
    def ts_diagram(self, r: BraytonResult) -> Figure:
        """Temperature-entropy diagram with actual and isentropic processes.

        Args:
            r: Solved cycle result.

        Returns:
            Matplotlib ``Figure``.
        """
        fig, ax = self._new()
        for i, (T, _P, s) in enumerate(self._cycle_paths(r)):
            ax.plot(s / 1e3, T, color=BLUE, lw=2, label="cycle (actual)" if i == 0 else None)
        st = r.states
        for a, b in (("1", "2s"), ("3", "4s")):
            ax.plot([st[a].s / 1e3, st[b].s / 1e3], [st[a].T, st[b].T], ls=":", color=MUTED,
                    lw=1.5, label="isentropic" if a == "1" else None)
        self._label_states(ax, [(st[k].s / 1e3, st[k].T, k) for k in st])
        ax.set_xlabel("Specific entropy s [kJ/(kg·K)]")
        ax.set_ylabel("Temperature T [K]")
        ax.set_title(f"T-s diagram ({r.provider_name})", color=INK)
        ax.legend(frameon=False)
        _style(ax)
        return fig

    def pv_diagram(self, r: BraytonResult, log: bool = True) -> Figure:
        """Pressure-specific volume diagram (log-log by default).

        Args:
            r: Solved cycle result.
            log: Use logarithmic axes.

        Returns:
            Matplotlib ``Figure``.
        """
        fig, ax = self._new()
        gas = self._provider(r)
        for T, P, _s in self._cycle_paths(r):
            v = np.array([gas.v(Ti, Pi) for Ti, Pi in zip(T, P)])
            ax.plot(v, P / 1e3, color=BLUE, lw=2)
        pts = [(gas.v(s.T, s.P), s.P / 1e3, k) for k, s in r.states.items() if not k.endswith("s")]
        self._label_states(ax, pts)
        if log:
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.set_xlabel("Specific volume v [m³/kg]" + (" (log)" if log else ""))
        ax.set_ylabel("Pressure P [kPa]" + (" (log)" if log else ""))
        ax.set_title(f"P-v diagram ({r.provider_name})", color=INK)
        _style(ax)
        return fig

    @staticmethod
    def _label_states(ax: Axes, pts: Sequence[tuple[float, float, str]]) -> None:
        for x, y, k in pts:
            ideal = k.endswith("s")
            ax.plot(x, y, "o", ms=6, color="white" if ideal else BLUE,
                    mec=MUTED if ideal else BLUE, mew=1.5, zorder=3)
            ax.annotate(k, (x, y), textcoords="offset points", xytext=(6, 4),
                        color=MUTED if ideal else INK, fontsize=9)

    def energy_audit(self, r: BraytonResult) -> Figure:
        """Bar charts of specific energies [kJ/kg] and entropy generation [J/(kg·K)].

        Args:
            r: Solved cycle result.

        Returns:
            Matplotlib ``Figure`` with two axes.
        """
        fig, (ax_e, ax_s) = self._new(1, 2, figsize=(9.0, 4.0))
        names = ["w_c", "w_t", "w_net", "q_in", "q_out"]
        vals = [r.w_c, r.w_t, r.w_net, r.q_in, r.q_out]
        colors = [BLUE, BLUE, BLUE, ORANGE, ORANGE]
        bars = ax_e.bar(names, np.array(vals) / 1e3, color=colors, width=0.6)
        ax_e.bar_label(bars, fmt="%.1f", padding=2, fontsize=8, color=INK)
        ax_e.set_ylabel("Specific energy [kJ/kg]")
        ax_e.set_title(f"Energy audit (residual {r.first_law_residual:.1e})", color=INK)
        ax_e.axhline(0.0, color=MUTED, lw=0.8)
        comp = list(r.s_gen)
        sb = ax_s.bar([c.replace("_", "\n") for c in comp], [r.s_gen[c] for c in comp],
                      color=AQUA, width=0.6)
        ax_s.bar_label(sb, fmt="%.1f", padding=2, fontsize=8, color=INK)
        ax_s.set_ylabel("Entropy generation s_gen [J/(kg·K)]")
        ax_s.set_title(f"Second-Law audit (total {r.s_gen_total:.1f})", color=INK)
        for ax in (ax_e, ax_s):
            _style(ax)
        return fig

    # --------------------------------------------------------- sweeps
    def sweep_1d(self, df: pd.DataFrame, parameter: str = "pressure_ratio",
                 kpis: Sequence[str] = ("w_net", "eta_th"),
                 optima: Mapping[str, float] | None = None) -> Figure:
        """One stacked panel per KPI over a shared x-axis (no dual y-axes).

        ``optima`` maps KPI name -> optimal parameter value, drawn as a marked point.

        Args:
            df: Sweep DataFrame from ``ParametricSweepEngine``.
            parameter: Swept column used for the x-axis.
            kpis: KPI columns to plot, one panel each.
            optima: KPI name -> optimal parameter value to mark.

        Returns:
            Matplotlib ``Figure``, one axis per KPI.
        """
        fig, axes = self._new(len(kpis), 1, sharex=True, figsize=(6.4, 2.4 * len(kpis) + 0.6))
        axes = np.atleast_1d(axes)
        x = df[parameter].to_numpy(dtype=float)
        for ax, kpi, color in zip(axes, kpis, (BLUE, ORANGE, AQUA, MUTED)):
            y = df[kpi].to_numpy(dtype=float) * KPI_SCALE.get(kpi, 1.0)
            ax.plot(x, y, color=color, lw=2, marker="o", ms=4)
            if optima and kpi in optima:
                xo = optima[kpi]
                yo = float(np.interp(xo, x[~np.isnan(y)], y[~np.isnan(y)]))
                ax.plot(xo, yo, "D", ms=8, color=color, mec="white", zorder=3)
                near_right = xo > x[0] + 0.75 * (x[-1] - x[0])
                ax.annotate(f"optimum r_p = {xo:.2f}", (xo, yo), textcoords="offset points",
                            xytext=(0, 10), ha="right" if near_right else "center",
                            va="bottom", fontsize=9, color=INK)
                ax.margins(y=0.18)
            ax.set_ylabel(KPI_LABELS.get(kpi, kpi))
            _style(ax)
        axes[-1].set_xlabel(PARAM_LABELS.get(parameter, parameter))
        axes[0].set_title(f"Sweep over {_name(parameter)}", color=INK)
        return fig

    def contour_2d(self, df: pd.DataFrame, kpi: str = "w_net", x: str = "pressure_ratio",
                   y: str = "T3", levels: int = 12) -> Figure:
        """Filled contour of ``kpi`` over a long-format 2-D sweep DataFrame.

        Args:
            df: Sweep DataFrame from ``ParametricSweepEngine``.
            kpi: KPI column to contour.
            x: Column for the x-axis.
            y: Column for the y-axis.
            levels: Number of contour levels.

        Returns:
            Matplotlib ``Figure`` (main axis + colorbar).
        """
        grid = df.pivot(index=y, columns=x, values=kpi).sort_index().sort_index(axis=1)
        Z = grid.to_numpy(dtype=float) * KPI_SCALE.get(kpi, 1.0)
        X, Y = np.meshgrid(grid.columns.to_numpy(float), grid.index.to_numpy(float))
        fig, ax = self._new()
        cf = ax.contourf(X, Y, np.ma.masked_invalid(Z), levels=levels, cmap=SEQUENTIAL_CMAP)
        cs = ax.contour(X, Y, np.ma.masked_invalid(Z), levels=cf.levels[::2], colors=INK,
                        linewidths=0.6)
        ax.clabel(cs, fmt="%.0f" if abs(np.nanmax(Z)) > 10 else "%.2f", fontsize=8)
        cbar = fig.colorbar(cf, ax=ax)
        cbar.set_label(KPI_LABELS.get(kpi, kpi))
        ax.set_xlabel(PARAM_LABELS.get(x, x))
        ax.set_ylabel(PARAM_LABELS.get(y, y))
        ax.set_title(f"{_name(kpi, KPI_LABELS)} over {_name(x)} × {_name(y)}", color=INK)
        return fig
