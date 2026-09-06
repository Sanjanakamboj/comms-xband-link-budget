"""Decibel-domain conversion helpers.

Convention used throughout this package:

- Power ratios (dimensionless, e.g. gain-over-noise-temperature ratios,
  loss factors) use ``db`` / ``undb`` with the 10*log10 form.
- Absolute powers referenced to 1 W are expressed in **dBW**.
- Absolute powers referenced to 1 mW are expressed in **dBm**.
- Spectral densities (power per Hz) are expressed in **dBW/Hz** or, when a
  bandwidth/rate is folded in, **dB-Hz** (e.g. C/N0, Eb/N0 bandwidth terms).

All functions operate on plain floats (or numpy arrays) in SI base units
(watts, hertz, kelvin) and return dB quantities, or vice versa. Keeping every
conversion in one module means every dB computation in the codebase is
traceable to a single, tested implementation.
"""

from __future__ import annotations

import numpy as np

ArrayLike = np.ndarray | float


def db(linear_ratio: ArrayLike) -> ArrayLike:
    """Convert a dimensionless power ratio to decibels: 10*log10(x).

    Parameters
    ----------
    linear_ratio : power ratio (must be > 0).
    """
    linear_ratio = np.asarray(linear_ratio, dtype=float)
    if np.any(linear_ratio <= 0):
        raise ValueError("linear_ratio must be strictly positive to take log10.")
    return 10.0 * np.log10(linear_ratio)


def undb(db_value: ArrayLike) -> ArrayLike:
    """Convert decibels back to a dimensionless power ratio: 10**(x/10)."""
    db_value = np.asarray(db_value, dtype=float)
    return 10.0 ** (db_value / 10.0)


def watts_to_dbw(power_w: ArrayLike) -> ArrayLike:
    """Convert power in watts to dBW (dB relative to 1 W)."""
    return db(power_w)


def dbw_to_watts(power_dbw: ArrayLike) -> ArrayLike:
    """Convert dBW back to watts."""
    return undb(power_dbw)


def watts_to_dbm(power_w: ArrayLike) -> ArrayLike:
    """Convert power in watts to dBm (dB relative to 1 mW)."""
    power_w = np.asarray(power_w, dtype=float)
    return db(power_w * 1e3)


def dbm_to_watts(power_dbm: ArrayLike) -> ArrayLike:
    """Convert dBm back to watts."""
    return undb(power_dbm) * 1e-3


def dbw_to_dbm(power_dbw: ArrayLike) -> ArrayLike:
    """Convert dBW to dBm (add 30)."""
    return np.asarray(power_dbw, dtype=float) + 30.0


def dbm_to_dbw(power_dbm: ArrayLike) -> ArrayLike:
    """Convert dBm to dBW (subtract 30)."""
    return np.asarray(power_dbm, dtype=float) - 30.0


def hz_to_dbhz(rate_hz: ArrayLike) -> ArrayLike:
    """Convert a rate/bandwidth in Hz to dB-Hz: 10*log10(rate_hz).

    Used to express data rates, bandwidths, and C/N0 units in the log
    domain, e.g. ``Eb/N0 [dB] = C/N0 [dB-Hz] - hz_to_dbhz(bit_rate_hz)``.
    """
    return db(rate_hz)


def dbhz_to_hz(rate_dbhz: ArrayLike) -> ArrayLike:
    """Convert dB-Hz back to a linear rate in Hz."""
    return undb(rate_dbhz)
