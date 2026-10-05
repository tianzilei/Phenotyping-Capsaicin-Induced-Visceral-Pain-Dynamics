"""Development-only EGG motion-proxy parameter sensitivity matrix."""

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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from capsaicin.egg_motion_diagnostic import motion_screened_spectrum, motion_support
from run_rest_waveform_qc import channel_indices, read_acq, read_rows

CFG = ROOT / "config/egg_motion_sweep_v1.json"
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
        key = row["mad_multiple"], row["reference_seconds"]
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
                    row["support_status"] == "MOTION_SCREENED_CANDIDATE_SUPPORT"
                    for row in group
                ),
                "candidate_spectra": sum(
                    row["motion_spectrum_status"]
                    == "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
                    for row in group
                ),
                "median_motion_candidate_fraction": statistics.median(
                    row["motion_candidate_fraction"] for row in group
                ),
                "maximum_motion_candidate_fraction": max(
                    row["motion_candidate_fraction"] for row in group
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


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if cfg["selection_rule"] is not None:
        raise ValueError("sweep must not contain a parameter selection rule")
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
            "egg_motion_sweep_"
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
        Path(__file__),
        ROOT / "src/capsaicin/egg_motion_diagnostic.py",
        ROOT / "src/capsaicin/electrophysiology_qc_v2.py",
        ROOT / "src/capsaicin/reanalysis_signals.py",
        ROOT / "scripts/run_rest_waveform_qc.py",
    ]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
    rows = []
    for sid, stem, stage, path in tasks:
        hashes[str(path)] = sha(path)
        array, fs, names = read_acq(path)
        _, egg_indices = channel_indices(names)
        egg = array[egg_indices]
        for multiple in cfg["derivative_mad_multiples"]:
            for reference in cfg["local_reference_seconds"]:
                row = {
                    "subject_id": sid,
                    "recording_stem": stem,
                    "stage": stage,
                    "pool": cfg["pool"],
                    "mad_multiple": multiple,
                    "reference_seconds": reference,
                }
                metrics, mask = motion_support(
                    egg,
                    fs,
                    cfg["coarse_sampling_hz"],
                    multiple,
                    cfg["guard_seconds"],
                    reference,
                    cfg["minimum_continuous_seconds"],
                    cfg["minimum_total_seconds"],
                )
                row.update(metrics)
                row.update(
                    motion_screened_spectrum(
                        egg,
                        fs,
                        mask,
                        cfg["minimum_continuous_seconds"],
                        cfg["minimum_total_seconds"],
                        cfg["spectrum_sampling_hz"],
                    )
                )
                rows.append(row)
        print(stage, "completed", flush=True)
    summary_rows = summarize(
        rows,
        cfg["anchor"]["derivative_mad_multiple"],
        cfg["anchor"]["local_reference_seconds"],
    )
    with (out / "record_scenarios_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (out / "scenario_summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    summary = {
        "development_records": len(tasks),
        "scenarios": len(summary_rows),
        "record_scenario_rows": len(rows),
        "minimum_candidate_support_across_scenarios": min(
            row["candidate_support"] for row in summary_rows
        ),
        "minimum_candidate_spectra_across_scenarios": min(
            row["candidate_spectra"] for row in summary_rows
        ),
        "maximum_scenario_peak_delta_from_anchor_cpm": max(
            row["maximum_abs_peak_delta_from_anchor_cpm"] or 0 for row in summary_rows
        ),
        "parameter_selected": False,
        "artifact_truth_validated": False,
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
