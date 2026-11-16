"""10-line demo: solve Case B, find the optimal r_p, write a report with figures."""
from brayton_cycle.analysis import ParametricSweepEngine
from brayton_cycle.reporting import ReportGenerator
from brayton_cycle.solver import BraytonConfig, BraytonSolver

cfg = BraytonConfig(T1=288.15, P1=101325, pressure_ratio=14, T3=1500, eta_c=0.86, eta_t=0.89,
                    eta_comb=0.99, dp_comb=0.03, mass_flow=25, provider="variable")
res = BraytonSolver().solve(cfg)
opt = ParametricSweepEngine().optimal_pressure_ratio(cfg, "eta_th")
print(f"eta_th = {res.eta_th:.2%}, W_net = {res.net_power/1e6:.2f} MW, best r_p = {opt.pressure_ratio:.1f}")
print(ReportGenerator().write_all(res, "demo_output", optima={"eta_th": opt})["markdown"])
