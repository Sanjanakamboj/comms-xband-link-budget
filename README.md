# COMMS-03 — X-band Downlink Budget

A rigorous, reproducible spacecraft X-band downlink link-budget tool.

**Central engineering question:** For a representative X-band spacecraft
downlink, how do antenna gain, data rate, transmit power, and worst-case
range trade against required link margin?

This is a portfolio-quality aerospace communications-systems project, built
milestone-by-milestone, demonstrating RF link-budget fundamentals,
free-space propagation, decibel-domain calculation discipline, thermal-
noise modeling, C/N0 / Eb/N0 / margin calculation, range/data-rate/gain
trade studies, sensitivity analysis, independent verification, and clean,
tested Python architecture.

## Status

- [x] **Milestone 1 — Link-Budget Foundations and Verification** (this
      commit): core equations, software architecture, baseline scenario,
      independent verification path, automated tests.
- [ ] Milestone 2 — Trade-study framework (power / gain / range / data-rate
      sweeps, margin contour plots).
- [ ] Milestone 3 — Uncertainty / sensitivity analysis.
- [ ] Milestone 4 — Final portfolio deliverable: link-budget table +
      worst-case-range margin analysis + trade-study plots.

## Repository layout

```
comms-xband-link-budget/
├── README.md
├── pyproject.toml
├── src/xband_link/
│   ├── constants.py      # physical constants (k_B, c, X-band allocation)
│   ├── conversions.py     # dB / dBW / dBm / dB-Hz conversion helpers
│   ├── propagation.py     # free-space path loss, slant-range geometry
│   ├── noise.py           # system noise temperature, N0, G/T
│   └── link_budget.py     # end-to-end link closure: EIRP -> Pr -> C/N0 -> Eb/N0 -> margin
├── tests/                 # pytest suite, each module independently verified
├── scripts/
│   ├── baseline_scenario.py   # single source of truth for the baseline mission scenario
│   ├── run_baseline.py        # computes + reports the baseline link budget
│   └── verify_link_budget.py  # independent cross-check of the equations + figure
├── docs/
│   ├── link_budget_equations.md  # equation reference (source of truth for the math)
│   ├── baseline_scenario.md      # parameter-by-parameter rationale for the baseline
│   └── verification.md           # verification strategy and results
└── results/                # generated tables and figures (tracked in git)
```

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m pytest -q                     # run the test suite
python scripts/run_baseline.py          # compute + report the baseline link budget
python scripts/verify_link_budget.py    # independent verification + figure
```

## Baseline scenario (Milestone 1)

A small lunar-orbit spacecraft (e.g. a lunar CubeSat/SmallSat in a highly
elliptical orbit) downlinking at X-band (8.425 GHz) to a ~12 m ground
station, evaluated at worst-case (maximum) range. Full parameter rationale
in [`docs/baseline_scenario.md`](docs/baseline_scenario.md); full equation
reference in [`docs/link_budget_equations.md`](docs/link_budget_equations.md).

| Quantity | Value |
|---|---:|
| Tx power (dBW) | 6.021 |
| EIRP (dBW) | 26.521 |
| Free-space path loss (dB) | 223.044 |
| Total path loss (dB) | 223.844 |
| Rx antenna gain (dBi) | 57.000 |
| G/T (dB/K) | 38.918 |
| Received power (dBW) | -140.823 |
| Noise PSD N0 (dBW/Hz) | -210.818 |
| C/N0 (dB-Hz) | 69.995 |
| Eb/N0, actual (dB) | 6.984 |
| Eb/N0, required (dB) | 4.500 |
| Implementation loss (dB) | 1.000 |
| **Link margin (dB)** | **+1.484 (closes)** |

Full table: [`results/baseline_link_budget.md`](results/baseline_link_budget.md).
Worst-case vs. best-case range comparison:
[`results/range_comparison.md`](results/range_comparison.md).

## Verification

Every equation is checked against an independently-derived formulation
(different unit system or constant derivation), not just re-tested against
itself. See [`docs/verification.md`](docs/verification.md) for the full
strategy and [`results/verification_report.md`](results/verification_report.md)
/ [`results/verification_fspl_vs_range.png`](results/verification_fspl_vs_range.png)
for results — free-space path loss and the thermal noise floor both agree
with independent references to well under 0.01 dB.

## Testing

```bash
python -m pytest -q
```

33 tests covering: dB-domain conversion round-trips and fixed points;
free-space path loss (independent-formula cross-check, scaling-law
invariants, slant-range geometry); thermal noise (classic reference
figures, G/T); and full link-budget closure (independent hand-calculation
cross-check, monotonicity/sensitivity invariants, closed-form data-rate
inversion round-trip).

## License

MIT.
