"""Attach symmetric observed-RR candidates to the resting-reference audit."""

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

WAVE = ROOT / "08_outputs/rest_waveform_qc_20260929T083000Z/rest_waveform_qc.csv"
PAIR = sorted((ROOT / "08_outputs").glob("rest_post_hrv_pair_symmetric_*"))[-1]
CFG = ROOT / "config/rest_relative_deviation_v1.json"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def read_csv(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def finite(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def main():
    wave = read_csv(WAVE)
    pair = read_csv(PAIR / "rest_post_hrv_symmetric.csv")
    wm = {(r["subject_id"], r["recording_stem"]): r for r in wave}
    pm = {(r["subject_id"], r["recording_stem"]): r for r in pair}
    if len(wm) != 104 or set(wm) != set(pm):
        raise ValueError("expected identical 104 strict pair keys")
    rows = []
    for key in sorted(wm):
        w, p = wm[key], pm[key]
        status = p["paired_status"]
        row = {
            "subject_id": key[0],
            "recording_stem": key[1],
            "rest_stage": w["baseline_stage"],
            "quality_stratum": status,
            "e07_status": status,
            "e05_status": w.get("e05_status", ""),
            "rest_reference_semantics": "experimental_resting_reference_state",
        }
        pairs = {
            "candidate_hr_bpm": (
                p.get("base_candidate_hr_bpm"),
                p.get("post_candidate_hr_bpm"),
            ),
            "candidate_rmssd_ms": (
                p.get("base_candidate_rmssd_ms"),
                p.get("post_candidate_rmssd_ms"),
            ),
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
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    summary = {
        "pairs": len(rows),
        "quality_strata": dict(Counter(r["quality_stratum"] for r in rows)),
        "e05_status_counts": dict(Counter(r["e05_status"] for r in rows)),
        "paired_delta": {},
        "significance_testing_performed": False,
        "parameter_selection_from_current_data": False,
        "physiological_effect_claim_allowed": False,
        "gastric_rhythm_claim_allowed": False,
        "rr_semantics": "symmetric observed RR candidate; not NN or clinical HRV",
    }
    for feature in cfg["features"]:
        vals = [
            r["delta_" + feature] for r in rows if r["delta_" + feature] is not None
        ]
        summary["paired_delta"][feature] = bootstrap_delta_summary(
            vals, cfg["bootstrap_seed"], cfg["bootstrap_replicates"]
        )
        for s in ("E07_TIER_C_ESTIMATED", "E07_INVALID_QUALITY"):
            vals = [
                r["delta_" + feature]
                for r in rows
                if r["quality_stratum"] == s and r["delta_" + feature] is not None
            ]
            summary["paired_delta"][feature + "__" + s] = bootstrap_delta_summary(
                vals, cfg["bootstrap_seed"], cfg["bootstrap_replicates"]
            )
    out = (
        ROOT
        / "08_outputs"
        / (
            "rest_relative_deviation_symmetric_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "paired_deviation_symmetric_private.csv").open(
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
    inputs = [CFG, Path(__file__), WAVE, PAIR / "rest_post_hrv_symmetric.csv"]
    (out / "run_manifest.json").write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
                "python": sys.version,
                "platform": platform.platform(),
                "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
                "output_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
