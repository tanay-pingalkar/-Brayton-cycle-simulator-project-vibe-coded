# References

Citation tags `[n]` are used in code docstrings (`brayton_cycle/core/constants.py`),
`docs/physics_formulation.md`, and `validation_reference_data.json`.

[1] Çengel, Y. A., Boles, M. A., & Kanoğlu, M. (2019). *Thermodynamics: An engineering approach* (9th ed.). McGraw-Hill Education.
  The tables used are:
  - Table A-1: $M_\text{air} = 28.97$ kg/kmol and $R = 0.2870$ kJ/(kg·K).
  - Table A-2a: $c_p = 1.005$ kJ/(kg·K) and $k = 1.4$ at 300 K.
  - Table A-2c: air $\bar c_p$ polynomial ($a$, $b$, $c$, $d$), valid for 273–1800 K with a maximum error of 0.72 %.
  - Table A-17: ideal-gas properties of air (validation).
  - Ch. 9: Brayton cycle.
  - Ch. 15: standard reference state.

[2] Lemmon, E. W., Jacobsen, R. T., Penoncello, S. G., & Friend, D. G. (2000). Thermodynamic properties of air and mixtures of nitrogen, argon, and oxygen from 60 to 2000 K at pressures to 2000 MPa. *Journal of Physical and Chemical Reference Data, 29*(3), 331–385. https://doi.org/10.1063/1.1285884

[3] Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and pseudo-pure fluid thermophysical property evaluation and the open-source thermophysical property library CoolProp. *Industrial & Engineering Chemistry Research, 53*(6), 2498–2508. https://doi.org/10.1021/ie4033999

[4] Goodwin, D. G., Speth, R. L., Moffat, H. K., & Weber, B. W. (n.d.). *Cantera: An object-oriented software toolkit for chemical kinetics, thermodynamics, and transport processes* [Computer software]. https://www.cantera.org
  **Action:** replace "(n.d.)" with the release year and add the Zenodo DOI of the installed version (`python -c "import cantera; print(cantera.__version__)"`, then look up that version on zenodo.org). The DOI is added on Day 2, when the adapter is written.

[5] McBride, B. J., Zehe, M. J., & Gordon, S. (2002). *NASA Glenn coefficients for calculating thermodynamic properties of individual species* (NASA/TP-2002-211556). NASA Glenn Research Center.

[6] Chase, M. W., Jr. (1998). NIST-JANAF thermochemical tables (4th ed.). *Journal of Physical and Chemical Reference Data, Monograph No. 9*.

[7] Saravanamuttoo, H. I. H., Rogers, G. F. C., Cohen, H., Straznicky, P. V., & Nix, A. C. (2017). *Gas turbine theory* (7th ed.). Pearson.
  Used for typical $\eta_c$, $\eta_t$ and $\Delta P_\text{comb}$ ranges, and kerosene LHV ≈ 43 MJ/kg.

[8] Tiesinga, E., Mohr, P. J., Newell, D. B., & Taylor, B. N. (2021). CODATA recommended values of the fundamental physical constants: 2018. *Reviews of Modern Physics, 93*, 025010. https://doi.org/10.1103/RevModPhys.93.025010
  Used for $R_u = 8.314462618$ J/(mol·K).

[9] Bejan, A. (2016). *Advanced engineering thermodynamics* (4th ed.). Wiley.
  Used for the entropy-generation formulation.

## Flagged values (not tied to [1]–[9])

The following values could not be tied to [1]–[9]. They are flagged here and are not given an invented source.

| Value | Where used | Issue |
|---|---|---|
| $P_\text{ref} = 101\,325$ Pa (1 atm) | `constants.P_REF` | Definitional (CGPM 1954). It is used in [1] Ch. 15, but the defining document is not in the list. |
| $T = 288.15$ K, $P = 101\,325$ Pa (sea-level ISA) | `constants.T_AMBIENT_ISA`, `P_AMBIENT_ISA`; Case B inputs | ISO 2533:1975 is not in the list. Add it as [10] if your grader requires a source. |
| Stoichiometric fuel-air ratio of kerosene, 0.068 | `constants.FAR_STOICH_KEROSENE` (upper bound on f in the combustor) | From general knowledge (about 1/14.7). The exact figure and page in [7] are still to be verified. |
| Default $\eta_c$, $\eta_t$, $\eta_\text{comb}$, $\Delta P_\text{comb}$ | `constants.*_DEFAULT` | These are attributed to [7], but the exact page or section is still to be recorded. |
| Table A-17 spot-check values | `validation_reference_data.json` | Transcribed without the printed table at hand. Verify them against your edition before Day 5. |
| Cantera version DOI | [4] | Depends on the installed version. |
| $T_\text{source} = T_3$, $T_\text{sink} = T_1$ | Second-law balance | These are modelling assumptions, not data. They are documented in `physics_formulation.md` §6. |

## Property data provenance

All backends share the same datum: h = 0 at $T_\text{ref} = 298.15$ K, and s = 0 at ($T_\text{ref}$, $P_\text{ref} = 101\,325$ Pa).

| Backend (`get_property_provider` name) | Correlation | Source | Validity range | Expected accuracy |
|---|---|---|---|---|
| `constant-cp` | Calorically perfect gas. $c_p = \gamma R/(\gamma-1)$ with defaults $c_p = 1005$ J/(kg·K) and $\gamma = 1.4$, so $R = 287.14$ J/(kg·K). | [1] Table A-2a (300 K) | Any T > 0. Physically meaningful only near 300 K. | Exact for the cold-air-standard model (REQ-N02). Against real air, $\Delta h$ is off by about 10 % from 300 K to 1500 K. |
| `variable-cp` | Cubic $\bar c_p(T)$ with $T$ in K. $h$ and $s^\circ$ are closed-form integrals. Inverses use `scipy.optimize.brentq` (bracket [273, 1800] K, xtol = 1e-12 K). | [1] Table A-2c; $M$ and $R$ from [1] Table A-1 | 273–1800 K. Outside this range it raises `ValueError`, or with `extrapolate=True` it warns and brackets [100, 3000] K. | Max $c_p$ error 0.72 % [1]. Measured against [1] Table A-17: $\Delta h$ ≤ 0.16 % and $\Delta s^\circ$ ≤ 0.28 % between 300, 1000 and 1500 K. |
| `coolprop` (optional) | Ideal-gas projection of the Lemmon et al. pseudo-pure air EOS. $h$ and $c_p$ are evaluated at $P_\text{ref}$, and $s = s(T, P_\text{ref}) - R\ln(P/P_\text{ref})$. | [2] EOS, [3] library | 60–2000 K [2] | EOS uncertainty is about 0.1–1 % in $c_p$ [2] (not re-verified here). The ideal-gas projection adds below 0.1 % for $P \le 1$ atm and $T \ge 273$ K. Cross-check tolerance against `variable-cp` is 1 %. |
| `cantera` (optional) | Frozen ideal-gas mixture N₂ 0.7812 / O₂ 0.2096 / Ar 0.0092 (the composition of air in [2]), using Cantera `air.yaml` species data. | [4] library; NASA 7-coefficient polynomials [5] (consistent with [6]) | Mechanism `min_temp`–`max_temp` (typically 200–3500 K). Enforced from the loaded file. | NASA fits reproduce JANAF tables to about 0.1 % [5] (not re-verified here). No dissociation is modelled. Cross-check tolerance against `variable-cp` is 1 %. |

**[FLAG]** The CoolProp and Cantera accuracy figures above are approximate values I recall from [2] and [5]. They are not quoted from a checked page, so verify them before citing. They have not been measured in this project either, because neither package was installed when Day 2 was built. The importorskip cross-checks in `tests/test_properties.py` measure them once the extras are installed.
