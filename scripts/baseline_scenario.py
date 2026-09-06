"""Baseline X-band downlink scenario used throughout Milestone 1.

See docs/baseline_scenario.md for the full rationale behind every number
below. In short: a small lunar-orbit spacecraft (e.g. a lunar CubeSat/
SmallSat in a highly-elliptical orbit such as a Near Rectilinear Halo
Orbit) downlinking science/telemetry data at X-band to a ~12 m
non-DSN-class ground station, evaluated at worst-case (maximum) range.

Kept as a single importable function so scripts/, tests/, and any future
trade-study code all build the exact same scenario from one source of
truth.
"""

from __future__ import annotations

from xband_link.link_budget import Channel, LinkBudget, LinkRequirement, Receiver, Transmitter

#: Worst-case (apogee-class) Earth-Moon-adjacent slant range used for the
#: baseline margin evaluation [m]. Representative of a lunar NRHO-type
#: orbit's maximum range to a single ground site, slightly beyond the
#: mean Earth-Moon distance (384,400 km) to include geometric margin.
WORST_CASE_RANGE_M = 402_000e3

#: Best-case (perigee-class) range used for range-trade comparisons [m].
BEST_CASE_RANGE_M = 70_000e3


def build_baseline(range_m: float = WORST_CASE_RANGE_M) -> LinkBudget:
    """Construct the Milestone 1 baseline LinkBudget at the given range."""
    return LinkBudget(
        name="baseline-lunar-xband-downlink",
        transmitter=Transmitter(
            power_w=4.0,  # representative SmallSat X-band SSPA output
            line_loss_db=1.0,  # RF harness + diplexer from PA to antenna
            antenna_gain_dbi=22.0,  # medium-gain horn/reflector, body- or gimbal-pointed
            pointing_loss_db=0.5,  # residual pointing error allowance
        ),
        channel=Channel(
            frequency_hz=8.425e9,  # center of the 8400-8450 MHz deep-space downlink band
            range_m=range_m,
            atmospheric_loss_db=0.5,  # clear-sky gaseous + margin, moderate elevation
            other_loss_db=0.3,  # polarization mismatch + miscellaneous margin
        ),
        receiver=Receiver(
            antenna_gain_dbi=57.0,  # ~12 m ground antenna, ~55% aperture efficiency, X-band
            system_noise_temp_k=60.0,  # uncooled/lightly-cooled LNA, moderate elevation
            line_loss_db=0.3,  # feed loss ahead of the noise-temperature reference point
            pointing_loss_db=0.2,  # ground antenna residual pointing error
        ),
        requirement=LinkRequirement(
            data_rate_bps=2.0e6,  # 2 Mbps science/telemetry downlink
            required_ebn0_db=4.5,  # rate-1/2 LDPC + BPSK/QPSK, ~1e-5 FER, incl. a few tenths dB margin
            implementation_loss_db=1.0,  # modem/hardware implementation loss
        ),
    )
