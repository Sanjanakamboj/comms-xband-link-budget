#!/usr/bin/env python3
"""Milestone 3 — Uncertainty, Monte Carlo Margin Statistics, and Closure Probability.

One command reproduces the milestone's main deliverables:

    python scripts/run_uncertainty_study.py

Produces (all under results/):
    uncertainty_report.md                        -- key numerical conclusions
    uncertainty_quantile_table.md / .csv          -- probabilistic design table
    fig1_margin_distribution.png                  -- histogram/CDF + quantiles
    fig2_closure_probability_vs_data_rate.png     -- P_close(Rb), 50/90/95% levels
    fig3_sensitivity_contribution.png             -- variance-contribution ranking
    fig4_probabilistic_hardware_trade.png         -- P_close(Pt, D_ground) contours
    fig5_closure_probability_vs_range.png         -- P_close(R), 50/90/95% levels

Master seed: MASTER_SEED (below) -- every sampling call in this script uses
an explicit numpy.random.Generator derived from it; nothing touches global
NumPy random state, so the entire study is bit-for-bit reproducible.

Scope (Milestone 3): parametric uncertainty and probabilistic link closure
only. No atmospheric fade, BER curves, Doppler, pass geometry, or hardware
reliability -- see docs/uncertainty_analysis.md for the explicit boundary.
"""

from __future__ import annotations

import dataclasses
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from baseline_scenario import WORST_CASE_RANGE_M, build_baseline  # noqa: E402
from xband_link.antennas import parabolic_dish_gain_dbi  # noqa: E402
from xband_link.link_budget import LinkBudget  # noqa: E402
from xband_link.monte_carlo import (  # noqa: E402
    analytical_sigma_margin,
    closure_probability,
    required_nominal_margin,
    run_monte_carlo,
    variance_contribution_shares,
    wilson_confidence_interval,
)
from xband_link.uncertainty import UncertaintyModel, default_uncertainty_model

RESULTS_DIR = REPO_ROOT / "results"

MASTER_SEED = 42  # single documented master seed for the entire study
BASELINE_N = 10_000
SWEEP_N = 20_000  # per-point N for 1D closure-probability sweeps (common random numbers)
GRID_N = 5_000  # per-cell N for the 2D probabilistic hardware trade
CLOSURE_LEVELS = (0.50, 0.90, 0.95, 0.99)


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def interp_rate_for_probability(rates_bps: np.ndarray, probs: np.ndarray, target: float) -> float:
    """Interpolate the data rate at which closure probability crosses ``target``.

    ``probs`` is monotonically non-increasing in ``rates_bps`` (higher rate
    -> lower margin -> lower closure probability), so reverse both arrays to
    feed np.interp an ascending x-axis (probs).
    """
    order = np.argsort(probs)
    return float(np.interp(target, probs[order], rates_bps[order]))


def interp_range_for_probability(ranges_m: np.ndarray, probs: np.ndarray, target: float) -> float:
    order = np.argsort(probs)
    return float(np.interp(target, probs[order], ranges_m[order]))


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    t_start = time.perf_counter()

    baseline = build_baseline(WORST_CASE_RANGE_M)
    nominal_margin = baseline.compute().margin_db
    model = default_uncertainty_model(baseline)

    report: list[str] = ["# Milestone 3 Uncertainty & Closure-Probability Report", ""]

    # =======================================================================
    # 1. Uncertainty model summary
    # =======================================================================
    section("1. Uncertainty model (representative engineering assumptions)")
    for name, p in model.as_dict().items():
        print(f"  {name:26s} nominal={p.nominal:10.4f} {p.unit:4s}  sigma={p.sigma:8.4f} "
              f"({p.domain}, eff. dB std = {p.effective_db_std():.4f} dB)")
    print(f"Master seed: {MASTER_SEED}")

    # =======================================================================
    # 2. Baseline Monte Carlo study
    # =======================================================================
    section("2. Baseline Monte Carlo study (worst-case range, 2 Mbps)")
    t0 = time.perf_counter()
    baseline_mc = run_monte_carlo(baseline, model, n_samples=BASELINE_N, seed=MASTER_SEED)
    mc_runtime_s = time.perf_counter() - t0
    summary = baseline_mc.summary(thresholds_db=(0.0, 1.0, 3.0))
    print(f"N = {BASELINE_N:,} samples, runtime = {mc_runtime_s*1e3:.2f} ms")
    print(summary.to_series().to_string())

    n_close = int(np.sum(baseline_mc.margin_db > 0.0))
    p_close, p_close_lo, p_close_hi = None, None, None
    p_close = n_close / BASELINE_N
    p_close_lo, p_close_hi = wilson_confidence_interval(n_close, BASELINE_N, confidence=0.95)
    print(f"\nP(margin > 0 dB) = {p_close:.4f}  (95% Wilson CI: [{p_close_lo:.4f}, {p_close_hi:.4f}])")

    # =======================================================================
    # 3. Analytical vs Monte Carlo sigma
    # =======================================================================
    section("3. Analytical (linearized) vs. Monte Carlo margin std-dev")
    sigma_analytical, contributions = analytical_sigma_margin(model)
    print(f"Analytical sigma_M (linearized, M2 sensitivities): {sigma_analytical:.4f} dB")
    print(f"Monte Carlo sigma_M ({BASELINE_N:,} samples):        {summary.std_margin_db:.4f} dB")
    print(f"Relative difference: {(summary.std_margin_db - sigma_analytical) / sigma_analytical:+.2%}")

    # =======================================================================
    # 4. Mean-shift analysis
    # =======================================================================
    section("4. Mean-shift analysis (nominal vs. mean MC margin)")
    observed_shift = summary.mean_margin_db - nominal_margin
    pointing_mean = model.excess_pointing_loss_db.sigma * math.sqrt(2.0 / math.pi)
    print(f"Deterministic nominal margin:  {nominal_margin:+.4f} dB")
    print(f"Mean Monte Carlo margin:       {summary.mean_margin_db:+.4f} dB")
    print(f"Observed mean shift:           {observed_shift:+.4f} dB")
    print(f"Predicted shift from half-normal excess-pointing-loss mean "
          f"(sigma*sqrt(2/pi) = {pointing_mean:.4f} dB): {-pointing_mean:+.4f} dB")
    print("Remainder (Jensen's-inequality curvature of 10*log10(x) applied to "
          "the symmetric fractional Tx-power/Tsys perturbations) is a much "
          "smaller, second-order effect -- see docs/uncertainty_analysis.md.")

    # =======================================================================
    # 5. Closure probability vs. data rate
    # =======================================================================
    section("5. Closure probability vs. data rate")
    rates_bps = np.logspace(math.log10(3e5), math.log10(1.2e7), 30)
    p_close_vs_rate = np.array(
        [closure_probability(run_monte_carlo(baseline, model, SWEEP_N, MASTER_SEED, data_rate_bps=r).margin_db, 0.0)
         for r in rates_bps]
    )
    rate_targets = {p: interp_rate_for_probability(rates_bps, p_close_vs_rate, p) for p in CLOSURE_LEVELS}
    for p in CLOSURE_LEVELS:
        print(f"  Data rate for ~{p:.0%} closure probability: {rate_targets[p]/1e6:.3f} Mbps")
    baseline_rate_pclose = closure_probability(baseline_mc.margin_db, 0.0)
    print(f"Baseline operating rate (2.00 Mbps) closure probability: {baseline_rate_pclose:.4f}")

    # =======================================================================
    # 6. Closure probability vs. range
    # =======================================================================
    section("6. Closure probability vs. range")
    ranges_m = np.linspace(200_000e3, 520_000e3, 30)
    p_close_vs_range = np.array(
        [closure_probability(run_monte_carlo(baseline, model, SWEEP_N, MASTER_SEED, range_m=r).margin_db, 0.0)
         for r in ranges_m]
    )
    range_targets = {p: interp_range_for_probability(ranges_m, p_close_vs_range, p) for p in CLOSURE_LEVELS}
    for p in CLOSURE_LEVELS:
        print(f"  Range for ~{p:.0%} closure probability: {range_targets[p]/1e3:,.0f} km")

    # =======================================================================
    # 7. Required nominal margin for target closure probability
    # =======================================================================
    section("7. Required deterministic nominal margin for target closure probability")
    large_mc = run_monte_carlo(baseline, model, n_samples=200_000, seed=MASTER_SEED)
    required_margins = {}
    for p in (0.90, 0.95, 0.99):
        m_req_mc = required_nominal_margin(nominal_margin, large_mc.margin_db, p)
        z = {0.90: 1.2816, 0.95: 1.6449, 0.99: 2.3263}[p]
        m_req_gaussian = z * sigma_analytical
        required_margins[p] = m_req_mc
        print(f"  Target {p:.0%}: required nominal margin (MC, empirical) = {m_req_mc:+.3f} dB   "
              f"(Gaussian approx z*sigma = {m_req_gaussian:+.3f} dB)")

    # =======================================================================
    # 8. Sensitivity ranking
    # =======================================================================
    section("8. Sensitivity ranking (variance contribution)")
    shares = variance_contribution_shares(contributions)
    ranked = sorted(shares.items(), key=lambda kv: -kv[1])
    for name, share in ranked:
        print(f"  {name:26s} variance share = {share:6.1%}   (sigma_eff = {math.sqrt(contributions[name]):.4f} dB)")

    # =======================================================================
    # 9. One-at-a-time uncertainty sweeps (top 3 hardware-relevant contributors)
    # =======================================================================
    section("9. One-at-a-time uncertainty sweeps")
    oat_params = ["tx_gain_dbi", "rx_gain_dbi", "tsys_k"]
    print("(4 parameters -- tx_gain_dbi, rx_gain_dbi, misc_loss_db, required_ebn0_db -- are "
          "tied for the largest variance share at baseline sigmas; tx_gain_dbi, rx_gain_dbi, "
          "and tsys_k are selected here as the most directly hardware-actionable of the group.)")
    oat_results: dict[str, pd.DataFrame] = {}
    for pname in oat_params:
        base_param = model.as_dict()[pname]
        sigma_grid_db = [0.1, 0.3, 0.5, 1.0]
        rows = []
        for sigma_db in sigma_grid_db:
            if base_param.domain == "fractional_linear":
                sigma_val = sigma_db * math.log(10.0) / 10.0  # invert effective_db_std()
            else:
                sigma_val = sigma_db
            new_param = dataclasses.replace(base_param, sigma=sigma_val)
            new_model = dataclasses.replace(model, **{pname: new_param})
            res = run_monte_carlo(baseline, new_model, n_samples=SWEEP_N, seed=MASTER_SEED)
            rows.append(
                {"sigma_db": sigma_db, "margin_std_db": res.summary().std_margin_db,
                 "p_close": closure_probability(res.margin_db, 0.0)}
            )
        df = pd.DataFrame(rows)
        oat_results[pname] = df
        print(f"\n  {pname}:")
        print(df.to_string(index=False))

    # =======================================================================
    # 10. Probabilistic hardware trade: P_close(Pt, D_ground)
    # =======================================================================
    section("10. Probabilistic hardware trade: Tx power vs. ground-dish diameter")
    powers_w = np.logspace(math.log10(0.5), math.log10(16.0), 30)
    diameters_m = np.linspace(3.0, 25.0, 30)
    freq_hz = baseline.channel.frequency_hz
    p_close_grid = np.empty((len(diameters_m), len(powers_w)))
    for j, d in enumerate(diameters_m):
        gr = float(parabolic_dish_gain_dbi(d, freq_hz))
        for i, p in enumerate(powers_w):
            trial = dataclasses.replace(
                baseline,
                transmitter=dataclasses.replace(baseline.transmitter, power_w=float(p)),
                receiver=dataclasses.replace(baseline.receiver, antenna_gain_dbi=gr),
            )
            trial_model = default_uncertainty_model(trial)
            res = run_monte_carlo(trial, trial_model, n_samples=GRID_N, seed=MASTER_SEED)
            p_close_grid[j, i] = closure_probability(res.margin_db, 0.0)
    print(f"Grid: {len(diameters_m)} dish diameters x {len(powers_w)} powers, N={GRID_N:,}/cell")
    print(f"Baseline point (Pt={baseline.transmitter.power_w:.1f} W, D~12 m): "
          f"P_close ~ {baseline_rate_pclose:.3f} (from Section 2's exact evaluation)")

    # =======================================================================
    # 11. Quantile-based probabilistic design table
    # =======================================================================
    section("11. Quantile-based probabilistic design table")
    table_df = _build_quantile_table(baseline, model)
    print(table_df.to_string(index=False))

    # =======================================================================
    # 12. Monte Carlo convergence study
    # =======================================================================
    section("12. Monte Carlo convergence study")
    convergence_rows = []
    for n in [100, 1_000, 10_000, 100_000]:
        res = run_monte_carlo(baseline, model, n_samples=n, seed=MASTER_SEED)
        s = res.summary()
        convergence_rows.append(
            {"N": n, "mean_margin_db": s.mean_margin_db, "std_margin_db": s.std_margin_db,
             "p_close": closure_probability(res.margin_db, 0.0)}
        )
    convergence_df = pd.DataFrame(convergence_rows)
    print(convergence_df.to_string(index=False))

    # =======================================================================
    # 13. Distribution shape check
    # =======================================================================
    section("13. Margin distribution shape")
    skewness = float(pd.Series(baseline_mc.margin_db).skew())
    print(f"Sample skewness of margin distribution: {skewness:+.4f} "
          "(0 = perfectly symmetric; small positive/negative values are consistent with "
          "approximately Gaussian, given the half-normal pointing-loss term's mild asymmetry.)")

    # =======================================================================
    # Figures
    # =======================================================================
    section("14. Generating figures")
    _fig1_margin_distribution(baseline_mc.margin_db, nominal_margin, summary)
    _fig2_closure_vs_rate(rates_bps, p_close_vs_rate, rate_targets, baseline.requirement.data_rate_bps)
    _fig3_sensitivity_bar(shares, contributions)
    _fig4_hardware_trade(powers_w, diameters_m, p_close_grid, baseline)
    _fig5_closure_vs_range(ranges_m, p_close_vs_range, range_targets, WORST_CASE_RANGE_M)
    print("Wrote: fig1..fig5 (results/)")

    # =======================================================================
    # Write tables/report
    # =======================================================================
    table_df.to_csv(RESULTS_DIR / "uncertainty_quantile_table.csv", index=False)
    md_lines = [
        "# Milestone 3 — Quantile-Based Probabilistic Design Table", "",
        f"Worst-case range = {WORST_CASE_RANGE_M/1e3:,.0f} km, N = {BASELINE_N:,} Monte Carlo samples "
        f"per case, master seed = {MASTER_SEED}. See docs/uncertainty_analysis.md.", "",
        table_df.to_markdown(index=False, floatfmt=".3f"), "",
    ]
    (RESULTS_DIR / "uncertainty_quantile_table.md").write_text("\n".join(md_lines))

    total_runtime_s = time.perf_counter() - t_start
    report += [
        f"Master seed: {MASTER_SEED}",
        f"Baseline Monte Carlo: N = {BASELINE_N:,} samples, runtime = {mc_runtime_s*1e3:.2f} ms",
        f"Total script runtime: {total_runtime_s:.2f} s",
        "",
        f"Nominal (deterministic) worst-case margin: {nominal_margin:+.3f} dB",
        f"Mean Monte Carlo margin: {summary.mean_margin_db:+.3f} dB "
        f"(shift {observed_shift:+.3f} dB, driven mainly by the asymmetric pointing-loss term)",
        f"Margin std-dev: MC = {summary.std_margin_db:.3f} dB, analytical (linearized) = {sigma_analytical:.3f} dB",
        f"5th / 1st percentile margin: {summary.p5_margin_db:+.3f} dB / {summary.p1_margin_db:+.3f} dB",
        f"P(margin > 0 dB) = {p_close:.4f}  (95% Wilson CI [{p_close_lo:.4f}, {p_close_hi:.4f}])",
        f"P(margin > 1 dB) = {summary.closure_probability[1.0]:.4f}",
        f"P(margin > 3 dB) = {summary.closure_probability[3.0]:.4f}",
        "",
        f"Data rate for ~95% closure at worst-case range: {rate_targets[0.95]/1e6:.3f} Mbps "
        f"(baseline operates at 2.00 Mbps, worst-case-range zero-*nominal*-margin rate was 2.81 Mbps in M2)",
        f"Range for ~95% closure at 2 Mbps: {range_targets[0.95]/1e3:,.0f} km "
        f"(worst-case range is {WORST_CASE_RANGE_M/1e3:,.0f} km)",
        "",
        f"Required nominal margin for 90% / 95% / 99% closure: "
        f"{required_margins[0.90]:+.2f} / {required_margins[0.95]:+.2f} / {required_margins[0.99]:+.2f} dB",
        "",
        "Top variance contributors (tied): tx_gain_dbi, rx_gain_dbi, misc_loss_db, "
        f"required_ebn0_db, each ~{ranked[0][1]:.1%} of margin variance.",
        "",
        "See results/uncertainty_quantile_table.md for the full probabilistic design table.",
        "",
    ]
    (RESULTS_DIR / "uncertainty_report.md").write_text("\n".join(report))
    print(f"\nWrote: {RESULTS_DIR / 'uncertainty_report.md'}")
    print(f"Wrote: {RESULTS_DIR / 'uncertainty_quantile_table.md'}")
    print(f"Wrote: {RESULTS_DIR / 'uncertainty_quantile_table.csv'}")
    print(f"\nTotal script runtime: {total_runtime_s:.2f} s")


def _build_quantile_table(baseline: LinkBudget, base_model: UncertaintyModel) -> pd.DataFrame:
    def row(name: str, link: LinkBudget) -> dict:
        nominal = link.compute().margin_db
        m = default_uncertainty_model(link)
        result = run_monte_carlo(link, m, n_samples=BASELINE_N, seed=MASTER_SEED)
        s = result.summary()
        return {
            "case": name,
            "nominal_margin_db": round(nominal, 3),
            "mean_mc_margin_db": round(s.mean_margin_db, 3),
            "p5_margin_db": round(s.p5_margin_db, 3),
            "p1_margin_db": round(s.p1_margin_db, 3),
            "p_close": round(closure_probability(result.margin_db, 0.0), 4),
        }

    rows = [row("Baseline (4 W, 22 dBi Tx, 57 dBi Rx)", baseline)]

    weak = dataclasses.replace(baseline, transmitter=dataclasses.replace(baseline.transmitter, power_w=2.0))
    rows.append(row("Weak design (2 W) -- nominal margin negative", weak))

    strong = dataclasses.replace(
        baseline, transmitter=dataclasses.replace(baseline.transmitter, power_w=8.0, antenna_gain_dbi=25.0)
    )
    rows.append(row("Strengthened design (8 W, 25 dBi Tx)", strong))

    return pd.DataFrame(rows)


def _fig1_margin_distribution(margins, nominal_margin, summary):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    ax1.hist(margins, bins=80, color="tab:blue", alpha=0.75, density=True)
    ax1.axvline(0.0, color="black", lw=1.5, linestyle="--", label="0 dB (closure boundary)")
    ax1.axvline(nominal_margin, color="tab:red", lw=1.5, label=f"Nominal ({nominal_margin:+.2f} dB)")
    ax1.axvline(summary.p5_margin_db, color="tab:orange", lw=1.2, linestyle=":", label=f"P5 ({summary.p5_margin_db:+.2f} dB)")
    ax1.set_xlabel("Link margin (dB)")
    ax1.set_ylabel("Probability density")
    ax1.set_title("Margin distribution (histogram)")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    sorted_m = np.sort(margins)
    cdf = np.arange(1, len(sorted_m) + 1) / len(sorted_m)
    ax2.plot(sorted_m, cdf, color="tab:blue", lw=2)
    ax2.axvline(0.0, color="black", lw=1.5, linestyle="--", label="0 dB")
    ax2.axhline(0.5, color="gray", lw=0.8, linestyle=":")
    ax2.set_xlabel("Link margin (dB)")
    ax2.set_ylabel("Cumulative probability")
    ax2.set_title("Margin CDF")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    fig.suptitle("Figure 1 — Worst-case-range margin distribution under uncertainty")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig1_margin_distribution.png", dpi=150)
    plt.close(fig)


def _fig2_closure_vs_rate(rates_bps, probs, targets, baseline_rate):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(rates_bps / 1e6, probs, lw=2, color="tab:blue")
    for offset, (level, color) in enumerate(zip((0.50, 0.90, 0.95), ("gray", "tab:orange", "tab:red"))):
        ax.axhline(level, color=color, lw=1, linestyle=":")
        ax.axvline(targets[level] / 1e6, color=color, lw=1, linestyle=":")
        y = 0.30 + 0.10 * offset
        ax.annotate(
            f"{level:.0%}: {targets[level]/1e6:.2f} Mbps",
            xy=(targets[level] / 1e6, y), xytext=(targets[level] / 1e6 * 1.35, y),
            fontsize=8, color=color, va="center",
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8),
        )
    ax.plot(baseline_rate / 1e6, np.interp(baseline_rate, rates_bps, probs), marker="*", markersize=16,
            color="black", zorder=5, label="Baseline (2 Mbps)")
    ax.set_xlabel("Data rate (Mbps)")
    ax.set_ylabel("Closure probability P(margin > 0 dB)")
    ax.set_xscale("log")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Figure 2 — Closure probability vs. data rate (worst-case range)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_closure_probability_vs_data_rate.png", dpi=150)
    plt.close(fig)


def _fig3_sensitivity_bar(shares, contributions):
    fig, ax = plt.subplots(figsize=(7.5, 5))
    items = sorted(shares.items(), key=lambda kv: kv[1])
    names = [n for n, _ in items]
    vals = [v for _, v in items]
    bars = ax.barh(names, vals, color="tab:blue")
    for bar, (name, v) in zip(bars, items):
        ax.text(v + 0.005, bar.get_y() + bar.get_height() / 2, f"{v:.1%}", va="center", fontsize=9)
    ax.set_xlabel("Share of margin variance")
    ax.set_title("Figure 3 — Uncertainty contribution to margin variance")
    ax.set_xlim(0, max(vals) * 1.25)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig3_sensitivity_contribution.png", dpi=150)
    plt.close(fig)


def _fig4_hardware_trade(powers_w, diameters_m, p_close_grid, baseline):
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    mesh = ax.pcolormesh(powers_w, diameters_m, p_close_grid, shading="auto", cmap="viridis", vmin=0, vmax=1)
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Closure probability P(margin > 0 dB)")

    cs = ax.contour(
        powers_w, diameters_m, p_close_grid, levels=[0.50, 0.90, 0.95, 0.99],
        colors="white", linewidths=1.3,
    )
    ax.clabel(cs, fmt=lambda v: f"{v:.0%}", inline=True, fontsize=8)

    ax.plot(baseline.transmitter.power_w, 12.0, marker="*", markersize=16, color="red", zorder=5, label="Baseline")
    ax.set_xscale("log")
    ax.set_xlabel("Spacecraft Tx power (W)")
    ax.set_ylabel("Ground-station dish diameter (m)")
    ax.set_title("Figure 4 — Probabilistic hardware trade: P(closure)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig4_probabilistic_hardware_trade.png", dpi=150)
    plt.close(fig)


def _fig5_closure_vs_range(ranges_m, probs, targets, worst_case_range_m):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(ranges_m / 1e3, probs, lw=2, color="tab:blue")
    for level, color in zip((0.50, 0.90, 0.95), ("gray", "tab:orange", "tab:red")):
        ax.axhline(level, color=color, lw=1, linestyle=":")
        if ranges_m.min() <= targets[level] <= ranges_m.max():
            ax.axvline(targets[level] / 1e3, color=color, lw=1, linestyle=":")
    ax.axvline(worst_case_range_m / 1e3, color="black", lw=1.3, linestyle="--", label="Worst-case range (402,000 km)")
    ax.set_xlabel("Slant range (km)")
    ax.set_ylabel("Closure probability P(margin > 0 dB)")
    ax.set_ylim(-0.02, 1.05)
    ax.xaxis.set_major_formatter(lambda x, pos: f"{x:,.0f}")
    ax.set_title("Figure 5 — Closure probability vs. range (2 Mbps)")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig5_closure_probability_vs_range.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
