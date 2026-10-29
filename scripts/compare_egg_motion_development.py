"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = ("subject_id", "recording_stem", "stage")


def compare_rows(unmasked, screened):

    def by_key(rows):
        result = {}
        for row in rows:
            if row.get("pool") != "development" or row.get("run_status") != "completed":
                raise ValueError(
                    "comparison requires completed development records only"
                )
            key = tuple((row.get(field) for field in KEY))
            if any((not part for part in key)) or key in result:
                raise ValueError("missing or duplicate record identity")
            result[key] = row
        return result

    old = by_key(unmasked)
    new = by_key(screened)
    if not old or set(old) != set(new):
        raise ValueError("paired record sets differ")
    pairs = []
    for key in sorted(old):
        a, b = (old[key], new[key])
        if (
            a.get("status") != "EGG_CANDIDATE_SPECTRUM_ONLY"
            or b.get("motion_spectrum_status")
            != "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
        ):
            raise ValueError("paired candidate spectrum missing")
        pairs.append(
            {
                **dict(zip(KEY, key)),
                "unmasked_peak_cpm": float(a["peak_cpm_weighted"]),
                "screened_peak_cpm": float(b["motion_spectrum_peak_cpm_weighted"]),
                "abs_peak_delta_cpm": abs(
                    float(a["peak_cpm_weighted"])
                    - float(b["motion_spectrum_peak_cpm_weighted"])
                ),
                "abs_slow_ratio_delta": abs(
                    float(a["slow_power_ratio"])
                    - float(b["motion_spectrum_slow_power_ratio"])
                ),
                "abs_coherence_delta": abs(
                    float(a["slow_coherence_descriptive"])
                    - float(b["motion_spectrum_coherence_descriptive"])
                ),
                "motion_candidate_fraction": float(b["motion_candidate_fraction"]),
                "screened_valid_seconds": float(b["motion_spectrum_used_seconds"]),
            }
        )
    summary = {
        "paired_development_records": len(pairs),
        "mean_abs_peak_delta_cpm": statistics.mean(
            (row["abs_peak_delta_cpm"] for row in pairs)
        ),
        "max_abs_peak_delta_cpm": max((row["abs_peak_delta_cpm"] for row in pairs)),
        "mean_abs_slow_ratio_delta": statistics.mean(
            (row["abs_slow_ratio_delta"] for row in pairs)
        ),
        "max_abs_slow_ratio_delta": max((row["abs_slow_ratio_delta"] for row in pairs)),
        "mean_abs_coherence_delta": statistics.mean(
            (row["abs_coherence_delta"] for row in pairs)
        ),
        "max_abs_coherence_delta": max((row["abs_coherence_delta"] for row in pairs)),
        "minimum_screened_valid_seconds": min(
            (row["screened_valid_seconds"] for row in pairs)
        ),
        "interpretation": "posthoc_candidate_sensitivity_only_not_artifact_validation",
    }
    return (pairs, summary)
