"""Independent arithmetic and provenance checks for a completed audit."""

import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = ROOT / sys.argv[1]
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed_provisional"
    for name, digest in manifest["sources_sha256"].items():
        assert sha(Path(name)) == digest, name
    for name, digest in manifest["outputs_sha256"].items():
        assert sha(run / name) == digest, name
    prior = ROOT / manifest["configuration"]["input_run"]
    prior_manifest = json.loads(
        (prior / "run_manifest.json").read_text(encoding="utf-8")
    )
    for name, digest in prior_manifest["input_sha256"].items():
        assert sha(Path(name)) == digest, name
    for name, digest in prior_manifest["outputs_sha256"].items():
        assert sha(prior / name) == digest, name
    long = read(prior / "vas_long.csv")
    counts = read(run / "minute_missingness_counts.csv")
    totals = Counter(r["status"] for r in long)
    assert len(long) == 4320 and totals["observed"] == 3444
    groups = Counter(
        r["eventual_marker"] for r in read(run / "subject_missingness_private.csv")
    )
    assert groups == {"E": 150, "T": 9, "none": 57}
    categories = [
        "observed",
        "termination_E",
        "termination_T",
        "pre_marker_missing",
        "post_termination_missing",
    ]
    for r in counts:
        assert sum(int(r[k]) for k in categories) == int(r["n_subjects"])
        if r["group"] == "all":
            expected = Counter(
                x["status"] for x in long if x["time_min"] == r["time_min"]
            )
            assert all(int(r[k]) == expected[k] for k in categories)
    pairs = read(run / "adjacent_mean_decomposition.csv")
    assert len(pairs) == 19
    errors = []
    for a, r in enumerate(pairs, 1):
        assert int(r["start_min"]) == a and int(r["end_min"]) == a + 1
        x = {
            s["subject_id"]: float(s["vas"])
            for s in long
            if s["status"] == "observed" and int(s["time_min"]) == a
        }
        y = {
            s["subject_id"]: float(s["vas"])
            for s in long
            if s["status"] == "observed" and int(s["time_min"]) == a + 1
        }
        common = sorted(x.keys() & y.keys())
        total = statistics.mean(y.values()) - statistics.mean(x.values())
        within = statistics.mean(y[s] - x[s] for s in common)
        assert (len(x), len(y), len(common)) == tuple(
            int(r[k]) for k in ("n_start", "n_end", "n_both")
        )
        assert math.isclose(total, float(r["observed_mean_change"]), abs_tol=1e-12)
        assert math.isclose(within, float(r["paired_observed_change"]), abs_tol=1e-12)
        errors.append(abs(total - within - float(r["composition_total"])))
    assert max(errors) < 1e-12
    assert "Ran 75 tests" in (run / "tests.log").read_text(encoding="utf-8")
    out = ROOT / "02_quality_control" / ("missingness_review_" + uuid.uuid4().hex[:8])
    subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "--quiet",
            str(out / "verification.json"),
        ],
        check=True,
        cwd=ROOT,
    )
    out.mkdir(exist_ok=False)
    result = dict(
        status="passed",
        run=str(run),
        manifest_sha256=sha(run / "run_manifest.json"),
        verifier_sha256=sha(Path(__file__)),
        cells=len(long),
        status_counts=dict(totals),
        subject_groups=dict(groups),
        adjacent_pairs=len(pairs),
        max_identity_error=max(errors),
        sources_and_outputs_verified=True,
        prior_inputs_and_outputs_verified=True,
        tests=75,
    )
    (out / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
