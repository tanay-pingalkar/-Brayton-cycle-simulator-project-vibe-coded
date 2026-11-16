"""Single source of truth for physical constants and property correlations.

Every value carries an inline citation tag that resolves to an entry in
``docs/references.md``. Values that cannot be tied to the project reference
list are marked ``[FLAG: ...]`` instead of being given an invented source.

Internal unit system (SI, mass-specific):
    temperature K, pressure Pa, specific energy J/kg, specific entropy J/(kg*K),
    molar mass kg/mol, LHV J/kg.

No other module may hard-code a physical constant; import it from here.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Fundamental constants
# ---------------------------------------------------------------------------
R_UNIVERSAL: Final[float] = 8.314462618
"""Molar gas constant R_u [J/(mol*K)]. [8] CODATA 2018 (exact in the 2019 SI)."""

# ---------------------------------------------------------------------------
# Air (ideal gas)
# ---------------------------------------------------------------------------
M_AIR: Final[float] = 28.97e-3
"""Molar mass of air [kg/mol] (= 28.97 kg/kmol). [1] Table A-1."""

R_AIR: Final[float] = 287.0
"""Specific gas constant of air [J/(kg*K)] (= 0.2870 kJ/kg*K). [1] Table A-1.
Consistency: R_UNIVERSAL / M_AIR = 287.004 J/(kg*K) (diff < 0.002 %)."""

CP_AIR_300K: Final[float] = 1005.0
"""Constant-pressure specific heat of air at 300 K [J/(kg*K)]. [1] Table A-2a."""

GAMMA_AIR_300K: Final[float] = 1.4
"""Specific-heat ratio k = cp/cv of air at 300 K [-]. [1] Table A-2a."""

# ---------------------------------------------------------------------------
# Variable-cp correlation for air: cp_bar = a + b*T + c*T^2 + d*T^3
# Units of cp_bar: kJ/(kmol*K) == J/(mol*K); T in KELVIN (NOT T/1000).
# Coefficients used exactly as published. An earlier draft scaled T by 1/1000
# while keeping these per-K coefficients (b, c, d effectively wrong) - do not.
# ---------------------------------------------------------------------------
CP_POLY_AIR_A: Final[float] = 28.11
"""[1] Table A-2c, air, a [kJ/(kmol*K)]."""
CP_POLY_AIR_B: Final[float] = 0.1967e-2
"""[1] Table A-2c, air, b [kJ/(kmol*K^2)]."""
CP_POLY_AIR_C: Final[float] = 0.4802e-5
"""[1] Table A-2c, air, c [kJ/(kmol*K^3)]."""
CP_POLY_AIR_D: Final[float] = -1.966e-9
"""[1] Table A-2c, air, d [kJ/(kmol*K^4)]."""
CP_POLY_AIR_T_MIN: Final[float] = 273.0
"""Lower validity limit of the Table A-2c air polynomial [K]. [1] Table A-2c."""
CP_POLY_AIR_T_MAX: Final[float] = 1800.0
"""Upper validity limit of the Table A-2c air polynomial [K]. [1] Table A-2c."""
CP_POLY_AIR_MAX_ERROR_PCT: Final[float] = 0.72
"""Maximum stated error of the Table A-2c air polynomial [%]. [1] Table A-2c."""

# ---------------------------------------------------------------------------
# Reference state for h and s
# ---------------------------------------------------------------------------
T_REF: Final[float] = 298.15
"""Reference temperature for h = 0, s_deg = 0 [K] (25 degC standard reference
state). [1] Ch. 15 (standard reference state, 25 degC and 1 atm)."""

P_REF: Final[float] = 101325.0
"""Reference pressure for entropy, s = s_deg - R ln(P/P_REF) [Pa] (1 atm).
[1] Ch. 15 standard reference state. Note: 1 atm = 101 325 Pa is a definitional
value [FLAG: the defining document (CGPM 1954) is not in the reference list]."""

# ---------------------------------------------------------------------------
# Fuel and default component performance
# ---------------------------------------------------------------------------
LHV_KEROSENE: Final[float] = 43.0e6
"""Lower heating value of kerosene [J/kg] (~43 MJ/kg). [7]."""

FAR_STOICH_KEROSENE: Final[float] = 0.068
"""Approximate stoichiometric fuel-air ratio of kerosene [-]. Used as the upper
bound of the physical f range in the combustor. [7] [FLAG: value from general
knowledge (about 1/14.7); exact figure and page in [7] to be verified]."""

ETA_C_DEFAULT: Final[float] = 0.86
"""Default compressor isentropic efficiency [-]; within typical range in [7]
[FLAG: exact page of the range in [7] to be recorded on Day 5]."""
ETA_T_DEFAULT: Final[float] = 0.89
"""Default turbine isentropic efficiency [-]; within typical range in [7]
[FLAG: page to be recorded]."""
ETA_COMB_DEFAULT: Final[float] = 0.99
"""Default combustion efficiency [-]; within typical range in [7]
[FLAG: page to be recorded]."""
DP_COMB_DEFAULT: Final[float] = 0.03
"""Default fractional combustor total-pressure loss dP/P2 [-]; within typical
range in [7] [FLAG: page to be recorded]."""

# ---------------------------------------------------------------------------
# Ambient default (Case B inlet)
# ---------------------------------------------------------------------------
T_AMBIENT_ISA: Final[float] = 288.15
"""Sea-level standard-atmosphere temperature [K].
[FLAG: ISO 2533:1975 Standard Atmosphere is not in the reference list.]"""
P_AMBIENT_ISA: Final[float] = 101325.0
"""Sea-level standard-atmosphere pressure [Pa].
[FLAG: ISO 2533:1975 Standard Atmosphere is not in the reference list.]"""

# ---------------------------------------------------------------------------
# Numerical tolerances (project requirements, not physical constants)
# ---------------------------------------------------------------------------
FIRST_LAW_RESIDUAL_TOL: Final[float] = 1e-6
"""Maximum allowed relative First-Law residual epsilon [-]. REQ-N01."""
S_GEN_TOL: Final[float] = 1e-9
"""Allowed round-off below zero for s_gen [J/(kg*K)] before a Second-Law
violation is raised. REQ-T02."""
J_PER_KWH: Final[float] = 3.6e6
"""Joules per kWh [J/kWh]; used in SFC = 3.6e6 * f / w_net with w_net in J/kg.
(Definitional unit conversion, 1 kWh = 3600 s * 1000 W.)"""
