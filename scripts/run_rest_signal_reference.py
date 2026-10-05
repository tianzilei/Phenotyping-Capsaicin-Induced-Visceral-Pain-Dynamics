"""Build subject-aggregated ECG/EGG candidate references from N/C/P rest."""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.ecg_lead_stability import candidate_rmssd_ms, consensus_times
from capsaicin.egg_motion_diagnostic import motion_screened_spectrum, motion_support
from run_ecg_candidate_quality import ecg_indices, lead_peaks
from run_rest_waveform_qc import channel_indices, read_acq

CFG = ROOT / "config/rest_signal_reference_v1.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def quantiles(values):
    x = np.asarray([v for v in values if v is not None and np.isfinite(v)], float)
    return {
        "n": int(len(x)),
        "median": float(np.median(x)) if len(x) else None,
        "q1": float(np.quantile(x, 0.25)) if len(x) else None,
        "q3": float(np.quantile(x, 0.75)) if len(x) else None,
        "minimum": float(np.min(x)) if len(x) else None,
        "maximum": float(np.max(x)) if len(x) else None,
    }


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    rest_cfg = ROOT / cfg["rest_reference_config"]
    motion_cfg_path = ROOT / cfg["egg_motion_config"]
    rest = json.loads(rest_cfg.read_text(encoding="utf-8"))
    motion = json.loads(motion_cfg_path.read_text(encoding="utf-8"))
    audit = ROOT / cfg["rest_audit_run"]
    ap = audit / "rest_reference_audit_private.csv"
    amp = audit / "run_manifest.json"
    split_path = ROOT / cfg["reference_split"]
    aman = json.loads(amp.read_text(encoding="utf-8"))
    if sha(ap) != aman["output_sha256"][ap.name]:
        raise ValueError("rest audit hash mismatch")
    with ap.open(encoding="utf-8-sig", newline="") as f:
        audit_rows = list(csv.DictReader(f))
    with split_path.open(encoding="utf-8-sig", newline="") as f:
        pool_map = {r["person_id"]: r["pool"] for r in csv.DictReader(f)}
    selected = [
        r
        for r in audit_rows
        if r["selected_rest_path"]
        and r["selected_rest_stage"] in rest["eligible_stages"]
    ]
    if not selected:
        raise ValueError("no selected rest records")
    rows = []
    hashes = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            CFG,
            rest_cfg,
            motion_cfg_path,
            ap,
            amp,
            Path(__file__),
            ROOT / "src/capsaicin/ecg_lead_stability.py",
            ROOT / "src/capsaicin/egg_motion_diagnostic.py",
        )
    }
    for n, item in enumerate(selected, 1):
        path = Path(item["selected_rest_path"])
        hashes[str(path)] = sha(path)
        row = {
            "subject_id": item["subject_id"],
            "pool": pool_map.get(item["subject_id"], "unassigned"),
            "recording_stem": item["recording_stem"],
            "stage": item["selected_rest_stage"],
            "source_path": str(path),
        }
        try:
            arr, fs, names = read_acq(path)
            ecg_idx, egg_idx = channel_indices(names)
            peaks = [lead_peaks(arr[i], fs)[0] for i in ecg_idx]
            events = consensus_times(
                peaks,
                fs,
                cfg["ecg_event_tolerance_seconds"],
                cfg["ecg_consensus_minimum_leads"],
            )
            rr = np.diff(events) / fs
            range_valid = rr[
                (rr >= cfg["rr_bounds_seconds"][0])
                & (rr <= cfg["rr_bounds_seconds"][1])
            ]
            row.update(
                {
                    "candidate_events": len(events),
                    "candidate_hr_bpm": float(60 / np.mean(range_valid))
                    if len(range_valid)
                    else None,
                    "candidate_rmssd_ms": candidate_rmssd_ms(
                        events, fs, cfg["rr_symmetric_jump_fraction"]
                    ),
                }
            )
            metrics, mask = motion_support(
                arr[egg_idx],
                fs,
                target_fs=motion["coarse_sampling_hz"],
                multiple=motion["derivative_mad_multiple"],
                guard_seconds=motion["guard_seconds"],
                reference_seconds=motion["local_reference_seconds"],
                minimum_run_seconds=motion["minimum_continuous_seconds"],
                minimum_total_seconds=motion["minimum_total_seconds"],
            )
            spectrum = motion_screened_spectrum(
                arr[egg_idx],
                fs,
                mask,
                motion["minimum_continuous_seconds"],
                motion["minimum_total_seconds"],
                motion["spectrum_sampling_hz"],
            )
            row.update(
                {
                    "motion_candidate_fraction": metrics["motion_candidate_fraction"],
                    "egg_support_status": metrics["support_status"],
                    "egg_spectrum_status": spectrum["motion_spectrum_status"],
                    "egg_candidate_peak_cpm": spectrum.get(
                        "motion_spectrum_peak_cpm_weighted"
                    ),
                    "egg_slow_power_ratio": spectrum.get(
                        "motion_spectrum_slow_power_ratio"
                    ),
                    "egg_spectral_entropy": spectrum.get("motion_spectrum_entropy"),
                    "egg_slow_coherence": spectrum.get(
                        "motion_spectrum_coherence_descriptive"
                    ),
                    "run_status": "completed",
                }
            )
        except Exception as exc:
            row.update(
                {"run_status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
        rows.append(row)
        if n % 25 == 0 or n == len(selected):
            print(f"{n}/{len(selected)}", flush=True)
    groups = defaultdict(list)
    for row in rows:
        if row["run_status"] == "completed":
            groups[row["subject_id"]].append(row)
    features = (
        "candidate_hr_bpm",
        "candidate_rmssd_ms",
        "egg_candidate_peak_cpm",
        "egg_slow_power_ratio",
        "egg_spectral_entropy",
        "egg_slow_coherence",
        "motion_candidate_fraction",
    )
    subjects = []
    for subject, items in sorted(groups.items()):
        pools = sorted({r["pool"] for r in items})
        out = {
            "subject_id": subject,
            "pool": pools[0] if len(pools) == 1 else "conflicting_pool",
            "rest_recordings": len(items),
            "stages": ";".join(sorted({r["stage"] for r in items})),
        }
        for feature in features:
            values = [
                r.get(feature)
                for r in items
                if r.get(feature) is not None and np.isfinite(r.get(feature))
            ]
            out[feature] = float(np.median(values)) if values else None
        subjects.append(out)
    completed = [r for r in rows if r["run_status"] == "completed"]
    subject_stages = []
    stage_groups = defaultdict(list)
    for row in completed:
        stage_groups[(row["subject_id"], row["pool"], row["stage"])].append(row)
    for (subject, pool, stage), items in sorted(stage_groups.items()):
        out = {
            "subject_id": subject,
            "pool": pool,
            "stage": stage,
            "rest_recordings": len(items),
        }
        for feature in features:
            values = [
                r.get(feature)
                for r in items
                if r.get(feature) is not None and np.isfinite(r.get(feature))
            ]
            out[feature] = float(np.median(values)) if values else None
        subject_stages.append(out)
    outdir = (
        ROOT
        / "08_outputs"
        / (
            "rest_signal_reference_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    outdir.mkdir()
    for name, data in (
        ("record_candidates_private.csv", rows),
        ("subject_reference_private.csv", subjects),
        ("subject_stage_reference_private.csv", subject_stages),
    ):
        fields = list(dict.fromkeys(k for r in data for k in r))
        with (outdir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(data)
    assigned_subjects = [
        r
        for r in subjects
        if r["pool"] in {"development", "application", "sealed_validation"}
    ]
    per_pool = {}
    for pool in sorted({r["pool"] for r in assigned_subjects}):
        subset = [r for r in assigned_subjects if r["pool"] == pool]
        per_pool[pool] = {
            "subjects": len(subset),
            "distributions": {
                feature: quantiles([r.get(feature) for r in subset])
                for feature in features
            },
        }
    per_stage = {}
    for stage in ("N", "C", "P"):
        subset = [
            r
            for r in subject_stages
            if r["stage"] == stage
            and r["pool"] in {"development", "application", "sealed_validation"}
        ]
        per_stage[stage] = {
            "subjects": len(subset),
            "distributions": {
                feature: quantiles([r.get(feature) for r in subset])
                for feature in features
            },
        }
    summary = {
        "eligible_rest_recordings": len(selected),
        "completed": len(completed),
        "failed": len(rows) - len(completed),
        "subjects_with_completed_rest_reference": len(subjects),
        "subjects_in_primary_assigned_summary": len(assigned_subjects),
        "unassigned_subjects_excluded_from_primary_summary": len(subjects)
        - len(assigned_subjects),
        "record_stage_counts": dict(Counter(r["stage"] for r in completed)),
        "record_pool_counts": dict(Counter(r["pool"] for r in completed)),
        "subject_pool_counts": dict(Counter(r["pool"] for r in subjects)),
        "subject_aggregated_distributions": {
            feature: quantiles([r.get(feature) for r in assigned_subjects])
            for feature in features
        },
        "subject_aggregated_distributions_by_pool": per_pool,
        "subject_stage_distributions": per_stage,
        "normal_condition_definition": "N/C/P experimental resting reference state",
        "development_pool_only_for_method_development": True,
        "sealed_validation_output_semantics": "algorithmically_exposed_inventory_not_independent_validation",
        "physiological_gold_standard": False,
        "recordings_treated_as_independent_subjects": False,
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    hashes[str(split_path.relative_to(ROOT))] = sha(split_path)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
        "output_sha256": {p.name: sha(p) for p in outdir.iterdir() if p.is_file()},
    }
    (outdir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(outdir)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
