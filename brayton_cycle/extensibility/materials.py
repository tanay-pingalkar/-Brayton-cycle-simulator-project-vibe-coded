"""Blade-material selection hook (REQ-E01).

ALL NUMBERS IN ``DEFAULT_BANDS`` ARE ILLUSTRATIVE PLACEHOLDERS, NOT DESIGN DATA.
They encode only the general trend described in [7]: a higher turbine entry
temperature needs more capable nickel-base alloys (cast, then directionally
solidified, then single-crystal), thermal-barrier coatings and more cooling
air bled from the compressor. Band edges and bleed fractions are rounded
teaching values [FLAG: no specific source; replace with vendor or [7] data
before any design use].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from brayton_cycle.core.exceptions import InputValidationError


@dataclass(frozen=True, slots=True)
class MaterialBand:
    """One T3 band of a rule table: applies to T_min <= T3 < T_max [K]."""

    T_min: float
    T_max: float
    alloy_family: str
    tbc_required: bool
    cooling_bleed_fraction: float


@dataclass(frozen=True, slots=True)
class MaterialSelection:
    """Typed result of a material selection.

    Attributes:
        T3: Turbine entry temperature the selection was made for [K].
        alloy_family: Indicative first-stage blade alloy family.
        tbc_required: Whether a thermal-barrier coating is indicated.
        cooling_bleed_fraction: Indicative cooling air as a fraction of
            compressor delivery [-] (not yet fed back into the cycle).
        band: The (T_min, T_max) band that matched [K].
        illustrative: True while the values are placeholders.
        selector: Name of the selector that produced the result.
    """

    T3: float
    alloy_family: str
    tbc_required: bool
    cooling_bleed_fraction: float
    band: tuple[float, float]
    illustrative: bool
    selector: str


class BladeMaterialSelector(ABC):
    """Strategy interface: choose a blade material concept for a given T3."""

    name: str = "abstract"

    @abstractmethod
    def select(self, T3: float) -> MaterialSelection:
        """Return a ``MaterialSelection`` for turbine entry temperature ``T3`` [K].

        Args:
            T3: Turbine entry temperature [K].

        Returns:
            ``MaterialSelection``.
        """


#: Illustrative placeholder bands (trend per [7]; numbers NOT sourced, see module doc).
DEFAULT_BANDS: tuple[MaterialBand, ...] = (
    MaterialBand(0.0, 1100.0, "cast Ni-base superalloy, uncooled", False, 0.00),
    MaterialBand(1100.0, 1400.0, "cast Ni-base superalloy, convection-cooled", False, 0.03),
    MaterialBand(1400.0, 1650.0, "directionally solidified Ni-base, film-cooled", True, 0.08),
    MaterialBand(1650.0, 1900.0, "single-crystal Ni-base, film-cooled", True, 0.15),
)


class RuleBasedMaterialSelector(BladeMaterialSelector):
    """Look up T3 in a contiguous, ascending table of ``MaterialBand`` rows.

    Raises ``InputValidationError`` if T3 lies outside the table, so a design
    beyond the table's experience (e.g. CMC territory) is never silently accepted.
    """

    name = "rule-based (illustrative)"

    def __init__(self, bands: Sequence[MaterialBand] = DEFAULT_BANDS,
                 illustrative: bool = True) -> None:
        if not bands:
            raise InputValidationError("at least one material band is required")
        for a, b in zip(bands, bands[1:]):
            if a.T_max != b.T_min:
                raise InputValidationError("material bands must be contiguous and ascending")
        for band in bands:
            if not (band.T_min < band.T_max and 0.0 <= band.cooling_bleed_fraction < 1.0):
                raise InputValidationError(f"invalid material band {band}")
        self.bands = tuple(bands)
        self.illustrative = illustrative

    def select(self, T3: float) -> MaterialSelection:
        """Look up ``T3`` in the band table. See ``BladeMaterialSelector.select``."""
        for band in self.bands:
            if band.T_min <= T3 < band.T_max:
                return MaterialSelection(T3=T3, alloy_family=band.alloy_family,
                                         tbc_required=band.tbc_required,
                                         cooling_bleed_fraction=band.cooling_bleed_fraction,
                                         band=(band.T_min, band.T_max),
                                         illustrative=self.illustrative, selector=self.name)
        raise InputValidationError(
            f"T3 = {T3:g} K is outside the material table "
            f"[{self.bands[0].T_min:g}, {self.bands[-1].T_max:g}) K")
