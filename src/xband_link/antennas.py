"""Idealized parabolic-dish aperture gain model.

Used only for the ground-station receive antenna trade (Milestone 2). This
is a standard, idealized uniform-illumination aperture-gain relation:

    G (linear) = eta * (pi * D * f / c)^2
    G [dBi]    = 10*log10(eta) + 20*log10(pi * D * f / c)

where ``D`` is the dish diameter [m], ``f`` is frequency [Hz], and ``eta``
is the aperture efficiency (dimensionless, typically 0.5-0.65 for a
well-illuminated parabolic reflector).

This module deliberately models only the ground-station receive antenna as
a parabolic dish. The spacecraft transmit antenna gain is treated purely as
an electrical requirement (``Transmitter.antenna_gain_dbi``) elsewhere in
this package — see the note in ``docs/trade_study.md`` on why a spacecraft
antenna is not assumed to be a dish.
"""

from __future__ import annotations

import numpy as np

from .constants import SPEED_OF_LIGHT
from .conversions import ArrayLike, db

#: A representative aperture efficiency for a well-illuminated parabolic
#: ground-station reflector, used as the default when none is specified.
DEFAULT_APERTURE_EFFICIENCY = 0.55


def parabolic_dish_gain_dbi(
    diameter_m: ArrayLike,
    freq_hz: ArrayLike,
    aperture_efficiency: float = DEFAULT_APERTURE_EFFICIENCY,
) -> ArrayLike:
    """Peak gain [dBi] of an idealized uniformly-illuminated parabolic dish.

    Parameters
    ----------
    diameter_m : dish diameter [m], > 0.
    freq_hz : operating frequency [Hz], > 0.
    aperture_efficiency : dimensionless illumination efficiency in (0, 1].
    """
    diameter_m = np.asarray(diameter_m, dtype=float)
    freq_hz = np.asarray(freq_hz, dtype=float)
    if np.any(diameter_m <= 0):
        raise ValueError("diameter_m must be strictly positive.")
    if np.any(freq_hz <= 0):
        raise ValueError("freq_hz must be strictly positive.")
    if not (0.0 < aperture_efficiency <= 1.0):
        raise ValueError("aperture_efficiency must be in (0, 1].")

    ratio = np.pi * diameter_m * freq_hz / SPEED_OF_LIGHT
    gain_linear = aperture_efficiency * ratio**2
    return db(gain_linear)


def parabolic_dish_diameter_for_gain_m(
    gain_dbi: ArrayLike,
    freq_hz: ArrayLike,
    aperture_efficiency: float = DEFAULT_APERTURE_EFFICIENCY,
) -> ArrayLike:
    """Inverse of :func:`parabolic_dish_gain_dbi`: dish diameter [m] for a target gain.

    Closed-form inversion (gain is proportional to D^2, i.e. 20*log10(D) is
    linear in gain_dbi) -- no numerical root-finding required.
    """
    gain_dbi = np.asarray(gain_dbi, dtype=float)
    freq_hz = np.asarray(freq_hz, dtype=float)
    if np.any(freq_hz <= 0):
        raise ValueError("freq_hz must be strictly positive.")
    if not (0.0 < aperture_efficiency <= 1.0):
        raise ValueError("aperture_efficiency must be in (0, 1].")

    from .conversions import undb

    gain_linear = undb(gain_dbi)
    ratio_squared = gain_linear / aperture_efficiency
    ratio = np.sqrt(ratio_squared)
    return ratio * SPEED_OF_LIGHT / (np.pi * freq_hz)
