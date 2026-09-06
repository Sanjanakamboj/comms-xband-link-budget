"""End-to-end verification of LinkBudget.compute() against an independent
hand/NumPy calculation of the baseline scenario (see docs/baseline_scenario.md).

This is the top-level closure check: every intermediate term (EIRP, path
loss, Pr, N0, C/N0, Eb/N0, margin) is recomputed here from first principles,
independently of link_budget.py's internal call graph, and compared to the
library's output to a tight tolerance.
"""

import math

import pytest

from xband_link.link_budget import (
    Channel,
    LinkBudget,
    LinkRequirement,
    Receiver,
    Transmitter,
)

C_LIGHT = 299_792_458.0
K_BOLTZMANN = 1.380649e-23


def _baseline() -> LinkBudget:
    return LinkBudget(
        name="baseline-lunar-worst-case",
        transmitter=Transmitter(
            power_w=4.0,
            line_loss_db=1.0,
            antenna_gain_dbi=22.0,
            pointing_loss_db=0.5,
        ),
        channel=Channel(
            frequency_hz=8.425e9,
            range_m=402_000e3,
            atmospheric_loss_db=0.5,
            other_loss_db=0.3,
        ),
        receiver=Receiver(
            antenna_gain_dbi=57.0,
            system_noise_temp_k=60.0,
            line_loss_db=0.3,
            pointing_loss_db=0.2,
        ),
        requirement=LinkRequirement(
            data_rate_bps=2.0e6,
            required_ebn0_db=4.5,
            implementation_loss_db=1.0,
        ),
    )


def _independent_reference(link: LinkBudget) -> dict:
    """Recompute the full chain independently, in plain math.log10."""
    tx, ch, rx, req = link.transmitter, link.channel, link.receiver, link.requirement

    pt_dbw = 10 * math.log10(tx.power_w)
    eirp = pt_dbw - tx.line_loss_db - tx.pointing_loss_db + tx.antenna_gain_dbi

    fspl = 20 * math.log10(4 * math.pi * ch.range_m * ch.frequency_hz / C_LIGHT)
    total_path = fspl + ch.atmospheric_loss_db + ch.other_loss_db

    pr = eirp - total_path + rx.antenna_gain_dbi - rx.line_loss_db - rx.pointing_loss_db
    n0 = 10 * math.log10(K_BOLTZMANN * rx.system_noise_temp_k)
    g_t = (rx.antenna_gain_dbi - rx.line_loss_db) - 10 * math.log10(rx.system_noise_temp_k)

    cn0 = pr - n0
    ebn0 = cn0 - 10 * math.log10(req.data_rate_bps)
    margin = ebn0 - req.required_ebn0_db - req.implementation_loss_db

    return dict(
        tx_power_dbw=pt_dbw,
        eirp_dbw=eirp,
        free_space_path_loss_db=fspl,
        total_path_loss_db=total_path,
        received_power_dbw=pr,
        noise_psd_dbw_hz=n0,
        g_over_t_db=g_t,
        c_over_n0_dbhz=cn0,
        ebn0_db=ebn0,
        margin_db=margin,
    )


def test_baseline_matches_independent_reference():
    link = _baseline()
    result = link.compute()
    ref = _independent_reference(link)

    assert result.tx_power_dbw == pytest.approx(ref["tx_power_dbw"], abs=1e-9)
    assert result.eirp_dbw == pytest.approx(ref["eirp_dbw"], abs=1e-9)
    assert result.free_space_path_loss_db == pytest.approx(ref["free_space_path_loss_db"], abs=1e-9)
    assert result.total_path_loss_db == pytest.approx(ref["total_path_loss_db"], abs=1e-9)
    assert result.received_power_dbw == pytest.approx(ref["received_power_dbw"], abs=1e-9)
    assert result.noise_psd_dbw_hz == pytest.approx(ref["noise_psd_dbw_hz"], abs=1e-9)
    assert result.g_over_t_db == pytest.approx(ref["g_over_t_db"], abs=1e-9)
    assert result.c_over_n0_dbhz == pytest.approx(ref["c_over_n0_dbhz"], abs=1e-9)
    assert result.ebn0_db == pytest.approx(ref["ebn0_db"], abs=1e-9)
    assert result.margin_db == pytest.approx(ref["margin_db"], abs=1e-9)


def test_baseline_scenario_closes_with_positive_but_tight_margin():
    """Sanity check on the chosen baseline: it should be realistically tight
    (order 1-2 dB), not trivially huge or negative, so later trade studies
    (Milestone 2+) have room to move margin in both directions."""
    result = _baseline().compute()
    assert 0.0 < result.margin_db < 5.0


def test_margin_decreases_with_range():
    near = _baseline()
    far = LinkBudget(
        transmitter=near.transmitter,
        channel=Channel(
            frequency_hz=near.channel.frequency_hz,
            range_m=near.channel.range_m * 2,
            atmospheric_loss_db=near.channel.atmospheric_loss_db,
            other_loss_db=near.channel.other_loss_db,
        ),
        receiver=near.receiver,
        requirement=near.requirement,
    )
    assert far.compute().margin_db < near.compute().margin_db


def test_margin_improves_with_more_tx_power():
    baseline = _baseline()
    boosted = LinkBudget(
        transmitter=Transmitter(
            power_w=baseline.transmitter.power_w * 2,
            line_loss_db=baseline.transmitter.line_loss_db,
            antenna_gain_dbi=baseline.transmitter.antenna_gain_dbi,
            pointing_loss_db=baseline.transmitter.pointing_loss_db,
        ),
        channel=baseline.channel,
        receiver=baseline.receiver,
        requirement=baseline.requirement,
    )
    # Doubling power is +3.01 dB EIRP -> +3.01 dB margin, exactly (linear in dB).
    delta = boosted.compute().margin_db - baseline.compute().margin_db
    assert delta == pytest.approx(10 * math.log10(2), abs=1e-9)


def test_margin_worsens_with_higher_data_rate():
    baseline = _baseline()
    faster = LinkBudget(
        transmitter=baseline.transmitter,
        channel=baseline.channel,
        receiver=baseline.receiver,
        requirement=LinkRequirement(
            data_rate_bps=baseline.requirement.data_rate_bps * 10,
            required_ebn0_db=baseline.requirement.required_ebn0_db,
            implementation_loss_db=baseline.requirement.implementation_loss_db,
        ),
    )
    delta = faster.compute().margin_db - baseline.compute().margin_db
    assert delta == pytest.approx(-10.0, abs=1e-9)


def test_max_data_rate_for_margin_round_trips_zero_margin():
    link = _baseline()
    rb_zero_margin = link.max_data_rate_for_margin(target_margin_db=0.0)

    zero_margin_link = LinkBudget(
        transmitter=link.transmitter,
        channel=link.channel,
        receiver=link.receiver,
        requirement=LinkRequirement(
            data_rate_bps=rb_zero_margin,
            required_ebn0_db=link.requirement.required_ebn0_db,
            implementation_loss_db=link.requirement.implementation_loss_db,
        ),
    )
    assert zero_margin_link.compute().margin_db == pytest.approx(0.0, abs=1e-6)


def test_to_series_has_expected_rows():
    result = _baseline().compute()
    series = result.to_series()
    assert "Link margin (dB)" in series.index
    assert "Eb/N0, actual (dB)" in series.index
    assert series["Link margin (dB)"] == pytest.approx(result.margin_db)
