"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pair_rows(rows):
    groups = {}
    for row in rows:
        if row.get("pool") != "development" or row.get("run_status") != "completed":
            raise ValueError("completed development rows required")
        key = (row["subject_id"], row["recording_stem"])
        if row["stage"] in groups.setdefault(key, {}):
            raise ValueError("duplicate stage")
        groups[key][row["stage"]] = row
    paired = []
    for key, stages in sorted(groups.items()):
        bases = [stage for stage in ("N", "C") if stage in stages]
        if len(bases) != 1 or "E" not in stages:
            raise ValueError("strict rest/stimulus pair missing")
        base, stim = (stages[bases[0]], stages["E"])
        result = {
            "subject_id": key[0],
            "recording_stem": key[1],
            "baseline_stage": bases[0],
        }
        for field in (
            "subslow_ratio_max",
            "exact_repeat_fraction_max",
            "ecg_egg_harmonic_coherence_max",
        ):
            result["baseline_" + field] = float(base[field])
            result["stimulus_" + field] = float(stim[field])
            result["stimulus_minus_baseline_" + field] = float(stim[field]) - float(
                base[field]
            )
        result["semantic_status"] = (
            "paired_advisory_description_not_artifact_filter_or_stimulus_effect_inference"
        )
        paired.append(result)
    return paired
