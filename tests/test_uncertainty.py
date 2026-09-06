import math

import numpy as np
import pytest

from xband_link.link_budget import Channel, LinkBudget, LinkRequirement, Receiver, Transmitter
from xband_link.uncertainty import UncertainParameter, default_uncertainty_model


def _baseline() -> LinkBudget:
    return LinkBudget(
        transmitter=Transmitter(power_w=4.0, line_loss_db=1.0, antenna_gain_dbi=22.0, pointing_loss_db=0.5),
        channel=Channel(frequency_hz=8.425e9, range_m=402_000e3, atmospheric_loss_db=0.5, other_loss_db=0.3),
        receiver=Receiver(antenna_gain_dbi=57.0, system_noise_temp_k=60.0, line_loss_db=0.3, pointing_loss_db=0.2),
        requirement=LinkRequirement(data_rate_bps=2.0e6, required_ebn0_db=4.5, implementation_loss_db=1.0),
    )


# ---------------------------------------------------------------------------
# UncertainParameter validation
# ---------------------------------------------------------------------------


def test_rejects_invalid_domain():
    with pytest.raises(ValueError):
        UncertainParameter(name="x", nominal=1.0, sigma=0.1, unit="dB", domain="bogus")


def test_rejects_negative_sigma():
    with pytest.raises(ValueError):
        UncertainParameter(name="x", nominal=1.0, sigma=-0.1, unit="dB", domain="additive_db")


def test_rejects_nonpositive_nominal_for_fractional_linear():
    with pytest.raises(ValueError):
        UncertainParameter(name="x", nominal=0.0, sigma=0.05, unit="K", domain="fractional_linear")
    with pytest.raises(ValueError):
        UncertainParameter(name="x", nominal=-5.0, sigma=0.05, unit="K", domain="fractional_linear")


def test_rejects_empty_unit():
    with pytest.raises(ValueError):
        UncertainParameter(name="x", nominal=1.0, sigma=0.1, unit="", domain="additive_db")


def test_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        UncertainParameter(
            name="x", nominal=1.0, sigma=0.1, unit="dB", domain="additive_db", lower_bound=5.0, upper_bound=1.0
        )


# ---------------------------------------------------------------------------
# Sampling domains
# ---------------------------------------------------------------------------


def test_additive_db_sampling_distribution():
    rng = np.random.default_rng(1)
    p = UncertainParameter(name="g", nominal=20.0, sigma=0.5, unit="dB", domain="additive_db")
    samples = p.sample(rng, 200_000)
    assert samples.mean() == pytest.approx(20.0, abs=0.01)
    assert samples.std() == pytest.approx(0.5, rel=0.02)


def test_half_normal_db_is_nonnegative_and_has_positive_mean():
    rng = np.random.default_rng(2)
    p = UncertainParameter(
        name="pointing", nominal=0.0, sigma=0.2, unit="dB", domain="half_normal_db", lower_bound=0.0
    )
    samples = p.sample(rng, 200_000)
    assert np.all(samples >= 0.0)
    expected_mean = 0.2 * math.sqrt(2.0 / math.pi)
    assert samples.mean() == pytest.approx(expected_mean, rel=0.02)


def test_fractional_linear_sampling_distribution():
    rng = np.random.default_rng(3)
    p = UncertainParameter(name="tsys", nominal=60.0, sigma=0.05, unit="K", domain="fractional_linear")
    samples = p.sample(rng, 200_000)
    assert samples.mean() == pytest.approx(60.0, rel=0.01)
    assert samples.std() == pytest.approx(60.0 * 0.05, rel=0.03)


def test_lower_bound_clips_samples():
    rng = np.random.default_rng(4)
    p = UncertainParameter(
        name="tsys", nominal=1.0, sigma=0.9, unit="K", domain="fractional_linear", lower_bound=0.5
    )
    samples = p.sample(rng, 50_000)
    assert np.all(samples >= 0.5)


def test_zero_sigma_gives_deterministic_samples():
    rng = np.random.default_rng(5)
    p = UncertainParameter(name="g", nominal=22.0, sigma=0.0, unit="dBi", domain="additive_db")
    samples = p.sample(rng, 10)
    np.testing.assert_array_equal(samples, np.full(10, 22.0))


# ---------------------------------------------------------------------------
# effective_db_std
# ---------------------------------------------------------------------------


def test_effective_db_std_additive_is_sigma_itself():
    p = UncertainParameter(name="g", nominal=20.0, sigma=0.3, unit="dB", domain="additive_db")
    assert p.effective_db_std() == pytest.approx(0.3)


def test_effective_db_std_half_normal_matches_known_variance_formula():
    p = UncertainParameter(name="pt", nominal=0.0, sigma=0.2, unit="dB", domain="half_normal_db", lower_bound=0.0)
    expected = 0.2 * math.sqrt(1.0 - 2.0 / math.pi)
    assert p.effective_db_std() == pytest.approx(expected)


def test_effective_db_std_fractional_matches_delta_method_and_is_nominal_independent():
    p1 = UncertainParameter(name="t", nominal=60.0, sigma=0.05, unit="K", domain="fractional_linear")
    p2 = UncertainParameter(name="t", nominal=600.0, sigma=0.05, unit="K", domain="fractional_linear")
    expected = 10.0 * 0.05 / math.log(10.0)
    assert p1.effective_db_std() == pytest.approx(expected)
    assert p2.effective_db_std() == pytest.approx(expected)  # independent of nominal


# ---------------------------------------------------------------------------
# UncertaintyModel / default factory
# ---------------------------------------------------------------------------


def test_default_uncertainty_model_uses_link_nominals():
    link = _baseline()
    model = default_uncertainty_model(link)
    assert model.tx_power_w.nominal == pytest.approx(link.transmitter.power_w)
    assert model.tx_gain_dbi.nominal == pytest.approx(link.transmitter.antenna_gain_dbi)
    assert model.rx_gain_dbi.nominal == pytest.approx(link.receiver.antenna_gain_dbi)
    assert model.tsys_k.nominal == pytest.approx(link.receiver.system_noise_temp_k)
    assert model.required_ebn0_db.nominal == pytest.approx(link.requirement.required_ebn0_db)
    assert model.misc_loss_db.nominal == pytest.approx(
        link.channel.atmospheric_loss_db + link.channel.other_loss_db
    )
    assert model.excess_pointing_loss_db.nominal == pytest.approx(0.0)


def test_as_dict_has_seven_entries():
    link = _baseline()
    model = default_uncertainty_model(link)
    d = model.as_dict()
    assert len(d) == 7
    assert set(d.keys()) == {
        "tx_power_w",
        "tx_gain_dbi",
        "rx_gain_dbi",
        "excess_pointing_loss_db",
        "misc_loss_db",
        "tsys_k",
        "required_ebn0_db",
    }
