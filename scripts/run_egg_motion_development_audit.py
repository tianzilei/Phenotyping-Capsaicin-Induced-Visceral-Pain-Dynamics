"""Evaluate EGG motion-proxy support in the original development pool only."""

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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy
import scipy

from capsaicin.egg_motion_diagnostic import motion_screened_spectrum, motion_support
from run_rest_waveform_qc import channel_indices, read_acq, read_rows

CFG = ROOT / "config/egg_motion_diagnostic_v1.json"
SPLIT = (
    ROOT
    / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed/reference_split_private.csv"
)
MAPPING = (
    ROOT
    / "01_data/bids_capsaicin_20260925/sourcedata/migration/subject_to_files_D_private.csv"
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if (
        cfg["spectrum_dpss_nw"],
        cfg["spectrum_dpss_tapers"],
        cfg["spectrum_slow_band_hz"],
        cfg["spectrum_total_band_hz"],
    ) != (3, 5, [0.033, 0.067], [0.008, 0.150]):
        raise ValueError("spectrum configuration differs from frozen estimator")
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
            "egg_motion_development_audit_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    inputs = [
        CFG,
        SPLIT,
        MAPPING,
        ROOT / cfg["source_config"],
        Path(__file__),
        ROOT / "src/capsaicin/egg_motion_diagnostic.py",
        ROOT / "src/capsaicin/reanalysis_signals.py",
        ROOT / "src/capsaicin/electrophysiology_qc_v2.py",
        ROOT / "scripts/run_rest_waveform_qc.py",
    ]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
    rows = []
    for sid, stem, stage, path in tasks:
        row = {
            "subject_id": sid,
            "recording_stem": stem,
            "stage": stage,
            "pool": cfg["pool"],
            "source_path": str(path),
        }
        try:
            hashes[str(path)] = sha(path)
            array, fs, names = read_acq(path)
            _, egg_indices = channel_indices(names)
            metrics, mask = motion_support(
                array[egg_indices],
                fs,
                target_fs=cfg["coarse_sampling_hz"],
                multiple=cfg["derivative_mad_multiple"],
                guard_seconds=cfg["guard_seconds"],
                reference_seconds=cfg["local_reference_seconds"],
                minimum_run_seconds=cfg["minimum_continuous_seconds"],
                minimum_total_seconds=cfg["minimum_total_seconds"],
            )
            row.update(metrics)
            row.update(
                motion_screened_spectrum(
                    array[egg_indices],
                    fs,
                    mask,
                    minimum_run_seconds=cfg["minimum_continuous_seconds"],
                    minimum_total_seconds=cfg["minimum_total_seconds"],
                    target_fs=cfg["spectrum_sampling_hz"],
                )
            )
            row["record_seconds"] = array.shape[1] / fs
            row["run_status"] = "completed"
        except Exception as exc:
            row.update(
                {"run_status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
        rows.append(row)
        print(stage, row["run_status"], flush=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (out / "record_diagnostics_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    completed = [row for row in rows if row["run_status"] == "completed"]
    summary = {
        "development_records": len(rows),
        "completed": len(completed),
        "failed": len(rows) - len(completed),
        "motion_screened_candidate_support": sum(
            row["support_status"] == "MOTION_SCREENED_CANDIDATE_SUPPORT"
            for row in completed
        ),
        "motion_screened_candidate_inestimable": sum(
            row["support_status"] == "MOTION_SCREENED_CANDIDATE_INESTIMABLE"
            for row in completed
        ),
        "motion_screened_spectra": sum(
            row["motion_spectrum_status"] == "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
            for row in completed
        ),
        "median_motion_candidate_fraction": statistics.median(
            row["motion_candidate_fraction"] for row in completed
        )
        if completed
        else None,
        "max_motion_candidate_fraction": max(
            (row["motion_candidate_fraction"] for row in completed), default=None
        ),
        "motion_or_artifact_truth_validated": False,
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
        "input_sha256": hashes,
        "python": sys.version,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "output_sha256": {
            path.name: sha(path) for path in out.iterdir() if path.is_file()
        },
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
