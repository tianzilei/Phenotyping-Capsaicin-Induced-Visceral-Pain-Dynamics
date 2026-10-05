"""Audit recent ECG/EGG claims without opening sealed validation results.

The inputs are candidate metadata and historical output tables. This script
does not activate a validation sample or calculate accuracy.
"""

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

ROOT = Path(__file__).resolve().parents[1]
ECG = (
    ROOT / "08_outputs/ecg_candidate_quality_20260929T130000Z/ecg_candidate_quality.csv"
)
E08 = ROOT / "08_outputs/e08_adaptive_egg_20260929T110000Z/e08_adaptive_egg.csv"
SAMPLE = (
    ROOT
    / "02_quality_control/validation_sampling_mabv_20260929T140000Z/sampling_log_hashed.csv"
)
SPLIT = (
    ROOT
    / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed/reference_split_private.csv"
)
EXPOSURE = (
    ROOT
    / "02_quality_control/validation_exposure_audit_20260928T060452Z_c34b4ad1/exposure_audit_blank.csv"
)
E08_CODE = ROOT / "scripts/run_e08_adaptive_egg.py"
ECG_CODE = ROOT / "scripts/run_ecg_candidate_quality.py"
SAMPLING_CODE = ROOT / "scripts/build_blinded_validation_sampling.py"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def old_pseudonym(row: dict[str, str]) -> str:
    key = f"{row['subject_id']}|{row['recording_stem']}|{row['stage']}"
    return "EVAL_" + hashlib.sha256(key.encode()).hexdigest()[:12].upper()


def audit(
    ecg: list[dict[str, str]],
    e08: list[dict[str, str]],
    sample: list[dict[str, str]],
    split: list[dict[str, str]],
    exposure: list[dict[str, str]],
) -> dict:
    pools = {row["person_id"]: row["pool"] for row in split}
    all_pool_counts = Counter(pools.get(row["subject_id"], "unknown") for row in ecg)
    by_blind_id = {old_pseudonym(row): row for row in ecg}
    sampled_ids = {row["blinded_record_id"] for row in sample}
    selected = [
        by_blind_id[blind_id] for blind_id in sampled_ids if blind_id in by_blind_id
    ]
    sampled_pool_counts = Counter(
        pools.get(row["subject_id"], "unknown") for row in selected
    )
    eligible_exposure = sum(
        bool(row.get("eligibility_decision", "").strip()) for row in exposure
    )
    sample_fields = set(sample[0]) if sample else set()
    e08_status = Counter(row.get("e08_alt_status", "") for row in e08)
    e08_errors = sum(bool(row.get("error", "").strip()) for row in e08)
    return {
        "validation_status": "NOT_ACTIVATED_INDEPENDENCE_UNESTABLISHED",
        "ecg_candidate_records": len(ecg),
        "ecg_candidate_records_by_pool": dict(sorted(all_pool_counts.items())),
        "historical_sampling_records": len(sampled_ids),
        "historical_sampling_rows": len(sample),
        "historical_sampling_unmatched_ids": len(sampled_ids) - len(selected),
        "historical_sampling_records_by_pool": dict(
            sorted(sampled_pool_counts.items())
        ),
        "historical_sampling_unique_subjects": len(
            {row["subject_id"] for row in selected}
        ),
        "exposure_rows": len(exposure),
        "exposure_eligibility_decisions_recorded": eligible_exposure,
        "historical_review_csv_exposes_stage": "source_stage" in sample_fields,
        "historical_review_csv_exposes_cqs_stratum": "sampling_stratum"
        in sample_fields,
        "historical_review_csv_exposes_source_hash": "source_path_sha256"
        in sample_fields,
        "historical_review_ids_reconstructable_from_subject_fields": True,
        "historical_window_selection": "start_midpoint_end_not_local_quality_extremes",
        "e08_historical_rows": len(e08),
        "e08_historical_status_counts": dict(sorted(e08_status.items())),
        "e08_historical_errors": e08_errors,
        "e08_artifact_screening": "finite_samples_only; no validated motion/saturation/dropout mask",
        "e08_safe_interpretation": "candidate_spectra_only_artifact_quality_not_established",
        "ecg_cqs_negative_control_limitation": "sample_permutation_destroys_ecg_time_structure; score_not_validated_as_a_peak_detection_null",
        "ecg_cqs_multi_denominator_limitation": "raw_lead_sample_indices_are_counted_before_unique_physiological_event_clustering",
        "ecg_cqs_safe_interpretation": "development_triage_only_not_accuracy_or_reference_acceptance",
        "scientific_error_rates_estimable": False,
    }


def main() -> None:
    inputs = [
        ECG,
        E08,
        SAMPLE,
        SPLIT,
        EXPOSURE,
        E08_CODE,
        ECG_CODE,
        SAMPLING_CODE,
        Path(__file__),
    ]
    result = audit(
        read_csv(ECG),
        read_csv(E08),
        read_csv(SAMPLE),
        read_csv(SPLIT),
        read_csv(EXPOSURE),
    )
    out = (
        ROOT
        / "02_quality_control"
        / (
            "recent_electrophysiology_integrity_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    (out / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = (
        "# Recent electrophysiology integrity audit\n\n"
        "The 36-record/108-window CQS-based package is a development triage list, "
        "not an independent blinded validation set. It includes sealed-pool records "
        "before exposure eligibility was established, and its review CSV reveals "
        "stage, CQS stratum, and source hash. Deterministic unsalted IDs can be "
        "reconstructed from subject, recording, and stage. It also uses fixed "
        "start/mid/end windows, not the claimed local-quality windows.\n\n"
        "The existing sealed-pool, person-level 59-person proposal remains "
        "unactivated. Do not replace it with CQS-selected records. E08's 208 "
        "spectra are candidate signal descriptions: the implementation masks "
        "non-finite samples only and does not establish artifact-free EGG. "
        "AQS and the 208/208 count are not validated quality acceptance.\n\n"
        "The ECG CQS also needs method review: its sample-permutation control "
        "destroys ECG time structure, and its cross-lead denominator counts "
        "raw sample indices before clustering physiological events. The 172 "
        "historical 'auto accepted' labels must not waive reference review.\n\n"
        "No reference labels or exposure decisions were produced by this audit.\n"
    )
    (out / "REPORT.md").write_text(report, encoding="utf-8")
    revision = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "output_sha256": {
            path.name: sha256(path) for path in out.iterdir() if path.is_file()
        },
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
