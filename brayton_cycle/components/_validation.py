"""Constructor-argument validators shared by all components."""

from __future__ import annotations

import math

from brayton_cycle.core.exceptions import (
    InputValidationError,
    InvalidEfficiencyError,
    InvalidPressureLossError,
    InvalidPressureRatioError,
)


def _real(name: str, value: object, exc: type[InputValidationError]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise exc(f"{name} must be a real number, got {value!r}")
    v = float(value)
    if not math.isfinite(v):
        raise exc(f"{name} must be finite, got {v!r}")
    return v


def require_efficiency(name: str, value: object) -> float:
    """Return ``value`` if 0 < value <= 1, else raise InvalidEfficiencyError.

    Args:
        name: Parameter or backend name (used in messages / as registry key).
        value: Value to validate or convert.

    Returns:
        The value as float.
    """
    v = _real(name, value, InvalidEfficiencyError)
    if not 0.0 < v <= 1.0:
        raise InvalidEfficiencyError(f"{name} must satisfy 0 < {name} <= 1, got {v}")
    return v


def require_pressure_loss(name: str, value: object) -> float:
    """Return ``value`` if 0 <= value < 1, else raise InvalidPressureLossError.

    Args:
        name: Parameter or backend name (used in messages / as registry key).
        value: Value to validate or convert.

    Returns:
        The value as float.
    """
    v = _real(name, value, InvalidPressureLossError)
    if not 0.0 <= v < 1.0:
        raise InvalidPressureLossError(f"{name} must satisfy 0 <= {name} < 1, got {v}")
    return v


def require_pressure_ratio(name: str, value: object) -> float:
    """Return ``value`` if value > 1, else raise InvalidPressureRatioError.

    Args:
        name: Parameter or backend name (used in messages / as registry key).
        value: Value to validate or convert.

    Returns:
        The value as float.
    """
    v = _real(name, value, InvalidPressureRatioError)
    if not v > 1.0:
        raise InvalidPressureRatioError(f"{name} must be > 1, got {v}")
    return v


def require_positive(name: str, value: object,
                     exc: type[InputValidationError] = InputValidationError) -> float:
    """Return ``value`` if value > 0, else raise ``exc``.

    Args:
        name: Parameter or backend name (used in messages / as registry key).
        value: Value to validate or convert.
        exc: Exception class raised on failure.

    Returns:
        The value as float.
    """
    v = _real(name, value, exc)
    if not v > 0.0:
        raise exc(f"{name} must be > 0, got {v}")
    return v


def optional_positive(name: str, value: object | None) -> float | None:
    """Like ``require_positive`` but passes ``None`` through.

    Args:
        name: Parameter or backend name (used in messages / as registry key).
        value: Value to validate or convert.

    Returns:
        The value as float, or None.
    """
    return None if value is None else require_positive(name, value)
