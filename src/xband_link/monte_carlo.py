"""Monte Carlo margin-uncertainty engine (Milestone 3).

Evaluates the link-budget margin over an ensemble of uncertain-parameter
samples and reports closure-probability statistics.

**Reuses, does not reimplement, the RF physics.** ``evaluate_margin``
below calls the exact same array-capable functions
``propagation.free_space_path_loss_db`` and
``noise.noise_power_spectral_density_dbw_hz`` that
``LinkBudget.compute()`` calls -- FSPL and thermal-noise physics live in
exactly one place. Only the linear dB-domain *summation* that
``LinkBudget.compute()`` performs (EIRP, path loss, received power,
C/N0, Eb/N0, margin) is duplicated here in vectorized form, because
``LinkBudget`` is an immutable per-point dataclass not designed for
array inputs and a Python-level loop over ``dataclasses.replace()`` +
``compute()`` does not scale to the >= 10,000-sample ensembles this
milestone needs (see ``docs/uncertainty_analysis.md`` for a runtime
comparison). Exact numerical equivalence between the two paths, at zero
uncertainty and at finite-sample points, is enforced by
``tests/test_monte_carlo.py``.

Deterministic RNG architecture: every sampling call takes an explicit
``numpy.random.Generator`` seeded from a single master seed. No global
NumPy random state is ever touched.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .link_budget import LinkBudget
from .noise import noise_power_spectral_density_dbw_hz
from .propagation import free_space_path_loss_db
from .uncertainty import UncertaintyModel

__all__ = [
    "MonteCarloSamples",
    "MonteCarloResult",
    "MonteCarloSummary",
    "sample_uncertainty",
    "evaluate_margin",
    "run_monte_carlo",
    "closure_probability",
    "wilson_confidence_interval",
    "analytical_sigma_margin",
    "variance_contribution_shares",
    "required_nominal_margin",
]

DEFAULT_CLOSURE_THRESHOLDS_DB = (0.0, 1.0, 3.0)


@dataclass(frozen=True)
class MonteCarloSamples:
    """One ensemble's worth of sampled uncertain-parameter values, arrays of length N."""

    tx_power_w: np.ndarray
    tx_gain_dbi: np.ndarray
    rx_gain_dbi: np.ndarray
    excess_pointing_loss_db: np.ndarray
    misc_loss_db: np.ndarray
    tsys_k: np.ndarray
    required_ebn0_db: np.ndarray

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "tx_power_w": self.tx_power_w,
                "tx_gain_dbi": self.tx_gain_dbi,
                "rx_gain_dbi": self.rx_gain_dbi,
                "excess_pointing_loss_db": self.excess_pointing_loss_db,
                "misc_loss_db": self.misc_loss_db,
                "tsys_k": self.tsys_k,
                "required_ebn0_db": self.required_ebn0_db,
            }
        )


def sample_uncertainty(model: UncertaintyModel, n: int, rng: np.random.Generator) -> MonteCarloSamples:
    """Draw one ensemble of size ``n`` from ``model`` using ``rng``.

    Parameters are sampled in a fixed field order (matching
    :class:`MonteCarloSamples`) so that, for a fixed ``rng`` seed and ``n``,
    every field's samples are exactly reproducible.
    """
    return MonteCarloSamples(
        tx_power_w=model.tx_power_w.sample(rng, n),
        tx_gain_dbi=model.tx_gain_dbi.sample(rng, n),
        rx_gain_dbi=model.rx_gain_dbi.sample(rng, n),
        excess_pointing_loss_db=model.excess_pointing_loss_db.sample(rng, n),
        misc_loss_db=model.misc_loss_db.sample(rng, n),
        tsys_k=model.tsys_k.sample(rng, n),
        required_ebn0_db=model.required_ebn0_db.sample(rng, n),
    )


def evaluate_margin(
    link: LinkBudget,
    samples: MonteCarloSamples,
    data_rate_bps: float | np.ndarray | None = None,
    range_m: float | np.ndarray | None = None,
) -> np.ndarray:
    """Vectorized link margin for every sample in ``samples``.

    Mirrors ``LinkBudget.compute()`` term-for-term. ``data_rate_bps`` and
    ``range_m`` default to ``link``'s own values but may be overridden
    (scalar or array) for data-rate/range closure-probability sweeps
    without rebuilding ``samples``.
    """
    tx, ch, rx, req = link.transmitter, link.channel, link.receiver, link.requirement
    rate = req.data_rate_bps if data_rate_bps is None else data_rate_bps
    rng_m = ch.range_m if range_m is None else range_m

    tx_power_dbw = 10.0 * np.log10(samples.tx_power_w)
    eirp_dbw = tx_power_dbw - tx.line_loss_db - tx.pointing_loss_db + samples.tx_gain_dbi

    fspl_db = free_space_path_loss_db(rng_m, ch.frequency_hz)
    total_path_loss_db = fspl_db + samples.misc_loss_db

    received_power_dbw = (
        eirp_dbw
        - total_path_loss_db
        + samples.rx_gain_dbi
        - rx.line_loss_db
        - rx.pointing_loss_db
        - samples.excess_pointing_loss_db
    )

    noise_psd_dbw_hz = noise_power_spectral_density_dbw_hz(samples.tsys_k)
    c_over_n0_dbhz = received_power_dbw - noise_psd_dbw_hz
    ebn0_db = c_over_n0_dbhz - 10.0 * np.log10(np.asarray(rate, dtype=float))

    margin_db = ebn0_db - samples.required_ebn0_db - req.implementation_loss_db
    return np.asarray(margin_db, dtype=float)


@dataclass(frozen=True)
class MonteCarloSummary:
    """Scalar summary statistics of one margin ensemble."""

    n_samples: int
    mean_margin_db: float
    median_margin_db: float
    std_margin_db: float
    p5_margin_db: float
    p1_margin_db: float
    min_margin_db: float
    max_margin_db: float
    closure_probability: dict[float, float]  # threshold_db -> P(margin > threshold_db)

    def to_series(self) -> pd.Series:
        data = {
            "N samples": self.n_samples,
            "Mean margin (dB)": self.mean_margin_db,
            "Median margin (dB)": self.median_margin_db,
            "Std margin (dB)": self.std_margin_db,
            "P5 margin (dB)": self.p5_margin_db,
            "P1 margin (dB)": self.p1_margin_db,
            "Min margin (dB)": self.min_margin_db,
            "Max margin (dB)": self.max_margin_db,
        }
        for threshold, prob in self.closure_probability.items():
            data[f"P(margin > {threshold:+.1f} dB)"] = prob
        return pd.Series(data)


@dataclass(frozen=True)
class MonteCarloResult:
    """Full result of one Monte Carlo run: margins, samples, and provenance."""

    margin_db: np.ndarray
    samples: MonteCarloSamples
    seed: int
    n_samples: int

    def summary(self, thresholds_db: tuple[float, ...] = DEFAULT_CLOSURE_THRESHOLDS_DB) -> MonteCarloSummary:
        m = self.margin_db
        return MonteCarloSummary(
            n_samples=self.n_samples,
            mean_margin_db=float(np.mean(m)),
            median_margin_db=float(np.median(m)),
            std_margin_db=float(np.std(m, ddof=1)),
            p5_margin_db=float(np.percentile(m, 5)),
            p1_margin_db=float(np.percentile(m, 1)),
            min_margin_db=float(np.min(m)),
            max_margin_db=float(np.max(m)),
            closure_probability={t: closure_probability(m, t) for t in thresholds_db},
        )


def run_monte_carlo(
    link: LinkBudget,
    model: UncertaintyModel,
    n_samples: int,
    seed: int,
    data_rate_bps: float | np.ndarray | None = None,
    range_m: float | np.ndarray | None = None,
) -> MonteCarloResult:
    """Draw ``n_samples`` and evaluate margin, from a single explicit master seed."""
    rng = np.random.default_rng(seed)
    samples = sample_uncertainty(model, n_samples, rng)
    margin_db = evaluate_margin(link, samples, data_rate_bps=data_rate_bps, range_m=range_m)
    return MonteCarloResult(margin_db=margin_db, samples=samples, seed=seed, n_samples=n_samples)


def closure_probability(margin_db: np.ndarray, threshold_db: float = 0.0) -> float:
    """Empirical P(margin_db > threshold_db)."""
    return float(np.mean(np.asarray(margin_db) > threshold_db))


def wilson_confidence_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion k/n.

    More reliable than the naive normal approximation at small n or
    p_hat near 0/1 -- appropriate here because tail closure probabilities
    (e.g. near a 95% design point) sit close to the boundary.
    """
    if n <= 0:
        raise ValueError("n must be > 0.")
    if not (0 <= k <= n):
        raise ValueError("k must satisfy 0 <= k <= n.")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be in (0, 1).")

    p_hat = k / n
    z = statistics.NormalDist().inv_cdf(0.5 + confidence / 2.0)
    denom = 1.0 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    half_width = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def analytical_sigma_margin(model: UncertaintyModel) -> tuple[float, dict[str, float]]:
    """Linearized (small-uncertainty) prediction of margin std-dev.

    Every parameter in ``model`` enters ``margin_db`` with a Milestone-2-
    verified sensitivity of exactly +-1 dB/dB (gains and power at +1, all
    losses/required-Eb/N0/noise at -1). Since the sign only affects
    variance through a square, the linearized total variance is simply the
    sum of each parameter's effective dB-domain variance:

        sigma_M^2 ~= sum_i (dM/dx_i * effective_db_std(x_i))^2
                   = sum_i effective_db_std(x_i)^2   (since |dM/dx_i| = 1)

    Returns ``(sigma_M, per_parameter_variance)``.
    """
    contributions = {name: p.effective_db_std() ** 2 for name, p in model.as_dict().items()}
    total_variance = sum(contributions.values())
    return math.sqrt(total_variance), contributions


def variance_contribution_shares(contributions: dict[str, float]) -> dict[str, float]:
    """Normalize a variance-contribution dict to fractional shares summing to 1."""
    total = sum(contributions.values())
    if total <= 0:
        raise ValueError("Total variance must be > 0 to compute shares.")
    return {name: value / total for name, value in contributions.items()}


def required_nominal_margin(
    nominal_margin_db: float,
    margin_db_samples: np.ndarray,
    target_probability: float,
) -> float:
    """Nominal (deterministic) design margin required so that
    P(margin > 0) >= target_probability, given an existing Monte Carlo
    ensemble run at nominal margin ``nominal_margin_db``.

    Let ``delta_i = margin_db_samples_i - nominal_margin_db`` be the
    per-sample uncertainty perturbation (mean ~= 0, some spread). A new
    design with nominal margin ``M0`` closes with probability
    ``P(M0 + delta > 0) = P(delta > -M0)``. Setting this equal to
    ``target_probability`` and solving for ``M0`` gives
    ``M0 = -quantile(delta, 1 - target_probability)``.

    This is non-parametric (uses the empirical quantile of ``delta``
    directly, not a Gaussian assumption) and is cross-checked against the
    Gaussian approximation ``z_p * sigma_M`` for small uncertainty in
    ``tests/test_monte_carlo.py``.
    """
    if not (0.0 < target_probability < 1.0):
        raise ValueError("target_probability must be in (0, 1).")
    deviation = np.asarray(margin_db_samples, dtype=float) - nominal_margin_db
    return float(-np.quantile(deviation, 1.0 - target_probability))
