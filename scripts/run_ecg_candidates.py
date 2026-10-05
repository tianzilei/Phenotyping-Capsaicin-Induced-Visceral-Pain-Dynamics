"""Frozen ECG candidate diagnostics, synthetic gates, raw-data hashes and no HRV."""

import collections
import csv
import importlib.metadata
import itertools
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import bioread
import numpy as np
import scipy
from audit_signal_readiness import ROOT, sha
from run_signal_spectra import write_rows
from capsaicin.data_locations import resolve_input, relocation_evidence

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.signal_spectra import resample_exact
from capsaicin.ecg_candidates import detect_candidates, match_candidates, synthetic_ecg


def pairing(a, b, tolerance):
    pairs = match_candidates(a, b, tolerance)
    errors = [abs(a[i] - b[j]) for i, j in pairs]
    return dict(
        matched=len(pairs),
        count_a=len(a),
        count_b=len(b),
        agreement=2 * len(pairs) / (len(a) + len(b)) if len(a) + len(b) else None,
        median_abs_timing_difference_s=float(np.median(errors)) if errors else None,
    )


def intervals_summary(t):
    gaps = np.diff(t)
    return dict(
        candidate_count=len(t),
        interval_count=len(gaps),
        median_interval_s=float(np.median(gaps)) if len(gaps) else None,
        min_interval_s=float(np.min(gaps)) if len(gaps) else None,
        max_interval_s=float(np.max(gaps)) if len(gaps) else None,
    )


def main():
    cp = ROOT / "config/ecg_candidates_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    prior = ROOT / cfg["source_run"]
    manifest = json.loads((prior / "run_manifest.json").read_text(encoding="utf-8"))
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_candidates_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    arrays_dir = out / "candidate_times_private"
    arrays_dir.mkdir()
    tmp = out / "test_temp"
    tmp.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "windows_private.csv")],
        cwd=ROOT,
        check=True,
    )
    inputs = [
        cp,
        ROOT / cfg["source_config"],
        prior / "run_manifest.json",
        prior / "windows_private.csv",
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/ecg_candidates.py",
        ROOT / "src/capsaicin/signal_spectra.py",
        ROOT / "tests/test_ecg_candidates.py",
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "scripts/run_signal_spectra.py",
    ]
    for p in (prior / "windows_private.csv", prior / "support_private.csv"):
        if sha(p) != manifest["outputs_sha256"][p.name]:
            raise ValueError("Source evidence changed")
    inputs += relocation_evidence()
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        bioread=importlib.metadata.version("bioread"),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in inputs},
        signals_sha256={},
    )
    windows = []
    between_channels = []
    synthetic = []
    failures = []
    started = time.monotonic()

    def save():
        for name, data in [
            ("windows_private.csv", windows),
            ("between_channels_private.csv", between_channels),
            ("synthetic_performance.csv", synthetic),
            ("failures_private.csv", failures),
        ]:
            write_rows(out / name, data)
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    print(out, flush=True)
    try:
        with (out / "tests.log").open("w", encoding="utf-8") as f:
            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ROOT,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, TMP=str(tmp), TEMP=str(tmp)),
                check=True,
            )
        rng = np.random.default_rng(cfg["synthetic_seed"])
        fs = cfg["target_rate_hz"]
        trim = cfg["edge_trim_seconds"]
        for case in cfg["synthetic_cases"]:
            for repeat in range(cfg["synthetic_replicates"]):
                y, truth = synthetic_ecg(case, rng, cfg["synthetic_seconds"], fs)
                truth = truth[
                    (truth >= trim) & (truth < cfg["synthetic_seconds"] - trim)
                ]
                found = detect_candidates(y, fs, cfg)
                for method in ("amplitude", "energy"):
                    detected = (found[method] + found["offset_samples"]) / fs
                    pair = pairing(detected, truth, cfg["matching_tolerance_seconds"])
                    precision = (
                        pair["matched"] / len(detected) if len(detected) else None
                    )
                    recall = pair["matched"] / len(truth) if len(truth) else None
                    row = dict(
                        case=case,
                        replicate=repeat,
                        method=method,
                        truth_count=len(truth),
                        candidate_count=len(detected),
                        matched=pair["matched"],
                        precision=precision,
                        recall=recall,
                        median_timing_error_s=pair["median_abs_timing_difference_s"],
                        false_candidates=len(detected) - pair["matched"],
                    )
                    synthetic.append(row)
                    if case in ("clean", "inverted"):
                        gate = cfg["clean_synthetic_gate"]
                        if (
                            precision is None
                            or recall is None
                            or precision < gate["minimum_precision"]
                            or recall < gate["minimum_recall"]
                            or pair["median_abs_timing_difference_s"]
                            > gate["maximum_median_timing_error_seconds"]
                        ):
                            raise AssertionError(
                                "Clean synthetic gate failed; real data not run"
                            )
        save()
        print("Synthetic clean/inverted gate passed; beginning raw records", flush=True)
        groups = collections.defaultdict(list)
        with (prior / "windows_private.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["label"] == "ECG100C":
                    groups[r["path"]].append(r)
        for number, (name, group) in enumerate(sorted(groups.items()), 1):
            if time.monotonic() - started > cfg["timeout_seconds"]:
                raise TimeoutError("Frozen timeout reached; partial results retained")
            try:
                p = resolve_input(name)
                digest = sha(p)
                if digest != manifest["signals_sha256"][name]:
                    raise ValueError("Raw input changed")
                state["signals_sha256"][name] = digest
                with p.open("rb") as f:
                    reader = bioread.reader.Reader(f)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
                file_rows = []
                saved = {}
                per_window = collections.defaultdict(dict)
                for item in group:
                    k = int(item["channel"])
                    w = int(item["window_index"])
                    channel = data.channels[k]
                    if (
                        channel.name != "ECG100C"
                        or channel.samples_per_second != cfg["input_rate_hz"]
                        or channel.units != "mV"
                    ):
                        raise ValueError("Unexpected raw metadata")
                    n = cfg["window_seconds"] * cfg["input_rate_hz"]
                    raw = channel.data[w * n : (w + 1) * n]
                    if len(raw) != n:
                        raise ValueError("Incomplete raw window")
                    if not np.isfinite(raw).all():
                        file_rows.append(
                            dict(
                                path=name,
                                source_file_index=number,
                                channel=k,
                                window_index=w,
                                status="nonfinite_no_fill",
                            )
                        )
                        continue
                    y = resample_exact(raw, cfg["input_rate_hz"], fs)
                    found = detect_candidates(y, fs, cfg)
                    times = {
                        method: (found[method] + found["offset_samples"]) / fs
                        + w * cfg["window_seconds"]
                        for method in ("amplitude", "energy")
                    }
                    record = dict(
                        path=name,
                        source_file_index=number,
                        channel=k,
                        window_index=w,
                        stage=item["stage"],
                        status=found["status"],
                        analysis_start_recording_s=w * cfg["window_seconds"] + trim,
                        analysis_end_recording_s=(w + 1) * cfg["window_seconds"] - trim,
                        raw_longest_constant_span_s=item["longest_constant_span_s"],
                    )
                    for method, t in times.items():
                        saved[f"c{k}_w{w}_{method}_recording_s"] = t
                        record.update(
                            {
                                method + "_" + key: value
                                for key, value in intervals_summary(t).items()
                            }
                        )
                    record.update(
                        pairing(
                            times["amplitude"],
                            times["energy"],
                            cfg["matching_tolerance_seconds"],
                        )
                    )
                    file_rows.append(record)
                    per_window[w][k] = times
                file_pairs = []
                for w, channels in per_window.items():
                    for a, b in itertools.combinations(sorted(channels), 2):
                        for method in ("amplitude", "energy"):
                            file_pairs.append(
                                dict(
                                    path=name,
                                    window_index=w,
                                    channel_a=a,
                                    channel_b=b,
                                    method=method,
                                    **pairing(
                                        channels[a][method],
                                        channels[b][method],
                                        cfg["matching_tolerance_seconds"],
                                    ),
                                )
                            )
                np.savez_compressed(arrays_dir / f"file_{number:04d}.npz", **saved)
                windows.extend(file_rows)
                between_channels.extend(file_pairs)
            except Exception as exc:
                failures.append(dict(path=name, error=f"{type(exc).__name__}: {exc}"))
            if number % 40 == 0 or number == len(groups):
                save()
                print(
                    f"{number}/{len(groups)} files, {len(windows)} channel windows, failures={len(failures)}",
                    flush=True,
                )
        synth_summary = []
        for case in cfg["synthetic_cases"]:
            for method in ("amplitude", "energy"):
                g = [
                    r for r in synthetic if r["case"] == case and r["method"] == method
                ]
                row = dict(
                    case=case,
                    method=method,
                    replicates=len(g),
                    truth_count=sum(r["truth_count"] for r in g),
                    candidate_count=sum(r["candidate_count"] for r in g),
                    matched=sum(r["matched"] for r in g),
                    false_candidates=sum(r["false_candidates"] for r in g),
                )
                row["pooled_precision"] = (
                    row["matched"] / row["candidate_count"]
                    if row["candidate_count"]
                    else None
                )
                row["pooled_recall"] = (
                    row["matched"] / row["truth_count"] if row["truth_count"] else None
                )
                synth_summary.append(row)
        write_rows(out / "synthetic_summary.csv", synth_summary)
        valid = [r for r in windows if r.get("agreement") is not None]
        summary = dict(
            files_planned=len(groups),
            files_completed=len(groups) - len(failures),
            failures=len(failures),
            channel_windows=len(windows),
            windows_with_defined_agreement=len(valid),
            method_agreement_median=float(np.median([r["agreement"] for r in valid]))
            if valid
            else None,
            between_channel_comparisons=len(between_channels),
            synthetic_datasets=len(synthetic) // 2,
            synthetic_clean_gate_passed=True,
            candidate_totals={
                m: sum(r.get(m + "_candidate_count", 0) for r in windows)
                for m in ("amplitude", "energy")
            },
            clinical_qc_passed=False,
        )
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        state["status"] = (
            "completed_candidate_diagnostics"
            if not failures
            else "completed_with_failures"
        )
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        save()
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
