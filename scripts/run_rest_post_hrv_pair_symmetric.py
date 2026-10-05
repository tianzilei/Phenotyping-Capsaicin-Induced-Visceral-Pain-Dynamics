"""Recompute paired resting/post ECG RR candidates with symmetric continuity.

This is a parallel E07 audit.  It never writes to the legacy pair output and
reports observed RR candidates only; no NN or clinical HRV interpretation is
made.
"""

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
from scipy import signal
import bioread

ROOT = Path(__file__).resolve().parents[1]
MAPPING = (
    ROOT
    / "01_data/bids_capsaicin_20260925/sourcedata/migration/subject_to_files_D_private.csv"
)
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.ecg_rr_candidates_v2 import symmetric_rr_continuity

RR_LOW, RR_HIGH, JUMP = 0.3, 1.8, 0.20
MIN_BLOCK = 2


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pairs():
    with MAPPING.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    grouped = defaultdict(dict)
    for r in rows:
        if (
            r.get("match_status") == "accepted_strict"
            and r.get("extension", "").lower() == ".acq"
            and r.get("stage") in {"E", "N", "C"}
        ):
            stem = Path(r["filename"]).stem
            if stem and stem[-1].upper() in "ENC":
                stem = stem[:-1]
            grouped[(r["current_subject_id"], stem)][r["stage"]] = r
    out = []
    for (sid, stem), d in sorted(grouped.items()):
        base = "N" if "N" in d else ("C" if "C" in d else "")
        if base and "E" in d:
            out.append(
                (
                    sid,
                    stem,
                    Path(d[base]["local_path"]),
                    Path(d["E"]["local_path"]),
                    base,
                )
            )
    return out


def read_acq(path):
    with path.open("rb") as f:
        reader = bioread.reader.Reader(f)
        reader._read_headers()
        reader._read_data(None, bioread.reader.CHUNK_SIZE)
        datafile = reader.datafile
    return (
        np.vstack([np.asarray(c.data, float) for c in datafile.channels]),
        float(datafile.channels[0].samples_per_second),
        [str(c.name) for c in datafile.channels],
    )


def ecg_indices(names):
    found = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    return (
        found[:3] if len(found) >= 3 else ([2, 3, 4] if len(names) == 5 else [3, 4, 5])
    )


def peaks(ecg, fs):
    all_peaks = []
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    for x in ecg:
        y = signal.sosfiltfilt(sos, x)
        n = max(1, round(0.12 * fs))
        energy = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(abs(energy - np.median(energy))) * 1.4826
        p, _ = signal.find_peaks(
            energy,
            distance=round(0.2 * fs),
            prominence=max(2 * mad, np.finfo(float).eps),
        )
        all_peaks.append(p)
    tol = round(0.02 * fs)
    events = []
    for p in sorted(set(int(v) for lead in all_peaks for v in lead)):
        votes = [
            int(lead[np.argmin(abs(lead - p))])
            for lead in all_peaks
            if np.any(abs(lead - p) <= tol)
        ]
        if len(votes) >= 2:
            aligned = int(round(np.median(votes)))
            if not events or aligned - events[-1] >= round(0.2 * fs):
                events.append(aligned)
    return np.asarray(events, dtype=float) / fs


def metrics(times):
    rr = np.diff(times)
    result = symmetric_rr_continuity(rr, RR_LOW, RR_HIGH, JUMP)
    valid = result["range_valid"]
    block_ids = result["block_ids"]
    usable = valid.copy()
    counts = {int(b): int(np.sum(block_ids == b)) for b in set(block_ids) if b >= 0}
    usable &= np.array([counts.get(int(b), 0) >= MIN_BLOCK for b in block_ids])
    vals = rr[usable]
    diffs = []
    for b in sorted(set(block_ids[usable])):
        v = rr[usable & (block_ids == b)]
        if len(v) >= MIN_BLOCK:
            diffs.extend(np.diff(v).tolist())
    longest = 0.0
    for b in sorted(set(block_ids[usable])):
        v = rr[usable & (block_ids == b)]
        if len(v):
            longest = max(longest, float(np.sum(v)))
    return {
        "r_peaks": int(len(times)),
        "rr_total": int(len(rr)),
        "observed_rr_valid": int(np.sum(usable)),
        "observed_rr_valid_fraction": float(np.mean(usable)) if len(rr) else 0.0,
        "candidate_hr_bpm": float(60 / np.mean(vals)) if len(vals) else np.nan,
        "candidate_rmssd_ms": float(np.sqrt(np.mean(np.square(diffs))) * 1000)
        if diffs
        else np.nan,
        "symmetric_blocks": int(sum(n >= MIN_BLOCK for n in counts.values())),
        "range_invalid_rr": int(np.sum(~valid)),
        "discontinuous_edges": int(np.sum(~result["edge_continuous"])),
        "longest_contiguous_s": longest,
        "semantics": "observed_rr_candidate_not_nn_or_clinical_hrv",
    }


def main():
    out = (
        ROOT
        / "08_outputs"
        / (
            "rest_post_hrv_pair_symmetric_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    rows, input_hashes = [], {str(MAPPING.relative_to(ROOT)): sha(MAPPING)}
    for sid, stem, base_path, post_path, stage in pairs():
        row = {
            "subject_id": sid,
            "recording_stem": stem,
            "baseline_stage": stage,
            "base_path": str(base_path),
            "post_path": str(post_path),
        }
        try:
            base, bfs, bn = read_acq(base_path)
            post, pfs, pn = read_acq(post_path)
            for label, arr, fs, names, path in (
                ("base", base, bfs, bn, base_path),
                ("post", post, pfs, pn, post_path),
            ):
                inds = ecg_indices(names)
                if not all(np.isfinite(arr[i]).all() for i in inds):
                    raise ValueError(
                        "nonfinite ECG source requires explicit gap-aware segmentation"
                    )
                m = metrics(peaks(arr[inds], fs))
                for key, value in m.items():
                    row[f"{label}_{key}"] = value
                input_hashes[str(path.relative_to(ROOT))] = sha(path)
            row["paired_status"] = (
                "E07_TIER_C_ESTIMATED"
                if row["base_observed_rr_valid_fraction"] >= 0.85
                and row["post_observed_rr_valid_fraction"] >= 0.85
                else "E07_INVALID_QUALITY"
            )
        except Exception as exc:
            row.update(
                {
                    "paired_status": "E07_FAILED_INPUT",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        rows.append(row)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (out / "rest_post_hrv_symmetric.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "pairs": len(rows),
        "tier_c_estimated": sum(
            r.get("paired_status") == "E07_TIER_C_ESTIMATED" for r in rows
        ),
        "invalid_quality": sum(
            r.get("paired_status") == "E07_INVALID_QUALITY" for r in rows
        ),
        "failed_input": sum(r.get("paired_status") == "E07_FAILED_INPUT" for r in rows),
        "rr_rule": "symmetric_rr_continuity",
        "rr_bounds_seconds": [RR_LOW, RR_HIGH],
        "adjacent_log_ratio_jump_fraction": JUMP,
        "minimum_intervals_per_block": MIN_BLOCK,
        "scientific_status": "within_subject_observed_rr_candidate_descriptive_no_independent_reference",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": input_hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
        "output_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
