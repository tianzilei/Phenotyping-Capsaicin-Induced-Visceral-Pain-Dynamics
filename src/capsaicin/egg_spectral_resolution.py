"""Physical DPSS bandwidth metadata, distinct from statistical uncertainty."""

from __future__ import annotations

import math


def bandwidth_metadata(
    widest_full_smoothing_hz: float,
    nw: float = 3.0,
    caution_below_seconds: float = 300.0,
):
    """Recover the shortest used run from 2*NW/T and annotate its coarsest width."""
    width = float(widest_full_smoothing_hz)
    if not math.isfinite(width) or width <= 0 or nw <= 0 or caution_below_seconds <= 0:
        raise ValueError("positive finite bandwidth parameters required")
    shortest = 2 * nw / width
    return {
        "shortest_used_run_seconds": shortest,
        "coarsest_native_bin_cpm": 60 / shortest,
        "dpss_half_bandwidth_cpm": 60 * nw / shortest,
        "dpss_full_bandwidth_cpm": 120 * nw / shortest,
        "resolution_annotation": "UNDER_300S_RESOLUTION_CAUTION"
        if shortest < caution_below_seconds
        else "RESOLUTION_METADATA_RECORDED",
        "bandwidth_is_confidence_interval": False,
    }
