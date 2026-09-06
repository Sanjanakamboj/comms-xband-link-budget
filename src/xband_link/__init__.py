"""xband_link — X-band spacecraft downlink link-budget toolkit.

Milestone 1 scope: link-budget fundamentals, free-space propagation,
thermal-noise modeling, and C/N0 / Eb/N0 / margin calculation, with a
software architecture that supports later trade-study and sensitivity
work without modification.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xband-link")
except PackageNotFoundError:  # pragma: no cover - editable/uninstalled use
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
