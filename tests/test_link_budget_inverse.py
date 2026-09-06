"""Milestone 2: forward/inverse closure verification for the analytical
inverse-design helpers added to LinkBudget (required tx power, required tx
gain, required rx gain). For each helper: compute the required design
variable, plug it back into a fresh forward LinkBudget, and confirm the
resulting margin matches the requested target to tight tolerance.
"""

import dataclasses
import math

import pytest

from xband_link.link_budget import Channel, LinkBudget, LinkRequirement, Receiver, Transmitter


def _baseline() -> LinkBudget:
    return LinkBudget(
        name="baseline-lunar-worst-case",
        transmitter=Transmitter(power_w=4.0, line_loss_db=1.0, antenna_gain_dbi=22.0, pointing_loss_db=0.5),
        channel=Channel(frequency_hz=8.425e9, range_m=402_000e3, atmospheric_loss_db=0.5, other_loss_db=0.3),
        receiver=Receiver(antenna_gain_dbi=57.0, system_noise_temp_k=60.0, line_loss_db=0.3, pointing_loss_db=0.2),
        requirement=LinkRequirement(data_rate_bps=2.0e6, required_ebn0_db=4.5, implementation_loss_db=1.0),
    )


@pytest.mark.parametrize("target_margin_db", [0.0, 1.0, 3.0, -2.0])
def test_required_tx_power_closes_to_target_margin(target_margin_db):
    link = _baseline()
    required_power_w = link.required_tx_power_w_for_margin(target_margin_db)
    trial = dataclasses.replace(link, transmitter=dataclasses.replace(link.transmitter, power_w=required_power_w))
    assert trial.compute().margin_db == pytest.approx(target_margin_db, abs=1e-8)


@pytest.mark.parametrize("target_margin_db", [0.0, 1.0, 3.0, -2.0])
def test_required_tx_gain_closes_to_target_margin(target_margin_db):
    link = _baseline()
    required_gain_dbi = link.required_tx_gain_dbi_for_margin(target_margin_db)
    trial = dataclasses.replace(
        link, transmitter=dataclasses.replace(link.transmitter, antenna_gain_dbi=required_gain_dbi)
    )
    assert trial.compute().margin_db == pytest.approx(target_margin_db, abs=1e-8)


@pytest.mark.parametrize("target_margin_db", [0.0, 1.0, 3.0, -2.0])
def test_required_rx_gain_closes_to_target_margin(target_margin_db):
    link = _baseline()
    required_gain_dbi = link.required_rx_gain_dbi_for_margin(target_margin_db)
    trial = dataclasses.replace(
        link, receiver=dataclasses.replace(link.receiver, antenna_gain_dbi=required_gain_dbi)
    )
    assert trial.compute().margin_db == pytest.approx(target_margin_db, abs=1e-8)


def test_required_tx_power_for_zero_margin_is_less_than_baseline():
    # Baseline margin is positive (~+1.48 dB), so 0 dB margin needs less power.
    link = _baseline()
    baseline_margin = link.compute().margin_db
    assert baseline_margin > 0
    required_power_w = link.required_tx_power_w_for_margin(0.0)
    assert required_power_w < link.transmitter.power_w


def test_doubling_tx_power_adds_3p01_db_margin():
    link = _baseline()
    boosted = dataclasses.replace(link, transmitter=dataclasses.replace(link.transmitter, power_w=link.transmitter.power_w * 2))
    delta = boosted.compute().margin_db - link.compute().margin_db
    assert delta == pytest.approx(10 * math.log10(2), abs=1e-9)


def test_max_data_rate_for_margin_matches_closed_form():
    link = _baseline()
    result = link.compute()
    rb_zero = link.max_data_rate_for_margin(0.0)
    expected = 10 ** ((result.c_over_n0_dbhz - result.required_ebn0_db - result.implementation_loss_db) / 10.0)
    assert rb_zero == pytest.approx(expected, rel=1e-9)
