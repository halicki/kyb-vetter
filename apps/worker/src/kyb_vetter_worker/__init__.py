"""Thin adapter over :mod:`kyb_vetter_core`. No business logic lives here."""

from importlib.metadata import version

__version__ = version("kyb-vetter-worker")

__all__ = ["__version__"]
