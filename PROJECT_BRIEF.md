# Brayton_Cycle_Project — Project Brief (Assignment 07)

## 1. Scope

This project is a modular Python 3.10+ simulator of the steady-flow,
air-standard Brayton gas-turbine cycle 1→2→3→4→1. It covers the following:

- Real-component losses: $\eta_c$, $\eta_t$, $\eta_\text{comb}$ and $\Delta P_\text{comb}$.
- A combustor with a target-T3 mode and a fuel-air-ratio mode.
- Four interchangeable property backends: constant-cp, variable-cp, CoolProp (optional) and Cantera (optional).
- First- and Second-Law audits.
- 1-D and 2-D parameter sweeps with optimal-$r_p$ search.
- Plots and JSON/Markdown reports.
- A headless CLI and a decoupled Tkinter GUI.
- Typed extensibility hooks for blade materials and rotor sizing.
- A pytest suite, validation and runtime benchmarks, and full documentation.

**Out of scope:** off-design and transient operation, combustion chemistry and
equilibrium beyond $q_\text{in} = \eta_\text{comb} f\,\text{LHV}$,
regeneration/intercooling/reheat (possible later through the `Component` ABC),
and blade cooling.

## 2. Six-day plan

| Day | Deliverables | REQs closed |
|---|---|---|
| 1 | This brief, repository skeleton, packaging, physics formulation, references and constants, independent reference data (Cases A/B), core `State` / `PropertyProvider` / `Component` | D01 (part), V01 (part) |
| 2 | `properties/`: constant-cp, variable-cp, CoolProp and Cantera adapters, registry; property tests | T01 |
| 3 | `components/`: compressor, combustor (2 modes), turbine, heat rejection; `core/exceptions.py`; component tests | F02, T02 |
| 4 | `solver/` (BraytonConfig / BraytonResult / BraytonSolver with First-Law and mass audits); `analysis.sweep_1d`; CLI (`brayton_cycle/cli.py`, `main.py`); `extensibility/` material and rotor stubs; end-to-end validation against Cases A/B | F01, N01, N02, E01, U01 (CLI) |
| 5 | `reporting/` T-s, P-v, energy-audit and sweep plots plus JSON/MD reports; `analysis` 2-D sweep and optimal $r_p$ for $w_\text{net}$ and $\eta_\text{th}$; `gui/` Tkinter front-end (MVC, no physics) | R01, A01, U01 (GUI) |
| 6 | `benchmarks/run_benchmarks.py` (verification, validation, runtime with 10× regression rule); README, architecture, user guide, validation report; Google-style docstrings; coverage audit (97.7 % non-GUI); final traceability audit | V01, D01 |

> Re-planned on Day 3, adjusted on Day 4 (extensibility pulled forward to Day 4, 2-D sweep and optimum moved to Day 5): components moved from Day 2 to Day 3, so each later block shifts one day and Days 5–6 are denser. If time runs short, the cut order is: the 2-D sweep's contour plot (keep the data), then GUI styling. No mandatory REQ is dropped.

## 3. Design rules

1. **Strict separation of concerns.** The dependency direction is
   `core ← properties ← components ← solver ← analysis ← reporting ← {cli, gui}`.
   No layer imports from a layer to its right.
2. **No thermodynamic equations in `gui/`.** The GUI only collects inputs,
   calls the public solver/analysis API, and displays results. `gui/app.py` (view)
   talks only to `gui/controller.py`. Enforced by `tests/test_architecture.py`, which
   scans `gui/*.py` for forbidden imports, `**`, math functions and arithmetic on
   thermodynamic identifiers, and also checks the package layering below.
3. **Single source of truth for constants.** Every physical constant and
   property correlation lives in `brayton_cycle/core/constants.py` with an
   inline citation tag `[n]` that resolves in `docs/references.md`. Values
   without a source are marked `[FLAG: …]` instead of being given an invented source.
4. **SI internally:** K, Pa, J/kg and J/(kg·K). Unit conversion happens only at
   the I/O edges (CLI, GUI, reports).
5. **Immutable data.** `State` and `ComponentResult` are frozen dataclasses,
   and components are stateless.
6. **Validation is non-circular.** Reference data comes from
   `tools/generate_reference.py`, which uses only the standard library, never
   imports `brayton_cycle`, and re-types its inputs from the primary sources.
7. **Optional backends degrade gracefully.** CoolProp and Cantera are imported
   lazily. If missing, they raise a clear `BackendUnavailable` error, and their
   tests are skipped via pytest markers.
8. **Strict typing and docstrings** on every public symbol.
9. **Sign conventions:** $w > 0$ is work done by the fluid, $q > 0$ is heat added to the fluid, and $s_\text{gen} \ge 0$ is enforced.

## 4. Repository layout

```
Brayton_Cycle_Project/
├── brayton_cycle/
│   ├── core/            constants, exceptions, State, PropertyProvider, Component
│   ├── properties/      property backends
│   ├── components/      compressor, combustor, turbine, heat rejection
│   ├── solver/          cycle assembly, KPIs, audits
│   ├── analysis/        sweeps, optimisation
│   ├── reporting/       plots, JSON/Markdown
│   ├── gui/             Tkinter (presentation only)
│   └── extensibility/   blade-material and rotor-sizing interfaces
├── tests/  benchmarks/  docs/  tools/
├── main.py (thin wrapper around brayton_cycle/cli.py)  pyproject.toml  requirements.txt
└── validation_reference_data.json
```

## 5. Requirements Traceability Matrix

Final audit (Day 6): 440 tests pass and 84 are skipped (all skips are CoolProp/Cantera tests,
which need the optional packages). Line coverage is 97.2 % overall and 97.7 % for non-GUI code
(`tools/stdlib_coverage.py`; see `docs/validation_report.md`). Every non-GUI subpackage is
≥ 96.9 %; the top-level `cli.py` is 91.7 % and `gui/` is 94.9 %. The 80 % target is met everywhere.
Validation: 68/68 checks pass. `test_docs.py::test_rtm_test_names_exist` verifies that every test named below exists.

Status: ✅ done · 🟡 partial.

| ID | Requirement | Module(s) | Covering test(s) | Status |
|---|---|---|---|---|
| REQ-F01 | 4-station cycle 1→2→3→4→1 | `components/*`, `solver/solver.py` | `test_solver_validation.py::test_case_A_ideal_cold_air`, `test_solver_validation.py::test_case_B_irreversible_variable_cp`, `test_components.py::test_component_chain_matches_reference`, `test_components.py::test_heat_rejection_closes_cycle` | ✅ |
| REQ-F02 | Combustor in target-T3 **and** fuel-air-ratio mode | `components/combustor.py` (`CombustorMode`) | `test_components.py::test_combustor_mode_roundtrip`, `test_components.py::test_combustor_energy_balance`, `test_solver_validation.py::test_case_B_fuel_air_ratio_mode_reproduces_T3`, `test_gui_controller.py::test_fuel_air_ratio_mode_round_trip` | ✅ |
| REQ-T01 | Constant-cp, variable-cp, CoolProp, Cantera backends | `properties/*`, `properties/registry.py` | `test_properties.py::test_mayer_relation`, `test_properties.py::test_cp_is_derivative_of_h`, `test_properties.py::test_isentropic_roundtrip`, `test_properties.py::test_variable_cp_vs_table_a17`, `test_properties.py::test_cross_backend_delta_h` (skips without packages), `test_property_adapters_stub.py::test_inverse_roundtrip`, `test_properties.py::test_registry_open_closed_extension` | ✅ (real CoolProp/Cantera cross-check not yet run, see gaps) |
| REQ-T02 | η_c, η_t, η_comb, ΔP_comb; s_gen ≥ 0 | `components/*`, `core/interfaces.py`, `core/exceptions.py` | `test_components.py::test_compressor_sgen_positive`, `test_components.py::test_turbine_sgen_positive`, `test_components.py::test_isentropic_when_eta_one`, `test_components.py::test_pressure_loss_formula`, `test_components.py::test_invalid_constructor_inputs`, `test_core.py::test_negative_sgen_raises` | ✅ |
| REQ-N01 | First-Law residual < 1e-6 | `solver/solver.py` (`_audit`), `core.constants.FIRST_LAW_RESIDUAL_TOL` | `test_solver_validation.py::test_first_law_residual_random`, `test_solver_validation.py::test_conservation_error_raised_when_tolerance_unmeetable`, `test_cli.py::test_conservation_error_exit_code`, `test_gui_controller.py::test_run_maps_conservation_error` | ✅ |
| REQ-N02 | Cold-air limit η_th = 1 − r_p^((1−γ)/γ) | `properties/constant_cp.py`, `solver/` | `test_solver_validation.py::test_cold_air_limit_efficiency`, `test_reference_data.py::test_case_A_matches_closed_form`, `test_properties.py::test_constant_cp_reproduces_cold_air_isentrope` | ✅ |
| REQ-A01 | 1-D and 2-D sweeps; optimal r_p for w_net and η_th | `analysis/sweep.py` (`ParametricSweepEngine`) | `test_analysis.py::test_optimal_rp_w_net_matches_analytical`, `test_analysis.py::test_real_cycle_eta_optimum_is_interior_and_above_w_net_optimum`, `test_analysis.py::test_sweep_rp_shape_and_columns`, `test_analysis.py::test_sweep_2d_shape_and_columns`, `test_analysis.py::test_optimum_survives_infeasible_region` | ✅ |
| REQ-R01 | T-s, P-v, energy-audit, sweep plots; JSON/Markdown reports | `reporting/*` | `test_reporting.py::test_ts_diagram_axes`, `test_reporting.py::test_pv_diagram_axes_and_log_scale`, `test_reporting.py::test_energy_audit_axes`, `test_reporting.py::test_sweep_plot_one_panel_per_kpi_no_twin_axes`, `test_reporting.py::test_contour_axes_and_colorbar`, `test_reporting.py::test_write_all_creates_parseable_files` | ✅ |
| REQ-U01 | CLI + decoupled GUI | `cli.py`, `main.py`, `gui/controller.py`, `gui/app.py` | `test_cli.py::test_single_case_B_table`, `test_cli.py::test_subprocess_main_py`, `test_gui_controller.py::test_solve_round_trip_matches_reference`, `test_gui_app_smoke.py::test_app_builds_and_runs`, `test_architecture.py::test_gui_has_no_thermodynamics`, `test_architecture.py::test_gui_view_talks_only_to_controller` | ✅ (real-window run pending, see gaps) |
| REQ-E01 | Typed blade-material and rotor-sizing interfaces | `extensibility/materials.py`, `extensibility/rotor.py` | `test_extensibility.py::test_material_selector_returns_typed_dto`, `test_extensibility.py::test_rotor_sizing_returns_typed_dto`, `test_extensibility.py::test_custom_selector_plugs_in` | ✅ (stub numbers are illustrative) |
| REQ-V01 | Tests + validation + runtime benchmarks | `tests/`, `benchmarks/run_benchmarks.py`, `tools/generate_reference.py`, `tools/stdlib_coverage.py` | `test_benchmarks.py::test_validation_all_rows_pass`, `test_benchmarks.py::test_regression_rule_only_fires_above_factor`, `test_benchmarks.py::test_main_writes_results`, `test_reference_data.py::test_generator_is_reproducible` | ✅ |
| REQ-D01 | Documentation | `README.md`, `docs/*`, Google-style docstrings | `test_docs.py::test_constant_reference_tag_resolves`, `test_docs.py::test_every_public_callable_has_docstring`, `test_docs.py::test_google_style_args_sections`, `test_docs.py::test_docs_exist`, `test_docs.py::test_architecture_examples_run`, `test_examples.py::test_demo_script_runs`, `test_reporting.py::test_citations_consistent_with_references_md` | ✅ |

## 6. Remaining gaps

These are stated plainly; none blocks a mandatory requirement, but each is unverified or simplified.

1. **CoolProp and Cantera were never run against the real libraries.** The packages could not be installed in the build environment (no network). The adapter code is exercised against stand-in modules (`test_property_adapters_stub.py`). The 84 real cross-checks skip until you run `pip install -e ".[coolprop,cantera]"`; then run `pytest` and `python main.py --benchmark`.
2. **The Tkinter window was never opened.** The build environment has no Tk. The controller is tested directly and the view's wiring against a stand-in Tk (`test_gui_app_smoke.py`), but layout and rendering need one manual `python main.py --gui` on a machine with Tk.
3. **Coverage tool.** pytest-cov was unavailable, so the figures come from `tools/stdlib_coverage.py` (`sys.monitoring`, the same executable-line source coverage.py uses). Expect `pytest --cov=brayton_cycle` to agree within a few per cent. Code run only in subprocesses (the `main.py` smoke tests) is not counted.
4. **Flagged data (`docs/references.md`).** Still to verify: the Table A-17 spot values (transcribed without the printed table), the page numbers in [7] for the default efficiencies, f_stoich = 0.068, the ISA ambient state (ISO 2533 not in the list), the Cantera version DOI, and the CoolProp/Cantera accuracy figures in the provenance table.
5. **Physics simplifications (by design).** The cycle is air-standard (no products, no fuel mass), the combustor uses T_source = T3, and the extensibility stubs use illustrative numbers. `docs/physics_formulation.md` §1 quantifies the air-standard error at about 2 % in turbine work for Case B.
6. **Runtime baseline** (`benchmarks/baseline.json`) was recorded on the build machine (2 CPU, Python 3.13). On a much slower machine, regenerate it with `--update-baseline` before relying on the 10× rule.
