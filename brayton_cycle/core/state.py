"""Immutable thermodynamic state of a working-fluid station."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class State:
    """Thermodynamic state at one cycle station.

    Attributes:
        T: Static temperature [K]. Must be finite and > 0.
        P: Static pressure [Pa]. Must be finite and > 0.
        h: Specific enthalpy [J/kg], relative to the provider's reference state
            (``constants.T_REF``). Only differences are physically meaningful.
        s: Specific entropy [J/(kg*K)], relative to (``T_REF``, ``P_REF``).
        label: Station label, e.g. ``"1"``, ``"2s"``, ``"3"``.

    The object is frozen: components never mutate an inlet state, they return a
    new outlet ``State``. Construct states through a ``PropertyProvider`` so
    that ``h`` and ``s`` are consistent with ``T`` and ``P``.
    """

    T: float
    P: float
    h: float
    s: float
    label: str = ""

    def __post_init__(self) -> None:
        for name in ("T", "P", "h", "s"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"State.{name} must be finite, got {value!r}")
        if self.T <= 0.0:
            raise ValueError(f"State.T must be > 0 K, got {self.T!r}")
        if self.P <= 0.0:
            raise ValueError(f"State.P must be > 0 Pa, got {self.P!r}")

    def relabel(self, label: str) -> State:
        """Return a copy of this state with a new station label.

        Args:
            label: Station label for the returned state.

        Returns:
            New ``State`` (this one is unchanged).
        """
        return replace(self, label=label)

    def as_dict(self) -> dict[str, float | str]:
        """Return a JSON-serialisable mapping (SI units)."""
        return {"label": self.label, "T": self.T, "P": self.P, "h": self.h, "s": self.s}
