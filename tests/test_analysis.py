"""Sweeps and optimal r_p (REQ-A01)."""

from __future__ import annotations

import numpy as np
import pytest

from brayton_cycle.analysis import KPI_COLUMNS, OptimumResult, ParametricSweepEngine
from brayton_cycle.core.exceptions import InputValidationError
from brayton_cycle.solver import BraytonConfig

ENGINE = ParametricSweepEngine()


def _cold_air(T1: float = 300.0, T3: float = 1400.0, gamma: float = 1.4) -> BraytonConfig:
    return BraytonConfig(T1=T1, P1=101325.0, pressure_ratio=10.0, T3=T3, provider="constant",
                         provider_options={"gamma": gamma})


@pytest.mark.parametrize(("T1", "T3", "gamma"), [(300.0, 1400.0, 1.4), (288.15, 1600.0, 1.4),
                                                 (300.0, 1200.0, 1.35)])
def test_optimal_rp_w_net_matches_analytical(T1: float, T3: float, gamma: float) -> None:
    """Ideal cold-air limit: r_p,opt = (T3/T1)^(gamma / (2 (gamma - 1))) within 1 %."""
    opt = ENGINE.optimal_pressure_ratio(_cold_air(T1, T3, gamma), "w_net", bounds=(1.05, 100.0))
    expected = (T3 / T1) ** (gamma / (2.0 * (gamma - 1.0)))
    assert opt.pressure_ratio == pytest.approx(expected, rel=1e-2)
    assert opt.pressure_ratio == pytest.approx(expected, rel=1e-4)  # actual accuracy
    assert not opt.at_bound and opt.converged and isinstance(opt, OptimumResult)


def test_w_net_max_matches_analytical() -> None:
    opt = ENGINE.optimal_pressure_ratio(_cold_air(), "w_net")
    assert opt.value == pytest.approx(1005.0 * (1400.0**0.5 - 300.0**0.5) ** 2, rel=1e-8)


def test_ideal_eta_optimum_sits_at_upper_bound() -> None:
    """eta_th of the ideal cycle rises monotonically with r_p (physics §9)."""
    opt = ENGINE.optimal_pressure_ratio(_cold_air(), "eta_th", bounds=(2.0, 50.0))
    assert opt.at_bound and opt.pressure_ratio == pytest.approx(50.0, rel=1e-3)


def test_real_cycle_eta_optimum_is_interior_and_above_w_net_optimum() -> None:
    cfg = BraytonConfig.from_reference_case("B")
    w = ENGINE.optimal_pressure_ratio(cfg, "w_net")
    e = ENGINE.optimal_pressure_ratio(cfg, "eta_th")
    assert not e.at_bound and 1.0 < w.pressure_ratio < e.pressure_ratio < 60.0
    df = ENGINE.sweep_rp(cfg, 2.0, 60.0, 117)  # grid step 0.5
    assert e.value >= df["eta_th"].max() - 1e-12
    assert abs(df.loc[df["eta_th"].idxmax(), "pressure_ratio"] - e.pressure_ratio) <= 0.5


def test_optimum_survives_infeasible_region() -> None:
    """Bounds reaching past T2 = T3 must not break the bounded search."""
    opt = ENGINE.optimal_pressure_ratio(_cold_air(T3=900.0), "w_net", bounds=(1.05, 400.0))
    assert opt.pressure_ratio == pytest.approx((900.0 / 300.0) ** 1.75, rel=1e-3)


def test_sweep_rp_shape_and_columns() -> None:
    df = ENGINE.sweep_rp(BraytonConfig.from_reference_case("B"))
    assert df.shape == (30, 1 + len(KPI_COLUMNS) + 1)
    assert list(df.columns) == ["pressure_ratio", *KPI_COLUMNS, "status"]
    assert np.allclose(df["pressure_ratio"], np.linspace(2, 40, 30))
    assert (df["status"] == "ok").all() and (df["first_law_residual"] < 1e-6).all()


def test_sweep_2d_shape_and_columns() -> None:
    df = ENGINE.sweep_2d(BraytonConfig.from_reference_case("B"))
    assert df.shape == (12 * 8, 2 + len(KPI_COLUMNS) + 1)
    assert list(df.columns[:2]) == ["pressure_ratio", "T3"]
    assert df["pressure_ratio"].nunique() == 12 and df["T3"].nunique() == 8
    w = df.pivot(index="T3", columns="pressure_ratio", values="w_net")
    assert (w.diff(axis=0).iloc[1:] > 0).all().all()  # w_net rises with T3 at fixed r_p


def test_sweep_2d_switches_fuel_air_ratio_mode_to_target_T3() -> None:
    cfg = BraytonConfig.from_reference_case("B").replace(
        combustor_mode="fuel_air_ratio", T3=None, fuel_air_ratio=0.02)
    df = ENGINE.sweep_2d(cfg, rp_values=[10.0, 20.0], T3_values=[1300.0, 1500.0])
    assert len(df) == 4 and (df["status"] == "ok").all()


def test_sweep_keeps_infeasible_points() -> None:
    df = ENGINE.sweep_rp(_cold_air(T3=900.0), 2.0, 200.0, 5)
    assert df["status"].str.startswith("infeasible").any()
    assert df.loc[df["status"] != "ok", "w_net"].isna().all()


@pytest.mark.parametrize("kwargs", [{"objective": "bwr"}, {"bounds": (0.5, 10.0)},
                                    {"bounds": (10.0, 5.0)}])
def test_optimum_rejects_bad_arguments(kwargs: dict) -> None:
    with pytest.raises(InputValidationError):
        ENGINE.optimal_pressure_ratio(_cold_air(), **kwargs)
