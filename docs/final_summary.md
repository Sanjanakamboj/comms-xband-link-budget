# COMMS-03 — Final Technical Summary

A compact reference for interview/portfolio review. For full depth, see
the milestone-specific docs this summarizes:
`link_budget_equations.md`, `baseline_scenario.md`, `verification.md`,
`trade_study.md`, `uncertainty_analysis.md`.

## Baseline scenario

Representative lunar-distance X-band downlink: a small spacecraft in a
highly elliptical orbit (e.g. NRHO-class) downlinking to a ~12 m
non-DSN-class ground station, evaluated at worst-case (maximum) range
(402,000 km). Every parameter is either a physical constant, a derived
quantity, or a labeled representative engineering assumption — see
`docs/baseline_scenario.md` for the parameter-by-parameter justification.
This is a study scenario, not a real mission's link budget.

## Headline equations

```
EIRP [dBW] = Pt[dBW] − Lt,line − Lt,point + Gt[dBi]
L_fs [dB]  = 20·log10(4πRf/c)                       (free-space path loss)
Pr [dBW]   = EIRP − L_fs − L_atm − L_other + Gr[dBi] − Lr,line − Lr,point
N0 [dBW/Hz]= 10·log10(k_B) + 10·log10(T_sys)
C/N0 [dB-Hz] = Pr − N0
Eb/N0 [dB] = C/N0 − 10·log10(Rb)
Margin [dB]= Eb/N0 − (Eb/N0)_req − L_impl
```

Every dB-domain term above enters `Margin` with a coefficient of exactly
±1 (gains/power at +1, losses/noise/required-Eb/N0 at −1); range and data
rate enter through `20·log10(R)` and `10·log10(Rb)` respectively. This
linearity is the basis for every closed-form inversion and every
analytical sensitivity in the project — nothing here needed numerical
root-finding.

## Verification evidence

- Free-space path loss: SI (meters/Hz) form vs. the independent km/MHz
  closed form agree to ~2 millidB across LEO-to-lunar ranges.
- Thermal noise floor: `k_B·T_sys` vs. the classic "−228.6 dBW/Hz/K"
  reference figure agree to <1 millidB.
- Full link closure: library `compute()` vs. an independently-written
  hand calculation agree to floating-point precision (1e-9 dB).
- Every inverse-design helper (required power, required Tx/Rx gain,
  required dish diameter, max data rate) is round-tripped: solve, plug
  back into the forward budget, confirm the target margin is hit exactly.
- Monte Carlo engine: exact equivalence with `LinkBudget.compute()` at
  zero uncertainty and at arbitrary sampled points (not just the mean).

## Deterministic trade results (worst-case range, nominal hardware)

| Result | Value |
|---|---:|
| Nominal margin | +1.484 dB |
| Max data rate, 0 dB margin | 2.81 Mbps (∝ R⁻²) |
| Required Tx power, 0 dB / +3 dB margin | 2.84 W / 5.67 W |
| Required ground dish, 0 dB / +3 dB margin | 9.11 m / 12.87 m |
| Margin sensitivity | +1 dB per dB of Pt/Gt/Gr; −20 dB/decade range; −10 dB/decade data rate |

## Probabilistic results (representative uncertainty model, N=10,000, seed 42)

| Result | Value |
|---|---:|
| Mean margin / σ | +1.341 dB / 0.664 dB |
| Analytical (linearized) σ | 0.667 dB (0.5% from MC) |
| P(margin > 0 dB) | 97.8% (95% Wilson CI: 97.5-98.1%) |
| 5th / 1st percentile margin | +0.246 dB / −0.205 dB |
| Data rate for ~95% closure | ~2.08 Mbps |
| Nominal margin needed for 95% / 99% closure | +1.26 dB / +1.71 dB |
| Top variance contributors | Tx gain, Rx gain, misc. loss, required Eb/N0 — tied ~20% each |

**The central finding**: +1.48 dB of nominal margin is real but not
absolute — it is enough to clear a 95%-closure design bar under
representative uncertainty, but not enough for 99%. Reporting margin
without its probability of closure understates design risk.

## Limitations

Not modeled: atmospheric/rain fade, elevation-dependent loss, weather
availability, pass geometry/occultation, coding-family BER/FER curves,
Doppler, link-layer retransmission, hardware reliability, correlated
uncertainty, or range uncertainty (range is a controlled sweep variable
throughout). See `docs/uncertainty_analysis.md` §17 and
`docs/trade_study.md` §13 for the full itemized scope boundary.

## Key design insights

1. Nominal margin and closure probability are different questions —
   report both.
2. Spacecraft power and ground aperture are fungible against each other
   for a given margin target; the right split is a cost/schedule
   decision, not a physics one.
3. Margin degrades predictably and steeply with range (∝ R⁻² in max data
   rate) — worst-case range, not average range, should drive design.
4. When uncertainty is spread across several comparable sources, adding
   hardware margin is usually more effective than tightening any single
   calibration uncertainty.
