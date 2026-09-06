import numpy as np
import pytest

from xband_link.antennas import parabolic_dish_diameter_for_gain_m, parabolic_dish_gain_dbi


def test_dish_gain_doubling_diameter_adds_6db():
    freq_hz = 8.425e9
    g1 = float(parabolic_dish_gain_dbi(6.0, freq_hz))
    g2 = float(parabolic_dish_gain_dbi(12.0, freq_hz))
    assert (g2 - g1) == pytest.approx(20.0 * np.log10(2.0), abs=1e-9)  # 6.0206 dB


def test_dish_gain_diameter_round_trip():
    freq_hz = 8.425e9
    for d in [3.0, 6.0, 12.0, 34.0]:
        g = float(parabolic_dish_gain_dbi(d, freq_hz, aperture_efficiency=0.6))
        d_back = float(parabolic_dish_diameter_for_gain_m(g, freq_hz, aperture_efficiency=0.6))
        assert d_back == pytest.approx(d, rel=1e-9)


def test_12m_dish_gain_is_close_to_baseline_rounded_assumption():
    # docs/baseline_scenario.md uses Gr = 57.0 dBi as a rounded representative
    # value for a ~12 m ground station. The precise idealized aperture-gain
    # formula gives 57.9 dBi for D=12 m, eta=0.55 -- i.e. the baseline's
    # 57.0 dBi is a deliberately rounded (and mildly conservative) input, not
    # a value computed through this function. This test only checks the two
    # are in the same ballpark (within ~1 dB), not bit-identical.
    g = float(parabolic_dish_gain_dbi(12.0, 8.425e9, aperture_efficiency=0.55))
    assert g == pytest.approx(57.9, abs=0.1)
    assert abs(g - 57.0) < 1.0


def test_higher_efficiency_gives_higher_gain():
    g_low = float(parabolic_dish_gain_dbi(12.0, 8.425e9, aperture_efficiency=0.4))
    g_high = float(parabolic_dish_gain_dbi(12.0, 8.425e9, aperture_efficiency=0.65))
    assert g_high > g_low


def test_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        parabolic_dish_gain_dbi(-1.0, 8.4e9)
    with pytest.raises(ValueError):
        parabolic_dish_gain_dbi(12.0, 0.0)
    with pytest.raises(ValueError):
        parabolic_dish_gain_dbi(12.0, 8.4e9, aperture_efficiency=0.0)
    with pytest.raises(ValueError):
        parabolic_dish_gain_dbi(12.0, 8.4e9, aperture_efficiency=1.5)
    with pytest.raises(ValueError):
        parabolic_dish_diameter_for_gain_m(50.0, 0.0)
