"""Run the user-requested NeuroKit2 ECG and fnirs-flow Hb feature route.

The script intentionally uses the official fnirs-flow vendor-Hb parser and
window/QC/feature functions.  It does not reconstruct optical density or run
an unavailable project-specific fixed-event pipeline.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FNIRS = Path(os.environ.get("CAPSAICIN_FNIRS_FLOW", "/private/fnirs-flow"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(FNIRS))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, data):
    data = list(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in data for k in r))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(data)


def main():
    from fnirs_flow.processed_hb import (
        read_vendor_processed_hb,
        evaluate_processed_hb_window_qc,
        extract_processed_hb_channel_window_features,
    )
    from fnirs_flow.processed_hb.windows import FrozenWindow, FrozenWindowSet
    import neurokit2 as nk

    out = (
        ROOT
        / "08_outputs"
        / f"reanalysis_neurokit_fnirsflow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True)
    hb_audit = (
        ROOT
        / "08_outputs/reanalysis_20260926_20260925T165400Z_c9b9d41d/hb_edefb824/record_audit_private.csv"
    )
    ecg_run = sorted(
        (ROOT / "08_outputs").glob("complete_physiology_*"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    ann_source = (
        ROOT
        / "01_data/bids_capsaicin_20260925/sourcedata/unassigned/860d3bb5104f9f17/16_fnirs_channel_qc.csv"
    )
    ann = {}
    for r in rows(ann_source):
        if not str(r.get("vendor_channel_number", "")).strip():
            continue
        cid = "ch-" + str(int(float(r["vendor_channel_number"])))
        ann[cid] = {
            "channel_id": cid,
            "vendor_channel_number": cid.split("-")[1],
            "source_id": r["source_id"],
            "detector_id": r["detector_id"],
            "source_detector_pair": r["source_detector_pair"],
            "roi_label": r["roi_label"],
            "aal_label": r["aal_label"],
            "laterality": r["laterality"],
            "probe_role": r["probe_role"],
        }
    window_seconds = int(os.environ.get("CAPSAICIN_WINDOW_SECONDS", "60"))
    windows = FrozenWindowSet(
        tuple(
            FrozenWindow(
                f"m{i + 1}",
                i * window_seconds,
                (i + 1) * window_seconds,
                anchor_type="recording_start",
            )
            for i in range(30)
        ),
        window_set_version=f"recording_relative_{window_seconds}s_v1",
    )
    audit_rows = rows(hb_audit)
    signals = [
        r for r in audit_rows if r.get("status") == "read" and Path(r["path"]).is_file()
    ]
    manifest = {
        "status": "running",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "neurokit2": nk.__version__,
        "fnirs_flow_root": str(FNIRS),
        "fnirs_flow_revision": subprocess.check_output(
            ["git", "-C", str(FNIRS), "rev-parse", "HEAD"], text=True
        ).strip(),
        "input_audit_sha256": sha(hb_audit),
        "channel_annotation_sha256": sha(ann_source),
        "ecg_run": str(ecg_run),
    }
    (out / "frozen_config.json").write_text(
        json.dumps(
            {
                "version": "neurokit2_fnirsflow_length_aligned_v1",
                "window_seconds": window_seconds,
                "ecg": {
                    "clean": "neurokit",
                    "peaks": "neurokit",
                    "quality": "zhao2018",
                    "fixpeaks": "Kubios_sensitivity_only",
                    "status": "not_independently_validated",
                },
                "fnirs": {
                    "parser": "fnirs_flow.processed_hb.read_vendor_processed_hb",
                    "windows": f"recording_relative_{window_seconds}s_v1",
                    "qc": "processed_hb_window_qc_v1",
                    "features": "processed_hb_channel_window_features_v1",
                    "absolute_units": "unverified",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    fnirs_audit = []
    fnirs_qc = []
    fnirs_features = []
    failures = []
    for i, r in enumerate(signals, 1):
        try:
            p = Path(r["path"])
            obj = read_vendor_processed_hb(
                p,
                expected_sha256=r["sha256"],
                expected_channels=42,
                fail_on_irregular_sampling=True,
            )
            annotations = {
                f"ch-{j + 1}": dict(
                    ann.get(f"ch-{j + 1}", {}), channel_id=f"ch-{j + 1}"
                )
                for j in range(42)
            }
            obj.channel_names = [f"ch-{j + 1}" for j in range(42)]
            obj.provenance["source_path_private"] = str(p)
            q = evaluate_processed_hb_window_qc(
                obj, windows, annotations, input_sha256=r["sha256"]
            )
            f = extract_processed_hb_channel_window_features(
                obj, q, windows, annotations, input_sha256=r["sha256"]
            )
            for x in q:
                x.update(
                    {"person_id": r["person_id"], "recording_id": r["recording_id"]}
                )
            for x in f:
                x.update(
                    {"person_id": r["person_id"], "recording_id": r["recording_id"]}
                )
            fnirs_qc.extend(q)
            fnirs_features.extend(f)
            fnirs_audit.append(
                dict(
                    person_id=r["person_id"],
                    recording_id=r["recording_id"],
                    path=str(p),
                    **{
                        k: v
                        for k, v in obj.provenance.items()
                        if k not in {"source_path"}
                    },
                )
            )
        except Exception as e:
            failures.append(
                {
                    "person_id": r.get("person_id", ""),
                    "path": r.get("path", ""),
                    "phase": "fnirs_flow",
                    "error": str(e),
                }
            )
        if i % 20 == 0:
            print(f"fnirs-flow {i}/{len(signals)}", flush=True)
    write(out / "fnirs_record_audit_private.csv", fnirs_audit)
    write(out / "fnirs_window_qc_private.csv", fnirs_qc)
    write(out / "fnirs_channel_window_features_private.csv", fnirs_features)
    ecg_features = (
        list(
            csv.DictReader(
                (ecg_run / "ecg_windows_private.csv").open(
                    encoding="utf-8-sig", newline=""
                )
            )
        )
        if (ecg_run / "ecg_windows_private.csv").is_file()
        else []
    )
    write(out / "ecg_neurokit_windows_private.csv", ecg_features)
    summary = {
        "fnirs_input_records": len(signals),
        "fnirs_processed_records": len(fnirs_audit),
        "fnirs_failed_records": len(failures),
        "fnirs_qc_rows": len(fnirs_qc),
        "fnirs_feature_rows": len(fnirs_features),
        "fnirs_qc_pass_rows": sum(x.get("qc_status") == "pass" for x in fnirs_qc),
        "ecg_windows": len(ecg_features),
        "ecg_qc_pass": sum(
            str(x.get("qc_pass")).lower() == "true" for x in ecg_features
        ),
        "association_status": "not_estimable_without_independent_reference_and_verified_minute_anchor",
        "validation_status": "not_independently_validated",
    }
    write(out / "failures_private.csv", failures)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = (
        "# NeuroKit2 + fnirs-flow exploratory reanalysis\n\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n\nECG uses NeuroKit2 cleaning, peak detection, Zhao2018 quality and Kubios fixpeaks as sensitivity metadata only. EGG is retained as spectral/QC material and is not processed with ECG algorithms. fNIRS uses fnirs-flow's official vendor-Hb parser, window QC and channel-window feature functions. No raw intensity/OD reconstruction was performed; Hb units and all physiological targets remain unverified without two independent annotators."
    )
    (out / "REPORT.md").write_text(report, encoding="utf-8")
    manifest.update(
        {
            "status": "completed",
            "summary": summary,
            "outputs_sha256": {
                str(p.relative_to(out)): sha(p)
                for p in out.rglob("*")
                if p.is_file() and p.name != "run_manifest.json"
            },
        }
    )
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"out": str(out), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
