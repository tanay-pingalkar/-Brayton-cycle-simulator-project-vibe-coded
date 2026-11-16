"""Extensibility stubs run and return their typed DTOs (REQ-E01)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from brayton_cycle.core.exceptions import InputValidationError
from brayton_cycle.extensibility import (
    BladeMaterialSelector,
    MaterialBand,
    MaterialSelection,
    MeanLineRotorSizingStub,
    RotorSizing,
    RotorSizingResult,
    RuleBasedMaterialSelector,
)
from brayton_cycle.solver import BraytonConfig, BraytonSolver


def test_material_selector_returns_typed_dto() -> None:
    sel: BladeMaterialSelector = RuleBasedMaterialSelector()
    out = sel.select(1500.0)
    assert isinstance(out, MaterialSelection)
    assert out.tbc_required and out.illustrative and out.band == (1400.0, 1650.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.T3 = 1.0  # type: ignore[misc]


def test_material_trend_monotonic() -> None:
    sel = RuleBasedMaterialSelector()
    bleed = [sel.select(T).cooling_bleed_fraction for T in (1000.0, 1300.0, 1500.0, 1800.0)]
    assert bleed == sorted(bleed)


def test_material_out_of_table_and_bad_bands() -> None:
    with pytest.raises(InputValidationError):
        RuleBasedMaterialSelector().select(2100.0)
    with pytest.raises(InputValidationError):
        RuleBasedMaterialSelector([MaterialBand(0, 1000, "a", False, 0.0),
                                   MaterialBand(1100, 1500, "b", True, 0.05)])


def test_rotor_sizing_returns_typed_dto() -> None:
    sizer: RotorSizing = MeanLineRotorSizingStub()
    r = BraytonSolver().solve(BraytonConfig.from_reference_case("B"))
    out = sizer.size(r.config.mass_flow, r.states["1"], 287.0)
    assert isinstance(out, RotorSizingResult) and out.illustrative
    assert 0.0 < out.hub_radius < out.mean_radius < out.tip_radius
    rho = r.states["1"].P / (287.0 * r.states["1"].T)
    assert out.annulus_area == pytest.approx(25.0 / (rho * 150.0), rel=1e-12)
    assert out.annulus_area == pytest.approx(
        math.pi * (out.tip_radius**2 - out.hub_radius**2), rel=1e-12)
    assert out.rotational_speed_rpm > 0.0


def test_rotor_sizing_rejects_bad_inputs() -> None:
    with pytest.raises(InputValidationError):
        MeanLineRotorSizingStub(hub_tip_ratio=1.2)
    with pytest.raises(InputValidationError):
        MeanLineRotorSizingStub().size(-1.0, BraytonSolver().solve(
            BraytonConfig.from_reference_case("B")).states["1"], 287.0)


def test_custom_selector_plugs_in() -> None:
    class Fixed(BladeMaterialSelector):
        name = "fixed"

        def select(self, T3: float) -> MaterialSelection:
            return MaterialSelection(T3, "CMC", True, 0.0, (0.0, 1e9), False, self.name)

    assert Fixed().select(2000.0).alloy_family == "CMC"
