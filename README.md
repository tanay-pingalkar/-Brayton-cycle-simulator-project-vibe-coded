# Brayton_Cycle_Project

A modular Python 3.10+ simulator of the steady-flow, air-standard **Brayton gas-turbine cycle**
1 → 2 → 3 → 4 → 1 (Assignment 07). It covers the following:

- **Component losses:** compressor and turbine isentropic efficiencies, combustion efficiency, and combustor pressure loss.
- **Combustor modes:** a target-T3 mode and a fuel-air-ratio mode.
- **Interchangeable property backends:** constant-cp, variable-cp (Çengel Table A-2c), and optional CoolProp and Cantera.
- **Audits on every solve:** First-Law (residual < 1e-6), mass, and Second-Law (s_gen ≥ 0).
- **Analysis:** 1-D and 2-D sweeps, and optimal pressure ratio for net work and efficiency.
- **Output:** T-s, P-v, energy-audit, sweep and contour plots, plus JSON/Markdown reports.
- **Front ends:** a headless CLI and a decoupled Tkinter GUI.
- **Extension points:** typed blade-material and rotor-sizing hooks.

All results are checked against reference data from an **independent** hand-calculation script
(`tools/generate_reference.py`), so validation is not circular.

## Install

```bash
git clone <repo-url> Brayton_Cycle_Project && cd Brayton_Cycle_Project
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .                    # core: numpy, scipy, pandas, matplotlib
pip install -e ".[dev]"             # + pytest, pytest-cov
pip install -e ".[coolprop,cantera]"  # optional property backends
```

The GUI needs Tk, which ships with the python.org installers. On Debian/Ubuntu run
`sudo apt install python3-tk`.

## Quick start

```bash
python main.py --case B                         # reference Case B, variable cp
python main.py --case A --provider constant     # ideal cold-air Case A
python main.py --config my_case.json --output-dir out --plots   # report + PNG figures
python main.py --case B --mode sweep --sweep-start 2 --sweep-stop 40 --sweep-num 30
python main.py --gui                            # Tkinter GUI
python main.py --benchmark                      # tests + validation + runtime benchmarks
```

After `pip install -e .`, the same commands are available as `brayton ...`. Here is an example `my_case.json` (SI units):

```json
{"T1": 288.15, "P1": 101325, "pressure_ratio": 14, "T3": 1500,
 "eta_c": 0.86, "eta_t": 0.89, "eta_comb": 0.99, "dp_comb": 0.03,
 "mass_flow": 25, "lhv": 43e6, "provider": "variable"}
```

The library API, from `examples/demo.py`:

```python
from brayton_cycle.analysis import ParametricSweepEngine
from brayton_cycle.reporting import ReportGenerator
from brayton_cycle.solver import BraytonConfig, BraytonSolver

cfg = BraytonConfig(T1=288.15, P1=101325, pressure_ratio=14, T3=1500, eta_c=0.86, eta_t=0.89,
                    eta_comb=0.99, dp_comb=0.03, mass_flow=25, provider="variable")
res = BraytonSolver().solve(cfg)
opt = ParametricSweepEngine().optimal_pressure_ratio(cfg, "eta_th")
print(f"eta_th = {res.eta_th:.2%}, W_net = {res.net_power/1e6:.2f} MW, best r_p = {opt.pressure_ratio:.1f}")
print(ReportGenerator().write_all(res, "demo_output", optima={"eta_th": opt})["markdown"])
```

That prints `eta_th = 37.31%, W_net = 9.07 MW, best r_p = 37.7`. More examples are in
[docs/user_guide.md](docs/user_guide.md).

CLI exit codes:

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Conservation or Second-Law audit failed |
| 2 | Usage error, or Tk unavailable |
| 3 | Invalid input |
| 4 | Backend not installed |

## Tests, coverage, benchmarks

```bash
pytest                                   # whole suite (CoolProp/Cantera tests skip if absent)
pytest --cov=brayton_cycle --cov-report=term-missing     # needs pytest-cov
python tools/stdlib_coverage.py          # same figure with no extra packages (Python >= 3.12)
python run_verification_and_benchmarks.py   # = python main.py --benchmark
```

The benchmark harness writes `benchmarks/results/benchmark_results.{json,md}` and refreshes
[docs/validation_report.md](docs/validation_report.md). A run fails if any test fails, any validation
check is out of tolerance, or any runtime exceeds 10× the stored baseline (`benchmarks/baseline.json`).
Use `--update-baseline` after an intentional performance change.

## Project structure

```
Brayton_Cycle_Project/
├── brayton_cycle/
│   ├── core/           constants (cited), exceptions, State, PropertyProvider/Component ABCs
│   ├── properties/     constant-cp, variable-cp, CoolProp & Cantera adapters, registry
│   ├── components/     Compressor, Combustor (2 modes), Turbine, HeatRejection
│   ├── solver/         BraytonConfig, BraytonResult, BraytonSolver (audits)
│   ├── analysis/       ParametricSweepEngine (1-D, 2-D, optimal r_p)
│   ├── reporting/      CyclePlotter, ReportGenerator, display tables, citations
│   ├── gui/            controller.py (no tkinter) + app.py (Tkinter view)
│   ├── extensibility/  blade-material and rotor-sizing interfaces + stubs
│   └── cli.py          argparse CLI
├── tests/              pytest suite (+ tests/data/cengel_table_a17.csv)
├── benchmarks/         run_benchmarks.py, baseline.json, results/
├── tools/              generate_reference.py (independent), stdlib_coverage.py
├── docs/               physics_formulation, references, architecture, user_guide, validation_report
├── examples/demo.py    10-line demo
├── main.py · run_verification_and_benchmarks.py · validation_reference_data.json
└── PROJECT_BRIEF.md    scope, plan, design rules, requirements traceability matrix
```

## Assumptions and limitations

- **Air-standard cycle.** The working fluid is air at every station. The combustor adds heat
  $q_\text{in} = \eta_\text{comb} f\,\text{LHV}$ with **no composition change and no fuel-mass
  addition**. Real combustion products (higher $c_p$, $(1+f)\dot m$) would raise turbine work by a few per cent.
- **Steady flow, KE and PE neglected,** adiabatic compressor and turbine, no exhaust pressure loss ($P_4 = P_1$).
- **Ideal gas.** The CoolProp adapter is used as an ideal-gas projection at 1 atm.
- **Polynomial validity.** The variable-cp backend (Table A-2c) is valid for **273–1800 K**, with a
  maximum error of 0.72 %. Outside that range it raises an error, or warns with `extrapolate=True`.
- **Entropy generation.** Heat is exchanged with reservoirs at $T_\text{source} = T_3$ and
  $T_\text{sink} = T_1$ by default. This captures external heat-transfer irreversibility, not combustion chemistry.
- **Extensibility stubs.** The blade-material and rotor-sizing numbers are **illustrative placeholders**, not design data.
- **Flagged values.** Values without a checked source are flagged in `docs/references.md`. Examples are the
  ISA ambient state, the default efficiency page numbers in [7], f_stoich = 0.068, and the Table A-17 spot values.

Details: [docs/physics_formulation.md](docs/physics_formulation.md).

## Citing the property data

Every report states the backend used and its references. In publications, cite:

- **variable-cp / constant-cp:** Çengel, Y. A., Boles, M. A., & Kanoğlu, M. (2019). *Thermodynamics: An engineering approach* (9th ed.). McGraw-Hill Education. Tables A-1, A-2a, A-2c.
- **CoolProp:** Lemmon et al. (2000), *J. Phys. Chem. Ref. Data* 29(3), 331–385, https://doi.org/10.1063/1.1285884; and Bell et al. (2014), *Ind. Eng. Chem. Res.* 53(6), 2498–2508, https://doi.org/10.1021/ie4033999.
- **Cantera:** Goodwin et al., Cantera (cite the Zenodo DOI of your installed version); and McBride, Zehe & Gordon (2002), NASA/TP-2002-211556.

The full APA list is in [docs/references.md](docs/references.md).

## Documentation

| Document | Contents |
|---|---|
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | Scope, 6-day plan, design rules, requirements traceability matrix |
| [docs/physics_formulation.md](docs/physics_formulation.md) | Governing equations, assumptions, KPIs |
| [docs/architecture.md](docs/architecture.md) | Module dependencies, design patterns, how to extend |
| [docs/user_guide.md](docs/user_guide.md) | GUI walkthrough, CLI examples with output |
| [docs/validation_report.md](docs/validation_report.md) | Benchmark tables, coverage |
| [docs/references.md](docs/references.md) | References, flagged values, property-data provenance |
