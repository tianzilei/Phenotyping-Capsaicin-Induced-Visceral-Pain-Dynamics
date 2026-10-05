"""Hash-checked paired sensitivity comparison for development EGG candidates."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/egg_motion_comparison_v1.json"
KEY = ("subject_id", "recording_stem", "stage")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_rows(folder: Path, name: str):
    manifest_path = folder / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = folder / name
    if sha(path) != manifest["output_sha256"][name]:
        raise ValueError(f"source output hash mismatch: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle)), [manifest_path, path]


def compare_rows(unmasked, screened):
    def by_key(rows):
        result = {}
        for row in rows:
            if row.get("pool") != "development" or row.get("run_status") != "completed":
                raise ValueError(
                    "comparison requires completed development records only"
                )
            key = tuple(row.get(field) for field in KEY)
            if any(not part for part in key) or key in result:
                raise ValueError("missing or duplicate record identity")
            result[key] = row
        return result

    old = by_key(unmasked)
    new = by_key(screened)
    if not old or set(old) != set(new):
        raise ValueError("paired record sets differ")
    pairs = []
    for key in sorted(old):
        a, b = old[key], new[key]
        if (
            a.get("status") != "EGG_CANDIDATE_SPECTRUM_ONLY"
            or b.get("motion_spectrum_status")
            != "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY"
        ):
            raise ValueError("paired candidate spectrum missing")
        pairs.append(
            {
                **dict(zip(KEY, key)),
                "unmasked_peak_cpm": float(a["peak_cpm_weighted"]),
                "screened_peak_cpm": float(b["motion_spectrum_peak_cpm_weighted"]),
                "abs_peak_delta_cpm": abs(
                    float(a["peak_cpm_weighted"])
                    - float(b["motion_spectrum_peak_cpm_weighted"])
                ),
                "abs_slow_ratio_delta": abs(
                    float(a["slow_power_ratio"])
                    - float(b["motion_spectrum_slow_power_ratio"])
                ),
                "abs_coherence_delta": abs(
                    float(a["slow_coherence_descriptive"])
                    - float(b["motion_spectrum_coherence_descriptive"])
                ),
                "motion_candidate_fraction": float(b["motion_candidate_fraction"]),
                "screened_valid_seconds": float(b["motion_spectrum_used_seconds"]),
            }
        )
    summary = {
        "paired_development_records": len(pairs),
        "mean_abs_peak_delta_cpm": statistics.mean(
            row["abs_peak_delta_cpm"] for row in pairs
        ),
        "max_abs_peak_delta_cpm": max(row["abs_peak_delta_cpm"] for row in pairs),
        "mean_abs_slow_ratio_delta": statistics.mean(
            row["abs_slow_ratio_delta"] for row in pairs
        ),
        "max_abs_slow_ratio_delta": max(row["abs_slow_ratio_delta"] for row in pairs),
        "mean_abs_coherence_delta": statistics.mean(
            row["abs_coherence_delta"] for row in pairs
        ),
        "max_abs_coherence_delta": max(row["abs_coherence_delta"] for row in pairs),
        "minimum_screened_valid_seconds": min(
            row["screened_valid_seconds"] for row in pairs
        ),
        "interpretation": "posthoc_candidate_sensitivity_only_not_artifact_validation",
    }
    return pairs, summary


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    old_dir = ROOT / cfg["unmasked_run"]
    new_dir = ROOT / cfg["motion_screened_run"]
    old, old_inputs = checked_rows(old_dir, "development_diagnostics_private.csv")
    new, new_inputs = checked_rows(new_dir, "record_diagnostics_private.csv")
    pairs, summary = compare_rows(old, new)
    out = (
        ROOT
        / "08_outputs"
        / (
            "egg_motion_sensitivity_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "paired_differences_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    revision = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    inputs = [CFG, Path(__file__), *old_inputs, *new_inputs]
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
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
