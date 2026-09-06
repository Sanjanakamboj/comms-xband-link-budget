"""Free-space propagation loss.

Implements the Friis free-space path loss (FSPL) equation, which is the
dominant loss term in any deep-space or near-Earth RF link budget.

    FSPL = (4 * pi * R * f / c)^2                      [linear power ratio]
    FSPL_dB = 20*log10(4*pi*R*f/c)
            = 20*log10(R) + 20*log10(f) + 20*log10(4*pi/c)

where R is the slant range [m] and f is the carrier frequency [Hz].

A second, independently-derived closed form (common in telecom references,
expressed in km and MHz) is also provided in ``tests/`` as a cross-check:

    FSPL_dB = 32.44 + 20*log10(R_km) + 20*log10(f_MHz)

Both forms are algebraically identical; carrying two independent
implementations through to the test suite is the verification strategy
required by this project (see docs/verification.md).
"""

from __future__ import annotations

import numpy as np

from .constants import SPEED_OF_LIGHT
from .conversions import ArrayLike, db


def free_space_path_loss_db(range_m: ArrayLike, freq_hz: ArrayLike) -> ArrayLike:
    """Free-space path loss in dB for slant range ``range_m`` at ``freq_hz``.

    Parameters
    ----------
    range_m : slant range between transmitter and receiver [m], > 0.
    freq_hz : carrier frequency [Hz], > 0.

    Returns
    -------
    Path loss in dB (a positive number representing signal attenuation).
    """
    range_m = np.asarray(range_m, dtype=float)
    freq_hz = np.asarray(freq_hz, dtype=float)
    if np.any(range_m <= 0):
        raise ValueError("range_m must be strictly positive.")
    if np.any(freq_hz <= 0):
        raise ValueError("freq_hz must be strictly positive.")

    ratio = 4.0 * np.pi * range_m * freq_hz / SPEED_OF_LIGHT
    return db(ratio**2)


def free_space_path_loss_linear(range_m: ArrayLike, freq_hz: ArrayLike) -> ArrayLike:
    """Free-space path loss as a dimensionless linear power ratio (>= 1)."""
    range_m = np.asarray(range_m, dtype=float)
    freq_hz = np.asarray(freq_hz, dtype=float)
    ratio = 4.0 * np.pi * range_m * freq_hz / SPEED_OF_LIGHT
    return ratio**2


def slant_range_from_altitude_and_elevation(
    altitude_m: float,
    elevation_deg: float,
    earth_radius_m: float = 6_378_137.0,
) -> float:
    """Slant range [m] from a circular-orbit spacecraft to a ground station.

    Uses exact spherical geometry (law of cosines in the Earth-center /
    spacecraft / ground-station triangle), not the flat-Earth
    approximation, so it stays valid down to low elevation angles.

    Parameters
    ----------
    altitude_m : spacecraft altitude above the Earth's surface [m].
    elevation_deg : ground-station elevation angle to the spacecraft
        [degrees], 0 (horizon) to 90 (zenith).
    earth_radius_m : mean Earth radius [m].
    """
    if not (0.0 <= elevation_deg <= 90.0):
        raise ValueError("elevation_deg must be in [0, 90].")
    if altitude_m <= 0:
        raise ValueError("altitude_m must be strictly positive.")

    r_e = earth_radius_m
    r_s = earth_radius_m + altitude_m
    el = np.radians(elevation_deg)

    # Angle at the spacecraft opposite the Earth-radius side, via the law of
    # sines applied to the Earth-center/ground-station/spacecraft triangle.
    gamma = np.arcsin((r_e / r_s) * np.cos(el))
    # Interior angle at Earth's center.
    earth_center_angle = np.pi / 2.0 - el - gamma
    # Law of cosines for the slant range side.
    slant_range = np.sqrt(
        r_e**2 + r_s**2 - 2.0 * r_e * r_s * np.cos(earth_center_angle)
    )
    return float(slant_range)
