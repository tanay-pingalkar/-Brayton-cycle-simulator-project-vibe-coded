# User Guide

All numbers below are real output of version 0.1.0 (reference Case B unless noted).

## 1. GUI walkthrough

Start the GUI with `python main.py --gui` (or `brayton --gui`). It needs Tk; see the README if it reports
"GUI unavailable".

The window has an **input panel** on the left and **output tabs** on the right.

1. **Property backend.** Choose *Variable cp (Table A-2c)* (the default), *Constant cp (cold air)*, or an
   optional backend. If CoolProp or Cantera is not installed, a dialog tells you which `pip install`
   command to run.
2. **Combustor mode.** *Target T3* means you give T3 and the GUI computes f. *Fuel-air ratio f* means you
   give f and the GUI computes T3. The entry not used by the selected mode is greyed out.
3. **Inputs** are pre-filled with Case B, in display units:

   | Entry | Unit | Case B default |
   |---|---|---|
   | Inlet pressure P1 | kPa | 101.325 |
   | Inlet temperature T1 | K | 288.15 |
   | Pressure ratio r_p | - | 14 |
   | Turbine inlet T3 / fuel-air ratio f | K / - | 1500 / 0.0228 |
   | η_c, η_t, η_comb | - | 0.86, 0.89, 0.99 |
   | Combustor loss ΔP/P2 | - | 0.03 |
   | Mass flow ṁ | kg/s | 25 |
   | Fuel LHV | MJ/kg | 43 |

   A comma decimal (`0,86`) is accepted.
4. **Run** solves the cycle. The *Results* tab shows the station table and the KPIs. The *T-s*, *P-v* and
   *Energy audit* tabs show the figures, each with the Matplotlib zoom/pan/save toolbar. The status
   bar reads, for example, `Solved with variable-cp: η_th = 37.315 %, w_net = 362.685 kJ/kg`.
5. **Sweep** (with *min*, *max* and *points* set in the *Sweep r_p* box) runs a 1-D pressure-ratio sweep.
   It finds the optimal r_p for w_net and η_th, fills the optimum table in *Results*, and draws the
   *Sweep* tab (two stacked panels with the optima marked).
6. **Export report** asks for a folder and writes `report.md`, `report.json`, `ts.png`, `pv.png` and
   `energy_audit.png` for the last run.

**Errors** appear as dialogs and never crash the window:

| Situation | Dialog title | Example message |
|---|---|---|
| Unparseable or empty entry | Invalid input | `'Compressor η_c' must be a number, got 'abc'.` The field is focused and selected. |
| Value out of range | Invalid input | `eta_c must satisfy 0 < eta_c <= 1, got 1.3` |
| Outside the backend's validity range | Outside property range | `variable-cp: T = 2500 K is outside the Table A-2c validity range [273, 1800] K ...` |
| Optional package missing | Property backend not installed | `... pip install -e ".[coolprop]"` |
| Energy, mass or entropy audit failed | Conservation check failed | The residual, and a note to report the case |
| Export before any run | Nothing to export | `Run a case first, then export the report.` |

## 2. CLI examples

### Single case (reference Case B)

```text
$ python main.py --case B
Brayton cycle  [B_irreversible_variable_cp]  provider: variable-cp

Station      T [K]     P [kPa]   h [kJ/kg]  s [kJ/(kg·K)]
---------------------------------------------------------
      1     288.15     101.325     -10.028       -0.03421
     2s     603.39    1418.550     314.079       -0.03421
      2     653.09    1418.550     366.840        0.04981
      3    1500.00    1375.994    1338.797        1.00396
     4s     783.70     101.325     507.839        1.00396
      4     866.72     101.325     599.244        1.11481

---------------------------------------------------------
Compressor work w_c    376.868 kJ/kg
Turbine work w_t       739.553 kJ/kg
Net work w_net         362.685 kJ/kg
Heat input q_in        971.957 kJ/kg
Heat rejected q_out    609.272 kJ/kg
Back-work ratio        0.5096
Thermal efficiency     37.315 %
Fuel-air ratio f       0.02283
SFC                    0.2266 kg/kWh
Net power              9.0671 MW  (m_dot = 25 kg/s)
First-Law residual     1.20e-16  (limit 1e-6)
Total s_gen            1.46645 kJ/(kg·K)
```

### Ideal cold-air Case A (closed-form check)

```text
$ python main.py --case A --provider constant
...
Compressor work w_c    280.605 kJ/kg
Turbine work w_t       678.248 kJ/kg
Net work w_net         397.643 kJ/kg
Heat input q_in        824.895 kJ/kg
Heat rejected q_out    427.252 kJ/kg
Back-work ratio        0.4137
Thermal efficiency     48.205 %
Fuel-air ratio f       0.01918
SFC                    0.1737 kg/kWh
Net power              0.3976 MW  (m_dot = 1 kg/s)
First-Law residual     7.06e-17  (limit 1e-6)
Total s_gen            0.83496 kJ/(kg·K)
```

Here η_th equals 1 − 10^(−0.4/1.4) = 48.205 % exactly.

### Own configuration, report and figures

```bash
python main.py --config my_case.json --output-dir out --plots
# writes out/result.json, out/report.json, out/report.md, out/ts.png, out/pv.png, out/energy_audit.png
```

`my_case.json` holds `BraytonConfig` fields in SI units. Accepted aliases are `rp` for
`pressure_ratio`, `mdot` for `mass_flow`, `f`, `mode`, and `cp`/`k` (constant-cp options). For the
fuel-air-ratio mode, use `"combustor_mode": "fuel_air_ratio", "fuel_air_ratio": 0.0228` and omit `T3`.

### Pressure-ratio sweep with optima

```text
$ python main.py --case B --mode sweep --sweep-start 4 --sweep-stop 40 --sweep-num 7
 pressure_ratio  w_net [kJ/kg]  eta_th    bwr  SFC [kg/kWh] status
         4.0000       280.0389  0.2362 0.3685        0.3580     ok
        10.0000       357.0171  0.3444 0.4665        0.2456     ok
        16.0000       361.5700  0.3828 0.5279        0.2209     ok
        22.0000       351.1650  0.4013 0.5743        0.2108     ok
        28.0000       335.9802  0.4105 0.6122        0.2060     ok
        34.0000       319.1424  0.4144 0.6445        0.2041     ok
        40.0000       301.8587  0.4148 0.6729        0.2039     ok
optimal r_p for w_net : 13.8466  ->  362.691 kJ/kg
optimal r_p for eta_th: 37.7470  ->  41.497 %
```

`--sweep-param` can be any numeric config field (`T3`, `eta_c`, `T1`, …). Optima are reported only
for `pressure_ratio`. Infeasible points (for example T2 ≥ T3 at very high r_p) are listed with
status `infeasible: …` instead of stopping the run. With `--output-dir`, the table is saved as
`sweep.csv` (SI units), plus `sweep.png` with `--plots`.

### Errors and exit codes

```text
$ python main.py --case B --provider coolprop
BACKEND UNAVAILABLE: CoolProp backend requested but the 'CoolProp' package is not installed. Install it with: pip install -e ".[coolprop]"  (or pip install CoolProp)
$ echo $?
4
```

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Conservation or Second-Law audit failed |
| 2 | Usage error, or GUI requested without Tk |
| 3 | Invalid input or configuration |
| 4 | Optional backend not installed |

### Benchmarks

```bash
python main.py --benchmark            # = python run_verification_and_benchmarks.py
python benchmarks/run_benchmarks.py --skip-tests --repeats 3    # quick runtime + validation only
```

Results are written to `benchmarks/results/` and summarised in [validation_report.md](validation_report.md).

## 3. Python API

```python
from brayton_cycle.solver import BraytonConfig, BraytonSolver
from brayton_cycle.analysis import ParametricSweepEngine
from brayton_cycle.reporting import CyclePlotter

cfg = BraytonConfig.from_reference_case("B")                   # or BraytonConfig(...)/from_json(...)
res = BraytonSolver().solve(cfg)                               # BraytonResult (frozen)
res.eta_th, res.w_net, res.states["4"].T, res.s_gen["combustor"]
eng = ParametricSweepEngine()
df  = eng.sweep_rp(cfg)                                        # 30-point DataFrame
grid = eng.sweep_2d(cfg)                                       # 12 x 8 r_p x T3 grid
opt = eng.optimal_pressure_ratio(cfg, "w_net")                 # OptimumResult
CyclePlotter().ts_diagram(res).savefig("ts.png")               # every plot returns a Figure
```
