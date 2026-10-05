"""Run development-only leave-one-lead-out ECG candidate stability."""

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
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.ecg_lead_stability import (
    candidate_rmssd_ms,
    consensus_times,
    tolerant_event_jaccard,
)
from run_ecg_candidate_quality import ecg_indices, lead_peaks
from run_rest_waveform_qc import read_acq, read_rows

CFG = ROOT / "config/ecg_lead_stability_v1.json"
SPLIT = (
    ROOT
    / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed/reference_split_private.csv"
)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    with SPLIT.open(encoding="utf-8-sig", newline="") as f:
        dev = {r["person_id"] for r in csv.DictReader(f) if r["pool"] == cfg["pool"]}
    tasks = [
        (s, stem, stage, p)
        for s, stem, b, e, base in read_rows()
        if s in dev
        for stage, p in ((base, b), ("E", e))
    ]
    rows = []
    hashes = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            CFG,
            SPLIT,
            Path(__file__),
            ROOT / "src/capsaicin/ecg_lead_stability.py",
        )
    }
    for sid, stem, stage, path in tasks:
        hashes[str(path)] = sha(path)
        arr, fs, names = read_acq(path)
        idx = ecg_indices(names)
        peaks = [lead_peaks(arr[i], fs)[0] for i in idx]
        full = consensus_times(
            peaks,
            fs,
            cfg["event_tolerance_seconds"],
            cfg["full_consensus_minimum_leads"],
        )
        full_rmssd = candidate_rmssd_ms(full, fs, cfg["symmetric_rr_jump_fraction"])
        for pair in cfg["pair_definitions"]:
            subset = consensus_times(
                [peaks[i] for i in pair],
                fs,
                cfg["event_tolerance_seconds"],
                cfg["pair_consensus_minimum_leads"],
            )
            jac, matches = tolerant_event_jaccard(
                full, subset, fs, cfg["event_tolerance_seconds"]
            )
            sub_rmssd = candidate_rmssd_ms(
                subset, fs, cfg["symmetric_rr_jump_fraction"]
            )
            rows.append(
                {
                    "subject_id": sid,
                    "recording_stem": stem,
                    "stage": stage,
                    "lead_pair": "-".join(map(str, pair)),
                    "full_events": len(full),
                    "pair_events": len(subset),
                    "matched_events": matches,
                    "event_jaccard": jac,
                    "full_candidate_rmssd_ms": full_rmssd,
                    "pair_candidate_rmssd_ms": sub_rmssd,
                    "absolute_rmssd_drift_ms": abs(sub_rmssd - full_rmssd)
                    if sub_rmssd is not None and full_rmssd is not None
                    else None,
                }
            )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_lead_stability_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "lead_pair_stability_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    drifts = [
        r["absolute_rmssd_drift_ms"]
        for r in rows
        if r["absolute_rmssd_drift_ms"] is not None
    ]
    summary = {
        "development_records": len(tasks),
        "pair_rows": len(rows),
        "median_event_jaccard": float(np.median([r["event_jaccard"] for r in rows])),
        "minimum_event_jaccard": float(min(r["event_jaccard"] for r in rows)),
        "median_absolute_candidate_rmssd_drift_ms": float(np.median(drifts))
        if drifts
        else None,
        "reference_accuracy_estimable": False,
        "application_or_sealed_records_read": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    run = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
        "output_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
    }
    (out / "run_manifest.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
