# Milestone 2 — Worst-Case-Range Trade Table

Worst-case range = 402,000 km. All cases share the baseline's fixed losses (line/pointing/atmospheric/other) and required Eb/N0 unless noted. See docs/trade_study.md for methodology.

| case                                       |   tx_power_w |   tx_gain_dbi |   rx_gain_dbi |   data_rate_mbps |   c_n0_dbhz |   ebn0_actual_db |   ebn0_required_db |   margin_db |
|:-------------------------------------------|-------------:|--------------:|--------------:|-----------------:|------------:|-----------------:|-------------------:|------------:|
| Baseline (worst-case range)                |         4.00 |         22.00 |         57.00 |             2.00 |       69.99 |             6.98 |               4.50 |        1.48 |
| Lower power (2 W)                          |         2.00 |         22.00 |         57.00 |             2.00 |       66.98 |             3.97 |               4.50 |       -1.53 |
| Higher data rate (8 Mbps) -- FAILS         |         4.00 |         22.00 |         57.00 |             8.00 |       69.99 |             0.96 |               4.50 |       -4.54 |
| Smaller ground station (6 m dish) -- FAILS |         4.00 |         22.00 |         51.88 |             2.00 |       64.88 |             1.87 |               4.50 |       -3.63 |
| Strengthened link (8 W, 25 dBi Tx)         |         8.00 |         25.00 |         57.00 |             2.00 |       76.00 |            12.99 |               4.50 |        7.49 |
