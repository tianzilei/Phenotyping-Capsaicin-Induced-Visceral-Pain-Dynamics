"""Build development-only RR candidates from the revised event table."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.ecg_rr_candidates_v2 import rr_candidates, rr_summary
from run_rest_waveform_qc import channel_indices, read_acq

CFG = ROOT / "config/ecg_rr_candidates_v2.json"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["input_run"]
    events_path = source / "ecg_events_private.csv"
    records_path = source / "development_diagnostics_private.csv"
    source_manifest = source / "run_manifest.json"
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    for path in (events_path, records_path):
        if sha(path) != manifest["output_sha256"][path.name]:
            raise ValueError(f"source output hash mismatch: {path}")
    with events_path.open(encoding="utf-8-sig", newline="") as handle:
        events = list(csv.DictReader(handle))
    with records_path.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    record_map = {
        (row["subject_id"], row["recording_stem"], row["stage"]): row for row in records
    }
    if len(record_map) != len(records) or any(
        row["pool"] != cfg["pool"] for row in records
    ):
        raise ValueError("unexpected record set")
    grouped = defaultdict(list)
    for event in events:
        key = event["subject_id"], event["recording_stem"], event["stage"]
        if key not in record_map:
            raise ValueError("event without record")
        grouped[key].append(
            (int(event["aligned_lead_ii_sample"]), int(event["distinct_lead_votes"]))
        )
    intervals, summaries = [], []
    for key in sorted(record_map):
        source_path = Path(record_map[key]["source_path"])
        source_hash = sha(source_path)
        recorded_hash = manifest["input_sha256"].get(str(source_path))
        if recorded_hash != source_hash:
            raise ValueError("source ACQ differs from event-generation manifest")
        array, fs, names = read_acq(source_path)
        ecg_indices, _ = channel_indices(names)
        if not ecg_indices or not all(
            np.isfinite(array[index]).all() for index in ecg_indices
        ):
            raise ValueError(
                "nonfinite ECG source requires explicit gap-aware segmentation"
            )
        rows = rr_candidates(
            grouped[key],
            fs,
            cfg["rr_bounds_seconds"][0],
            cfg["rr_bounds_seconds"][1],
            cfg["local_jump_fraction"],
            cfg["refractory_seconds"],
        )
        for index, row in enumerate(rows):
            intervals.append(
                {
                    "subject_id": key[0],
                    "recording_stem": key[1],
                    "stage": key[2],
                    "interval_index": index,
                    **row,
                }
            )
        summaries.append(
            {
                "subject_id": key[0],
                "recording_stem": key[1],
                "stage": key[2],
                "sampling_rate_hz": fs,
                **rr_summary(rows),
            }
        )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_rr_candidates_v2_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "rr_intervals_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(intervals[0]))
        writer.writeheader()
        writer.writerows(intervals)
    with (out / "record_summary_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    summary = {
        "development_records": len(summaries),
        "rr_candidates": sum(row["rr_candidates"] for row in summaries),
        "locally_plausible_rr": sum(row["locally_plausible_rr"] for row in summaries),
        "flagged_rr": sum(row["flagged_rr"] for row in summaries),
        "records_with_candidate_rmssd": sum(
            row["candidate_rmssd_seconds"] is not None for row in summaries
        ),
        "normal_beat_or_nn_reference_available": False,
        "application_or_sealed_records_read": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    revision = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    inputs = [
        CFG,
        Path(__file__),
        ROOT / "src/capsaicin/ecg_rr_candidates_v2.py",
        events_path,
        records_path,
        source_manifest,
    ]
    run_manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
        "source_sampling_rate_hz": sorted(
            {row["sampling_rate_hz"] for row in summaries}
        ),
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
