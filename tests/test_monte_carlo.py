import dataclasses
import math

import numpy as np
import pytest

from xband_link.link_budget import Channel, LinkBudget, LinkRequirement, Receiver, Transmitter
from xband_link.monte_carlo import (
    analytical_sigma_margin,
    closure_probability,
    evaluate_margin,
    required_nominal_margin,
    run_monte_carlo,
    sample_uncertainty,
    variance_contribution_shares,
    wilson_confidence_interval,
)
from xband_link.uncertainty import UncertaintyModel, default_uncertainty_model


def _baseline() -> LinkBudget:
    return LinkBudget(
        transmitter=Transmitter(power_w=4.0, line_loss_db=1.0, antenna_gain_dbi=22.0, pointing_loss_db=0.5),
        channel=Channel(frequency_hz=8.425e9, range_m=402_000e3, atmospheric_loss_db=0.5, other_loss_db=0.3),
        receiver=Receiver(antenna_gain_dbi=57.0, system_noise_temp_k=60.0, line_loss_db=0.3, pointing_loss_db=0.2),
        requirement=LinkRequirement(data_rate_bps=2.0e6, required_ebn0_db=4.5, implementation_loss_db=1.0),
    )


def _zero_uncertainty_model(link: LinkBudget) -> UncertaintyModel:
    """All sigmas zero -- every sample equals the nominal value exactly."""
    model = default_uncertainty_model(link)
    zeroed = {name: dataclasses.replace(p, sigma=0.0) for name, p in model.as_dict().items()}
    return UncertaintyModel(**zeroed)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_fixed_seed_is_exactly_reproducible():
    link = _baseline()
    model = default_uncertainty_model(link)
    r1 = run_monte_carlo(link, model, n_samples=5000, seed=42)
    r2 = run_monte_carlo(link, model, n_samples=5000, seed=42)
    np.testing.assert_array_equal(r1.margin_db, r2.margin_db)


def test_different_seed_gives_different_result():
    link = _baseline()
    model = default_uncertainty_model(link)
    r1 = run_monte_carlo(link, model, n_samples=5000, seed=1)
    r2 = run_monte_carlo(link, model, n_samples=5000, seed=2)
    assert not np.array_equal(r1.margin_db, r2.margin_db)


def test_result_and_sample_dimensions_match_n():
    link = _baseline()
    model = default_uncertainty_model(link)
    n = 1234
    result = run_monte_carlo(link, model, n_samples=n, seed=7)
    assert result.margin_db.shape == (n,)
    assert result.samples.tx_power_w.shape == (n,)
    assert result.samples.tsys_k.shape == (n,)


# ---------------------------------------------------------------------------
# Zero-uncertainty limit and exact equivalence with LinkBudget.compute()
# ---------------------------------------------------------------------------


def test_zero_uncertainty_matches_deterministic_compute_exactly():
    link = _baseline()
    zero_model = _zero_uncertainty_model(link)
    result = run_monte_carlo(link, zero_model, n_samples=100, seed=0)
    deterministic_margin = link.compute().margin_db
    assert np.all(result.margin_db == pytest.approx(deterministic_margin, abs=1e-9))


def test_evaluate_margin_matches_link_budget_compute_at_arbitrary_point():
    """Cross-check the vectorized formula against LinkBudget.compute() at a
    handful of specific, non-nominal sample points (not just all-nominal)."""
    link = _baseline()
    rng = np.random.default_rng(99)
    model = default_uncertainty_model(link)
    samples = sample_uncertainty(model, 5, rng)
    margins = evaluate_margin(link, samples)

    for i in range(5):
        trial = LinkBudget(
            transmitter=Transmitter(
                power_w=float(samples.tx_power_w[i]),
                line_loss_db=link.transmitter.line_loss_db,
                antenna_gain_dbi=float(samples.tx_gain_dbi[i]),
                pointing_loss_db=link.transmitter.pointing_loss_db,
            ),
            channel=Channel(
                frequency_hz=link.channel.frequency_hz,
                range_m=link.channel.range_m,
                atmospheric_loss_db=0.0,
                other_loss_db=float(samples.misc_loss_db[i]),
            ),
            receiver=Receiver(
                antenna_gain_dbi=float(samples.rx_gain_dbi[i]),
                system_noise_temp_k=float(samples.tsys_k[i]),
                line_loss_db=link.receiver.line_loss_db,
                pointing_loss_db=link.receiver.pointing_loss_db + float(samples.excess_pointing_loss_db[i]),
            ),
            requirement=LinkRequirement(
                data_rate_bps=link.requirement.data_rate_bps,
                required_ebn0_db=float(samples.required_ebn0_db[i]),
                implementation_loss_db=link.requirement.implementation_loss_db,
            ),
        )
        assert margins[i] == pytest.approx(trial.compute().margin_db, abs=1e-9)


# ---------------------------------------------------------------------------
# MC mean approaches deterministic margin under tiny uncertainty
# ---------------------------------------------------------------------------


def test_mc_mean_approaches_deterministic_under_tiny_uncertainty():
    link = _baseline()
    model = default_uncertainty_model(link)
    tiny = {name: dataclasses.replace(p, sigma=p.sigma * 1e-4) for name, p in model.as_dict().items()}
    tiny_model = UncertaintyModel(**tiny)
    result = run_monte_carlo(link, tiny_model, n_samples=20000, seed=11)
    deterministic_margin = link.compute().margin_db
    assert result.summary().mean_margin_db == pytest.approx(deterministic_margin, abs=1e-3)


# ---------------------------------------------------------------------------
# Analytical vs Monte Carlo sigma agreement
# ---------------------------------------------------------------------------


def test_analytical_and_monte_carlo_sigma_agree_for_baseline_uncertainty():
    link = _baseline()
    model = default_uncertainty_model(link)
    result = run_monte_carlo(link, model, n_samples=200_000, seed=2024)
    sigma_analytical, _ = analytical_sigma_margin(model)
    sigma_mc = result.summary().std_margin_db
    assert sigma_mc == pytest.approx(sigma_analytical, rel=0.03)


def test_variance_contribution_shares_sum_to_one():
    link = _baseline()
    model = default_uncertainty_model(link)
    _, contributions = analytical_sigma_margin(model)
    shares = variance_contribution_shares(contributions)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in shares.values())


def test_variance_contribution_shares_rejects_zero_total():
    with pytest.raises(ValueError):
        variance_contribution_shares({"a": 0.0, "b": 0.0})


# ---------------------------------------------------------------------------
# Closure probability monotonicity
# ---------------------------------------------------------------------------


def test_closure_probability_monotonic_decreasing_in_data_rate():
    link = _baseline()
    model = default_uncertainty_model(link)
    rates = [5e5, 2e6, 8e6, 3.2e7]
    probs = []
    for r in rates:
        result = run_monte_carlo(link, model, n_samples=20000, seed=55, data_rate_bps=r)
        probs.append(closure_probability(result.margin_db, 0.0))
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))


def test_closure_probability_monotonic_decreasing_in_range():
    link = _baseline()
    model = default_uncertainty_model(link)
    ranges = [1e8, 2e8, 3e8, 4.5e8]
    probs = []
    for r in ranges:
        result = run_monte_carlo(link, model, n_samples=20000, seed=66, range_m=r)
        probs.append(closure_probability(result.margin_db, 0.0))
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))


def test_closure_probability_improves_with_transmit_power():
    link = _baseline()
    probs = []
    for power_w in [1.0, 2.0, 4.0, 8.0]:
        trial = dataclasses.replace(link, transmitter=dataclasses.replace(link.transmitter, power_w=power_w))
        trial_model = default_uncertainty_model(trial)
        result = run_monte_carlo(trial, trial_model, n_samples=20000, seed=77)
        probs.append(closure_probability(result.margin_db, 0.0))
    assert all(probs[i] <= probs[i + 1] for i in range(len(probs) - 1))


# ---------------------------------------------------------------------------
# Wilson confidence interval
# ---------------------------------------------------------------------------


def test_wilson_interval_contains_point_estimate():
    lo, hi = wilson_confidence_interval(k=9744, n=10000, confidence=0.95)
    assert lo < 0.9744 < hi


def test_wilson_interval_narrows_with_more_samples():
    lo1, hi1 = wilson_confidence_interval(k=950, n=1000, confidence=0.95)
    lo2, hi2 = wilson_confidence_interval(k=9500, n=10000, confidence=0.95)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_wilson_interval_known_reference_case():
    # k=n (100% observed) at n=100 -> Wilson interval should stay strictly < 1.0
    # and be a reasonably tight, well-defined band (not [1,1]).
    lo, hi = wilson_confidence_interval(k=100, n=100, confidence=0.95)
    assert 0.9 < lo < 1.0
    assert hi == pytest.approx(1.0, abs=1e-9)


def test_wilson_interval_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        wilson_confidence_interval(k=5, n=0)
    with pytest.raises(ValueError):
        wilson_confidence_interval(k=-1, n=10)
    with pytest.raises(ValueError):
        wilson_confidence_interval(k=11, n=10)
    with pytest.raises(ValueError):
        wilson_confidence_interval(k=5, n=10, confidence=1.5)


# ---------------------------------------------------------------------------
# Required nominal margin
# ---------------------------------------------------------------------------


def test_required_nominal_margin_round_trips_via_shifted_ensemble():
    link = _baseline()
    model = default_uncertainty_model(link)
    nominal_margin = link.compute().margin_db
    result = run_monte_carlo(link, model, n_samples=200_000, seed=321)

    target = 0.90
    m_required = required_nominal_margin(nominal_margin, result.margin_db, target)

    # Re-center the *same* deviation ensemble on the new required margin and
    # check the empirical closure probability lands at (approximately) the
    # target -- this is an exact identity for the empirical quantile used,
    # not just a close approximation.
    deviation = result.margin_db - nominal_margin
    shifted_margin = m_required + deviation
    p_close_shifted = closure_probability(shifted_margin, 0.0)
    assert p_close_shifted == pytest.approx(target, abs=0.01)


def test_required_nominal_margin_increases_with_target_probability():
    link = _baseline()
    model = default_uncertainty_model(link)
    nominal_margin = link.compute().margin_db
    result = run_monte_carlo(link, model, n_samples=200_000, seed=321)

    m90 = required_nominal_margin(nominal_margin, result.margin_db, 0.90)
    m95 = required_nominal_margin(nominal_margin, result.margin_db, 0.95)
    m99 = required_nominal_margin(nominal_margin, result.margin_db, 0.99)
    assert m90 < m95 < m99


def test_required_nominal_margin_rejects_invalid_probability():
    with pytest.raises(ValueError):
        required_nominal_margin(1.0, np.array([0.1, 0.2]), 1.5)
    with pytest.raises(ValueError):
        required_nominal_margin(1.0, np.array([0.1, 0.2]), 0.0)


# ---------------------------------------------------------------------------
# Mean shift explanation (half-normal pointing loss)
# ---------------------------------------------------------------------------


def test_mean_margin_shift_matches_half_normal_pointing_mean():
    link = _baseline()
    model = default_uncertainty_model(link)
    result = run_monte_carlo(link, model, n_samples=200_000, seed=2024)
    nominal_margin = link.compute().margin_db
    observed_shift = result.summary().mean_margin_db - nominal_margin

    expected_pointing_mean = model.excess_pointing_loss_db.sigma * math.sqrt(2.0 / math.pi)
    # The dominant contributor to the mean shift is the (deliberately
    # asymmetric) half-normal excess-pointing-loss mean; the remainder is a
    # much smaller, second-order Jensen's-inequality effect from the
    # fractional_linear (log-domain) tx-power/Tsys transforms.
    assert observed_shift == pytest.approx(-expected_pointing_mean, abs=0.02)
