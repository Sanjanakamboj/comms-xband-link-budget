import pytest

from xband_link.constants import BOLTZMANN_CONSTANT
from xband_link.noise import (
    g_over_t_db,
    noise_figure_db_to_temperature,
    noise_power_spectral_density_dbw_hz,
    noise_power_spectral_density_w_per_hz,
    system_noise_temperature,
)


def test_noise_psd_at_290k_is_classic_minus_204_dbw_per_hz():
    # k_B * 290 K = 4.002e-21 W/Hz -> a widely-cited reference value
    # engineers memorize as "-204 dBW/Hz" (or -228.6 dBW/Hz/K for k_B alone).
    psd_dbw_hz = float(noise_power_spectral_density_dbw_hz(290.0))
    assert psd_dbw_hz == pytest.approx(-203.98, abs=0.02)


def test_noise_psd_linear_matches_boltzmann_product():
    t_sys = 150.0
    psd = float(noise_power_spectral_density_w_per_hz(t_sys))
    assert psd == pytest.approx(BOLTZMANN_CONSTANT * t_sys, rel=1e-12)


def test_boltzmann_constant_alone_in_dbw_hz_per_k():
    # 10*log10(k_B) is the classic "-228.6 dBW/Hz/K" figure.
    import numpy as np

    assert 10.0 * np.log10(BOLTZMANN_CONSTANT) == pytest.approx(-228.60, abs=0.01)


def test_noise_figure_zero_db_gives_zero_temperature():
    assert noise_figure_db_to_temperature(0.0) == pytest.approx(0.0, abs=1e-9)


def test_noise_figure_3db_gives_t0():
    # NF = 10*log10(1 + Te/T0) = 3 dB => Te ~ T0 (since 10^0.3 - 1 ~ 0.995).
    te = float(noise_figure_db_to_temperature(3.0, t0_k=290.0))
    assert te == pytest.approx(290.0 * (10 ** 0.3 - 1), rel=1e-9)


def test_system_noise_temperature_is_additive():
    assert system_noise_temperature(antenna_temp_k=30.0, receiver_temp_k=120.0) == pytest.approx(150.0)


def test_g_over_t_known_value():
    # G = 50 dBi, T_sys = 100 K -> G/T = 50 - 20 = 30 dB/K.
    assert float(g_over_t_db(50.0, 100.0)) == pytest.approx(30.0, abs=1e-9)


def test_noise_psd_rejects_nonpositive_temperature():
    with pytest.raises(ValueError):
        noise_power_spectral_density_w_per_hz(0.0)
    with pytest.raises(ValueError):
        noise_power_spectral_density_w_per_hz(-10.0)
