"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(rows, anchor_multiple=8, anchor_reference=60):
    anchors = {
        (row["subject_id"], row["recording_stem"], row["stage"]): row
        for row in rows
        if row["mad_multiple"] == anchor_multiple
        and row["reference_seconds"] == anchor_reference
    }
    if not anchors:
        raise ValueError("anchor scenario absent")
    grouped = defaultdict(list)
    for row in rows:
        key = (row["mad_multiple"], row["reference_seconds"])
        anchor = anchors[row["subject_id"], row["recording_stem"], row["stage"]]
        value = dict(row)
        if (
            row["motion_spectrum_status"] == "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
            and anchor["motion_spectrum_status"]
            == "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
        ):
            value["abs_peak_delta_from_anchor_cpm"] = abs(
                row["motion_spectrum_peak_cpm_weighted"]
                - anchor["motion_spectrum_peak_cpm_weighted"]
            )
        else:
            value["abs_peak_delta_from_anchor_cpm"] = math.nan
        grouped[key].append(value)
    result = []
    for key, group in sorted(grouped.items()):
        deltas = [
            row["abs_peak_delta_from_anchor_cpm"]
            for row in group
            if math.isfinite(row["abs_peak_delta_from_anchor_cpm"])
        ]
        result.append(
            {
                "mad_multiple": key[0],
                "reference_seconds": key[1],
                "records": len(group),
                "candidate_support": sum(
                    (
                        row["support_status"] == "MOTION_SCREENED_CANDIDATE_SUPPORT"
                        for row in group
                    )
                ),
                "candidate_spectra": sum(
                    (
                        row["motion_spectrum_status"]
                        == "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
                        for row in group
                    )
                ),
                "median_motion_candidate_fraction": statistics.median(
                    (row["motion_candidate_fraction"] for row in group)
                ),
                "maximum_motion_candidate_fraction": max(
                    (row["motion_candidate_fraction"] for row in group)
                ),
                "mean_abs_peak_delta_from_anchor_cpm": statistics.mean(deltas)
                if deltas
                else None,
                "maximum_abs_peak_delta_from_anchor_cpm": max(deltas)
                if deltas
                else None,
                "interpretation": "parameter_sensitivity_only_no_selected_scenario",
            }
        )
    return result
