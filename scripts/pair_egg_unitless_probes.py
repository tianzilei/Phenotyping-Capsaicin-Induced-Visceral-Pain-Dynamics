"""Describe paired rest-to-stimulus probe changes without filtering or inference."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/egg_unitless_pair_v1.json"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pair_rows(rows):
    groups = {}
    for row in rows:
        if row.get("pool") != "development" or row.get("run_status") != "completed":
            raise ValueError("completed development rows required")
        key = row["subject_id"], row["recording_stem"]
        if row["stage"] in groups.setdefault(key, {}):
            raise ValueError("duplicate stage")
        groups[key][row["stage"]] = row
    paired = []
    for key, stages in sorted(groups.items()):
        bases = [stage for stage in ("N", "C") if stage in stages]
        if len(bases) != 1 or "E" not in stages:
            raise ValueError("strict rest/stimulus pair missing")
        base, stim = stages[bases[0]], stages["E"]
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


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if cfg["thresholds"] is not None or cfg["use_for_artifact_exclusion"]:
        raise ValueError("paired probe description cannot contain filtering rules")
    source = ROOT / cfg["input_run"]
    source_csv = source / "probe_features_private.csv"
    source_manifest = source / "run_manifest.json"
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if sha(source_csv) != manifest["output_sha256"][source_csv.name]:
        raise ValueError("source output hash mismatch")
    with source_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = pair_rows(list(csv.DictReader(handle)))
    out = (
        ROOT
        / "08_outputs"
        / (
            "egg_unitless_pairs_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "paired_features_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fields = [
        "subslow_ratio_max",
        "exact_repeat_fraction_max",
        "ecg_egg_harmonic_coherence_max",
    ]
    summary = {
        "development_pairs": len(rows),
        "paired_differences": {
            field: {
                "minimum": min(row["stimulus_minus_baseline_" + field] for row in rows),
                "median": statistics.median(
                    row["stimulus_minus_baseline_" + field] for row in rows
                ),
                "maximum": max(row["stimulus_minus_baseline_" + field] for row in rows),
            }
            for field in fields
        },
        "filtering_or_inference_performed": False,
        "artifact_or_crosstalk_truth_validated": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    revision = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    inputs = [CFG, Path(__file__), source_csv, source_manifest]
    run_manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "output_sha256": {
            path.name: sha(path) for path in out.iterdir() if path.is_file()
        },
    }
    (out / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
