"""Exception hierarchy for the whole package.

All project errors derive from ``BraytonError``, so callers (CLI, GUI) can
catch one type. Input-validation errors also derive from ``ValueError``, so
generic handlers keep working.
"""

from __future__ import annotations


class BraytonError(Exception):
    """Base class for every error raised by brayton_cycle."""


class InputValidationError(BraytonError, ValueError):
    """A user-supplied parameter is outside its physical or allowed range."""


class InvalidEfficiencyError(InputValidationError):
    """An efficiency is not in (0, 1]."""


class InvalidPressureLossError(InputValidationError):
    """A fractional pressure loss is not in [0, 1)."""


class InvalidPressureRatioError(InputValidationError):
    """A pressure ratio is not > 1, or a turbine outlet pressure is not below its inlet."""


class CombustorTemperatureError(InputValidationError):
    """Target T3 is not above the combustor inlet temperature T2 (mode a)."""


class FuelAirRatioError(InputValidationError):
    """A given or required fuel-air ratio is outside (0, f_stoich]."""


class ConservationError(BraytonError):
    """A First-Law (energy) or mass audit failed (REQ-N01)."""


class MassConservationError(ConservationError):
    """Mass flow entering a component differs from the cycle mass flow."""


class CycleClosureError(BraytonError):
    """The heat-rejection process cannot return the fluid to station 1."""


class SecondLawViolation(BraytonError, ValueError):
    """A component reports s_gen < -S_GEN_TOL."""


class BackendUnavailable(BraytonError, ImportError):
    """An optional property backend's package is not installed."""
