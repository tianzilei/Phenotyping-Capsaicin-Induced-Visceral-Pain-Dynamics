"""Run revised ECG/EGG engineering diagnostics only on the original development pool."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from capsaicin.electrophysiology_qc_v2 import (
    align_candidate,
    coincidence_diagnostic,
    egg_candidate,
    event_clusters,
)
from run_ecg_candidate_quality import ecg_indices, lead_peaks
from run_rest_waveform_qc import channel_indices, read_acq, read_rows

CFG = ROOT / "config/electrophysiology_development_qc_v2.json"
SPLIT = (
    ROOT
    / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed/reference_split_private.csv"
)
MAPPING = (
    ROOT
    / "01_data/bids_capsaicin_20260925/sourcedata/migration/subject_to_files_D_private.csv"
)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    with SPLIT.open(encoding="utf-8-sig", newline="") as handle:
        development = {
            row["person_id"]
            for row in csv.DictReader(handle)
            if row["pool"] == cfg["pool"]
        }
    tasks = [
        (sid, stem, stage, path)
        for sid, stem, bp, ep, base in read_rows()
        if sid in development
        for stage, path in ((base, bp), ("E", ep))
    ]
    if not tasks or any(sid not in development for sid, _, _, _ in tasks):
        raise RuntimeError("empty or non-development task set")
    out = (
        ROOT
        / "08_outputs"
        / (
            "electrophysiology_development_qc_v2_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    rows = []
    events = []
    input_hashes = {
        str(p.relative_to(ROOT)): sha(p)
        for p in [
            CFG,
            SPLIT,
            MAPPING,
            Path(__file__),
            ROOT / "src/capsaicin/electrophysiology_qc_v2.py",
            ROOT / "scripts/run_ecg_candidate_quality.py",
            ROOT / "scripts/run_rest_waveform_qc.py",
        ]
    }
    for sid, stem, stage, path in tasks:
        row = {
            "subject_id": sid,
            "recording_stem": stem,
            "stage": stage,
            "pool": "development",
            "source_path": str(path),
        }
        try:
            input_hashes[str(path)] = sha(path)
            arr, fs, names = read_acq(path)
            detected = [lead_peaks(arr[i], fs) for i in ecg_indices(names)]
            leads = [peaks for peaks, _ in detected]
            clusters = event_clusters(
                leads, fs, cfg["ecg"]["event_cluster_max_span_seconds"]
            )
            consensus = [
                time
                for time, votes in clusters
                if votes >= cfg["ecg"]["consensus_min_distinct_leads"]
            ]
            for energy_sample, votes in clusters:
                aligned = align_candidate(
                    energy_sample,
                    detected[1][1],
                    fs,
                    cfg["ecg"]["alignment_radius_seconds"],
                )
                events.append(
                    {
                        "subject_id": sid,
                        "recording_stem": stem,
                        "stage": stage,
                        "source_path": str(path),
                        "energy_sample": energy_sample,
                        "aligned_lead_ii_sample": aligned,
                        "aligned_seconds": aligned / fs,
                        "distinct_lead_votes": votes,
                        "candidate_status": "MULTILEAD_CANDIDATE"
                        if votes >= 2
                        else "ISOLATED_CANDIDATE",
                    }
                )
            row.update(
                {
                    "ecg_cluster_count": len(clusters),
                    "ecg_consensus_candidates": len(consensus),
                    "ecg_multilead_fraction": len(consensus) / len(clusters)
                    if clusters
                    else 0.0,
                    "ecg_status": "RPEAK_DEVELOPMENT_CANDIDATES_UNVALIDATED",
                }
            )
            row.update(
                coincidence_diagnostic(
                    leads,
                    fs,
                    arr.shape[1],
                    cfg["ecg"]["shift_null_seed"],
                    cfg["ecg"]["shift_null_replicates"],
                    cfg["ecg"]["shift_minimum_seconds"],
                    cfg["ecg"]["shift_maximum_seconds"],
                )
                or {}
            )
            _, egg_idx = channel_indices(names)
            row.update(
                egg_candidate(
                    arr[egg_idx],
                    fs,
                    cfg["egg"]["minimum_continuous_seconds"],
                    cfg["egg"]["minimum_total_seconds"],
                    cfg["egg"]["target_sampling_hz"],
                )
            )
            row["run_status"] = "completed"
        except Exception as exc:
            row.update(
                {"run_status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
        rows.append(row)
        print(stage, row["run_status"], flush=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (out / "development_diagnostics_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (out / "ecg_events_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "subject_id",
                "recording_stem",
                "stage",
                "source_path",
                "energy_sample",
                "aligned_lead_ii_sample",
                "aligned_seconds",
                "distinct_lead_votes",
                "candidate_status",
            ],
        )
        writer.writeheader()
        writer.writerows(events)
    summary = {
        "development_records": len(rows),
        "completed": sum(row["run_status"] == "completed" for row in rows),
        "failed": sum(row["run_status"] == "failed" for row in rows),
        "egg_candidate_spectra": sum(
            row.get("status") == "EGG_CANDIDATE_SPECTRUM_ONLY" for row in rows
        ),
        "ecg_event_candidates": len(events),
        "ecg_multilead_candidates": sum(
            event["distinct_lead_votes"] >= 2 for event in events
        ),
        "reference_accuracy_estimable": False,
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
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": input_hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "output_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
