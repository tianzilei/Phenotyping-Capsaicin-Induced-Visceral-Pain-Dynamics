"""Development-only EGG segment stationarity and truncation audit."""

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
from capsaicin.electrophysiology_qc_v2 import continuous_runs
from capsaicin.egg_motion_diagnostic import motion_support
from capsaicin.egg_stability import fixed_segment, segment_metrics, spectrum_distance
from run_rest_waveform_qc import channel_indices, read_acq, read_rows

CFG = ROOT / "config/egg_stability_v1.json"
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
    motion_cfg = json.loads(
        (ROOT / cfg["source_motion_config"]).read_text(encoding="utf-8")
    )
    with SPLIT.open(encoding="utf-8-sig", newline="") as f:
        dev = {r["person_id"] for r in csv.DictReader(f) if r["pool"] == cfg["pool"]}
    tasks = [
        (s, stem, stage, p)
        for s, stem, b, e, base in read_rows()
        if s in dev
        for stage, p in ((base, b), ("E", e))
    ]
    station = []
    trunc = []
    hashes = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            CFG,
            SPLIT,
            ROOT / cfg["source_motion_config"],
            Path(__file__),
            ROOT / "src/capsaicin/egg_stability.py",
            ROOT / "src/capsaicin/egg_motion_diagnostic.py",
        )
    }
    for sid, stem, stage, path in tasks:
        hashes[str(path)] = sha(path)
        arr, fs, names = read_acq(path)
        _, egg_idx = channel_indices(names)
        egg = arr[egg_idx]
        _, mask = motion_support(
            egg,
            fs,
            target_fs=motion_cfg["coarse_sampling_hz"],
            multiple=motion_cfg["derivative_mad_multiple"],
            guard_seconds=motion_cfg["guard_seconds"],
            reference_seconds=motion_cfg["local_reference_seconds"],
            minimum_run_seconds=motion_cfg["minimum_continuous_seconds"],
            minimum_total_seconds=motion_cfg["minimum_total_seconds"],
        )
        runs = continuous_runs(
            mask, round(motion_cfg["minimum_continuous_seconds"] * fs)
        )
        if not runs:
            continue
        a, b = max(runs, key=lambda q: q[1] - q[0])
        length = (b - a) / fs
        seglen = cfg["stationarity_segment_seconds"]
        if length >= 2 * seglen:
            first = fixed_segment(egg, fs, a / fs, seglen, cfg["target_sampling_hz"])
            last = fixed_segment(
                egg, fs, b / fs - seglen, seglen, cfg["target_sampling_hz"]
            )
            m1 = segment_metrics(first, cfg["target_sampling_hz"])
            m2 = segment_metrics(last, cfg["target_sampling_hz"])
            corr, wd = spectrum_distance(first, last, cfg["target_sampling_hz"])
            station.append(
                {
                    "subject_id": sid,
                    "recording_stem": stem,
                    "stage": stage,
                    "qualifying_run_seconds": length,
                    "segment_seconds": seglen,
                    "spectral_correlation": corr,
                    "wasserstein_hz": wd,
                    "absolute_peak_drift_cpm": abs(m2["peak_cpm"] - m1["peak_cpm"]),
                    "absolute_slow_power_ratio_drift": abs(
                        m2["slow_power"] / max(m2["total_power"], 1e-30)
                        - m1["slow_power"] / max(m1["total_power"], 1e-30)
                    ),
                }
            )
        if length >= cfg["long_record_minimum_seconds"]:
            full = fixed_segment(egg, fs, a / fs, length, cfg["target_sampling_hz"])
            fm = segment_metrics(full, cfg["target_sampling_hz"])
            for seconds in cfg["truncation_lengths_seconds"]:
                offsets = {
                    "start": a / fs,
                    "center": a / fs + (length - seconds) / 2,
                    "end": b / fs - seconds,
                }
                for position in cfg["truncation_positions"]:
                    segment = fixed_segment(
                        egg, fs, offsets[position], seconds, cfg["target_sampling_hz"]
                    )
                    sm = segment_metrics(segment, cfg["target_sampling_hz"])
                    corr, wd = spectrum_distance(
                        full, segment, cfg["target_sampling_hz"]
                    )
                    trunc.append(
                        {
                            "subject_id": sid,
                            "recording_stem": stem,
                            "stage": stage,
                            "qualifying_run_seconds": length,
                            "truncation_seconds": seconds,
                            "position": position,
                            "full_peak_cpm": fm["peak_cpm"],
                            "truncated_peak_cpm": sm["peak_cpm"],
                            "absolute_peak_drift_cpm": abs(
                                sm["peak_cpm"] - fm["peak_cpm"]
                            ),
                            "full_dpss_half_bandwidth_cpm": fm[
                                "dpss_smoothing_width_hz"
                            ]
                            * 30,
                            "truncated_dpss_half_bandwidth_cpm": sm[
                                "dpss_smoothing_width_hz"
                            ]
                            * 30,
                            "spectral_correlation": corr,
                            "wasserstein_hz": wd,
                        }
                    )
    out = (
        ROOT
        / "08_outputs"
        / (
            "egg_stability_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    for name, rows, fields in (
        ("segment_stationarity_private.csv", station, None),
        ("truncation_benchmark_private.csv", trunc, None),
    ):
        with (out / name).open("w", encoding="utf-8-sig", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            else:
                f.write("")
    summary = {
        "development_records": len(tasks),
        "stationarity_records": len(station),
        "long_record_benchmarks": len(
            {(r["subject_id"], r["recording_stem"], r["stage"]) for r in trunc}
        ),
        "truncation_rows": len(trunc),
        "median_stationarity_spectral_correlation": float(
            np.median([r["spectral_correlation"] for r in station])
        )
        if station
        else None,
        "median_stationarity_peak_drift_cpm": float(
            np.median([r["absolute_peak_drift_cpm"] for r in station])
        )
        if station
        else None,
        "truncation_peak_drift_cpm_by_length": {
            str(s): {
                "median": float(
                    np.median(
                        [
                            r["absolute_peak_drift_cpm"]
                            for r in trunc
                            if r["truncation_seconds"] == s
                        ]
                    )
                ),
                "maximum": float(
                    max(
                        r["absolute_peak_drift_cpm"]
                        for r in trunc
                        if r["truncation_seconds"] == s
                    )
                ),
            }
            for s in cfg["truncation_lengths_seconds"]
            if any(r["truncation_seconds"] == s for r in trunc)
        },
        "gastric_rhythm_truth_validated": False,
        "parameter_selection_from_current_data": False,
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
