# Milestone 2 — Trade-Study Methodology

This document covers the reusable trade-study layer (`src/xband_link/trades.py`,
`src/xband_link/antennas.py`) added in Milestone 2, the inverse-design
equations, the analytical sensitivities, and the scope boundary for this
milestone. It builds directly on `docs/link_budget_equations.md` and
`docs/baseline_scenario.md` (Milestone 1) — nothing there changed.

## 1. Design principle: no reimplemented physics

Every sweep in `trades.py` either (a) builds a modified copy of a
`LinkBudget` via `dataclasses.replace()` and calls its already-verified
`compute()` / inverse methods, or (b) — for the two relationships that are
*exactly* linear in the dB domain (range and data rate against margin) —
evaluates the closed form directly using a single `compute()` call's
`C/N0`, for speed on large sweeps/grids. In both cases the RF equations
themselves live only in `propagation.py`, `noise.py`, and `link_budget.py`.
`tests/test_trades.py` cross-checks every fast/closed-form path against the
slower per-point `compute()` path at sample grid locations.

## 2. Why margin is linear in the dB domain

Every term in the link-budget chain (`docs/link_budget_equations.md`)
enters `margin_db` as a sum or difference of dB quantities:

```
margin = Pt[dBW] - Lt_line - Lt_point + Gt - FSPL - L_atm - L_other
         + Gr - Lr_line - Lr_point - N0[dBW/Hz] - 10log10(Rb)
         - Eb/N0_req - L_impl
```

This is why:
- transmit power, both antenna gains, and receive gain each have a
  **coefficient of exactly +1 dB/dB**;
- every named loss term has a coefficient of **exactly -1 dB/dB**;
- range enters only through FSPL = `20*log10(R) + const`, so margin falls
  by **exactly 20 dB per decade of range**;
- data rate enters only through `-10*log10(Rb)`, so margin falls by
  **exactly 10 dB per decade of data rate**.

None of the inverse-design helpers below need a numerical root-find as a
result — every one is a closed-form consequence of this linearity.

## 3. Inverse-design helpers

All implemented as methods on `LinkBudget` (`link_budget.py`) or as small
compositions in `trades.py`:

| Helper | Equation | Location |
|---|---|---|
| Required Tx power | `Pt_req[dBW] = Pt[dBW] + (M_target - M_current)` | `LinkBudget.required_tx_power_w_for_margin` |
| Required Tx antenna gain | `Gt_req = Gt + (M_target - M_current)` | `LinkBudget.required_tx_gain_dbi_for_margin` |
| Required Rx antenna gain | `Gr_req = Gr + (M_target - M_current)` | `LinkBudget.required_rx_gain_dbi_for_margin` |
| Max data rate | `Rb,max = 10^((C/N0 - Eb/N0_req - L_impl - M_target)/10)` | `LinkBudget.max_data_rate_for_margin` (Milestone 1) |
| Required ground-dish diameter | `Gr_req` above, then invert the aperture-gain relation | `trades.required_ground_dish_diameter_for_margin` |

**Verification**: every helper is round-tripped in
`tests/test_link_budget_inverse.py` and `tests/test_trades.py` — compute the
required value, build a fresh forward `LinkBudget` from it, recompute, and
assert the resulting margin matches the requested target to `1e-6`-`1e-8` dB.

## 4. Parabolic-dish aperture-gain model

`antennas.py` implements the standard idealized uniform-illumination
aperture relation, used **only for the ground-station receive antenna**:

```
G [dBi] = 10*log10(eta) + 20*log10(pi*D*f/c)
```

Doubling `D` therefore adds exactly `20*log10(2) = 6.0206 dB` of gain, and
(since `Rb,max` depends on `C/N0` which depends on `Gr` at +1 dB/dB, and
`Rb,max` scales as `10^(C/N0/10)`) quadruples the zero-margin maximum data
rate. Both are checked directly in `tests/test_trades.py` and printed by
`scripts/run_trade_study.py`.

**The spacecraft transmit antenna is deliberately *not* modeled as a
dish.** `Transmitter.antenna_gain_dbi` is treated purely as an electrical
gain requirement — Milestone 2's antenna-gain trade (Section 5,
`required_tx_gain_dbi_for_margin`) reports only the dBi figure needed to
close the link, without implying the spacecraft antenna is a parabolic
reflector (in practice it could be a horn, patch array, or small
gimbaled reflector).

## 5. Range and data-rate sweeps

`sweep_range` and `sweep_data_rate` hold everything else fixed and report
the full intermediate chain (FSPL/C/N0/Eb/N0/margin for range;
Eb/N0/margin for data rate). Both are checked against the `-20 dB/decade`
and `-10 dB/decade` scaling laws directly (`scripts/run_trade_study.py`
Section 1-2 asserts this numerically at runtime, not just in the test
suite).

## 6. Maximum data rate vs. range and the R⁻² law

`max_data_rate_vs_range` calls the closed-form `max_data_rate_for_margin`
at each range point. Because `C/N0[dB-Hz] = ... - 20*log10(R) + const` and
`Rb,max = 10^(C/N0/10 - const')`, doubling range divides `Rb,max` by
exactly 4 (`R⁻²` in linear units). Verified to `1e-6` relative tolerance in
both the test suite and the trade-study script's runtime assertion.

## 7. Closure map M(R, Rb)

`closure_map` builds the 2D margin grid as an *outer sum* in the dB
domain: `C/N0(range)` is computed once per range value (data rate is
irrelevant to C/N0), then `margin[i,j] = C/N0[i] - 10log10(Rb[j]) -
Eb/N0_req - L_impl`. This is algebraically exact (not an approximation)
and is cross-checked point-by-point against full `LinkBudget.compute()`
calls in `tests/test_trades.py`.

**Reading the map (Figure 2)**: the heavy black contour is the **feasible
design boundary** — the locus of (range, data rate) pairs that close the
link with exactly 0 dB margin. Blue (positive margin) is inside/left of
the boundary; red (negative margin) is outside/right. The color scale is
symmetric about zero (a diverging colormap centered on 0 dB) specifically
so the zero crossing is never hidden inside a single-hue gradient.

## 8. Joint hardware trade M(Pt, D_ground)

`joint_power_dish_trade` answers: *how much spacecraft RF power can be
traded against ground-station aperture for the same worst-case margin?*
Both axes enter margin at +1 dB/dB in their respective dB-domain
transforms (`10log10(Pt)` and `20log10(D)`), so the grid is again an exact
outer sum, not a nested numerical sweep — verified against direct
`compute()` calls at sample points.

Spacecraft power and ground-station aperture were chosen for the joint
trade (over, e.g., power vs. spacecraft antenna gain) because they map to
two genuinely different **subsystems and cost drivers** — a smallsat power
budget vs. ground-segment procurement/access — making the trade a
realistic systems-engineering question rather than two knobs on the same
box.

## 9. Analytical sensitivities

| Quantity | ∂Margin/∂X |
|---|---|
| Tx power [dBW] | +1 dB/dB |
| Tx antenna gain [dBi] | +1 dB/dB |
| Rx antenna gain [dBi] | +1 dB/dB |
| Any named loss [dB] | -1 dB/dB |
| log10(Range) | -20 |
| log10(Data rate) | -10 |

`trades.finite_difference_slope` computes a central-difference numerical
derivative of `margin_db` with respect to any of these, and
`tests/test_trades.py` verifies each analytical value against its
finite-difference estimate to `1e-4`-`1e-6` absolute tolerance. This is a
useful regression check: if a future change to the link equations breaks
this linearity (e.g. adding a nonlinear coding-gain curve), these tests
will catch it immediately.

## 10. Worst-case-range interpretation

All hardware trades (power, gain, ground dish, joint trade) are evaluated
**at the baseline's worst-case range** (402,000 km, Milestone 1). This is
deliberate: a design that only has to close the link at typical range is
not stress-tested for the mission's hardest operating point. Any margin
reported in this milestone's tables/figures/report is therefore the margin
available at the worst point in the orbit, not an average or best-case
figure — see `docs/baseline_scenario.md` for why 402,000 km was chosen as
representative.

## 11. Table assumptions

`results/trade_study_table.md` / `.csv` hold representative worst-case-range
design options built by varying one or two parameters at a time from the
Milestone 1 baseline; every other parameter (fixed losses, frequency,
system noise temperature, required Eb/N0, implementation loss) is held at
its baseline value unless the row explicitly says otherwise. The table
intentionally includes two failing cases (higher data rate, smaller ground
station) alongside closing cases, so it demonstrates the feasibility
boundary rather than only successful configurations.

## 12. Precision conventions

Internal computation retains full floating-point precision throughout;
only *displayed* values are rounded, and only to a level defensible for
each quantity: gains/losses/margin to 0.01-0.1 dB, dish diameters to 0.1 m,
transmit power to 0.01-0.1 W, data rates to 3 significant figures in Mbps.
Reporting margin to 0.01 dB in verification output does not imply hardware
is characterized to that precision — it is there so cross-checks (forward
vs. inverse, closed-form vs. per-point) can be shown to agree tightly.

## 13. Scope boundary (explicitly deferred to later milestones)

This milestone is a **deterministic** link trade study. The following are
intentionally out of scope and were not added:

- ITU-R atmospheric attenuation, rain fade, gaseous absorption, cloud
  attenuation, or elevation-angle-dependent loss models (the fixed
  `atmospheric_loss_db` / `other_loss_db` scalars from Milestone 1 are
  unchanged);
- probabilistic/statistical pointing losses;
- modulation and coding family modeling or BER/FER curves (`required_ebn0_db`
  remains a fixed input, as in Milestone 1);
- Doppler;
- ground-station pass geometry or contact-time modeling;
- lunar occultation or line-of-sight blockage;
- link availability statistics;
- Monte Carlo uncertainty/sensitivity analysis (Milestone 2's
  "sensitivity" section is purely analytical/deterministic — partial
  derivatives, not probability distributions).

These are candidates for Milestone 3 and beyond.
