"""Citations of the property data behind each backend (mirrors docs/references.md)."""

from __future__ import annotations

#: Full APA entries, keyed by the tag used in docs/references.md.
REFERENCES: dict[str, str] = {
    "1": "Çengel, Y. A., Boles, M. A., & Kanoğlu, M. (2019). Thermodynamics: An engineering "
         "approach (9th ed.). McGraw-Hill Education.",
    "2": "Lemmon, E. W., Jacobsen, R. T., Penoncello, S. G., & Friend, D. G. (2000). "
         "Thermodynamic properties of air and mixtures of nitrogen, argon, and oxygen from 60 "
         "to 2000 K at pressures to 2000 MPa. Journal of Physical and Chemical Reference Data, "
         "29(3), 331–385. https://doi.org/10.1063/1.1285884",
    "3": "Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and pseudo-pure "
         "fluid thermophysical property evaluation and the open-source thermophysical property "
         "library CoolProp. Industrial & Engineering Chemistry Research, 53(6), 2498–2508. "
         "https://doi.org/10.1021/ie4033999",
    "4": "Goodwin, D. G., Speth, R. L., Moffat, H. K., & Weber, B. W. (n.d.). Cantera: An "
         "object-oriented software toolkit for chemical kinetics, thermodynamics, and transport "
         "processes [Computer software]. https://www.cantera.org",
    "5": "McBride, B. J., Zehe, M. J., & Gordon, S. (2002). NASA Glenn coefficients for "
         "calculating thermodynamic properties of individual species (NASA/TP-2002-211556). "
         "NASA Glenn Research Center.",
}

#: Backend name -> (short description of the property data, reference tags).
PROPERTY_DATA: dict[str, tuple[str, tuple[str, ...]]] = {
    "constant-cp": ("Constant cp = 1.005 kJ/(kg K), k = 1.4 at 300 K, [1] Table A-2a", ("1",)),
    "variable-cp": ("Air cp polynomial, [1] Table A-2c (273–1800 K, max error 0.72 %); "
                    "M and R from [1] Table A-1", ("1",)),
    "coolprop": ("Lemmon et al. (2000) air EOS [2] via CoolProp [3], ideal-gas projection "
                 "at 1 atm", ("2", "3")),
    "cantera": ("Frozen N2/O2/Ar ideal-gas mixture, NASA 7-coefficient polynomials [5] via "
                "Cantera [4]", ("4", "5")),
}


def property_citation(provider_name: str) -> dict[str, object]:
    """Description and full references for a backend (unknown names are flagged).

    Args:
        provider_name: Backend name, e.g. ``"variable-cp"``.

    Returns:
        Dict with backend, description and full references.
    """
    desc, tags = PROPERTY_DATA.get(
        provider_name, (f"[FLAG: no citation registered for backend {provider_name!r}]", ()))
    return {"backend": provider_name, "description": desc,
            "references": [f"[{t}] {REFERENCES[t]}" for t in tags]}
