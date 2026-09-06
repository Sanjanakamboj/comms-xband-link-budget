# Milestone 3 Uncertainty & Closure-Probability Report

Master seed: 42
Baseline Monte Carlo: N = 10,000 samples, runtime = 0.89 ms
Total script runtime: 0.74 s

Nominal (deterministic) worst-case margin: +1.484 dB
Mean Monte Carlo margin: +1.341 dB (shift -0.143 dB, driven mainly by the asymmetric pointing-loss term)
Margin std-dev: MC = 0.664 dB, analytical (linearized) = 0.667 dB
5th / 1st percentile margin: +0.246 dB / -0.205 dB
P(margin > 0 dB) = 0.9779  (95% Wilson CI [0.9748, 0.9806])
P(margin > 1 dB) = 0.6982
P(margin > 3 dB) = 0.0058

Data rate for ~95% closure at worst-case range: 2.075 Mbps (baseline operates at 2.00 Mbps, worst-case-range zero-*nominal*-margin rate was 2.81 Mbps in M2)
Range for ~95% closure at 2 Mbps: 412,420 km (worst-case range is 402,000 km)

Required nominal margin for 90% / 95% / 99% closure: +1.01 / +1.26 / +1.71 dB

Top variance contributors (tied): tx_gain_dbi, rx_gain_dbi, misc_loss_db, required_ebn0_db, each ~20.2% of margin variance.

See results/uncertainty_quantile_table.md for the full probabilistic design table.
