"""
Capsaicin Analysis Package
==========================
Oral capsaicin-induced pain trajectory analysis, text mining,
network fusion, and prediction tools.
"""

__version__ = "0.1.0"

from analysis import constants, data_loader, io, parsing, rome_matcher, rome_rules

__all__ = [
    "constants",
    "rome_rules",
    "parsing",
    "rome_matcher",
    "data_loader",
    "io",
]
