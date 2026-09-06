"""Thermal-noise modeling: system noise temperature and noise spectral density.

The receiver noise floor is characterized by a single-sided thermal noise
power spectral density:

    N0 = k_B * T_sys                                   [W/Hz]

where k_B is Boltzmann's constant and T_sys is the total system noise
temperature referenced to the same point as the receive antenna gain
(typically the low-noise amplifier input). T_sys is built up from:

    T_sys = T_antenna + T_receiver

with T_receiver derived from the receiver noise figure NF (dB) referenced
to T0 = 290 K:

    T_receiver = T0 * (10**(NF/10) - 1)

This module keeps the noise-temperature budget separate from the
propagation and link-closure logic so each physical effect is independently
testable.
"""

from __future__ import annotations

import numpy as np

from .constants import BOLTZMANN_CONSTANT, T0_REFERENCE
from .conversions import ArrayLike, db, undb


def noise_figure_db_to_temperature(noise_figure_db: ArrayLike, t0_k: float = T0_REFERENCE) -> ArrayLike:
    """Convert a receiver noise figure [dB] to an equivalent noise temperature [K].

    Uses the IEEE definition NF = 10*log10(1 + Te/T0) referenced to
    T0 = 290 K unless otherwise specified.
    """
    noise_figure_db = np.asarray(noise_figure_db, dtype=float)
    return t0_k * (undb(noise_figure_db) - 1.0)


def system_noise_temperature(antenna_temp_k: ArrayLike, receiver_temp_k: ArrayLike) -> ArrayLike:
    """Total system noise temperature [K] referenced at the receiver input.

    Simple series (cascaded-to-a-single-stage) model: T_sys = T_ant + T_rx.
    This is the standard first-order model used at the link-budget level;
    a full cascaded-stage (Friis) noise-figure chain is out of scope for
    Milestone 1 and can be added later without changing this function's
    interface.
    """
    return np.asarray(antenna_temp_k, dtype=float) + np.asarray(receiver_temp_k, dtype=float)


def noise_power_spectral_density_w_per_hz(t_sys_k: ArrayLike) -> ArrayLike:
    """Single-sided thermal noise PSD N0 = k_B * T_sys [W/Hz]."""
    t_sys_k = np.asarray(t_sys_k, dtype=float)
    if np.any(t_sys_k <= 0):
        raise ValueError("t_sys_k must be strictly positive.")
    return BOLTZMANN_CONSTANT * t_sys_k


def noise_power_spectral_density_dbw_hz(t_sys_k: ArrayLike) -> ArrayLike:
    """Thermal noise PSD N0 in dBW/Hz for system noise temperature T_sys [K]."""
    return db(noise_power_spectral_density_w_per_hz(t_sys_k))


def g_over_t_db(gain_dbi: ArrayLike, t_sys_k: ArrayLike) -> ArrayLike:
    """Receiver figure of merit G/T [dB/K] = Gain[dBi] - 10*log10(T_sys[K])."""
    t_sys_k = np.asarray(t_sys_k, dtype=float)
    if np.any(t_sys_k <= 0):
        raise ValueError("t_sys_k must be strictly positive.")
    return np.asarray(gain_dbi, dtype=float) - db(t_sys_k)
