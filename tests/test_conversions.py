import numpy as np
import pytest

from xband_link import conversions as cv


def test_db_undb_round_trip():
    for x in [0.001, 0.5, 1.0, 2.0, 1e6, 3.7e-9]:
        assert cv.undb(cv.db(x)) == pytest.approx(x, rel=1e-12)


def test_db_known_values():
    assert cv.db(1.0) == pytest.approx(0.0)
    assert cv.db(10.0) == pytest.approx(10.0)
    assert cv.db(100.0) == pytest.approx(20.0)
    assert cv.db(2.0) == pytest.approx(3.0103, abs=1e-3)


def test_db_rejects_nonpositive():
    with pytest.raises(ValueError):
        cv.db(0.0)
    with pytest.raises(ValueError):
        cv.db(-5.0)


def test_watts_dbw_round_trip():
    for p in [1e-3, 1.0, 4.0, 100.0]:
        assert cv.dbw_to_watts(cv.watts_to_dbw(p)) == pytest.approx(p, rel=1e-12)


def test_dbw_dbm_offset():
    assert cv.dbw_to_dbm(0.0) == pytest.approx(30.0)
    assert cv.dbm_to_dbw(30.0) == pytest.approx(0.0)
    assert cv.watts_to_dbm(1.0) == pytest.approx(30.0)
    assert cv.dbm_to_watts(0.0) == pytest.approx(1e-3)


def test_hz_dbhz_round_trip():
    for r in [1.0, 1e3, 2_000_000.0]:
        assert cv.dbhz_to_hz(cv.hz_to_dbhz(r)) == pytest.approx(r, rel=1e-12)


def test_array_input():
    arr = np.array([1.0, 10.0, 100.0])
    result = cv.db(arr)
    np.testing.assert_allclose(result, [0.0, 10.0, 20.0])
