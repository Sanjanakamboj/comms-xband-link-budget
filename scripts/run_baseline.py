#!/usr/bin/env python3
"""Compute and report the Milestone 1 baseline link budget.

Produces:
    results/baseline_link_budget.md   -- itemized link-budget table (worst-case range)
    results/baseline_link_budget.csv  -- same table, machine-readable
    results/range_comparison.md       -- worst-case vs. best-case range comparison

Run from the repository root:
    python scripts/run_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pandas as pd  # noqa: E402

from baseline_scenario import BEST_CASE_RANGE_M, WORST_CASE_RANGE_M, build_baseline  # noqa: E402

RESULTS_DIR = REPO_ROOT / "results"


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)

    worst = build_baseline(WORST_CASE_RANGE_M)
    best = build_baseline(BEST_CASE_RANGE_M)

    worst_result = worst.compute()
    best_result = best.compute()

    worst_series = worst_result.to_series()
    best_series = best_result.to_series()

    print("=" * 72)
    print(f"Baseline X-band downlink link budget: {worst.name}")
    print(f"Worst-case range: {WORST_CASE_RANGE_M / 1e3:,.0f} km")
    print("=" * 72)
    for label, value in worst_series.items():
        print(f"{label:<32s} {value:10.3f}")
    print("-" * 72)
    print(f"{'RESULT':<32s} "
          f"{'MARGIN CLOSES' if worst_result.margin_db > 0 else 'MARGIN FAILS':>10s} "
          f"({worst_result.margin_db:+.2f} dB)")
    print("=" * 72)

    # --- itemized markdown table (worst-case range) ---
    md_lines = [
        "# Baseline X-band Downlink Link Budget (Milestone 1)",
        "",
        f"Scenario: `{worst.name}`, worst-case range = "
        f"{WORST_CASE_RANGE_M / 1e3:,.0f} km. See `docs/baseline_scenario.md` for parameter rationale.",
        "",
        "| Quantity | Value |",
        "|---|---:|",
    ]
    for label, value in worst_series.items():
        md_lines.append(f"| {label} | {value:.3f} |")
    md_lines += [
        "",
        f"**Link margin: {worst_result.margin_db:+.2f} dB "
        f"({'CLOSES' if worst_result.margin_db > 0 else 'FAILS'} at worst-case range)**",
        "",
    ]
    (RESULTS_DIR / "baseline_link_budget.md").write_text("\n".join(md_lines))

    # --- CSV (machine-readable) ---
    worst_series.rename("value").to_csv(RESULTS_DIR / "baseline_link_budget.csv", header=True)

    # --- worst-case vs best-case comparison table ---
    comparison = pd.DataFrame(
        {
            f"Best case ({BEST_CASE_RANGE_M / 1e3:,.0f} km)": best_series,
            f"Worst case ({WORST_CASE_RANGE_M / 1e3:,.0f} km)": worst_series,
        }
    )
    comp_lines = [
        "# Worst-Case vs. Best-Case Range Comparison",
        "",
        comparison.to_markdown(floatfmt=".3f"),
        "",
    ]
    (RESULTS_DIR / "range_comparison.md").write_text("\n".join(comp_lines))

    print(f"\nWrote: {RESULTS_DIR / 'baseline_link_budget.md'}")
    print(f"Wrote: {RESULTS_DIR / 'baseline_link_budget.csv'}")
    print(f"Wrote: {RESULTS_DIR / 'range_comparison.md'}")


if __name__ == "__main__":
    main()
