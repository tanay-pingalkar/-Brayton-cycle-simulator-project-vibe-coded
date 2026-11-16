# Physics Formulation

Steady-flow, air-standard Brayton cycle with four stations
$1 \rightarrow 2 \rightarrow 3 \rightarrow 4 \rightarrow 1$
(compressor, combustor, turbine, heat rejection). All quantities are per unit
mass of air, in SI units (J/kg, J/(kg·K), K, Pa). Citation tags refer to
[`references.md`](references.md).

## 1. Assumptions

1. Steady flow, one inlet and one outlet per control volume (CV).
2. Kinetic- and potential-energy changes are neglected.
3. Compressor and turbine are adiabatic.
4. Air is an ideal gas at every station (air-standard). Fuel mass addition is
   ignored in the turbine mass flow; the fuel-air ratio $f$ is used only for the
   combustor energy balance, SFC, and fuel flow.
5. Heat is supplied from a source at $T_\text{source}$ and rejected to a sink at
   $T_\text{sink}$ (Section 6).
6. No exhaust pressure loss: $P_4 = P_1$.

**Documented limitation: air-standard combustor.** The combustor changes
neither composition nor mass flow. Real combustion products have a higher
$c_p$ and a lower $\gamma$, and the turbine mass flow is $(1+f)\dot m$. Both
effects raise the real turbine work above the air-standard value. The gap grows
with $f$; at $f \approx 0.023$ (Case B) the mass-flow effect alone is about 2 %.
The fuel-air ratio is limited to $0 < f \le f_\text{stoich}$ (about 0.068 for
kerosene; flagged in `constants.FAR_STOICH_KEROSENE`). Lifting this limitation
needs a products-aware provider, for example a Cantera adapter with an
equilibrium mixture. The `PropertyProvider` / `Component` interfaces allow that
without solver changes.

## 2. Steady-flow energy equation (SFEE) per CV

With KE and PE neglected [1, Ch. 5]:

$$
q - w = h_\text{out} - h_\text{in}
$$

Sign convention: $q > 0$ is heat added to the fluid and $w > 0$ is work done by
the fluid. `ComponentResult.energy_residual` evaluates
$(h_\text{out}-h_\text{in}) - (q - w)$ for every CV.

## 3. Components

### 3.1 Compressor (1 → 2)

$$
P_2 = r_p P_1,\qquad s(T_{2s},P_2) = s(T_1,P_1),\qquad
w_c = \frac{h_{2s}-h_1}{\eta_c},\qquad h_2 = h_1 + w_c
$$

### 3.2 Combustor (2 → 3)

$$
P_3 = P_2\,(1-\Delta P_\text{comb}),\qquad
q_\text{in} = h_3 - h_2 = \eta_\text{comb}\, f\, \text{LHV}
$$

The combustor has two modes (REQ-F02):

- **Target-T3 mode:** $T_3$ is given, so $f = (h_3-h_2)/(\eta_\text{comb}\,\text{LHV})$.
- **Fuel-air-ratio mode:** $f$ is given, so $h_3 = h_2 + \eta_\text{comb} f\,\text{LHV}$ and $T_3 = T(h_3)$.

### 3.3 Turbine (3 → 4)

$$
s(T_{4s},P_4) = s(T_3,P_3),\qquad
w_t = \eta_t\,(h_3 - h_{4s}),\qquad h_4 = h_3 - w_t
$$

### 3.4 Heat rejection (4 → 1)

$$
q_\text{out} = h_4 - h_1
$$

## 4. Property models

### 4.1 Constant cp (cold-air standard)

$$
h(T) = c_p (T - T_\text{ref}),\qquad
s^\circ(T) = c_p \ln\frac{T}{T_\text{ref}}
$$

with $c_p = 1005$ J/(kg·K) and $k = 1.4$ [1, Table A-2a]. For exact isentropic
self-consistency, the cold-air backend uses $R = c_p(1-1/k) = 287.14$ J/(kg·K).
This differs from the Table A-1 value of 287.0 J/(kg·K) by 0.05 %.

### 4.2 Variable cp (Table A-2c polynomial)

$$
\bar c_p(T) = a + bT + cT^2 + dT^3 \quad[\text{kJ/(kmol·K)}],\; T \text{ in K}
$$

with $a = 28.11$, $b = 0.1967\times10^{-2}$, $c = 0.4802\times10^{-5}$ and
$d = -1.966\times10^{-9}$. The correlation is valid for 273–1800 K with a
maximum error of 0.72 % [1, Table A-2c]. The coefficients are used **as
published, with T in kelvin**; no $T/1000$ scaling is applied. The analytical
integrals are:

$$
h(T) = \frac{1}{M}\left[a(T-T_r) + \tfrac{b}{2}(T^2-T_r^2) + \tfrac{c}{3}(T^3-T_r^3) + \tfrac{d}{4}(T^4-T_r^4)\right]
$$

$$
s^\circ(T) = \frac{1}{M}\left[a\ln\frac{T}{T_r} + b(T-T_r) + \tfrac{c}{2}(T^2-T_r^2) + \tfrac{d}{3}(T^3-T_r^3)\right]
$$

$$
s(T,P) = s^\circ(T) - R\ln\frac{P}{P_\text{ref}}
$$

where $T_r = T_\text{ref} = 298.15$ K, $P_\text{ref} = 101\,325$ Pa, $M = 28.97$ kg/kmol and $R = 287.0$ J/(kg·K) [1, Tables A-1, A-2c].
The inverse functions $T(h)$ and $T(s,P)$ are found with a bracketed root finder.

### 4.3 CoolProp and Cantera (optional adapters)

The CoolProp adapter uses the Lemmon et al. pseudo-pure air EOS [2][3]. The
Cantera adapter uses NASA-polynomial species data [4][5]. Both adapters are
re-referenced to $(T_\text{ref}, P_\text{ref})$ so that backends can be swapped
without changing results beyond model differences.

## 5. Key performance indicators

$$
w_\text{net} = w_t - w_c,\qquad
\text{BWR} = \frac{w_c}{w_t},\qquad
\eta_\text{th} = \frac{w_\text{net}}{q_\text{in}}
$$

$$
\text{SFC} = \frac{3.6\times10^{6}\, f}{w_\text{net}}\;[\text{kg/kWh}],\quad w_\text{net}\text{ in J/kg}
$$

$$
\dot W_\text{net} = \dot m\, w_\text{net},\qquad \dot m_f = \dot m\, f
$$

## 6. Second Law: entropy generation

The entropy balance for a steady-flow CV that exchanges heat $q$ with a
reservoir at $T_b$ is [9]:

$$
s_\text{gen} = (s_\text{out} - s_\text{in}) - \frac{q}{T_b} \;\ge 0
$$

| CV | $s_\text{gen}$ |
|---|---|
| Compressor | $s_2 - s_1$ |
| Combustor | $(s_3 - s_2) - q_\text{in}/T_\text{source}$ |
| Turbine | $s_4 - s_3$ |
| Heat rejection | $(s_1 - s_4) + q_\text{out}/T_\text{sink}$ |

> **Assumption.** By default, $T_\text{source} = T_3$ (the maximum cycle
> temperature) and $T_\text{sink} = T_1$ (ambient). These are the most
> favourable reservoir temperatures that still give $s_\text{gen} \ge 0$
> for any heat addition between $T_2$ and $T_3$. The values therefore
> include the external irreversibility of heat transfer across a finite
> $\Delta T$, but no combustion (chemical) irreversibility. Both reservoir
> temperatures are user-overridable. Runs fail with `SecondLawViolation` if
> $s_\text{gen} < -10^{-9}$ J/(kg·K). Constructors reject $T_\text{source} < T_3$
> and $T_\text{sink} > T_1$, because heat cannot flow up the temperature gradient.

The cycle total reduces to
$s_\text{gen,tot} = q_\text{out}/T_\text{sink} - q_\text{in}/T_\text{source}$.

## 7. First-Law residual (REQ-N01)

$$
\varepsilon = \frac{\left|(q_\text{in} - q_\text{out}) - w_\text{net}\right|}{q_\text{in}} < 10^{-6}
$$

## 8. Cold-air limit (REQ-N02)

With $\eta_c = \eta_t = 1$, $\Delta P_\text{comb} = 0$ and constant $c_p, k$
[1, Ch. 9]:

$$
\eta_\text{th} = 1 - r_p^{(1-\gamma)/\gamma},\qquad
\frac{T_2}{T_1} = \frac{T_3}{T_4} = r_p^{(\gamma-1)/\gamma}
$$

## 9. Optimum pressure ratio for net work (ideal cycle, REQ-A01)

Setting $\partial w_\text{net}/\partial r_p = 0$ in the ideal cold-air cycle gives
$T_2 = T_4 = \sqrt{T_1 T_3}$. Then:

$$
r_{p,\text{opt}}(w_\text{net}) = \left(\frac{T_3}{T_1}\right)^{\gamma/(2(\gamma-1))},\qquad
w_\text{net,max} = c_p\left(\sqrt{T_3} - \sqrt{T_1}\right)^2
$$

For the ideal cycle, $\eta_\text{th}$ increases monotonically with $r_p$. Its
practical maximum is bounded by $T_2 \le T_3$, that is,
$r_p \le (T_3/T_1)^{\gamma/(\gamma-1)}$, where $w_\text{net} \to 0$. For the
non-ideal cycle, both optima are found numerically (Day 3).
