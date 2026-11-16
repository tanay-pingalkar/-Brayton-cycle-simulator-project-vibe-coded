"""Shared helpers for property backends: errors, warnings, monotonic inversion."""

from __future__ import annotations

from collections.abc import Callable

from scipy.optimize import brentq

from brayton_cycle.core.exceptions import BackendUnavailable

__all__ = ["BackendUnavailable", "PropertyRangeWarning", "invert_monotonic"]

#: Absolute tolerance on temperature for all inversions [K]. Far below the
#: 1e-8 K round-trip requirement and far above double-precision noise at 2000 K.
T_XTOL: float = 1e-12
#: Relative tolerance passed to brentq (4x machine epsilon, scipy's minimum).
T_RTOL: float = 4.0 * 2.220446049250313e-16
#: Maximum brentq iterations (bisection on [273, 1800] K would need ~51).
T_MAXITER: int = 200


class PropertyRangeWarning(UserWarning):
    """Issued when a correlation is evaluated outside its validity range."""


def invert_monotonic(
    fun: Callable[[float], float],
    target: float,
    T_lo: float,
    T_hi: float,
    quantity: str,
    backend: str,
) -> float:
    """Solve ``fun(T) = target`` for T on [T_lo, T_hi] with Brent's method.

    ``fun`` must be strictly increasing in T (true for h(T) and s(T, P) because
    cp > 0). Raises ``ValueError`` naming the backend and bracket if the root
    is not bracketed, i.e. the requested state lies outside the valid range.

    Args:
        fun: Strictly increasing function of T.
        target: Value to match.
        T_lo: Lower end of the bracket [K].
        T_hi: Upper end of the bracket [K].
        quantity: Name of the inverted quantity (for messages).
        backend: Backend name (for messages).

    Returns:
        Temperature [K] with |error| below T_XTOL.

    Raises:
        ValueError: target outside the bracket.
    """
    f_lo = fun(T_lo) - target
    f_hi = fun(T_hi) - target
    if f_lo > 0.0 or f_hi < 0.0:
        raise ValueError(
            f"{backend}: {quantity} = {target:.6g} lies outside the range "
            f"[{fun(T_lo):.6g}, {fun(T_hi):.6g}] that corresponds to "
            f"T in [{T_lo:g}, {T_hi:g}] K"
        )
    if f_lo == 0.0:
        return T_lo
    if f_hi == 0.0:
        return T_hi
    return float(
        brentq(lambda T: fun(T) - target, T_lo, T_hi,
               xtol=T_XTOL, rtol=T_RTOL, maxiter=T_MAXITER)
    )
