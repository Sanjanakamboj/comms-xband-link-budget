"""Structured trade-study sweeps over a baseline :class:`LinkBudget`.

This module is a thin, vectorized *analysis layer* on top of the verified
Milestone 1 physics (``propagation.py``, ``noise.py``, ``link_budget.py``).
It never reimplements an RF equation: every sweep below constructs modified
copies of an existing ``LinkBudget`` (via ``dataclasses.replace``) and calls
its already-verified ``compute()`` / inverse-helper methods, or — where the
underlying relationship is exactly linear in the dB domain (range and data
rate) — evaluates the closed form directly for speed on large sweeps.

All sweep functions return a small, explicitly-typed dataclass (never a bare
dict), each with a ``to_dataframe()`` method for tables/CSV/plots.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .antennas import DEFAULT_APERTURE_EFFICIENCY, parabolic_dish_diameter_for_gain_m, parabolic_dish_gain_dbi
from .conversions import ArrayLike, hz_to_dbhz
from .link_budget import LinkBudget

__all__ = [
    "RangeSweep",
    "DataRateSweep",
    "ClosureMap",
    "HardwareSweep",
    "JointHardwareTrade",
    "sweep_range",
    "sweep_data_rate",
    "max_data_rate_vs_range",
    "closure_map",
    "sweep_transmit_power",
    "sweep_tx_gain",
    "sweep_ground_dish",
    "joint_power_dish_trade",
    "required_ground_dish_diameter_for_margin",
    "finite_difference_slope",
]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RangeSweep:
    """Result of sweeping slant range at fixed hardware/data-rate."""

    range_m: np.ndarray
    free_space_path_loss_db: np.ndarray
    received_power_dbw: np.ndarray
    c_over_n0_dbhz: np.ndarray
    ebn0_db: np.ndarray
    margin_db: np.ndarray

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "range_km": self.range_m / 1e3,
                "fspl_db": self.free_space_path_loss_db,
                "received_power_dbw": self.received_power_dbw,
                "c_over_n0_dbhz": self.c_over_n0_dbhz,
                "ebn0_db": self.ebn0_db,
                "margin_db": self.margin_db,
            }
        )


@dataclass(frozen=True)
class DataRateSweep:
    """Result of sweeping data rate at fixed hardware/range."""

    data_rate_bps: np.ndarray
    ebn0_db: np.ndarray
    margin_db: np.ndarray

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "data_rate_bps": self.data_rate_bps,
                "ebn0_db": self.ebn0_db,
                "margin_db": self.margin_db,
            }
        )


@dataclass(frozen=True)
class ClosureMap:
    """2D link-margin map over (range, data rate)."""

    range_m: np.ndarray  #: 1D array, length N_r.
    data_rate_bps: np.ndarray  #: 1D array, length N_b.
    margin_db: np.ndarray  #: 2D array, shape (N_r, N_b): margin_db[i, j] at (range_m[i], data_rate_bps[j]).

    def to_dataframe(self) -> pd.DataFrame:
        """Long-form (tidy) table: one row per (range, data_rate) pair."""
        rr, bb = np.meshgrid(self.range_m, self.data_rate_bps, indexing="ij")
        return pd.DataFrame(
            {
                "range_km": rr.ravel() / 1e3,
                "data_rate_bps": bb.ravel(),
                "margin_db": self.margin_db.ravel(),
            }
        )


@dataclass(frozen=True)
class HardwareSweep:
    """Result of sweeping a single hardware parameter at fixed worst-case range."""

    parameter_name: str
    parameter_unit: str
    parameter_values: np.ndarray
    margin_db: np.ndarray
    max_data_rate_bps: np.ndarray  #: Max data rate for zero margin at each parameter value.

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                self.parameter_name: self.parameter_values,
                "margin_db": self.margin_db,
                "max_data_rate_bps": self.max_data_rate_bps,
            }
        )


@dataclass(frozen=True)
class JointHardwareTrade:
    """2D link-margin map over two hardware parameters."""

    x_name: str
    x_unit: str
    x_values: np.ndarray
    y_name: str
    y_unit: str
    y_values: np.ndarray
    margin_db: np.ndarray  #: shape (len(y_values), len(x_values)) -- matplotlib contour/pcolormesh convention.

    def to_dataframe(self) -> pd.DataFrame:
        xx, yy = np.meshgrid(self.x_values, self.y_values)
        return pd.DataFrame(
            {
                self.x_name: xx.ravel(),
                self.y_name: yy.ravel(),
                "margin_db": self.margin_db.ravel(),
            }
        )


# ---------------------------------------------------------------------------
# Range and data-rate sweeps
# ---------------------------------------------------------------------------


def sweep_range(link: LinkBudget, ranges_m: ArrayLike) -> RangeSweep:
    """Sweep slant range, holding all other parameters at ``link``'s values."""
    ranges_m = np.atleast_1d(np.asarray(ranges_m, dtype=float))
    fspl = np.empty_like(ranges_m)
    pr = np.empty_like(ranges_m)
    cn0 = np.empty_like(ranges_m)
    ebn0 = np.empty_like(ranges_m)
    margin = np.empty_like(ranges_m)

    for i, r in enumerate(ranges_m):
        trial = dataclasses.replace(link, channel=dataclasses.replace(link.channel, range_m=float(r)))
        result = trial.compute()
        fspl[i] = result.free_space_path_loss_db
        pr[i] = result.received_power_dbw
        cn0[i] = result.c_over_n0_dbhz
        ebn0[i] = result.ebn0_db
        margin[i] = result.margin_db

    return RangeSweep(
        range_m=ranges_m,
        free_space_path_loss_db=fspl,
        received_power_dbw=pr,
        c_over_n0_dbhz=cn0,
        ebn0_db=ebn0,
        margin_db=margin,
    )


def sweep_data_rate(link: LinkBudget, data_rates_bps: ArrayLike) -> DataRateSweep:
    """Sweep data rate, holding range/hardware at ``link``'s values.

    Vectorized directly from the closed form (Eb/N0 = C/N0 - 10log10(Rb)),
    since C/N0 does not depend on data rate -- computed once via
    ``link.compute()`` and reused for every point.
    """
    data_rates_bps = np.atleast_1d(np.asarray(data_rates_bps, dtype=float))
    base = link.compute()
    ebn0 = base.c_over_n0_dbhz - hz_to_dbhz(data_rates_bps)
    margin = ebn0 - base.required_ebn0_db - base.implementation_loss_db
    return DataRateSweep(data_rate_bps=data_rates_bps, ebn0_db=ebn0, margin_db=margin)


def max_data_rate_vs_range(
    link: LinkBudget, ranges_m: ArrayLike, target_margin_db: float = 0.0
) -> np.ndarray:
    """Maximum data rate [bit/s] for ``target_margin_db``, as a function of range.

    Uses the closed-form inversion (``LinkBudget.max_data_rate_for_margin``)
    at each range point -- no numerical search.
    """
    ranges_m = np.atleast_1d(np.asarray(ranges_m, dtype=float))
    out = np.empty_like(ranges_m)
    for i, r in enumerate(ranges_m):
        trial = dataclasses.replace(link, channel=dataclasses.replace(link.channel, range_m=float(r)))
        out[i] = trial.max_data_rate_for_margin(target_margin_db)
    return out


def closure_map(link: LinkBudget, ranges_m: ArrayLike, data_rates_bps: ArrayLike) -> ClosureMap:
    """2D margin map M(R, Rb).

    C/N0 depends only on range (not on data rate), so this is computed as an
    outer sum in the dB domain rather than a doubly-nested call into
    ``compute()`` -- exact, and fast even for large grids.
    """
    ranges_m = np.atleast_1d(np.asarray(ranges_m, dtype=float))
    data_rates_bps = np.atleast_1d(np.asarray(data_rates_bps, dtype=float))

    range_sweep = sweep_range(
        link,
        ranges_m,
    )  # gives c_over_n0_dbhz(range) at the link's own data rate (irrelevant to C/N0)
    base = link.compute()

    # margin[i, j] = c_over_n0(range_i) - 10log10(Rb_j) - required_ebn0 - impl_loss
    margin = (
        range_sweep.c_over_n0_dbhz[:, None]
        - hz_to_dbhz(data_rates_bps)[None, :]
        - base.required_ebn0_db
        - base.implementation_loss_db
    )
    return ClosureMap(range_m=ranges_m, data_rate_bps=data_rates_bps, margin_db=margin)


# ---------------------------------------------------------------------------
# Single-parameter hardware sweeps (evaluated at the link's own range, i.e.
# the caller should pass a `link` already configured at worst-case range)
# ---------------------------------------------------------------------------


def sweep_transmit_power(link: LinkBudget, powers_w: ArrayLike) -> HardwareSweep:
    """Sweep spacecraft transmit power [W], holding everything else fixed."""
    powers_w = np.atleast_1d(np.asarray(powers_w, dtype=float))
    margin = np.empty_like(powers_w)
    max_rate = np.empty_like(powers_w)
    for i, p in enumerate(powers_w):
        trial = dataclasses.replace(link, transmitter=dataclasses.replace(link.transmitter, power_w=float(p)))
        margin[i] = trial.compute().margin_db
        max_rate[i] = trial.max_data_rate_for_margin(0.0)
    return HardwareSweep(
        parameter_name="tx_power_w",
        parameter_unit="W",
        parameter_values=powers_w,
        margin_db=margin,
        max_data_rate_bps=max_rate,
    )


def sweep_tx_gain(link: LinkBudget, gains_dbi: ArrayLike) -> HardwareSweep:
    """Sweep spacecraft transmit antenna gain [dBi], holding everything else fixed."""
    gains_dbi = np.atleast_1d(np.asarray(gains_dbi, dtype=float))
    margin = np.empty_like(gains_dbi)
    max_rate = np.empty_like(gains_dbi)
    for i, g in enumerate(gains_dbi):
        trial = dataclasses.replace(
            link, transmitter=dataclasses.replace(link.transmitter, antenna_gain_dbi=float(g))
        )
        margin[i] = trial.compute().margin_db
        max_rate[i] = trial.max_data_rate_for_margin(0.0)
    return HardwareSweep(
        parameter_name="tx_gain_dbi",
        parameter_unit="dBi",
        parameter_values=gains_dbi,
        margin_db=margin,
        max_data_rate_bps=max_rate,
    )


def sweep_ground_dish(
    link: LinkBudget,
    diameters_m: ArrayLike,
    aperture_efficiency: float = DEFAULT_APERTURE_EFFICIENCY,
) -> HardwareSweep:
    """Sweep ground-station dish diameter [m] at fixed frequency and aperture efficiency.

    Receive gain is recomputed at each diameter via the idealized parabolic-
    dish model (``antennas.parabolic_dish_gain_dbi``); system noise
    temperature and all other parameters are held fixed.
    """
    diameters_m = np.atleast_1d(np.asarray(diameters_m, dtype=float))
    margin = np.empty_like(diameters_m)
    max_rate = np.empty_like(diameters_m)
    for i, d in enumerate(diameters_m):
        gr = float(parabolic_dish_gain_dbi(d, link.channel.frequency_hz, aperture_efficiency))
        trial = dataclasses.replace(link, receiver=dataclasses.replace(link.receiver, antenna_gain_dbi=gr))
        margin[i] = trial.compute().margin_db
        max_rate[i] = trial.max_data_rate_for_margin(0.0)
    return HardwareSweep(
        parameter_name="ground_dish_diameter_m",
        parameter_unit="m",
        parameter_values=diameters_m,
        margin_db=margin,
        max_data_rate_bps=max_rate,
    )


def required_ground_dish_diameter_for_margin(
    link: LinkBudget,
    target_margin_db: float = 0.0,
    aperture_efficiency: float = DEFAULT_APERTURE_EFFICIENCY,
) -> float:
    """Ground-dish diameter [m] (all else fixed) that yields ``target_margin_db``.

    Composes two closed-form inversions: the required receive gain
    (``LinkBudget.required_rx_gain_dbi_for_margin``) and the dish diameter
    for that gain (``antennas.parabolic_dish_diameter_for_gain_m``).
    """
    required_gain_dbi = link.required_rx_gain_dbi_for_margin(target_margin_db)
    return float(
        parabolic_dish_diameter_for_gain_m(required_gain_dbi, link.channel.frequency_hz, aperture_efficiency)
    )


# ---------------------------------------------------------------------------
# Joint two-parameter hardware trade
# ---------------------------------------------------------------------------


def joint_power_dish_trade(
    link: LinkBudget,
    powers_w: ArrayLike,
    diameters_m: ArrayLike,
    aperture_efficiency: float = DEFAULT_APERTURE_EFFICIENCY,
) -> JointHardwareTrade:
    """2D margin map M(Pt, D_ground): spacecraft power vs. ground-dish diameter.

    Both terms enter margin linearly in the dB domain (Pt via 10log10(W),
    D via 20log10(D) through the aperture-gain relation), so this is
    computed as an exact outer sum rather than a nested call into
    ``compute()`` at every grid point.
    """
    powers_w = np.atleast_1d(np.asarray(powers_w, dtype=float))
    diameters_m = np.atleast_1d(np.asarray(diameters_m, dtype=float))

    tx_power_dbw = 10.0 * np.log10(powers_w)
    gr_dbi = np.asarray(
        parabolic_dish_gain_dbi(diameters_m, link.channel.frequency_hz, aperture_efficiency)
    )

    base = link.compute()
    baseline_tx_power_dbw = link.transmitter.power_dbw
    baseline_gr_dbi = link.receiver.antenna_gain_dbi

    # margin[j, i] at (powers_w[i], diameters_m[j]) -- rows = y (diameter), cols = x (power)
    delta_power = (tx_power_dbw - baseline_tx_power_dbw)[None, :]
    delta_gain = (gr_dbi - baseline_gr_dbi)[:, None]
    margin = base.margin_db + delta_power + delta_gain

    return JointHardwareTrade(
        x_name="tx_power_w",
        x_unit="W",
        x_values=powers_w,
        y_name="ground_dish_diameter_m",
        y_unit="m",
        y_values=diameters_m,
        margin_db=margin,
    )


# ---------------------------------------------------------------------------
# Sensitivity utility
# ---------------------------------------------------------------------------


def finite_difference_slope(f: Callable[[float], float], x0: float, step: float) -> float:
    """Central-difference slope of scalar function ``f`` at ``x0``.

    Used to numerically verify the analytical link-budget sensitivities
    documented in docs/trade_study.md (dM/dPt[dB] = +1, dM/dGt = +1,
    dM/dGr = +1, dM/dlog10(R) = -20, dM/dlog10(Rb) = -10, etc.).
    """
    return (f(x0 + step) - f(x0 - step)) / (2.0 * step)
