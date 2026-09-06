"""Parametric uncertainty model for Milestone 3.

Defines a small, explicit distribution type (:class:`UncertainParameter`)
and a bundle of seven of them (:class:`UncertaintyModel`) covering every
uncertain input the project scope calls for: transmit power, spacecraft
transmit gain, ground receive gain, excess pointing loss, miscellaneous RF
loss, system noise temperature, and required Eb/N0.

**All default sigma values below are representative uncertainty
assumptions for engineering sensitivity analysis** -- illustrative
numbers in a plausible engineering range (a few tenths of a dB for
gains/losses, a few percent for power/temperature), not values sourced
from a qualification program, vendor datasheet, or test campaign. See
``docs/uncertainty_analysis.md`` for the full rationale.

Independence assumption: every parameter here is sampled independently.
This is a modeling choice (Milestone 3 scope), documented and not silently
overridden -- see ``docs/uncertainty_analysis.md`` Section on correlation.

Physical-domain discipline:

- Gains and losses are naturally additive in the dB domain
  (``domain="additive_db"``) -- gains/losses combine that way in every
  link-budget equation, so a dB-normal is the natural choice.
- Pointing loss can only ever *add* attenuation relative to the nominal
  (deterministic) allocation already in the link budget -- mispointing
  never improves pointing -- so excess pointing uncertainty is modeled as
  a non-negative perturbation (``domain="half_normal_db"``), not a
  symmetric error.
- Transmit power and system noise temperature are physically positive
  linear quantities; their uncertainty is specified as a **fractional**
  perturbation in linear units (``domain="fractional_linear"``), sampled
  in W / K respectively and only converted to the dB domain inside the
  link-budget arithmetic (10*log10(Pt) for EIRP, 10*log10(T_sys) for N0).
  This is the one genuinely nonlinear transform in the model and is the
  source of the small mean-shift discussed in
  ``docs/uncertainty_analysis.md`` Section 6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

VALID_DOMAINS = ("additive_db", "half_normal_db", "fractional_linear")


@dataclass(frozen=True)
class UncertainParameter:
    """A single uncertain input, with nominal value, distribution, and units.

    Parameters
    ----------
    name : short identifier, used as a dict/column key in results.
    nominal : nominal (deterministic, Milestone 1/2) value, in ``unit``.
    sigma : distribution spread, interpretation depends on ``domain``:
        - ``additive_db`` / ``half_normal_db``: standard deviation in dB.
        - ``fractional_linear``: standard deviation as a *fraction* of
          ``nominal`` (e.g. 0.05 = 5%), applied in linear units.
    unit : physical unit of ``nominal`` (e.g. "W", "dBi", "K", "dB").
    domain : one of ``VALID_DOMAINS`` (see module docstring).
    lower_bound, upper_bound : optional hard clip applied after sampling,
        to exclude physically impossible samples (e.g. T_sys <= 0).
    rationale : free-text justification, surfaced in docs/reports.
    """

    name: str
    nominal: float
    sigma: float
    unit: str
    domain: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.domain not in VALID_DOMAINS:
            raise ValueError(f"domain must be one of {VALID_DOMAINS}, got {self.domain!r}")
        if self.sigma < 0:
            raise ValueError(f"sigma must be >= 0, got {self.sigma}")
        if self.domain == "fractional_linear" and self.nominal <= 0:
            raise ValueError("fractional_linear domain requires nominal > 0 (a physical linear quantity).")
        if not self.unit:
            raise ValueError("unit must be a non-empty string.")
        if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound > self.upper_bound:
            raise ValueError("lower_bound must be <= upper_bound.")

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        """Draw ``n`` samples using the supplied, explicit RNG (no global state)."""
        if self.sigma == 0.0:
            samples = np.full(n, self.nominal, dtype=float)
        elif self.domain == "additive_db":
            samples = self.nominal + rng.normal(0.0, self.sigma, n)
        elif self.domain == "half_normal_db":
            samples = self.nominal + np.abs(rng.normal(0.0, self.sigma, n))
        elif self.domain == "fractional_linear":
            samples = self.nominal * (1.0 + rng.normal(0.0, self.sigma, n))
        else:  # pragma: no cover - guarded in __post_init__
            raise ValueError(self.domain)

        if self.lower_bound is not None:
            samples = np.clip(samples, self.lower_bound, None)
        if self.upper_bound is not None:
            samples = np.clip(samples, None, self.upper_bound)
        return samples

    def effective_db_std(self) -> float:
        """1-sigma spread of this parameter's contribution, converted to dB.

        Used for analytical (linearized) margin-variance propagation
        (``monte_carlo.analytical_sigma_margin``). For ``fractional_linear``
        this is the delta-method local slope of ``10*log10(x)`` at the
        nominal value: ``d(10log10 x)/dx * (sigma_frac * x) = 10*sigma_frac/ln(10)``,
        which is independent of the nominal value.
        """
        if self.domain in ("additive_db",):
            return self.sigma
        if self.domain == "half_normal_db":
            # Var[|N(0,sigma)|] = sigma^2 * (1 - 2/pi)
            return self.sigma * math.sqrt(1.0 - 2.0 / math.pi)
        if self.domain == "fractional_linear":
            return 10.0 * self.sigma / math.log(10.0)
        raise ValueError(self.domain)  # pragma: no cover


# ---------------------------------------------------------------------------
# Representative baseline uncertainty magnitudes (Milestone 3).
#
# Illustrative engineering-judgment values, NOT sourced from a specific
# hardware qualification program. See docs/uncertainty_analysis.md.
# ---------------------------------------------------------------------------

TX_POWER_SIGMA_FRACTIONAL = 0.035  #: ~3.5% (1 sigma) SSPA output power uncertainty.
TX_GAIN_SIGMA_DB = 0.3  #: Spacecraft antenna gain uncertainty/pattern knowledge [dB].
RX_GAIN_SIGMA_DB = 0.3  #: Ground antenna gain uncertainty [dB].
EXCESS_POINTING_SIGMA_DB = 0.2  #: Underlying half-normal sigma for excess mispointing loss [dB].
MISC_LOSS_SIGMA_DB = 0.3  #: Combined atmospheric+other loss estimate uncertainty [dB].
TSYS_SIGMA_FRACTIONAL = 0.05  #: ~5% (1 sigma) system noise temperature uncertainty.
REQUIRED_EBN0_SIGMA_DB = 0.3  #: Modem/coding implementation (required Eb/N0) uncertainty [dB].


@dataclass(frozen=True)
class UncertaintyModel:
    """Bundle of independent :class:`UncertainParameter` objects covering the
    Milestone 3 scope: transmit power, both antenna gains, excess pointing
    loss, miscellaneous RF loss, system noise temperature, and required
    Eb/N0. Range is deliberately excluded from the default model -- the
    project keeps worst-case range as a fixed conditioning variable
    throughout (see docs/uncertainty_analysis.md)."""

    tx_power_w: UncertainParameter
    tx_gain_dbi: UncertainParameter
    rx_gain_dbi: UncertainParameter
    excess_pointing_loss_db: UncertainParameter
    misc_loss_db: UncertainParameter
    tsys_k: UncertainParameter
    required_ebn0_db: UncertainParameter

    def as_dict(self) -> dict[str, UncertainParameter]:
        return {
            "tx_power_w": self.tx_power_w,
            "tx_gain_dbi": self.tx_gain_dbi,
            "rx_gain_dbi": self.rx_gain_dbi,
            "excess_pointing_loss_db": self.excess_pointing_loss_db,
            "misc_loss_db": self.misc_loss_db,
            "tsys_k": self.tsys_k,
            "required_ebn0_db": self.required_ebn0_db,
        }


def default_uncertainty_model(link) -> UncertaintyModel:
    """Build the representative Milestone 3 uncertainty model around ``link``'s
    nominal (Milestone 1/2) values.

    ``link`` is a ``xband_link.link_budget.LinkBudget`` -- typed loosely here
    (rather than imported) to avoid a circular import, since ``trades.py``
    and ``monte_carlo.py`` both sit alongside ``link_budget.py``.
    """
    misc_loss_nominal = link.channel.atmospheric_loss_db + link.channel.other_loss_db
    return UncertaintyModel(
        tx_power_w=UncertainParameter(
            name="tx_power_w",
            nominal=link.transmitter.power_w,
            sigma=TX_POWER_SIGMA_FRACTIONAL,
            unit="W",
            domain="fractional_linear",
            lower_bound=1e-3,
            rationale="Representative SSPA output-power uncertainty (calibration + temperature drift).",
        ),
        tx_gain_dbi=UncertainParameter(
            name="tx_gain_dbi",
            nominal=link.transmitter.antenna_gain_dbi,
            sigma=TX_GAIN_SIGMA_DB,
            unit="dBi",
            domain="additive_db",
            rationale="Representative spacecraft antenna gain/pattern-knowledge uncertainty.",
        ),
        rx_gain_dbi=UncertainParameter(
            name="rx_gain_dbi",
            nominal=link.receiver.antenna_gain_dbi,
            sigma=RX_GAIN_SIGMA_DB,
            unit="dBi",
            domain="additive_db",
            rationale="Representative ground-station antenna gain calibration uncertainty.",
        ),
        excess_pointing_loss_db=UncertainParameter(
            name="excess_pointing_loss_db",
            nominal=0.0,
            sigma=EXCESS_POINTING_SIGMA_DB,
            unit="dB",
            domain="half_normal_db",
            lower_bound=0.0,
            rationale=(
                "Excess mispointing loss beyond the nominal tx+rx pointing-loss "
                "allocations already in the link budget; non-negative because "
                "mispointing cannot reduce loss below the nominal allocation."
            ),
        ),
        misc_loss_db=UncertainParameter(
            name="misc_loss_db",
            nominal=misc_loss_nominal,
            sigma=MISC_LOSS_SIGMA_DB,
            unit="dB",
            domain="additive_db",
            rationale="Uncertainty in the fixed atmospheric+other loss estimate (not a new physical effect).",
        ),
        tsys_k=UncertainParameter(
            name="tsys_k",
            nominal=link.receiver.system_noise_temp_k,
            sigma=TSYS_SIGMA_FRACTIONAL,
            unit="K",
            domain="fractional_linear",
            lower_bound=1.0,
            rationale="Representative system noise temperature calibration/environmental uncertainty.",
        ),
        required_ebn0_db=UncertainParameter(
            name="required_ebn0_db",
            nominal=link.requirement.required_ebn0_db,
            sigma=REQUIRED_EBN0_SIGMA_DB,
            unit="dB",
            domain="additive_db",
            rationale="Modem/coding implementation (required Eb/N0 at target BER/FER) uncertainty.",
        ),
    )
