# Link-Budget Equations and Conventions

This document is the engineering reference for every equation implemented in
`src/xband_link/`. It is the source of truth: code should match this
document, and any change to the equations should update both.

## 1. Units and sign conventions

- All physical quantities are carried in **SI base units** internally
  (meters, seconds, kelvin, watts, hertz).
- Power ratios and absolute powers are converted to the **decibel domain**
  only at the point of use (`conversions.py`), never silently mixed.
- **dBW**: dB relative to 1 W. **dBm**: dB relative to 1 mW (`dBW = dBm - 30`).
- **dBi**: antenna gain in dB relative to an isotropic radiator.
- **dB-Hz**: used for rate-like and spectral-density-like quantities
  (C/N0, data rate expressed in the log domain) — literally
  `10*log10(value_in_Hz)`.
- **All loss terms (`*_loss_db`, `L*`) are entered as positive numbers**
  representing attenuation. The link-budget arithmetic subtracts them
  explicitly; a loss is never pre-negated by the caller.

## 2. Free-space path loss (FSPL)

For a transmitter and receiver separated by slant range `R` [m] at carrier
frequency `f` [Hz], propagating in vacuum/near-vacuum:

```
FSPL (linear) = (4*pi*R*f / c)^2
FSPL [dB]     = 20*log10(4*pi*R*f/c)
              = 20*log10(R) + 20*log10(f) + 20*log10(4*pi/c)
```

This is the dominant loss term for any deep-space or near-Earth downlink —
at X-band lunar range (~400,000 km) it is on the order of 220 dB.

Implementation: `propagation.free_space_path_loss_db`.

**Independent cross-check form** (km, MHz units, commonly tabulated):

```
FSPL [dB] = 32.45 + 20*log10(R_km) + 20*log10(f_MHz)
```

The two forms are algebraically identical (the constant `32.45` absorbs the
km->m, MHz->Hz unit conversion and the `20*log10(4*pi/c)` term); see
`tests/test_propagation.py` and `scripts/verify_link_budget.py`.

## 3. EIRP (Effective Isotropic Radiated Power)

```
EIRP [dBW] = Pt [dBW] - L_t,line [dB] - L_t,point [dB] + Gt [dBi]
```

where `Pt` is the power amplifier RF output power, `L_t,line` is the cabling/
waveguide loss between the PA and the antenna feed, `L_t,point` is the
antenna pointing-error loss, and `Gt` is the transmit antenna peak gain.

## 4. Total path loss

```
L_path,total [dB] = FSPL [dB] + L_atm [dB] + L_other [dB]
```

`L_atm` covers clear-sky gaseous absorption (and, if relevant, rain/cloud
attenuation); `L_other` bundles polarization mismatch and any additional
margin allowances not otherwise itemized. Milestone 1 treats these as fixed
scalar allowances; a full atmospheric model (ITU-R P.618-style, elevation-
and weather-dependent) is out of scope here.

## 5. Received power

```
Pr [dBW] = EIRP [dBW] - L_path,total [dB] + Gr [dBi] - L_r,line [dB] - L_r,point [dB]
```

`Gr` is the ground-station antenna peak gain, `L_r,line` is the feed/LNA-
input loss ahead of the noise-temperature reference point, and `L_r,point`
is the ground antenna pointing-error loss.

## 6. Thermal noise floor

The receiver's thermal noise is characterized by a single-sided power
spectral density:

```
N0 [W/Hz]   = k_B * T_sys
N0 [dBW/Hz] = 10*log10(k_B) + 10*log10(T_sys)
```

`k_B = 1.380649e-23 J/K` (exact, 2019 SI). `T_sys` [K] is the total system
noise temperature referenced at the same point as `Gr` (typically the LNA
input):

```
T_sys = T_antenna + T_receiver
T_receiver = T0 * (10^(NF/10) - 1),   T0 = 290 K
```

A widely-used reference figure: `10*log10(k_B) = -228.60 dBW/Hz/K`, so at
`T_sys = 290 K`, `N0 = -228.60 + 10*log10(290) = -203.98 dBW/Hz`
(`noise.py`, cross-checked in `tests/test_noise.py`).

### Receiver figure of merit, G/T

```
G/T [dB/K] = (Gr [dBi] - L_r,line [dB]) - 10*log10(T_sys [K])
```

A single number summarizing ground-station receive performance, standard
in DSN/CCSDS-style link budgets.

## 7. Carrier-to-noise-density ratio, C/N0

```
C/N0 [dB-Hz] = Pr [dBW] - N0 [dBW/Hz]
```

## 8. Energy-per-bit-to-noise-density ratio, Eb/N0

```
Eb/N0 [dB] = C/N0 [dB-Hz] - 10*log10(Rb [bit/s])
```

where `Rb` is the information (or channel symbol) rate.

## 9. Link margin

```
Margin [dB] = Eb/N0,actual [dB] - Eb/N0,required [dB] - L_implementation [dB]
```

`Eb/N0,required` is the value needed to close the link at the target
bit/frame-error rate for the chosen modulation and coding scheme (an input,
not derived by this tool in Milestone 1). `L_implementation` bundles modem
and hardware implementation losses not otherwise captured.

A positive margin means the link closes with the stated allowance; by
convention this project reports raw margin (no additional blanket adverse-
tolerance subtracted beyond what is itemized above) so every loss is
traceable to a named term.

## 10. Inverting the equations (data-rate solve)

Because `Eb/N0 [dB]` is linear in `10*log10(Rb)`, the maximum data rate for
a target margin has a closed form (no numerical search needed):

```
Eb/N0,allowed [dB] = C/N0 [dB-Hz] - Eb/N0,required [dB] - L_implementation [dB] - target_margin [dB]
Rb,max [bit/s]      = 10^(Eb/N0,allowed / 10)
```

Implementation: `LinkBudget.max_data_rate_for_margin`.
