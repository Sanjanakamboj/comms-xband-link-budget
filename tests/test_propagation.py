"""Verification tests for free-space path loss.

Cross-checks the SI-unit implementation in ``propagation.py`` against the
independently-derived, commonly tabulated km/MHz closed form:

    FSPL_dB = 32.44 + 20*log10(R_km) + 20*log10(f_MHz)

Agreement between two algebraically-independent formulations (different
unit systems, different constant derivations) is the verification strategy
for this module; see docs/verification.md.
"""

import numpy as np
import pytest

from xband_link.propagation import (
    free_space_path_loss_db,
    free_space_path_loss_linear,
    slant_range_from_altitude_and_elevation,
)


def _fspl_db_km_mhz_reference(range_km: float, freq_mhz: float) -> float:
    """Independent reference formula (km, MHz), the standard telecom form.

    32.45 = 20*log10(4*pi*1000*1e6/c) rounded, i.e. the constant absorbs the
    km->m and MHz->Hz unit conversions (c = 299,792,458 m/s exactly).
    """
    return 32.45 + 20.0 * np.log10(range_km) + 20.0 * np.log10(freq_mhz)


@pytest.mark.parametrize(
    "range_km,freq_mhz",
    [
        (400.0, 8400.0),        # LEO-ish
        (35_786.0, 8400.0),     # GEO altitude
        (384_400.0, 8425.0),    # lunar distance
        (401_000.0, 8450.0),    # near lunar apogee, upper band edge
    ],
)
def test_fspl_matches_independent_km_mhz_formula(range_km, freq_mhz):
    fspl_si = float(free_space_path_loss_db(range_km * 1e3, freq_mhz * 1e6))
    fspl_ref = _fspl_db_km_mhz_reference(range_km, freq_mhz)
    # 32.44 constant is rounded to 2 decimal places in the reference formula.
    assert fspl_si == pytest.approx(fspl_ref, abs=5e-3)


def test_fspl_scales_20db_per_decade_of_range():
    freq_hz = 8.4e9
    fspl_1 = float(free_space_path_loss_db(1e6, freq_hz))
    fspl_10 = float(free_space_path_loss_db(1e7, freq_hz))
    assert (fspl_10 - fspl_1) == pytest.approx(20.0, abs=1e-9)


def test_fspl_scales_20db_per_decade_of_frequency():
    range_m = 4e8
    fspl_1 = float(free_space_path_loss_db(range_m, 1e9))
    fspl_10 = float(free_space_path_loss_db(range_m, 1e10))
    assert (fspl_10 - fspl_1) == pytest.approx(20.0, abs=1e-9)


def test_fspl_linear_and_db_consistent():
    range_m, freq_hz = 4.0e8, 8.425e9
    linear = float(free_space_path_loss_linear(range_m, freq_hz))
    db_val = float(free_space_path_loss_db(range_m, freq_hz))
    assert 10.0 * np.log10(linear) == pytest.approx(db_val, rel=1e-12)


def test_fspl_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        free_space_path_loss_db(-1.0, 8.4e9)
    with pytest.raises(ValueError):
        free_space_path_loss_db(1.0e6, 0.0)


def test_slant_range_zenith_equals_altitude():
    # At 90 deg elevation (zenith), slant range must equal altitude exactly.
    r = slant_range_from_altitude_and_elevation(altitude_m=500e3, elevation_deg=90.0)
    assert r == pytest.approx(500e3, rel=1e-9)


def test_slant_range_increases_as_elevation_decreases():
    r_high = slant_range_from_altitude_and_elevation(altitude_m=500e3, elevation_deg=80.0)
    r_low = slant_range_from_altitude_and_elevation(altitude_m=500e3, elevation_deg=10.0)
    assert r_low > r_high


def test_slant_range_rejects_bad_elevation():
    with pytest.raises(ValueError):
        slant_range_from_altitude_and_elevation(altitude_m=500e3, elevation_deg=95.0)
