"""Pair neutral ECG/EGG candidate changes in the development pool."""

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
from capsaicin.paired_candidate_change import (
    bootstrap_median_interval,
    rank_change_summary,
    strict_pair,
)

CFG = ROOT / "config/ecg_egg_paired_candidates_v1.json"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def verified_rows(run, filename):
    mp = run / "run_manifest.json"
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    p = run / filename
    if sha(p) != manifest["output_sha256"][p.name]:
        raise ValueError(f"source hash mismatch: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f)), mp, p


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    rest_cfg = ROOT / cfg["rest_reference_config"]
    rest = json.loads(rest_cfg.read_text(encoding="utf-8"))
    if cfg["baseline_stages"] != rest["selection_priority"]:
        raise ValueError("paired baseline priority differs from frozen rest reference")
    rrrun = ROOT / cfg["rr_run"]
    eggrun = ROOT / cfg["egg_run"]
    intervals, rrmp, rrip = verified_rows(rrrun, "interval_continuity_private.csv")
    rrsum, _, rrsp = verified_rows(rrrun, "record_summary_private.csv")
    egg, eggmp, eggp = verified_rows(eggrun, "record_diagnostics_private.csv")
    rr_values = defaultdict(list)
    for r in intervals:
        if r["range_valid"].lower() == "true":
            rr_values[(r["subject_id"], r["recording_stem"], r["stage"])].append(
                float(r["rr_seconds"])
            )
    rr_summary = {(r["subject_id"], r["recording_stem"], r["stage"]): r for r in rrsum}
    egg_summary = {
        (r["subject_id"], r["recording_stem"], r["stage"]): r
        for r in egg
        if r["run_status"] == "completed"
    }
    records = []
    for key, values in rr_values.items():
        if key not in rr_summary or key not in egg_summary:
            raise ValueError(f"missing modality row: {key}")
        er = egg_summary[key]
        rs = rr_summary[key]
        records.append(
            {
                "subject_id": key[0],
                "recording_stem": key[1],
                "stage": key[2],
                "candidate_hr_bpm": 60 / np.mean(values),
                "candidate_rmssd_ms": float(rs["candidate_rmssd_seconds"]) * 1000,
                "egg_candidate_peak_cpm": float(
                    er["motion_spectrum_peak_cpm_weighted"]
                ),
                "egg_slow_power_ratio": float(er["motion_spectrum_slow_power_ratio"]),
                "egg_spectral_entropy": float(er["motion_spectrum_entropy"]),
                "egg_slow_coherence": float(
                    er["motion_spectrum_coherence_descriptive"]
                ),
            }
        )
    paired = []
    for key, base_stage, base, stim in strict_pair(
        records, tuple(cfg["baseline_stages"]), cfg["stimulus_stage"]
    ):
        row = {
            "subject_id": key[0],
            "recording_stem": key[1],
            "baseline_stage": base_stage,
        }
        for feature in cfg["features"]:
            row["baseline_" + feature] = base[feature]
            row["stimulus_" + feature] = stim[feature]
            row["delta_" + feature] = stim[feature] - base[feature]
        row["semantic_status"] = (
            "development_paired_candidate_description_not_stimulus_effect"
        )
        paired.append(row)
    summary = {
        "development_pairs": len(paired),
        "significance_testing_performed": False,
        "parameter_selection_from_current_data": False,
        "paired_change": {
            feature: bootstrap_median_interval(
                [r["delta_" + feature] for r in paired],
                cfg["bootstrap_seed"],
                cfg["bootstrap_replicates"],
            )
            for feature in cfg["features"]
        },
        "change_associations": {},
        "physiological_or_stimulus_effect_claim_allowed": False,
    }
    ecg = ("candidate_hr_bpm", "candidate_rmssd_ms")
    egg_features = (
        "egg_candidate_peak_cpm",
        "egg_slow_power_ratio",
        "egg_spectral_entropy",
        "egg_slow_coherence",
    )
    for a in ecg:
        for b in egg_features:
            summary["change_associations"][a + "__" + b] = rank_change_summary(
                [r["delta_" + a] for r in paired], [r["delta_" + b] for r in paired]
            )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_egg_paired_candidates_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "paired_candidate_changes_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(paired[0]))
        w.writeheader()
        w.writerows(paired)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    inputs = (
        CFG,
        rest_cfg,
        Path(__file__),
        ROOT / "src/capsaicin/paired_candidate_change.py",
        rrmp,
        rrip,
        rrsp,
        eggmp,
        eggp,
    )
    run = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
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
