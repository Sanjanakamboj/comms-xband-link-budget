# Milestone 1 Verification Report

## Free-space path loss

Compared `xband_link.propagation.free_space_path_loss_db` (SI units, meters/Hz) against the independent km/MHz closed form `32.45 + 20*log10(R_km) + 20*log10(f_MHz)` across 200 log-spaced ranges from 1000 km to 500,000 km at 8425 MHz.

- Maximum absolute discrepancy: **2.217 mdB** (attributable only to the 32.45 constant's rounding).
- See `results/verification_fspl_vs_range.png`.

## Thermal noise floor

Compared `xband_link.noise.noise_power_spectral_density_dbw_hz` (N0 = k_B * T_sys, T_sys = 60.0 K) against the classic -228.60 dBW/Hz/K Boltzmann-constant reference figure.

- Library N0: -210.8177 dBW/Hz
- Independent reference N0: -210.8185 dBW/Hz
- Discrepancy: **0.83 mdB**

## Conclusion

Both independently-derived formulations agree with the library implementation to well under 0.01 dB across the full range of interest, confirming the propagation and noise models are implemented correctly and consistently in the dB domain.
