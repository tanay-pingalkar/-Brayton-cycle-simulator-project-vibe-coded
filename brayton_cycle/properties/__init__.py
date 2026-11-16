"""Property backends implementing ``core.PropertyProvider`` (REQ-T01).

Built-in backends (names accepted by ``get_property_provider``):
    "constant-cp"  cold-air standard, [1] Table A-2a
    "variable-cp"  Table A-2c cubic cp(T), analytical h and s0, [1]
    "coolprop"     optional, Lemmon et al. air EOS [2] via CoolProp [3]
    "cantera"      optional, NASA-polynomial air mixture [4][5]

The optional adapters import their package only when instantiated, so
importing this package never requires CoolProp or Cantera.
"""

from brayton_cycle.properties._common import BackendUnavailable, PropertyRangeWarning
from brayton_cycle.properties.cantera_provider import CanteraProvider
from brayton_cycle.properties.constant_cp import ConstantCpProvider
from brayton_cycle.properties.coolprop_provider import CoolPropProvider
from brayton_cycle.properties.registry import (
    available_providers,
    get_property_provider,
    register_provider,
    unregister_provider,
)
from brayton_cycle.properties.variable_cp import VariableCpProvider

register_provider("constant-cp", ConstantCpProvider)
register_provider("variable-cp", VariableCpProvider)
register_provider("coolprop", CoolPropProvider)
register_provider("cantera", CanteraProvider)

__all__ = [
    "BackendUnavailable",
    "CanteraProvider",
    "ConstantCpProvider",
    "CoolPropProvider",
    "PropertyRangeWarning",
    "VariableCpProvider",
    "available_providers",
    "get_property_provider",
    "register_provider",
    "unregister_provider",
]
