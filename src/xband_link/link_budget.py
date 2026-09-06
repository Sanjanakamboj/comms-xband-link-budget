"""End-to-end X-band downlink link-budget closure.

This module composes the propagation (``propagation.py``) and noise
(``noise.py``) models into a single, auditable link-budget calculation:

    EIRP [dBW]      = Pt [dBW] - Lt_line [dB] - Lt_point [dB] + Gt [dBi]
    Path loss [dB]  = FSPL(range, freq) + L_atm + L_other (polarization,
                                                             scintillation, etc.)
    Pr [dBW]        = EIRP - Path loss + Gr [dBi] - Lr_line [dB] - Lr_point [dB]
    N0 [dBW/Hz]     = 10*log10(k_B) + 10*log10(T_sys)
    C/N0 [dB-Hz]    = Pr - N0
    Eb/N0 [dB]      = C/N0 - 10*log10(Rb)
    Margin [dB]     = Eb/N0 - (Eb/N0)_required - L_implementation

Every stage is kept as an explicit, named dB term so the resulting table
reads like a classical JPL/CCSDS-style link-budget sheet and each row can be
cross-checked by hand.

Sign convention: all *_loss_db fields are entered as **positive** numbers
representing attenuation (a loss of 1.5 dB is written as ``1.5``, not
``-1.5``); the arithmetic below subtracts them explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .conversions import dbhz_to_hz, hz_to_dbhz
from .noise import (
    g_over_t_db,
    noise_power_spectral_density_dbw_hz,
)
from .propagation import free_space_path_loss_db


@dataclass(frozen=True)
class Transmitter:
    """Spacecraft transmit chain parameters."""

    power_w: float  #: RF power at the power amplifier output [W].
    line_loss_db: float = 0.0  #: Waveguide/cabling loss from PA to antenna feed [dB].
    antenna_gain_dbi: float = 0.0  #: Spacecraft antenna peak gain [dBi].
    pointing_loss_db: float = 0.0  #: Antenna mispointing loss [dB].

    @property
    def power_dbw(self) -> float:
        from .conversions import watts_to_dbw

        return float(watts_to_dbw(self.power_w))


@dataclass(frozen=True)
class Channel:
    """Propagation-path parameters."""

    frequency_hz: float  #: Carrier frequency [Hz].
    range_m: float  #: Slant range, transmitter to receiver [m].
    atmospheric_loss_db: float = 0.0  #: Gaseous/rain/cloud attenuation [dB].
    other_loss_db: float = 0.0  #: Polarization mismatch, scintillation, margin allowances [dB].


@dataclass(frozen=True)
class Receiver:
    """Ground-station receive chain parameters."""

    antenna_gain_dbi: float  #: Ground antenna peak gain [dBi].
    system_noise_temp_k: float  #: Total system noise temperature at the LNA input [K].
    line_loss_db: float = 0.0  #: Feed/LNA-input loss ahead of the noise-temperature reference point [dB].
    pointing_loss_db: float = 0.0  #: Ground antenna mispointing loss [dB].


@dataclass(frozen=True)
class LinkRequirement:
    """Modulation/coding and data-rate requirements."""

    data_rate_bps: float  #: Information (or channel symbol) rate [bit/s].
    required_ebn0_db: float  #: Required Eb/N0 for the target BER/FER with the chosen mod/code [dB].
    implementation_loss_db: float = 0.0  #: Modem/hardware implementation loss [dB].


@dataclass(frozen=True)
class LinkBudgetResult:
    """Full itemized output of a link-budget closure, in the units noted."""

    tx_power_dbw: float
    eirp_dbw: float
    free_space_path_loss_db: float
    total_path_loss_db: float
    rx_gain_dbi: float
    g_over_t_db: float
    received_power_dbw: float
    noise_psd_dbw_hz: float
    c_over_n0_dbhz: float
    ebn0_db: float
    required_ebn0_db: float
    implementation_loss_db: float
    margin_db: float

    def to_series(self) -> pd.Series:
        """Return the result as a labeled pandas Series (one link-budget row)."""
        return pd.Series(
            {
                "Tx power (dBW)": self.tx_power_dbw,
                "EIRP (dBW)": self.eirp_dbw,
                "Free-space path loss (dB)": self.free_space_path_loss_db,
                "Total path loss (dB)": self.total_path_loss_db,
                "Rx antenna gain (dBi)": self.rx_gain_dbi,
                "G/T (dB/K)": self.g_over_t_db,
                "Received power (dBW)": self.received_power_dbw,
                "Noise PSD N0 (dBW/Hz)": self.noise_psd_dbw_hz,
                "C/N0 (dB-Hz)": self.c_over_n0_dbhz,
                "Eb/N0, actual (dB)": self.ebn0_db,
                "Eb/N0, required (dB)": self.required_ebn0_db,
                "Implementation loss (dB)": self.implementation_loss_db,
                "Link margin (dB)": self.margin_db,
            }
        )


@dataclass(frozen=True)
class LinkBudget:
    """A complete X-band downlink scenario: transmitter, channel, receiver, and requirement."""

    transmitter: Transmitter
    channel: Channel
    receiver: Receiver
    requirement: LinkRequirement
    name: str = "downlink"

    def compute(self) -> LinkBudgetResult:
        tx = self.transmitter
        ch = self.channel
        rx = self.receiver
        req = self.requirement

        tx_power_dbw = tx.power_dbw
        eirp_dbw = tx_power_dbw - tx.line_loss_db - tx.pointing_loss_db + tx.antenna_gain_dbi

        fspl_db = float(free_space_path_loss_db(ch.range_m, ch.frequency_hz))
        total_path_loss_db = fspl_db + ch.atmospheric_loss_db + ch.other_loss_db

        received_power_dbw = (
            eirp_dbw
            - total_path_loss_db
            + rx.antenna_gain_dbi
            - rx.line_loss_db
            - rx.pointing_loss_db
        )

        g_t_db = g_over_t_db(rx.antenna_gain_dbi - rx.line_loss_db, rx.system_noise_temp_k)
        noise_psd_dbw_hz = float(noise_power_spectral_density_dbw_hz(rx.system_noise_temp_k))

        c_over_n0_dbhz = received_power_dbw - noise_psd_dbw_hz
        ebn0_db = c_over_n0_dbhz - float(hz_to_dbhz(req.data_rate_bps))

        margin_db = ebn0_db - req.required_ebn0_db - req.implementation_loss_db

        return LinkBudgetResult(
            tx_power_dbw=tx_power_dbw,
            eirp_dbw=eirp_dbw,
            free_space_path_loss_db=fspl_db,
            total_path_loss_db=total_path_loss_db,
            rx_gain_dbi=rx.antenna_gain_dbi,
            g_over_t_db=float(g_t_db),
            received_power_dbw=received_power_dbw,
            noise_psd_dbw_hz=noise_psd_dbw_hz,
            c_over_n0_dbhz=c_over_n0_dbhz,
            ebn0_db=ebn0_db,
            required_ebn0_db=req.required_ebn0_db,
            implementation_loss_db=req.implementation_loss_db,
            margin_db=margin_db,
        )

    def max_data_rate_for_margin(self, target_margin_db: float = 0.0) -> float:
        """Solve for the maximum data rate [bit/s] that yields ``target_margin_db``.

        Since Eb/N0 [dB] = C/N0 [dB-Hz] - 10*log10(Rb) is linear in
        10*log10(Rb), the margin equation can be inverted in closed form
        rather than searched numerically.
        """
        result = self.compute()
        # margin = c_over_n0 - 10log10(Rb) - required_ebn0 - impl_loss - target_margin = 0
        allowed_ebn0_db = result.c_over_n0_dbhz - result.required_ebn0_db - result.implementation_loss_db - target_margin_db
        return float(dbhz_to_hz(allowed_ebn0_db))

    # -- Closed-form inverse-design helpers -------------------------------
    #
    # Margin is linear in every dB-domain term of the link equation with a
    # coefficient of exactly +1 for Pt[dBW], Gt[dBi], and Gr[dBi] (and -1 for
    # any additional loss term). That means "what value of X closes the link
    # with target margin M?" never needs a numerical root-find: shift the
    # current value of X in the dB domain by
    # (target_margin_db - current_margin_db) and the forward model reproduces
    # the requested margin exactly. Each helper below is a one-line
    # consequence of that linearity; docs/link_budget_equations.md derives it
    # and tests/test_link_budget.py verifies the forward/inverse round trip.

    def required_tx_power_w_for_margin(self, target_margin_db: float = 0.0) -> float:
        """Transmit power [W] (all else fixed) that yields ``target_margin_db``."""
        from .conversions import dbw_to_watts

        current_margin_db = self.compute().margin_db
        delta_db = target_margin_db - current_margin_db
        required_power_dbw = self.transmitter.power_dbw + delta_db
        return float(dbw_to_watts(required_power_dbw))

    def required_tx_gain_dbi_for_margin(self, target_margin_db: float = 0.0) -> float:
        """Spacecraft transmit antenna gain [dBi] (all else fixed) for ``target_margin_db``."""
        current_margin_db = self.compute().margin_db
        delta_db = target_margin_db - current_margin_db
        return self.transmitter.antenna_gain_dbi + delta_db

    def required_rx_gain_dbi_for_margin(self, target_margin_db: float = 0.0) -> float:
        """Ground-station receive antenna gain [dBi] (all else fixed) for ``target_margin_db``."""
        current_margin_db = self.compute().margin_db
        delta_db = target_margin_db - current_margin_db
        return self.receiver.antenna_gain_dbi + delta_db
