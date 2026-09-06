"""Physical constants and standard reference values used throughout the package.

All values are SI (meters, seconds, kelvin, watts, hertz) unless noted.
Sources: CODATA 2018 (via NIST) and standard telecom-engineering references.
"""

from __future__ import annotations

#: Speed of light in vacuum [m/s] (exact, by SI definition).
SPEED_OF_LIGHT: float = 299_792_458.0

#: Boltzmann constant [J/K] = [W/(Hz*K)] (exact, 2019 SI redefinition).
BOLTZMANN_CONSTANT: float = 1.380649e-23

#: Standard reference noise temperature used in noise-figure definitions [K].
T0_REFERENCE: float = 290.0

#: Conventional "room temperature" used for some antenna-noise baselines [K].
T_AMBIENT: float = 290.0

# --- X-band downlink allocation (deep-space / near-Earth, ITU/CCSDS) -----
#: Lower edge of the X-band deep-space downlink allocation [Hz].
X_BAND_DOWNLINK_MIN_HZ: float = 8_400e6

#: Upper edge of the X-band deep-space downlink allocation [Hz].
X_BAND_DOWNLINK_MAX_HZ: float = 8_450e6

#: Commonly used representative X-band downlink center frequency [Hz].
X_BAND_DOWNLINK_CENTER_HZ: float = 8_425e6
