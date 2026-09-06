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

- [x] **Milestone 1 — Link-Budget Foundations and Verification**: core
      equations, software architecture, baseline scenario, independent
      verification path, automated tests.
- [x] **Milestone 2 — Range, Data-Rate, Gain, and Power Trade Study** (this
      commit): reusable trade-study API, range/data-rate/power/gain/dish
      sweeps, closure maps, closed-form inverse-design helpers, analytical
      sensitivities, worst-case-range trade table, portfolio figures.
- [ ] Milestone 3 — Uncertainty / sensitivity analysis (probabilistic).
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
│   ├── link_budget.py     # end-to-end link closure + closed-form inverse-design helpers
│   ├── antennas.py        # idealized parabolic-dish aperture-gain model (Milestone 2)
│   └── trades.py          # vectorized trade-study sweeps and joint hardware trades (Milestone 2)
├── tests/                 # pytest suite, each module independently verified
├── scripts/
│   ├── baseline_scenario.py   # single source of truth for the baseline mission scenario
│   ├── run_baseline.py        # computes + reports the baseline link budget
│   ├── verify_link_budget.py  # independent cross-check of the equations + figure
│   └── run_trade_study.py     # Milestone 2 trade study: table + 4 portfolio figures
├── docs/
│   ├── link_budget_equations.md  # equation reference (source of truth for the math)
│   ├── baseline_scenario.md      # parameter-by-parameter rationale for the baseline
│   ├── verification.md           # verification strategy and results
│   └── trade_study.md            # Milestone 2 methodology, inverse equations, sensitivities
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
python scripts/run_trade_study.py       # Milestone 2 trade study: table + 4 figures
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

## Trade study (Milestone 2)

**Central question:** how do range, downlink data rate, spacecraft RF
power, and antenna gain trade against link margin, and what combinations
close the link at worst-case range (402,000 km)? Full methodology,
inverse-design equations, and analytical sensitivities in
[`docs/trade_study.md`](docs/trade_study.md); reproduce everything below
with `python scripts/run_trade_study.py`.

**Key findings at the baseline worst-case range:**

| Question | Answer |
|---|---|
| Baseline worst-case margin | **+1.48 dB** (2.00 Mbps) |
| Maximum data rate at worst-case range (0 dB margin) | **2.81 Mbps** |
| Effect of doubling range | margin drops **6.02 dB** (exactly `20*log10(2)`) |
| Effect of doubling data rate | margin drops **3.01 dB** (exactly `10*log10(2)`) |
| Required Tx power for 0 dB / +3 dB margin | **2.84 W** / **5.67 W** (baseline: 4.0 W) |
| Required ground-dish diameter for 0 dB / +3 dB margin | **9.11 m** / **12.87 m** (baseline: 12 m) |

Full worst-case-range design-option table (incl. two failing cases, so the
feasibility boundary is visible, not just successes):
[`results/trade_study_table.md`](results/trade_study_table.md) /
[`.csv`](results/trade_study_table.csv). Full numeric report:
[`results/trade_study_report.md`](results/trade_study_report.md).

**Portfolio figures:**

| | |
|---|---|
| ![Fig 1](results/fig1_max_data_rate_vs_range.png) Fig. 1 — Max data rate vs. range (R⁻² scaling) | ![Fig 2](results/fig2_range_datarate_closure_map.png) Fig. 2 — Range/data-rate margin map, zero-margin boundary |
| ![Fig 3](results/fig3_margin_vs_ground_dish.png) Fig. 3 — Worst-case margin vs. ground-dish diameter | ![Fig 4](results/fig4_joint_power_dish_trade.png) Fig. 4 — Joint Tx-power / ground-dish trade |

Figure 2's heavy black contour is the feasible-design boundary: 0 dB
margin. Figure 4 answers the systems question "how much spacecraft power
can be traded against ground-station aperture for the same margin?" —
e.g. at the baseline's 4 W, roughly a 12 m dish is needed to sit near
+1.5 dB margin; a much smaller/cheaper ground station instead demands
substantially more spacecraft RF power.

Scope note: this is a **deterministic** trade study (fixed scalar losses,
no atmospheric/coding/Doppler/pass-geometry/Monte-Carlo modeling yet) — see
`docs/trade_study.md` §13 for the explicit scope boundary and what's
planned for later milestones.

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

86 tests covering: dB-domain conversion round-trips and fixed points;
free-space path loss (independent-formula cross-check, scaling-law
invariants, slant-range geometry); thermal noise (classic reference
figures, G/T); full link-budget closure (independent hand-calculation
cross-check, monotonicity/sensitivity invariants, closed-form data-rate
inversion round-trip); the parabolic-dish aperture-gain model; and
(Milestone 2) trade-sweep dimensions, range/data-rate/R⁻² scaling laws,
power/gain/dish-diameter hardware trades, the joint hardware trade,
forward/inverse closure round-trips for every inverse-design helper, and
analytical-vs-finite-difference sensitivity checks.

## License

MIT.
