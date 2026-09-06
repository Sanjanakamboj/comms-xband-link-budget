# Milestone 3 — Quantile-Based Probabilistic Design Table

Worst-case range = 402,000 km, N = 10,000 Monte Carlo samples per case, master seed = 42. See docs/uncertainty_analysis.md.

| case                                         |   nominal_margin_db |   mean_mc_margin_db |   p5_margin_db |   p1_margin_db |   p_close |
|:---------------------------------------------|--------------------:|--------------------:|---------------:|---------------:|----------:|
| Baseline (4 W, 22 dBi Tx, 57 dBi Rx)         |               1.484 |               1.341 |          0.246 |         -0.205 |     0.978 |
| Weak design (2 W) -- nominal margin negative |              -1.526 |              -1.669 |         -2.764 |         -3.216 |     0.006 |
| Strengthened design (8 W, 25 dBi Tx)         |               7.495 |               7.351 |          6.256 |          5.805 |     1.000 |
