#!/usr/bin/env python3
"""Milestone 2 — Range, Data-Rate, Gain, and Power Trade Study.

One command reproduces the milestone's main deliverables:

    python scripts/run_trade_study.py

Produces (all under results/):
    trade_study_table.md / .csv         -- worst-case-range design-option table
    fig1_max_data_rate_vs_range.png     -- Rb,max(R), baseline/worst-case marked
    fig2_range_datarate_closure_map.png -- M(R, Rb) heatmap + zero-margin contour
    fig3_margin_vs_ground_dish.png      -- worst-case margin vs. ground dish diameter
    fig4_joint_power_dish_trade.png     -- M(Pt, D_ground) joint hardware trade
    trade_study_report.md               -- key numerical conclusions

Scope (Milestone 2): deterministic hardware/geometry trades only. No
atmospheric attenuation, coding/BER curves, Doppler, pass geometry, or
Monte Carlo uncertainty -- see docs/trade_study.md for the scope boundary.
"""

from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from baseline_scenario import BEST_CASE_RANGE_M, WORST_CASE_RANGE_M, build_baseline  # noqa: E402
from xband_link.antennas import parabolic_dish_gain_dbi  # noqa: E402
from xband_link.link_budget import LinkBudget  # noqa: E402
from xband_link.trades import (  # noqa: E402
    closure_map,
    joint_power_dish_trade,
    max_data_rate_vs_range,
    required_ground_dish_diameter_for_margin,
    sweep_ground_dish,
    sweep_range,
    sweep_transmit_power,
)

RESULTS_DIR = REPO_ROOT / "results"

# Range sweep bounds: from a representative near-perigee range out to and
# beyond the baseline worst-case (apogee-class) range, see docs/trade_study.md.
RANGE_SWEEP_MIN_M = 50_000e3
RANGE_SWEEP_MAX_M = 450_000e3


def fmt_rate(bps: float) -> str:
    """Human-readable data rate."""
    if bps >= 1e6:
        return f"{bps / 1e6:.2f} Mbps"
    if bps >= 1e3:
        return f"{bps / 1e3:.1f} kbps"
    return f"{bps:.0f} bps"


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    baseline = build_baseline(WORST_CASE_RANGE_M)
    baseline_result = baseline.compute()
    freq_hz = baseline.channel.frequency_hz

    report_lines: list[str] = ["# Milestone 2 Trade-Study Report", ""]

    # =======================================================================
    # 1. Range sweep
    # =======================================================================
    section("1. Range sweep")
    ranges_m = np.linspace(RANGE_SWEEP_MIN_M, RANGE_SWEEP_MAX_M, 200)
    range_result = sweep_range(baseline, ranges_m)

    # Numerical check of -20*log10(R) scaling across the sweep endpoints.
    expected_delta = -20.0 * math.log10(RANGE_SWEEP_MAX_M / RANGE_SWEEP_MIN_M)
    actual_delta = range_result.margin_db[-1] - range_result.margin_db[0]
    print(f"Margin({RANGE_SWEEP_MAX_M/1e3:,.0f} km) - Margin({RANGE_SWEEP_MIN_M/1e3:,.0f} km) "
          f"= {actual_delta:+.3f} dB  (expected -20*log10(ratio) = {expected_delta:+.3f} dB)")
    assert abs(actual_delta - expected_delta) < 1e-6, "range scaling law violated"

    # =======================================================================
    # 2. Data-rate sweep + max data rate vs range (R^-2 scaling)
    # =======================================================================
    section("2. Maximum data rate vs. range")
    rb_max_vs_range = max_data_rate_vs_range(baseline, ranges_m, target_margin_db=0.0)
    rb_max_worst_case = float(max_data_rate_vs_range(baseline, [WORST_CASE_RANGE_M], 0.0)[0])
    rb_max_best_case = float(max_data_rate_vs_range(baseline, [BEST_CASE_RANGE_M], 0.0)[0])
    print(f"Max data rate (0 dB margin) at worst-case range ({WORST_CASE_RANGE_M/1e3:,.0f} km): "
          f"{fmt_rate(rb_max_worst_case)}")
    print(f"Max data rate (0 dB margin) at best-case range ({BEST_CASE_RANGE_M/1e3:,.0f} km): "
          f"{fmt_rate(rb_max_best_case)}")
    print(f"Baseline operating data rate: {fmt_rate(baseline.requirement.data_rate_bps)} "
          f"(margin = {baseline_result.margin_db:+.2f} dB)")

    r_ratio = 2.0
    r_test = 1.5e8
    rb_test = max_data_rate_vs_range(baseline, [r_test, r_ratio * r_test], 0.0)
    scale_observed = rb_test[1] / rb_test[0]
    print(f"R^-2 scaling check: R -> {r_ratio}R gives Rb,max ratio = {scale_observed:.6f} "
          f"(expected {1/r_ratio**2:.6f})")
    assert abs(scale_observed - 1 / r_ratio**2) < 1e-6, "R^-2 scaling law violated"

    # =======================================================================
    # 3. Range/data-rate closure map
    # =======================================================================
    section("3. Range/data-rate closure map")
    closure_rates = np.logspace(4, 8, 200)  # 10 kbps to 100 Mbps
    cmap = closure_map(baseline, ranges_m, closure_rates)
    frac_positive = float(np.mean(cmap.margin_db > 0))
    print(f"Closure map grid: {cmap.margin_db.shape[0]} ranges x {cmap.margin_db.shape[1]} data rates")
    print(f"Fraction of grid with positive margin: {frac_positive:.1%}")

    # =======================================================================
    # 4. Transmit-power trade
    # =======================================================================
    section("4. Transmit-power trade (at worst-case range)")
    required_power_0db = baseline.required_tx_power_w_for_margin(0.0)
    required_power_1db = baseline.required_tx_power_w_for_margin(1.0)
    required_power_3db = baseline.required_tx_power_w_for_margin(3.0)
    for label, p in [("0 dB", required_power_0db), ("+1 dB", required_power_1db), ("+3 dB", required_power_3db)]:
        print(f"  Required Tx power for {label} margin: {p:.3f} W ({10*math.log10(p):+.2f} dBW)")

    doubled = sweep_transmit_power(baseline, [baseline.transmitter.power_w, 2 * baseline.transmitter.power_w])
    delta_2x = doubled.margin_db[1] - doubled.margin_db[0]
    print(f"Doubling Tx power ({baseline.transmitter.power_w:.1f} W -> "
          f"{2*baseline.transmitter.power_w:.1f} W): margin change = {delta_2x:+.4f} dB "
          f"(expected +{10*math.log10(2):.4f} dB)")
    assert abs(delta_2x - 10 * math.log10(2)) < 1e-6

    # =======================================================================
    # 5. Spacecraft antenna-gain trade
    # =======================================================================
    section("5. Spacecraft transmit antenna-gain trade (at worst-case range)")
    required_tx_gain_0db = baseline.required_tx_gain_dbi_for_margin(0.0)
    print(f"Minimum spacecraft Tx antenna gain for closure (0 dB margin): {required_tx_gain_0db:.2f} dBi "
          f"(baseline uses {baseline.transmitter.antenna_gain_dbi:.1f} dBi)")

    # =======================================================================
    # 6. Ground-station dish trade
    # =======================================================================
    section("6. Ground-station dish trade (at worst-case range)")
    dish_diameters_m = np.linspace(3.0, 25.0, 60)
    dish_sweep = sweep_ground_dish(baseline, dish_diameters_m)
    d_0db = required_ground_dish_diameter_for_margin(baseline, 0.0)
    d_1db = required_ground_dish_diameter_for_margin(baseline, 1.0)
    d_3db = required_ground_dish_diameter_for_margin(baseline, 3.0)
    for label, d in [("0 dB", d_0db), ("+1 dB", d_1db), ("+3 dB", d_3db)]:
        gr = float(parabolic_dish_gain_dbi(d, freq_hz))
        print(f"  Required ground dish diameter for {label} margin: {d:.2f} m (Gr = {gr:.2f} dBi)")

    g1 = float(parabolic_dish_gain_dbi(8.0, freq_hz))
    g2 = float(parabolic_dish_gain_dbi(16.0, freq_hz))
    print(f"Dish diameter doubling check: G(16 m) - G(8 m) = {g2-g1:+.4f} dB (expected +6.0206 dB)")
    assert abs((g2 - g1) - 20 * math.log10(2)) < 1e-6

    ds = sweep_ground_dish(baseline, [8.0, 16.0])
    rate_ratio = ds.max_data_rate_bps[1] / ds.max_data_rate_bps[0]
    print(f"Max-data-rate ratio for 8m -> 16m dish: {rate_ratio:.4f} (expected 4.0)")
    assert abs(rate_ratio - 4.0) < 1e-4

    # =======================================================================
    # 7. Joint power/ground-dish trade
    # =======================================================================
    section("7. Joint spacecraft-power / ground-dish trade")
    joint_powers_w = np.logspace(np.log10(0.5), np.log10(16.0), 60)
    joint_diameters_m = np.linspace(3.0, 25.0, 60)
    joint = joint_power_dish_trade(baseline, joint_powers_w, joint_diameters_m)
    print(f"Joint trade grid: {joint.margin_db.shape[0]} dish diameters x {joint.margin_db.shape[1]} powers")
    print(f"Baseline point: Pt = {baseline.transmitter.power_w:.1f} W, "
          f"D ~ 12 m (baseline uses Gr = {baseline.receiver.antenna_gain_dbi:.1f} dBi as a direct input)")

    # =======================================================================
    # 8. Worst-case-range trade table
    # =======================================================================
    section("8. Worst-case-range trade table")
    table_rows = _build_trade_table(baseline)
    table_df = pd.DataFrame(table_rows)
    print(table_df.to_string(index=False))

    md_lines = ["# Milestone 2 — Worst-Case-Range Trade Table", "",
                f"Worst-case range = {WORST_CASE_RANGE_M/1e3:,.0f} km. "
                "All cases share the baseline's fixed losses "
                "(line/pointing/atmospheric/other) and required Eb/N0 "
                "unless noted. See docs/trade_study.md for methodology.", "",
                table_df.to_markdown(index=False, floatfmt=".2f"), ""]
    (RESULTS_DIR / "trade_study_table.md").write_text("\n".join(md_lines))
    table_df.to_csv(RESULTS_DIR / "trade_study_table.csv", index=False)

    # =======================================================================
    # Figures
    # =======================================================================
    section("9. Generating figures")
    _fig1_max_rate_vs_range(ranges_m, rb_max_vs_range, baseline, rb_max_worst_case, rb_max_best_case)
    _fig2_closure_map(cmap, baseline)
    _fig3_margin_vs_dish(dish_sweep, baseline, d_0db)
    _fig4_joint_trade(joint, baseline)
    print("Wrote: fig1_max_data_rate_vs_range.png, fig2_range_datarate_closure_map.png, "
          "fig3_margin_vs_ground_dish.png, fig4_joint_power_dish_trade.png")

    # =======================================================================
    # Summary report
    # =======================================================================
    report_lines += [
        f"Baseline worst-case range: {WORST_CASE_RANGE_M/1e3:,.0f} km",
        f"Baseline worst-case margin: {baseline_result.margin_db:+.2f} dB "
        f"({fmt_rate(baseline.requirement.data_rate_bps)} operating rate)",
        f"Maximum supported data rate at worst-case range (0 dB margin): {fmt_rate(rb_max_worst_case)}",
        f"Effect of doubling range (worst-case): margin drops by "
        f"{20*math.log10(2):.2f} dB",
        f"Effect of doubling data rate: margin drops by {10*math.log10(2):.2f} dB",
        f"Required Tx power for 0 dB margin: {required_power_0db:.2f} W "
        f"({10*math.log10(required_power_0db):+.2f} dBW)",
        f"Required Tx power for +3 dB margin: {required_power_3db:.2f} W "
        f"({10*math.log10(required_power_3db):+.2f} dBW)",
        f"Required ground dish diameter for 0 dB margin: {d_0db:.2f} m",
        f"Required ground dish diameter for +3 dB margin: {d_3db:.2f} m",
        "",
        "See results/trade_study_table.md for the full worst-case-range design-option table.",
        "",
    ]
    (RESULTS_DIR / "trade_study_report.md").write_text("\n".join(report_lines))
    print(f"\nWrote: {RESULTS_DIR / 'trade_study_report.md'}")
    print(f"Wrote: {RESULTS_DIR / 'trade_study_table.md'}")
    print(f"Wrote: {RESULTS_DIR / 'trade_study_table.csv'}")


def _build_trade_table(baseline: LinkBudget) -> list[dict]:
    """Representative worst-case-range design options, including a failing case."""
    freq_hz = baseline.channel.frequency_hz

    def row(name: str, link: LinkBudget) -> dict:
        r = link.compute()
        return {
            "case": name,
            "tx_power_w": round(link.transmitter.power_w, 2),
            "tx_gain_dbi": round(link.transmitter.antenna_gain_dbi, 1),
            "rx_gain_dbi": round(link.receiver.antenna_gain_dbi, 2),
            "data_rate_mbps": round(link.requirement.data_rate_bps / 1e6, 3),
            "c_n0_dbhz": round(r.c_over_n0_dbhz, 2),
            "ebn0_actual_db": round(r.ebn0_db, 2),
            "ebn0_required_db": round(r.required_ebn0_db, 2),
            "margin_db": round(r.margin_db, 2),
        }

    rows = []
    rows.append(row("Baseline (worst-case range)", baseline))

    lower_power = dataclasses.replace(baseline, transmitter=dataclasses.replace(baseline.transmitter, power_w=2.0))
    rows.append(row("Lower power (2 W)", lower_power))

    higher_rate = dataclasses.replace(
        baseline, requirement=dataclasses.replace(baseline.requirement, data_rate_bps=8.0e6)
    )
    rows.append(row("Higher data rate (8 Mbps) -- FAILS", higher_rate))

    smaller_dish_gr = float(parabolic_dish_gain_dbi(6.0, freq_hz))
    smaller_dish = dataclasses.replace(
        baseline, receiver=dataclasses.replace(baseline.receiver, antenna_gain_dbi=smaller_dish_gr)
    )
    rows.append(row("Smaller ground station (6 m dish) -- FAILS", smaller_dish))

    strengthened = dataclasses.replace(
        baseline,
        transmitter=dataclasses.replace(baseline.transmitter, power_w=8.0, antenna_gain_dbi=25.0),
    )
    rows.append(row("Strengthened link (8 W, 25 dBi Tx)", strengthened))

    return rows


def _mark_baseline(ax, x, y, label="Baseline"):
    ax.plot(x, y, marker="*", markersize=16, color="black", zorder=5, label=label, linestyle="none")


def _fig1_max_rate_vs_range(ranges_m, rb_max, baseline, rb_worst, rb_best):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(ranges_m / 1e3, rb_max / 1e6, lw=2, color="tab:blue", label=r"$R_{b,max}(R)$, 0 dB margin")
    _mark_baseline(ax, WORST_CASE_RANGE_M / 1e3, rb_worst / 1e6, "Worst-case range (0 dB margin)")
    ax.plot(
        WORST_CASE_RANGE_M / 1e3,
        baseline.requirement.data_rate_bps / 1e6,
        marker="o",
        markersize=10,
        color="tab:red",
        zorder=5,
        label="Baseline operating point",
    )
    ax.set_xlabel("Slant range (km)")
    ax.set_ylabel("Maximum data rate for 0 dB margin (Mbps)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Figure 1 — Maximum data rate vs. range")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig1_max_data_rate_vs_range.png", dpi=150)
    plt.close(fig)


def _fig2_closure_map(cmap, baseline):
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    rr_km = cmap.range_m / 1e3
    rb_mbps = cmap.data_rate_bps / 1e6

    vmax = np.max(np.abs(cmap.margin_db))
    mesh = ax.pcolormesh(
        rr_km, rb_mbps, cmap.margin_db.T, shading="auto", cmap="RdBu", vmin=-vmax, vmax=vmax
    )
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Link margin (dB)")

    cs = ax.contour(rr_km, rb_mbps, cmap.margin_db.T, levels=[0.0], colors="black", linewidths=2.0)
    ax.clabel(cs, fmt={0.0: "0 dB margin"}, inline=True, fontsize=9)

    ax.axvline(WORST_CASE_RANGE_M / 1e3, color="black", linestyle="--", lw=1, alpha=0.6)
    ax.text(
        WORST_CASE_RANGE_M / 1e3, rb_mbps.min() * 3.0, " worst-case\n range", fontsize=8, ha="left", va="bottom"
    )
    ax.plot(
        WORST_CASE_RANGE_M / 1e3,
        baseline.requirement.data_rate_bps / 1e6,
        marker="*",
        markersize=16,
        color="black",
        zorder=5,
        label="Baseline",
    )

    ax.set_xlabel("Slant range (km)")
    ax.set_ylabel("Data rate (Mbps)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Figure 2 — Range/data-rate link-margin map")
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_range_datarate_closure_map.png", dpi=150)
    plt.close(fig)


def _fig3_margin_vs_dish(dish_sweep, baseline, d_0db):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(dish_sweep.parameter_values, dish_sweep.margin_db, lw=2, color="tab:blue")
    ax.axhline(0.0, color="black", lw=1, linestyle="--", alpha=0.7, label="0 dB margin")
    ax.axvline(d_0db, color="tab:orange", lw=1.5, linestyle=":", label=f"Required D = {d_0db:.1f} m")
    ax.plot(12.0, baseline.compute().margin_db, marker="*", markersize=16, color="black", zorder=5, label="Baseline (12 m)")
    ax.set_xlabel("Ground-station dish diameter (m)")
    ax.set_ylabel("Worst-case-range link margin (dB)")
    ax.set_title("Figure 3 — Worst-case margin vs. ground-dish diameter")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig3_margin_vs_ground_dish.png", dpi=150)
    plt.close(fig)


def _fig4_joint_trade(joint, baseline):
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    vmax = np.max(np.abs(joint.margin_db))
    mesh = ax.pcolormesh(
        joint.x_values, joint.y_values, joint.margin_db, shading="auto", cmap="RdBu", vmin=-vmax, vmax=vmax
    )
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Link margin (dB)")

    cs = ax.contour(
        joint.x_values, joint.y_values, joint.margin_db, levels=[-3.0, 0.0, 3.0],
        colors=["gray", "black", "gray"], linewidths=[1.2, 2.0, 1.2], linestyles=["--", "-", "--"]
    )
    ax.clabel(cs, fmt=lambda v: f"{v:+.0f} dB", inline=True, fontsize=8)

    ax.plot(
        baseline.transmitter.power_w, 12.0, marker="*", markersize=16, color="black", zorder=5, label="Baseline"
    )
    ax.set_xscale("log")
    ax.set_xlabel("Spacecraft Tx power (W)")
    ax.set_ylabel("Ground-station dish diameter (m)")
    ax.set_title("Figure 4 — Joint Tx-power / ground-dish trade")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig4_joint_power_dish_trade.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
