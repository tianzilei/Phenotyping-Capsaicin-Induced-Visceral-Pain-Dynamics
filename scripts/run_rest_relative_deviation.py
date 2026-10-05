"""Audit E minus selected N/C/P resting-reference candidate deviations."""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.rest_relative_deviation import bootstrap_delta_summary

CFG = ROOT / "config/rest_relative_deviation_v1.json"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read_verified(run, name):
    p = ROOT / run / name
    m = json.loads((ROOT / run / "run_manifest.json").read_text(encoding="utf-8"))
    outputs = m.get("output_sha256", m.get("outputs_sha256", {}))
    expected = outputs.get(name)
    if expected and sha(p) != expected:
        raise ValueError(f"hash mismatch {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f)), p, ROOT / run / "run_manifest.json"


def finite(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    rest_cfg = ROOT / cfg["rest_reference_config"]
    wv, wp, wmp = read_verified(cfg["waveform_qc_run"], "rest_waveform_qc.csv")
    hv, hp, hmp = read_verified(cfg["hrv_pair_run"], "rest_post_hrv.csv")
    if len(wv) != 104 or len(hv) != 104:
        raise ValueError("expected 104 strict E/rest pairs")
    wmap = {(r["subject_id"], r["recording_stem"]): r for r in wv}
    hmap = {(r["subject_id"], r["recording_stem"]): r for r in hv}
    if set(wmap) != set(hmap):
        raise ValueError("waveform and HRV pair keys differ")
    rows = []
    for key in sorted(wmap):
        w = wmap[key]
        h = hmap[key]
        status = h["paired_status"]
        row = {
            "subject_id": key[0],
            "recording_stem": key[1],
            "rest_stage": w["baseline_stage"],
            "quality_stratum": "E07_TIER_C_ESTIMATED"
            if status == "E07_TIER_C_ESTIMATED"
            else "E07_INVALID_QUALITY",
            "e07_status": status,
            "e05_status": w.get("e05_status", ""),
            "rest_reference_semantics": "experimental_resting_reference_state",
        }
        pairs = {
            "candidate_hr_bpm": (h.get("base_mean_hr_bpm"), h.get("post_mean_hr_bpm")),
            "candidate_rmssd_ms": (h.get("base_rmssd_ms"), h.get("post_rmssd_ms")),
            "egg_df1_cpm": (w.get("base_df1_cpm"), w.get("exp_df1_cpm")),
            "egg_df2_cpm": (w.get("base_df2_cpm"), w.get("exp_df2_cpm")),
            "egg_coherence": (w.get("base_egg_coherence"), w.get("exp_egg_coherence")),
            "finite_coverage": (w.get("base_finite_min"), w.get("exp_finite_min")),
            "flatline_fraction": (
                w.get("base_flatline_max"),
                w.get("exp_flatline_max"),
            ),
        }
        for feature, (rest, stim) in pairs.items():
            row["rest_" + feature] = finite(rest)
            row["stimulus_" + feature] = finite(stim)
            row["delta_" + feature] = (
                row["stimulus_" + feature] - row["rest_" + feature]
                if row["rest_" + feature] is not None
                and row["stimulus_" + feature] is not None
                else None
            )
        rows.append(row)
    features = cfg["features"]
    summary = {
        "pairs": len(rows),
        "quality_strata": dict(Counter(r["quality_stratum"] for r in rows)),
        "e05_status_counts": dict(Counter(r["e05_status"] for r in rows)),
        "paired_delta": {},
        "significance_testing_performed": False,
        "parameter_selection_from_current_data": False,
        "physiological_effect_claim_allowed": False,
        "gastric_rhythm_claim_allowed": False,
    }
    for feature in features:
        vals = [
            r["delta_" + feature] for r in rows if r["delta_" + feature] is not None
        ]
        summary["paired_delta"][feature] = bootstrap_delta_summary(
            vals, cfg["bootstrap_seed"], cfg["bootstrap_replicates"]
        )
        for stratum in ("E07_TIER_C_ESTIMATED", "E07_INVALID_QUALITY"):
            subset = [
                r["delta_" + feature]
                for r in rows
                if r["quality_stratum"] == stratum and r["delta_" + feature] is not None
            ]
            summary["paired_delta"][feature + "__" + stratum] = bootstrap_delta_summary(
                subset, cfg["bootstrap_seed"], cfg["bootstrap_replicates"]
            )
    out = (
        ROOT
        / "08_outputs"
        / (
            "rest_relative_deviation_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "paired_deviation_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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
        ROOT / "src/capsaicin/rest_relative_deviation.py",
        wp,
        hp,
        wmp,
        hmp,
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
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
