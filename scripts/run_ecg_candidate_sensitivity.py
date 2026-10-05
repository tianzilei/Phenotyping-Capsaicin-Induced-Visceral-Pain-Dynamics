"""Run frozen ECG threshold sensitivity scenarios on synthetic and raw channels."""

import collections
import csv
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
from capsaicin.ecg_candidates import (
    detect_candidates,
    detect_candidates_from_filtered,
    synthetic_ecg,
    match_candidates,
)


def main():
    cp = ROOT / "config/ecg_candidate_sensitivity_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    base = ROOT / "config/ecg_candidates_v1.json"
    bcfg = json.loads(base.read_text(encoding="utf-8"))
    prior = ROOT / cfg["source_run"]
    pm = json.loads((prior / "run_manifest.json").read_text(encoding="utf-8"))
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_candidate_sensitivity_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    tmp = out / "test_temp"
    tmp.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "raw_sensitivity_private.csv")],
        cwd=ROOT,
        check=True,
    )
    sources = [
        cp,
        base,
        prior / "run_manifest.json",
        prior / "windows_private.csv",
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/ecg_candidates.py",
        ROOT / "src/capsaicin/signal_spectra.py",
        ROOT / "tests/test_ecg_candidate_sensitivity.py",
        ROOT / "scripts/run_signal_spectra.py",
        ROOT / "scripts/audit_signal_readiness.py",
    ]
    sources += relocation_evidence()
    for name, digest in pm["outputs_sha256"].items():
        if sha(prior / name) != digest:
            raise ValueError("Source output changed")
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        signals_sha256={},
    )
    synthetic = []
    raw = []
    failures = []
    started = time.monotonic()

    def save():
        for name, data in [
            ("synthetic_sensitivity.csv", synthetic),
            ("raw_sensitivity_private.csv", raw),
            ("failures_private.csv", failures),
        ]:
            write_rows(out / name, data)
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

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
    for case in cfg["synthetic_cases"]:
        for rep in range(cfg["synthetic_replicates"]):
            y, truth = synthetic_ecg(
                case, rng, bcfg["synthetic_seconds"], bcfg["target_rate_hz"]
            )
            truth = truth[
                (truth >= bcfg["edge_trim_seconds"])
                & (truth < bcfg["synthetic_seconds"] - bcfg["edge_trim_seconds"])
            ]
            for a, e in cfg["paired_variants"]:
                cc = dict(
                    bcfg,
                    amplitude_prominence_mad_multiplier=a,
                    energy_threshold_mad_multiplier=e,
                )
                found = detect_candidates(y, 250, cc)
                for method in ("amplitude", "energy"):
                    t = (found[method] + found["offset_samples"]) / 250
                    pairs = match_candidates(t, truth, cc["matching_tolerance_seconds"])
                    synthetic.append(
                        dict(
                            case=case,
                            replicate=rep,
                            amplitude_multiplier=a,
                            energy_multiplier=e,
                            method=method,
                            truth_count=len(truth),
                            candidate_count=len(t),
                            matched=len(pairs),
                            false_candidates=len(t) - len(pairs),
                            precision=len(pairs) / len(t) if len(t) else None,
                            recall=len(pairs) / len(truth) if len(truth) else None,
                        )
                    )
    groups = collections.defaultdict(list)
    with (prior / "windows_private.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            groups[r["path"]].append(r)
    print(out, flush=True)
    for number, (name, items) in enumerate(sorted(groups.items()), 1):
        if time.monotonic() - started > cfg["timeout_seconds"]:
            raise TimeoutError("Frozen timeout; partial output retained")
        try:
            p = resolve_input(name)
            digest = sha(p)
            if digest != pm["signals_sha256"][name]:
                raise ValueError("Raw input changed")
            state["signals_sha256"][name] = digest
            with p.open("rb") as f:
                reader = bioread.reader.Reader(f)
                reader._read_headers()
                reader._read_data(None, bioread.reader.CHUNK_SIZE)
                data = reader.datafile
            for item in items:
                k = int(item["channel"])
                w = int(item["window_index"])
                n = 600000
                c = data.channels[k]
                rawv = c.data[w * n : (w + 1) * n]
                y = resample_exact(rawv, 2000, 250)
                for a, e in cfg["paired_variants"]:
                    cc = dict(
                        bcfg,
                        amplitude_prominence_mad_multiplier=a,
                        energy_threshold_mad_multiplier=e,
                    )
                    found = detect_candidates(y, 250, cc)
                    aa, ee = found["amplitude"], found["energy"]
                    pairs = match_candidates(
                        (aa + found["offset_samples"]) / 250,
                        (ee + found["offset_samples"]) / 250,
                        cc["matching_tolerance_seconds"],
                    )
                    raw.append(
                        dict(
                            path=name,
                            source_file_index=number,
                            channel=k,
                            window_index=w,
                            amplitude_multiplier=a,
                            energy_multiplier=e,
                            amplitude_candidates=len(aa),
                            energy_candidates=len(ee),
                            matched=len(pairs),
                            agreement=2 * len(pairs) / (len(aa) + len(ee))
                            if len(aa) + len(ee)
                            else None,
                        )
                    )
        except Exception as exc:
            failures.append(dict(path=name, error=f"{type(exc).__name__}: {exc}"))
        if number % 40 == 0 or number == len(groups):
            save()
            print(
                f"{number}/{len(groups)} files; rows={len(raw)}; failures={len(failures)}",
                flush=True,
            )
    summaries = []
    for a, e in cfg["paired_variants"]:
        g = [
            r
            for r in raw
            if int(r["amplitude_multiplier"]) == a and int(r["energy_multiplier"]) == e
        ]
        defined = [r for r in g if r["agreement"] != ""]
        summaries.append(
            dict(
                amplitude_multiplier=a,
                energy_multiplier=e,
                channel_windows=len(g),
                amplitude_candidates=sum(int(r["amplitude_candidates"]) for r in g),
                energy_candidates=sum(int(r["energy_candidates"]) for r in g),
                median_agreement=float(
                    np.median([float(r["agreement"]) for r in defined])
                )
                if defined
                else None,
                low_agreement_fraction=sum(float(r["agreement"]) < 0.5 for r in defined)
                / len(defined)
                if defined
                else None,
            )
        )
    write_rows(out / "raw_sensitivity_summary.csv", summaries)
    synth = []
    for case in cfg["synthetic_cases"]:
        for a, e in cfg["paired_variants"]:
            g = [
                r
                for r in synthetic
                if r["case"] == case and r["amplitude_multiplier"] == a
            ]
            synth.append(
                dict(
                    case=case,
                    amplitude_multiplier=a,
                    energy_multiplier=e,
                    amplitude_candidates=sum(
                        r["candidate_count"] for r in g if r["method"] == "amplitude"
                    ),
                    energy_candidates=sum(
                        r["candidate_count"] for r in g if r["method"] == "energy"
                    ),
                    false_amplitude=sum(
                        r["false_candidates"] for r in g if r["method"] == "amplitude"
                    ),
                    false_energy=sum(
                        r["false_candidates"] for r in g if r["method"] == "energy"
                    ),
                )
            )
    write_rows(out / "synthetic_sensitivity_summary.csv", synth)
    summary = dict(
        files_planned=len(groups),
        files_completed=len(groups) - len(failures),
        failures=len(failures),
        raw_rows=len(raw),
        synthetic_rows=len(synthetic),
        scenario_count=len(cfg["paired_variants"]),
        clinical_qc_passed=False,
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    state["status"] = (
        "completed_sensitivity_descriptions"
        if not failures
        else "completed_with_failures"
    )
    save()
    state["outputs_sha256"] = {
        str(p.relative_to(out)): sha(p)
        for p in out.rglob("*")
        if p.is_file() and p.name != "run_manifest.json"
    }
    (out / "run_manifest.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
