# Milestone 3 — Uncertainty Analysis Methodology

This document covers the probabilistic layer added in Milestone 3
(`src/xband_link/uncertainty.py`, `src/xband_link/monte_carlo.py`): what is
uncertain, how it is sampled, how it is propagated, and what the resulting
numbers mean. It builds on `docs/link_budget_equations.md` (Milestone 1) and
`docs/trade_study.md` (Milestone 2); nothing there changed.

## 1. Uncertain parameters and distributions

**All values below are representative uncertainty assumptions for
engineering sensitivity analysis** — plausible engineering-judgment
magnitudes, not values sourced from a specific hardware qualification
program, vendor datasheet, or test campaign.

| Parameter | Nominal | Domain | Sigma | Effective dB std | Rationale |
|---|---:|---|---:|---:|---|
| Tx power | 4.0 W | fractional_linear | 3.5% | 0.152 dB | SSPA output-power calibration/temperature drift |
| Tx antenna gain | 22.0 dBi | additive_db | 0.3 dB | 0.300 dB | Spacecraft antenna gain/pattern-knowledge uncertainty |
| Rx antenna gain | 57.0 dBi | additive_db | 0.3 dB | 0.300 dB | Ground antenna gain calibration uncertainty |
| Excess pointing loss | 0.0 dB | half_normal_db | 0.2 dB | 0.121 dB | Mispointing beyond the nominal tx+rx allocation (non-negative) |
| Misc. (atmospheric+other) loss | 0.8 dB | additive_db | 0.3 dB | 0.300 dB | Uncertainty in the fixed loss *estimate*, not a new physical effect |
| System noise temperature | 60.0 K | fractional_linear | 5% | 0.217 dB | Receiver noise-temperature calibration/environmental uncertainty |
| Required Eb/N0 | 4.5 dB | additive_db | 0.3 dB | 0.300 dB | Modem/coding implementation uncertainty |

Nominal values are pulled directly from whichever `LinkBudget` is passed to
`uncertainty.default_uncertainty_model()`, so they always track the current
Milestone 1/2 baseline rather than being duplicated as separate constants.

## 2. Distribution-domain discipline

Three explicit domains (`uncertainty.VALID_DOMAINS`):

- **`additive_db`**: `sample = nominal + Normal(0, sigma)`. Used for gains
  and losses, which combine additively in the dB-domain link equation —
  the natural choice, and the one that keeps the analytical variance
  propagation (Section 4) exact.
- **`half_normal_db`**: `sample = nominal + |Normal(0, sigma)|`, clipped to
  `>= 0`. Used *only* for excess pointing loss, because mispointing can
  only add attenuation relative to the nominal allocation already in the
  link budget — a symmetric error would let "pointing" occasionally
  *reduce* loss below the nominal allocation, which is not physical.
- **`fractional_linear`**: `sample = nominal * (1 + Normal(0, sigma))`,
  with `sigma` interpreted as a *fraction* of nominal. Used only for Tx
  power [W] and system noise temperature [K] — genuinely positive linear
  physical quantities, sampled in their natural linear unit and only
  converted to the dB domain (`10*log10(Pt)`, `10*log10(T_sys)`) inside the
  margin equation itself. `tx_power_w` is additionally floor-clipped at
  1 mW and `tsys_k` at 1 K to exclude non-physical (<=0) samples; at the
  sigma values used here this floor is many standard deviations away and
  never actually engaged.

This is the one place a physically-motivated choice (linear vs. dB domain)
materially matters: had Tx power/T_sys instead been modeled as symmetric
dB perturbations, the small mean-shift discussed in Section 6 would not
appear, because the nonlinearity (`10*log10`) is what produces it.

## 3. Independence assumption

Every one of the seven parameters is sampled **independently** — a
deliberate Milestone 3 scope decision, not an oversight. In particular:
tx_gain_dbi and rx_gain_dbi are not correlated (different hardware,
different calibration processes); tx_power_w and tx_gain_dbi are not
correlated (no shared root cause modeled); tsys_k is independent of
everything else. If a specific correlation (e.g., a shared calibration
error moving tx_gain and rx_gain together) becomes relevant, the
recommended approach is a dedicated *sensitivity case* built by sampling a
shared latent variable and adding it to both parameters' draws — not a
silent change to the baseline model. See Section 10 (limitations).

## 4. Deterministic RNG architecture

Every sample call takes an explicit `numpy.random.Generator` — there is no
use of `numpy.random.seed()` or any other global random state anywhere in
`xband_link`. `monte_carlo.run_monte_carlo()` builds
`np.random.default_rng(seed)` once per call and threads it through
`sample_uncertainty()`, which draws each of the seven parameters **in a
fixed field order** (matching `MonteCarloSamples`'s declaration order), so
for a given `(seed, n_samples)` every field's draw is bit-for-bit
reproducible (`tests/test_monte_carlo.py::test_fixed_seed_is_exactly_reproducible`).

`scripts/run_uncertainty_study.py` uses a single documented
`MASTER_SEED = 42` for the entire study.

**Common random numbers**: the 1D closure-probability sweeps (vs. data
rate, vs. range) and the 2D probabilistic hardware-trade grid all reuse
the *same* `MASTER_SEED` at every sweep point/grid cell, rather than a
fresh seed per point. This is a standard variance-reduction technique
(common random numbers): the same underlying normalized random draws are
reused at every point, so point-to-point differences in the resulting
curve/surface reflect the actual change in the model, not independent
sampling noise — producing visibly smoother sweep curves and contours for
a given per-point sample size.

## 5. Why the RF physics is not reimplemented

`monte_carlo.evaluate_margin()` is a **vectorized** re-expression of
`LinkBudget.compute()`'s summation, but it calls the exact same two
array-capable functions `compute()` calls for the actual RF physics:
`propagation.free_space_path_loss_db` and
`noise.noise_power_spectral_density_dbw_hz`. The only thing duplicated is
the linear dB-domain arithmetic (EIRP = ..., path loss = ..., margin =
...), which is necessary because `LinkBudget` is an immutable per-point
dataclass, and looping `dataclasses.replace()` + `compute()` in Python
does not scale to the sample counts and sweep/grid sizes this milestone
needs — a benchmark during development showed ~15 microseconds/sample
for the loop-based path (100,000 samples => ~1.5 s for *one* scenario)
versus <1 ms for 10,000 vectorized samples and ~0.7 s for the *entire*
study script (baseline ensemble, two 30-point 1D sweeps, a 30x30 grid,
convergence study, and OAT sweeps combined).

**Exact equivalence is enforced, not assumed**:
`tests/test_monte_carlo.py::test_zero_uncertainty_matches_deterministic_compute_exactly`
checks the vectorized path against `LinkBudget.compute()` at zero
uncertainty, and
`test_evaluate_margin_matches_link_budget_compute_at_arbitrary_point`
checks it at five arbitrary (non-nominal) sampled points, both to `1e-9`
dB.

## 6. Baseline Monte Carlo results

At the worst-case range (402,000 km) and baseline data rate (2 Mbps), with
`N = 10,000` samples and `MASTER_SEED = 42` (runtime: under 1 ms):

| Statistic | Value |
|---|---:|
| Nominal (deterministic) margin | +1.484 dB |
| Mean MC margin | +1.341 dB |
| Median MC margin | +1.348 dB |
| Std-dev | 0.664 dB |
| P5 | +0.246 dB |
| P1 | −0.205 dB |
| Min / Max (of this ensemble) | −1.09 dB / +4.02 dB |
| **P(margin > 0 dB)** | **0.978** |
| P(margin > 1 dB) | 0.698 |
| P(margin > 3 dB) | 0.006 |

The full run (`scripts/run_uncertainty_study.py`) uses this exact
configuration; see `results/uncertainty_report.md` for the reproduced
numbers alongside every other section below.

## 7. Analytical vs. Monte Carlo variance propagation

Because every parameter enters `margin_db` with a Milestone-2-verified
sensitivity of exactly `+-1 dB/dB` (gains/power at `+1`, losses/required-
Eb/N0/noise at `-1`), the linearized (small-uncertainty) margin variance is
simply the sum of each parameter's *effective dB-domain* variance
(`UncertainParameter.effective_db_std()`, squared):

```
sigma_M^2 ~= sum_i effective_db_std(x_i)^2
```

For the baseline model this gives **sigma_M = 0.667 dB**, versus
**0.664 dB** from the N=10,000 Monte Carlo run — a 0.5% relative
difference, well within Monte Carlo sampling noise at this N. This
agreement is the main verification result for this milestone's
uncertainty propagation: the additive-dB-domain design of the model (and
the delta-method dB-equivalent for the two `fractional_linear` parameters)
makes the linearized approximation essentially exact here, because the
underlying sigma values are small relative to the ~1 (unitless) log slope.

## 8. Mean-shift analysis

The mean Monte Carlo margin (+1.341 dB) is measurably below the
deterministic nominal margin (+1.484 dB) — a −0.143 dB shift. This is
**not a bug**; it has two identifiable causes:

1. **Dominant cause — asymmetric pointing-loss model.** Excess pointing
   loss is modeled as `half_normal_db` (Section 2) specifically because it
   cannot be negative. Its distribution therefore has a strictly positive
   mean, `sigma * sqrt(2/pi) = 0.2 * 0.798 = 0.160 dB`, which is *always*
   subtracted from margin, every sample. This alone predicts a −0.160 dB
   shift, accounting for essentially all of the observed −0.143 dB.
2. **Second-order cause — Jensen's-inequality curvature.** `10*log10(x)`
   is concave, so for a symmetric fractional perturbation of `x` (Tx power
   or `T_sys`), `E[10log10(x)] < 10log10(E[x])`. This nudges the *mean* of
   each nonlinear-domain term slightly below its nominal dB value. The two
   instances (Tx power, entering margin at `+1`; `T_sys`, entering at `-1`
   through the noise floor) act in **opposite directions on margin** and
   are similar in magnitude (both a few thousandths of a dB at these
   sigma values), so they largely cancel and do not explain the observed
   shift's sign or size on their own.

`tests/test_monte_carlo.py::test_mean_margin_shift_matches_half_normal_pointing_mean`
checks the observed shift against the half-normal prediction directly.

## 9. Closure probability vs. data rate and range

Sweeping data rate (30 log-spaced points, 500 kbps-12 Mbps) and range (30
linear points, 200,000-520,000 km) at `N = 20,000`/point with common random
numbers (Section 4) gives smooth S-shaped closure-probability curves
(Figures 2 and 5). Approximate crossing points (linear interpolation on
the empirical curve, not a parametric fit):

| Target | Data rate (worst-case range) | Range (2 Mbps) |
|---|---:|---:|
| 50% | 2.73 Mbps | 468,900 km |
| 90% | 2.20 Mbps | 423,800 km |
| 95% | 2.08 Mbps | 412,400 km |
| 99% | 1.84 Mbps | 389,700 km |

These are read directly off a 30-point interpolated curve — do not treat
the third significant figure as more precise than the underlying N=20,000
Monte Carlo noise justifies (see Section 11 on finite-sample confidence).

## 10. Required nominal margin for target closure probability

Using the non-parametric empirical-quantile method (`monte_carlo.required_nominal_margin`,
derived from a single N=200,000 ensemble at the baseline design) rather
than assuming Gaussian margin uncertainty:

| Target | Required nominal margin (MC, empirical) | Gaussian approx. `z_p * sigma_M` |
|---|---:|---:|
| 90% | +1.01 dB | +0.86 dB |
| 95% | +1.26 dB | +1.10 dB |
| 99% | +1.71 dB | +1.55 dB |

The empirical (non-parametric) values run consistently ~0.15-0.16 dB above
the Gaussian approximation — exactly the half-normal pointing-loss mean
shift from Section 8, since the Gaussian approximation implicitly assumes
a zero-mean, symmetric perturbation while the true (empirical) margin
distribution is centered slightly below nominal. This is a second, useful
cross-check that the mean-shift explanation in Section 8 is correct and
material to design decisions, not just a curiosity.

**Design implication**: the baseline's nominal margin (+1.484 dB) already
exceeds the empirical 95% requirement (+1.26 dB) but falls short of 99%
(+1.71 dB) — consistent with the directly-measured baseline closure
probability of 97.8% (Section 6), which sits between the 95% and 99%
reference levels.

## 11. Sensitivity ranking

Using the analytical variance-contribution decomposition (Section 7),
normalized to shares summing to 1:

| Parameter | Variance share |
|---|---:|
| tx_gain_dbi | 20.2% |
| rx_gain_dbi | 20.2% |
| misc_loss_db | 20.2% |
| required_ebn0_db | 20.2% |
| tsys_k | 10.6% |
| tx_power_w | 5.2% |
| excess_pointing_loss_db | 3.3% |

Four parameters are exactly tied at the baseline sigma values because
they share the same 0.3 dB additive-dB sigma and each has a `+-1` dB/dB
margin sensitivity — the ranking is a direct, mechanical consequence of
the chosen uncertainty *magnitudes*, not of any parameter being
intrinsically "more important" to the physics. Changing any one
parameter's assumed sigma changes its rank; Section 12 (one-at-a-time
sweeps) explores this directly.

## 12. One-at-a-time uncertainty sweeps

For `tx_gain_dbi`, `rx_gain_dbi`, and `tsys_k` (selected as the most
directly hardware-actionable of the four tied top contributors — antenna
calibration/alignment and receiver noise-temperature control are concrete
engineering levers, unlike, e.g., `required_ebn0_db`, which is a modem/
coding property), sigma was swept over {0.1, 0.3, 0.5, 1.0} dB
(dB-equivalent, converting via the delta-method formula for `tsys_k`'s
fractional sigma):

- Margin std-dev grows roughly linearly with each parameter's sigma in
  this range (consistent with the additive-variance model), from ~0.61 dB
  at 0.1 dB up to ~1.17-1.25 dB at 1.0 dB.
- Closure probability is relatively insensitive at small sigma (>=95% up
  to ~0.4-0.5 dB) and degrades sharply past ~0.5-0.7 dB, dropping to
  ~87-89% at 1.0 dB sigma for any of the three parameters individually.

**Conclusion**: none of the three individually dominates at *plausible*
engineering sigma ranges (0.1-0.5 dB is a realistic calibration-quality
range for gain/temperature knowledge) — closure probability stays above
~95% for all three even at 0.5 dB. The practical takeaway is that
*reducing* any single uncertainty below ~0.3 dB buys little; the
uncertainty budget is comfortably spread across four roughly-equal
contributors, so a *hardware capability* improvement (Section 13, more
power or aperture) is a more effective lever than chasing any one
calibration uncertainty down further. See `results/uncertainty_report.md`
Section 9 for the full numeric sweep tables.

## 13. Probabilistic hardware trade

`trades.joint_power_dish_trade` (Milestone 2) showed a *deterministic*
zero-margin boundary in (Tx power, ground-dish diameter) space. Adding
uncertainty (Figure 4, `p_close_grid`) reveals that the deterministic
boundary is not a hard cliff: the 50%/90%/95%/99% closure-probability
contours are a *band* straddling the deterministic 0 dB contour, several
dB wide in either axis. A design sitting exactly on the deterministic
zero-margin line closes only about half the time; comfortably clearing
the 95%/99% contours requires meaningfully more power or aperture than
the deterministic M2 boundary alone would suggest. The baseline design
(4 W, ~12 m dish) sits in the high-probability region (>=95%), consistent
with its directly-computed 97.8% closure probability.

## 14. Monte Carlo convergence

| N | Mean margin (dB) | Std margin (dB) | P(close) |
|---:|---:|---:|---:|
| 100 | 1.360 | 0.705 | 0.980 |
| 1,000 | 1.303 | 0.680 | 0.972 |
| 10,000 | 1.341 | 0.664 | 0.978 |
| 100,000 | 1.330 | 0.669 | 0.976 |

Mean and std-dev stabilize to within ~0.01-0.02 dB by N=10,000, and P(close)
stabilizes to within ~0.002 by the same point — consistent with the
1/sqrt(N) Monte Carlo convergence rate (std-dev of the mean estimator at
N=10,000, given sigma_M~0.66 dB, is ~0.0066 dB; the run-to-run scatter
above is consistent with that). N=10,000 is adequate for the headline
statistics in this report; the 90/95/99%-margin and P>3dB tail estimates
use N=200,000 specifically because tail quantiles converge more slowly
than the mean/std (fewer effective samples in the tail).

## 15. Distribution shape

The margin distribution's sample skewness is small (~ -0.01 at N=10,000),
consistent with an approximately Gaussian/symmetric distribution overall
(Figure 1). This is expected: six of the seven uncertain parameters are
symmetric (`additive_db` or `fractional_linear`, both symmetric in their
native domain and only mildly warped by the `10*log10` transform for the
two `fractional_linear` ones), and only one (`excess_pointing_loss_db`,
`half_normal_db`) is asymmetric — its skew is present but small relative
to the combined width of the other six (roughly consistent with a
Gaussian by the central-limit-theorem-like effect of summing several
comparable-magnitude independent terms, only one of which is skewed).

## 16. Finite-sample confidence in the closure-probability estimate

The baseline `P(margin > 0 dB) = 0.9779` was estimated from N=10,000
Bernoulli trials. Its 95% **Wilson score interval** (chosen over the naive
normal approximation because it stays well-behaved and does not exceed
[0,1] even as `p_hat` approaches 1, which matters here since the estimate
sits close to the boundary) is **[0.9748, 0.9806]** — i.e., report the
closure probability as "97.8% (95% CI: 97.5-98.1%)", not "0.97790000...".

## 17. Limitations and scope boundary

Intentionally **not** modeled in Milestone 3 (deferred to later
milestones):

- rain attenuation, atmospheric gaseous absorption, cloud attenuation, or
  any elevation-angle-dependent slant loss model (the fixed
  `atmospheric_loss_db`/`other_loss_db` from Milestone 1 remain fixed
  scalars, with only *estimation* uncertainty on their sum modeled here as
  `misc_loss_db`);
- weather-conditioned availability statistics;
- ground-station pass geometry, contact-time modeling, or lunar
  occultation;
- modulation/coding family modeling or explicit BER/FER curves (required
  Eb/N0 remains a single scalar with its own uncertainty, not a
  coding-family-specific curve);
- Doppler;
- link-layer retransmission;
- hardware reliability / failure-rate modeling;
- correlated uncertainty (Section 3) beyond the independent baseline.
- range uncertainty in the *default* model — range is deliberately kept
  as a controlled sweep variable (Sections 9, 13) rather than an uncertain
  input, so that "worst-case range" retains its Milestone 1/2 meaning as a
  fixed, known conditioning point.

These are candidates for Milestone 4 and beyond.
