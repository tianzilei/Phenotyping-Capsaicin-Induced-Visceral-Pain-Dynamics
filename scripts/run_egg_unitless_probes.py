"""Run unit-free EGG advisory probes on the original development pool only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
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

from capsaicin.egg_unitless_probes import unitless_egg_probes
from run_rest_waveform_qc import channel_indices, read_acq, read_rows

CFG = ROOT / "config/egg_unitless_probes_v1.json"
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


def numeric_summary(rows, field):
    values = [
        float(row[field])
        for row in rows
        if row.get(field) not in (None, "") and math.isfinite(float(row[field]))
    ]
    return (
        {
            "minimum": min(values),
            "median": statistics.median(values),
            "maximum": max(values),
        }
        if values
        else None
    )


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if cfg["thresholds"] is not None:
        raise ValueError(
            "advisory probe configuration must not contain acceptance thresholds"
        )
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
            "egg_unitless_probes_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    input_paths = [
        CFG,
        SPLIT,
        MAPPING,
        Path(__file__),
        ROOT / "src/capsaicin/egg_unitless_probes.py",
        ROOT / "scripts/run_rest_waveform_qc.py",
    ]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in input_paths}
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
            ecg_indices, egg_indices = channel_indices(names)
            row.update(
                unitless_egg_probes(
                    array[egg_indices],
                    array[ecg_indices[1]],
                    fs,
                    cfg["target_sampling_hz"],
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
    with (out / "probe_features_private.csv").open(
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
        "subslow_ratio_max": numeric_summary(completed, "subslow_ratio_max"),
        "exact_repeat_fraction_max": numeric_summary(
            completed, "exact_repeat_fraction_max"
        ),
        "modal_difference_fraction_max": numeric_summary(
            completed, "modal_difference_fraction_max"
        ),
        "ecg_egg_harmonic_coherence_max": numeric_summary(
            completed, "ecg_egg_harmonic_coherence_max"
        ),
        "harmonic_probe_in_egg_analysis_band_records": sum(
            row.get("harmonic_probe_in_egg_analysis_band") is True for row in completed
        ),
        "repeat_probe_interpretation": "raw_quantization_or_oversampling_descriptor_not_dropout_evidence",
        "harmonic_probe_interpretation": "high_frequency_leakage_descriptor_not_slow_band_contamination_proof",
        "acceptance_thresholds_used": False,
        "artifact_or_crosstalk_truth_validated": False,
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
