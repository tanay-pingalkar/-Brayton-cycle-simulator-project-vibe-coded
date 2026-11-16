"""Typed extension points (REQ-E01): blade-material selection and rotor sizing.

Both are strategy ABCs with frozen-dataclass results. The bundled
implementations are stubs with ILLUSTRATIVE placeholder numbers. They depend
only on ``core``, never on the solver, so they can be fed from any
``BraytonResult`` (e.g. ``selector.select(result.states["3"].T)``).
"""

from brayton_cycle.extensibility.materials import (
    DEFAULT_BANDS,
    BladeMaterialSelector,
    MaterialBand,
    MaterialSelection,
    RuleBasedMaterialSelector,
)
from brayton_cycle.extensibility.rotor import (
    MeanLineRotorSizingStub,
    RotorSizing,
    RotorSizingResult,
)

__all__ = [
    "DEFAULT_BANDS",
    "BladeMaterialSelector",
    "MaterialBand",
    "MaterialSelection",
    "MeanLineRotorSizingStub",
    "RotorSizing",
    "RotorSizingResult",
    "RuleBasedMaterialSelector",
]
