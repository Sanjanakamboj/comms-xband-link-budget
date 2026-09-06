# Baseline Scenario Rationale

Milestone 1 needs a single, defensible baseline scenario to verify the
equations against and to seed later trade studies. This document justifies
every parameter in `scripts/baseline_scenario.py`.

## Mission concept

A small spacecraft (CubeSat/SmallSat class) in a highly-elliptical lunar
orbit — e.g., a Near Rectilinear Halo Orbit (NRHO), similar in spirit to
missions such as CAPSTONE — downlinking science and telemetry data at
X-band to a single non-DSN-class ground station. The orbit's range to Earth
varies substantially over an orbit, from a few tens of thousands of km near
perigee to beyond the mean Earth-Moon distance near apogee. This makes
**worst-case (maximum) range** the natural, mission-realistic driver for a
margin analysis, rather than an arbitrary fixed range.

X-band (8400-8450 MHz downlink) is chosen because it is the standard deep-
space/near-Earth downlink band for this class of mission (CCSDS/ITU
deep-space allocation), offering more bandwidth than S-band while requiring
less pointing precision than Ka-band.

## Parameter-by-parameter justification

| Parameter | Value | Rationale |
|---|---:|---|
| Tx power (PA output) | 4.0 W | Representative output for a flight-qualified SmallSat X-band SSPA (solid-state power amplifier); consistent with e.g. Iris-class deep-space transponders. |
| Tx line loss | 1.0 dB | Typical RF harness + diplexer loss between PA and antenna feed on a small spacecraft. |
| Tx antenna gain | 22.0 dBi | A medium-gain horn or small reflector, body- or gimbal-pointed; achievable on a SmallSat without a large deployable. |
| Tx pointing loss | 0.5 dB | Allowance for residual attitude/pointing knowledge error. |
| Frequency | 8.425 GHz | Center of the 8400-8450 MHz deep-space downlink allocation. |
| Worst-case range | 402,000 km | Slightly beyond the mean Earth-Moon distance (384,400 km), representative of a lunar NRHO-type orbit's maximum range to a single Earth ground site. |
| Best-case range | 70,000 km | Representative near-perigee range for the same orbit class, used for range-trade comparison (see `results/range_comparison.md`). |
| Atmospheric loss | 0.5 dB | Clear-sky gaseous absorption plus a small weather margin at a moderate elevation angle; X-band is only mildly weather-sensitive compared to Ka-band. |
| Other/polarization loss | 0.3 dB | Polarization mismatch and miscellaneous unmodeled effects. |
| Rx (ground) antenna gain | 57.0 dBi | Aperture-gain estimate for a ~12 m parabolic ground antenna at X-band with ~55% aperture efficiency: `G = 10*log10(eta*(pi*D/lambda)^2)`. Representative of a capable non-DSN-class ground station (e.g. a commercial/university network antenna), not a full 34 m DSN dish (~67 dBi), which is often oversubscribed for SmallSat missions. |
| Rx line loss | 0.3 dB | Feed loss ahead of the noise-temperature reference point. |
| Rx pointing loss | 0.2 dB | Ground antenna residual pointing error. |
| System noise temperature | 60 K | A good but not cryogenically-cooled LNA front end at moderate elevation; consistent with `T_sys = T_ant + T_rx` for a well-designed non-DSN X-band ground station. |
| Data rate | 2.0 Mbps | A representative science/telemetry downlink rate for this mission class — high enough to be interesting (produces a realistically tight margin at worst-case range) rather than trivially over-closed. |
| Required Eb/N0 | 4.5 dB | Representative of a rate-1/2 LDPC-coded BPSK/QPSK link at a low frame-error-rate operating point (CCSDS-style coded performance), with a small allowance folded in. |
| Implementation loss | 1.0 dB | Standard allowance for modem/hardware implementation loss not otherwise itemized. |

## Why this baseline (not a bigger/smaller one)

The parameters above were deliberately tuned so the **worst-case-range
link margin is realistically tight (~1-2 dB)** rather than either failing
outright or closing with tens of dB to spare. A link budget that always
closes with 15+ dB of margin (e.g., using a full 34 m DSN antenna at a
modest data rate) is not an interesting engineering trade — nothing is at
stake. A baseline that fails to close at all isn't representative of a
credibly designed mission either. Sitting close to the margin boundary
means the Milestone 2+ trade studies (power vs. gain vs. range vs. data
rate vs. required Eb/N0) will visibly move the link between closing and
failing, which is the whole point of a trade-study tool.

See `results/baseline_link_budget.md` for the computed baseline table and
`results/range_comparison.md` for the worst-case vs. best-case comparison.
