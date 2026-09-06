# Verification Strategy

Every physical relationship implemented in this project is verified against
an **independent formulation** — a different unit system, a different
constant derivation, or a plain hand/NumPy recomputation outside the
library's own call graph — not merely re-tested against itself.

## 1. Free-space path loss

- **Primary implementation**: `propagation.free_space_path_loss_db`, SI
  units (meters, Hz), `20*log10(4*pi*R*f/c)`.
- **Independent check**: the classic telecom km/MHz closed form
  `32.45 + 20*log10(R_km) + 20*log10(f_MHz)`, implemented separately in
  `tests/test_propagation.py::_fspl_db_km_mhz_reference` and again in
  `scripts/verify_link_budget.py::fspl_km_mhz_reference`.
- **Result**: agreement to within ~2 mdB (`5e-3` dB tolerance) across LEO,
  GEO, and lunar-range test cases, and across a 200-point log sweep from
  1,000 km to 500,000 km (`results/verification_fspl_vs_range.png`,
  `results/verification_report.md`). The residual is attributable entirely
  to the rounding of the `32.45` constant.
- **Scaling-law checks**: FSPL must increase by exactly 20 dB per decade of
  range and per decade of frequency — checked directly, independent of any
  numeric reference value.

## 2. Thermal noise floor

- **Primary implementation**: `noise.noise_power_spectral_density_dbw_hz`,
  `N0 = k_B * T_sys` computed in linear watts then converted to dB.
- **Independent check**: the classic engineering reference figure
  `10*log10(k_B) = -228.60 dBW/Hz/K`, added to `10*log10(T_sys)` directly in
  the dB domain (`tests/test_noise.py`, `scripts/verify_link_budget.py`).
- **Result**: agreement to within ~1 mdB. The commonly memorized
  "-204 dBW/Hz at 290 K" figure is also checked directly.

## 3. Full link-budget closure

- **Primary implementation**: `LinkBudget.compute()`, which calls into
  `propagation.py` and `noise.py`.
- **Independent check**: `tests/test_link_budget.py::_independent_reference`
  recomputes every intermediate term (EIRP, path loss, Pr, N0, G/T, C/N0,
  Eb/N0, margin) using plain `math.log10` arithmetic, written independently
  of the library's internal function calls, for the baseline scenario.
  Every term matches to `1e-9` dB (floating-point precision).
- **Physical sanity checks**: margin must decrease monotonically with
  range; doubling transmit power must improve margin by exactly
  `10*log10(2) = 3.01` dB; a 10x increase in data rate must worsen margin by
  exactly 10 dB. These are consequences of the dB-domain linearity of the
  equations and are checked as invariants, not just point values.
- **Round-trip check**: `LinkBudget.max_data_rate_for_margin(0.0)` is solved
  in closed form, then fed back into a fresh `LinkBudget` and confirmed to
  produce exactly 0 dB margin (`test_max_data_rate_for_margin_round_trips_zero_margin`).

## 4. Conversions module

- Every `conversions.py` function is checked for round-trip consistency
  (`db(undb(x)) == x`), known fixed points (`db(1) = 0`, `db(10) = 10`,
  `db(2) ≈ 3.0103`), and correct rejection of non-positive inputs (which
  are undefined in the log domain).

## Running the verification suite

```bash
python -m pytest -q                 # 33 unit/verification tests
python scripts/run_baseline.py      # baseline link-budget table
python scripts/verify_link_budget.py  # independent cross-check + figure
```

All three are re-run at the end of every milestone per the project's
Git/GitHub working protocol before a commit is made.
