"""Independent NumPy re-computation of R residual and burden outputs."""

import csv
import json
import sys
from pathlib import Path
import numpy as np
from run_fpca_followup import ROOT, read, sha


def main():
    run = ROOT / sys.argv[1]
    prior = ROOT / "08_outputs/provisional_vas_20260916T144537Z_11f54777/vas_long.csv"
    data = read(prior)
    by = {}
    for r in data:
        if r["status"] == "observed":
            by.setdefault(r["subject_id"], {})[int(r["time_min"])] = float(r["vas"])
    errors = []
    for r in read(run / "residual_metrics_private.csv"):
        t = np.array(
            sorted(t for t in by[r["subject_id"]] if t <= int(r["end_min"])),
            dtype=float,
        )
        y = np.array([by[r["subject_id"]][t] for t in t])
        degree = int(r["degree"])
        x = np.vander(t - t.mean(), degree + 1, increasing=True)
        coef = np.linalg.lstsq(x, y, rcond=None)[0]
        e = y - x @ coef
        variance = float(e @ e / (len(e) - degree - 1))
        diff = np.diff(e)[np.diff(t) == 1]
        errors += [
            abs(variance - float(r["residual_variance"])),
            abs(float(np.mean(diff**2)) - float(r["residual_mssd"])),
        ]
    for r in read(run / "burden_metrics_private.csv"):
        t = np.arange(1, int(r["end_min"]) + 1, dtype=float)
        y = np.array([by[r["subject_id"]][t] for t in t])
        # Simpson integrates t*y(t), a quadratic on every linearly interpolated segment, exactly.
        mids = (t[:-1] + t[1:]) / 2
        ym = (y[:-1] + y[1:]) / 2
        area = np.sum((y[:-1] + y[1:]) / 2)
        moment = np.sum((t[:-1] * y[:-1] + 4 * mids * ym + t[1:] * y[1:]) / 6)
        errors.append(abs(area - float(r["auc"])))
        if area:
            errors.append(abs(moment / area - float(r["time_centroid"])))
    assert max(errors) < 1e-10, max(errors)
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["outputs_sha256"].items():
        assert sha(run / name) == digest, name
    print(
        json.dumps(
            dict(
                status="passed",
                comparisons=len(errors),
                max_absolute_difference=max(errors),
                output_hashes_verified=True,
            )
        )
    )


if __name__ == "__main__":
    main()
