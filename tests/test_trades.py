"""Milestone 2: trade-study sweep tests.

Covers sweep dimensions/shapes, monotonicity, the analytical R^-2
max-data-rate scaling law, hardware-sweep scaling (power doubling,
dish-diameter doubling), the joint hardware trade, and analytical
sensitivities verified against finite differences.
"""

import dataclasses
import math

import numpy as np
import pytest

from xband_link.antennas import parabolic_dish_gain_dbi
from xband_link.conversions import dbw_to_watts
from xband_link.link_budget import Channel, LinkBudget, LinkRequirement, Receiver, Transmitter
from xband_link.trades import (
    closure_map,
    finite_difference_slope,
    joint_power_dish_trade,
    max_data_rate_vs_range,
    required_ground_dish_diameter_for_margin,
    sweep_data_rate,
    sweep_ground_dish,
    sweep_range,
    sweep_tx_gain,
    sweep_transmit_power,
)


def _baseline() -> LinkBudget:
    return LinkBudget(
        name="baseline-lunar-worst-case",
        transmitter=Transmitter(power_w=4.0, line_loss_db=1.0, antenna_gain_dbi=22.0, pointing_loss_db=0.5),
        channel=Channel(frequency_hz=8.425e9, range_m=402_000e3, atmospheric_loss_db=0.5, other_loss_db=0.3),
        receiver=Receiver(antenna_gain_dbi=57.0, system_noise_temp_k=60.0, line_loss_db=0.3, pointing_loss_db=0.2),
        requirement=LinkRequirement(data_rate_bps=2.0e6, required_ebn0_db=4.5, implementation_loss_db=1.0),
    )


WORST_CASE_RANGE_M = 402_000e3


# ---------------------------------------------------------------------------
# Range sweep
# ---------------------------------------------------------------------------


def test_range_sweep_shapes():
    link = _baseline()
    ranges = np.linspace(50_000e3, 450_000e3, 25)
    result = sweep_range(link, ranges)
    assert result.range_m.shape == (25,)
    assert result.margin_db.shape == (25,)
    assert result.free_space_path_loss_db.shape == (25,)


def test_margin_monotonically_decreases_with_range():
    link = _baseline()
    ranges = np.linspace(50_000e3, 450_000e3, 25)
    result = sweep_range(link, ranges)
    assert np.all(np.diff(result.margin_db) < 0)


def test_margin_follows_minus_20_log10_r_scaling():
    link = _baseline()
    r1, r2 = 100_000e3, 200_000e3  # exactly 2x
    result = sweep_range(link, [r1, r2])
    delta_margin = result.margin_db[1] - result.margin_db[0]
    assert delta_margin == pytest.approx(-20.0 * math.log10(2.0), abs=1e-9)


def test_fspl_matches_20log10_r_scaling_in_sweep():
    link = _baseline()
    result = sweep_range(link, [1e8, 2e8, 4e8])
    # FSPL must increase by exactly 20*log10(2) per doubling.
    assert (result.free_space_path_loss_db[1] - result.free_space_path_loss_db[0]) == pytest.approx(
        20 * math.log10(2), abs=1e-9
    )
    assert (result.free_space_path_loss_db[2] - result.free_space_path_loss_db[1]) == pytest.approx(
        20 * math.log10(2), abs=1e-9
    )


# ---------------------------------------------------------------------------
# Data-rate sweep
# ---------------------------------------------------------------------------


def test_data_rate_sweep_shapes():
    link = _baseline()
    rates = np.logspace(4, 8, 20)
    result = sweep_data_rate(link, rates)
    assert result.data_rate_bps.shape == (20,)
    assert result.margin_db.shape == (20,)


def test_margin_monotonically_decreases_with_data_rate():
    link = _baseline()
    rates = np.logspace(4, 8, 20)
    result = sweep_data_rate(link, rates)
    assert np.all(np.diff(result.margin_db) < 0)


def test_margin_drops_10db_per_decade_of_data_rate():
    link = _baseline()
    result = sweep_data_rate(link, [1e6, 1e7])
    assert (result.margin_db[1] - result.margin_db[0]) == pytest.approx(-10.0, abs=1e-9)


def test_data_rate_sweep_matches_link_budget_compute_directly():
    link = _baseline()
    rate = 3.5e6
    result = sweep_data_rate(link, [rate])
    direct = dataclasses.replace(
        link, requirement=dataclasses.replace(link.requirement, data_rate_bps=rate)
    ).compute()
    assert result.margin_db[0] == pytest.approx(direct.margin_db, abs=1e-9)


# ---------------------------------------------------------------------------
# Max data rate vs range (R^-2 scaling)
# ---------------------------------------------------------------------------


def test_max_data_rate_vs_range_matches_per_point_inversion():
    link = _baseline()
    ranges = np.array([1e8, 2e8, 3e8])
    rb_max = max_data_rate_vs_range(link, ranges, target_margin_db=0.0)
    for i, r in enumerate(ranges):
        trial = dataclasses.replace(link, channel=dataclasses.replace(link.channel, range_m=float(r)))
        assert rb_max[i] == pytest.approx(trial.max_data_rate_for_margin(0.0), rel=1e-9)


def test_max_data_rate_scales_as_inverse_range_squared():
    link = _baseline()
    r = 1.5e8
    rb_max = max_data_rate_vs_range(link, [r, 2 * r], target_margin_db=0.0)
    # R -> 2R  =>  Rb,max -> Rb,max / 4
    assert rb_max[1] == pytest.approx(rb_max[0] / 4.0, rel=1e-6)


def test_max_data_rate_at_worst_case_range_gives_positive_rate():
    link = _baseline()
    rb_max = max_data_rate_vs_range(link, [WORST_CASE_RANGE_M], target_margin_db=0.0)[0]
    assert rb_max > 0
    # Baseline data rate (2 Mbps) should be below the zero-margin max rate,
    # consistent with the baseline's positive margin.
    assert link.requirement.data_rate_bps < rb_max


# ---------------------------------------------------------------------------
# Closure map
# ---------------------------------------------------------------------------


def test_closure_map_shape():
    link = _baseline()
    ranges = np.linspace(50_000e3, 450_000e3, 10)
    rates = np.logspace(4, 8, 8)
    cmap = closure_map(link, ranges, rates)
    assert cmap.margin_db.shape == (10, 8)


def test_closure_map_matches_full_compute_at_sample_points():
    link = _baseline()
    ranges = np.array([1e8, 3e8])
    rates = np.array([1e6, 1e7])
    cmap = closure_map(link, ranges, rates)
    for i, r in enumerate(ranges):
        for j, b in enumerate(rates):
            trial = dataclasses.replace(
                link,
                channel=dataclasses.replace(link.channel, range_m=float(r)),
                requirement=dataclasses.replace(link.requirement, data_rate_bps=float(b)),
            )
            assert cmap.margin_db[i, j] == pytest.approx(trial.compute().margin_db, abs=1e-8)


def test_closure_map_has_both_positive_and_negative_margin_regions():
    link = _baseline()
    ranges = np.linspace(50_000e3, 450_000e3, 15)
    rates = np.logspace(4, 8, 15)
    cmap = closure_map(link, ranges, rates)
    assert np.any(cmap.margin_db > 0)
    assert np.any(cmap.margin_db < 0)


# ---------------------------------------------------------------------------
# Hardware sweeps: transmit power, transmit gain, ground dish
# ---------------------------------------------------------------------------


def test_transmit_power_sweep_margin_increases_with_power():
    link = _baseline()
    result = sweep_transmit_power(link, [1.0, 2.0, 4.0, 8.0])
    assert np.all(np.diff(result.margin_db) > 0)


def test_transmit_power_doubling_adds_3p01_db():
    link = _baseline()
    result = sweep_transmit_power(link, [4.0, 8.0])
    assert (result.margin_db[1] - result.margin_db[0]) == pytest.approx(10 * math.log10(2), abs=1e-9)


def test_tx_gain_sweep_margin_increases_with_gain():
    link = _baseline()
    result = sweep_tx_gain(link, [15.0, 20.0, 25.0, 30.0])
    assert np.all(np.diff(result.margin_db) > 0)


def test_tx_gain_sweep_1db_increase_gives_1db_margin():
    link = _baseline()
    result = sweep_tx_gain(link, [20.0, 21.0])
    assert (result.margin_db[1] - result.margin_db[0]) == pytest.approx(1.0, abs=1e-9)


def test_ground_dish_sweep_margin_increases_with_diameter():
    link = _baseline()
    result = sweep_ground_dish(link, [4.0, 8.0, 12.0, 20.0])
    assert np.all(np.diff(result.margin_db) > 0)


def test_ground_dish_diameter_doubling_adds_6p02_db_gain_and_margin():
    link = _baseline()
    freq = link.channel.frequency_hz
    g1 = float(parabolic_dish_gain_dbi(6.0, freq))
    g2 = float(parabolic_dish_gain_dbi(12.0, freq))
    assert (g2 - g1) == pytest.approx(20 * math.log10(2), abs=1e-9)

    result = sweep_ground_dish(link, [6.0, 12.0])
    assert (result.margin_db[1] - result.margin_db[0]) == pytest.approx(20 * math.log10(2), abs=1e-6)


def test_ground_dish_diameter_doubling_quadruples_max_data_rate():
    link = _baseline()
    result = sweep_ground_dish(link, [6.0, 12.0])
    assert result.max_data_rate_bps[1] == pytest.approx(4.0 * result.max_data_rate_bps[0], rel=1e-6)


def test_required_ground_dish_diameter_round_trips_to_target_margin():
    link = _baseline()
    for target in [0.0, 1.0, 3.0]:
        d_required = required_ground_dish_diameter_for_margin(link, target)
        gr = float(parabolic_dish_gain_dbi(d_required, link.channel.frequency_hz))
        trial = dataclasses.replace(link, receiver=dataclasses.replace(link.receiver, antenna_gain_dbi=gr))
        assert trial.compute().margin_db == pytest.approx(target, abs=1e-6)


# ---------------------------------------------------------------------------
# Joint hardware trade
# ---------------------------------------------------------------------------


def test_joint_power_dish_trade_shape():
    link = _baseline()
    powers = np.array([1.0, 2.0, 4.0, 8.0])
    diameters = np.array([4.0, 8.0, 12.0])
    trade = joint_power_dish_trade(link, powers, diameters)
    assert trade.margin_db.shape == (3, 4)  # (len(y=diameters), len(x=powers))


def test_joint_power_dish_trade_matches_full_compute_at_sample_points():
    link = _baseline()
    powers = np.array([2.0, 8.0])
    diameters = np.array([6.0, 18.0])
    trade = joint_power_dish_trade(link, powers, diameters)
    for j, d in enumerate(diameters):
        for i, p in enumerate(powers):
            gr = float(parabolic_dish_gain_dbi(d, link.channel.frequency_hz))
            trial = dataclasses.replace(
                link,
                transmitter=dataclasses.replace(link.transmitter, power_w=float(p)),
                receiver=dataclasses.replace(link.receiver, antenna_gain_dbi=gr),
            )
            assert trade.margin_db[j, i] == pytest.approx(trial.compute().margin_db, abs=1e-6)


def test_joint_trade_has_zero_margin_crossing():
    link = _baseline()
    powers = np.logspace(-1, 1.5, 20)  # 0.1 W to ~32 W
    diameters = np.linspace(2.0, 20.0, 20)
    trade = joint_power_dish_trade(link, powers, diameters)
    assert np.any(trade.margin_db > 0)
    assert np.any(trade.margin_db < 0)


# ---------------------------------------------------------------------------
# Sensitivity: analytical vs. finite-difference
# ---------------------------------------------------------------------------


def _margin_vs_tx_power_dbw(link: LinkBudget, power_dbw: float) -> float:
    trial = dataclasses.replace(
        link, transmitter=dataclasses.replace(link.transmitter, power_w=float(dbw_to_watts(power_dbw)))
    )
    return trial.compute().margin_db


def _margin_vs_tx_gain(link: LinkBudget, gain_dbi: float) -> float:
    trial = dataclasses.replace(link, transmitter=dataclasses.replace(link.transmitter, antenna_gain_dbi=gain_dbi))
    return trial.compute().margin_db


def _margin_vs_rx_gain(link: LinkBudget, gain_dbi: float) -> float:
    trial = dataclasses.replace(link, receiver=dataclasses.replace(link.receiver, antenna_gain_dbi=gain_dbi))
    return trial.compute().margin_db


def _margin_vs_atm_loss(link: LinkBudget, loss_db: float) -> float:
    trial = dataclasses.replace(link, channel=dataclasses.replace(link.channel, atmospheric_loss_db=loss_db))
    return trial.compute().margin_db


def _margin_vs_log10_range(link: LinkBudget, log10_r: float) -> float:
    trial = dataclasses.replace(link, channel=dataclasses.replace(link.channel, range_m=10.0**log10_r))
    return trial.compute().margin_db


def _margin_vs_log10_rate(link: LinkBudget, log10_rb: float) -> float:
    trial = dataclasses.replace(link, requirement=dataclasses.replace(link.requirement, data_rate_bps=10.0**log10_rb))
    return trial.compute().margin_db


def test_sensitivity_dmargin_dtxpower_db_is_one():
    link = _baseline()
    slope = finite_difference_slope(lambda x: _margin_vs_tx_power_dbw(link, x), link.transmitter.power_dbw, 1e-4)
    assert slope == pytest.approx(1.0, abs=1e-6)


def test_sensitivity_dmargin_dtxgain_is_one():
    link = _baseline()
    slope = finite_difference_slope(lambda x: _margin_vs_tx_gain(link, x), link.transmitter.antenna_gain_dbi, 1e-4)
    assert slope == pytest.approx(1.0, abs=1e-6)


def test_sensitivity_dmargin_drxgain_is_one():
    link = _baseline()
    slope = finite_difference_slope(lambda x: _margin_vs_rx_gain(link, x), link.receiver.antenna_gain_dbi, 1e-4)
    assert slope == pytest.approx(1.0, abs=1e-6)


def test_sensitivity_dmargin_dloss_is_minus_one():
    link = _baseline()
    slope = finite_difference_slope(lambda x: _margin_vs_atm_loss(link, x), link.channel.atmospheric_loss_db, 1e-4)
    assert slope == pytest.approx(-1.0, abs=1e-6)


def test_sensitivity_dmargin_dlog10range_is_minus_20():
    link = _baseline()
    log10_r0 = math.log10(link.channel.range_m)
    slope = finite_difference_slope(lambda x: _margin_vs_log10_range(link, x), log10_r0, 1e-5)
    assert slope == pytest.approx(-20.0, abs=1e-4)


def test_sensitivity_dmargin_dlog10rate_is_minus_10():
    link = _baseline()
    log10_rb0 = math.log10(link.requirement.data_rate_bps)
    slope = finite_difference_slope(lambda x: _margin_vs_log10_rate(link, x), log10_rb0, 1e-5)
    assert slope == pytest.approx(-10.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


def test_sweep_range_rejects_nonpositive_range():
    link = _baseline()
    with pytest.raises(ValueError):
        sweep_range(link, [-1.0])


def test_sweep_ground_dish_rejects_nonpositive_diameter():
    link = _baseline()
    with pytest.raises(ValueError):
        sweep_ground_dish(link, [0.0])
