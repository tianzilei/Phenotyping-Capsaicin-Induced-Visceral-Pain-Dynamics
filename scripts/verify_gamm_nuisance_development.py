"""Verify every synthetic checkpoint, deterministic request and saved diagnostic."""

import argparse
import collections
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from capsaicin.distributed_r import canonical, sha_bytes
from run_gamm_nuisance_development import synthetic_request
from run_dask_derivative_development import write_new, sha


def verify(run, output):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a Git-external audit file")
    m = json.loads((run / "manifest.json").read_bytes())
    c = m["config"]
    if sha_bytes(canonical(c)) != m["config_sha256"]:
        raise ValueError("Config changed")
    completion = json.loads((run / "completion.json").read_bytes())
    for name, h in completion["outputs_sha256"].items():
        if sha(run / name) != h:
            raise ValueError("Completion artifact changed")
    for name, h in m["sources_sha256"].items():
        if sha(run / "snapshot" / name) != h:
            raise ValueError("Frozen source changed")
    # This verifier imports the generator. Do not silently use edited source.
    if (
        sha(ROOT / "scripts/run_gamm_nuisance_development.py")
        != m["sources_sha256"]["scripts/run_gamm_nuisance_development.py"]
    ):
        raise ValueError("Current generator differs from frozen code")
    journal = [json.loads(x) for x in (run / "journal.jsonl").read_bytes().splitlines()]
    if len(journal) != m["jobs"] or len({j["task"] for j in journal}) != m["jobs"]:
        raise ValueError("Journal roster incomplete")
    rows = pd.read_csv(run / "synthetic_diagnostics.csv")
    counts = collections.Counter()
    warning_messages = []
    if len(rows) != m["jobs"] or rows.task.duplicated().any():
        raise ValueError("Summary roster incomplete")
    maxrmse = 0.0
    maxvar = 0.0
    pairs = collections.defaultdict(list)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        for j in journal:
            f = run / "results" / (j["task"] + ".json")
            e = json.loads(f.read_bytes())
            if (
                sha(f) != j["file_sha256"]
                or sha_bytes(canonical(e["payload"])) != e["payload_sha256"]
            ):
                raise ValueError("Checkpoint hash mismatch")
            a = e["payload"]
            request, truth = synthetic_request(c, *a["spec"])
            execution = a["result"]
            r = execution["result"]
            if (
                execution["task"] != request["task"]
                or request["task"] != j["task"]
                or execution["request_sha256"] != sha_bytes(canonical(request))
                or execution["assets_sha256"] != m["R_assets_sha256"]
            ):
                raise ValueError("Task request/assets mismatch")
            pairs[tuple(a["spec"][:-1])].append(sha_bytes(canonical(request["data"])))
            counts[r["status"]] += 1
            saved = rows[rows.task == j["task"]].iloc[0]
            if saved.status != r["status"]:
                raise ValueError("Saved status mismatch")
            if r["status"] == "estimated":
                curve = np.asarray(r["curve"])
                if len(curve) != a["spec"][0] or not np.isfinite(curve).all():
                    raise ValueError("Nonfinite curve")
                rmse = float(np.sqrt(np.mean((curve - truth) ** 2)))
                maxrmse = max(maxrmse, abs(saved.curve_RMSE - rmse))
                if not np.isclose(saved.curve_RMSE, rmse, rtol=1e-12, atol=1e-12):
                    raise ValueError("Saved RMSE mismatch")
                vc = dict(zip(r["VarCorr_rows"], r["VarCorr_values"]))
                maxvar = max(
                    maxvar, abs(float(vc["Residual"][0]) - r["residual_sigma"] ** 2)
                )
                if not np.isclose(
                    float(vc["Residual"][0]),
                    r["residual_sigma"] ** 2,
                    rtol=1e-6,
                    atol=1e-9,
                ):
                    raise ValueError("Printed VarCorr rounding exceeds allowance")
                if r["apVar_finite_matrix"]:
                    eigenvalues = np.linalg.eigvalsh(np.asarray(r["apVar_matrix"]))
                    if bool(eigenvalues.min() > 0) != r[
                        "apVar_positive_definite"
                    ] or not np.allclose(
                        eigenvalues[::-1],
                        r["apVar_covariance_eigenvalues"],
                        rtol=1e-8,
                        atol=1e-8,
                    ):
                        raise ValueError("apVar covariance spectrum mismatch")
        warning_messages = sorted({str(w.message) for w in captured})
    if len(pairs) != m["jobs"] // 2 or any(
        len(p) != 2 or len(set(p)) != 1 for p in pairs.values()
    ):
        raise ValueError("Paired models used different synthetic data")
    summary = []
    for key, g in rows.groupby(
        ["end", "true_intercept_variance", "true_rho", "fitted_CAR1"]
    ):
        ok = g[g.status == "estimated"]
        summary.append(
            dict(
                end=int(key[0]),
                true_intercept_variance=key[1],
                true_rho=key[2],
                fitted_CAR1=bool(key[3]),
                attempted=len(g),
                estimated=len(ok),
                failed=len(g) - len(ok),
                apVar_nonfinite=int((ok.apVar_finite_matrix == False).sum()),
                intercept_small=int(ok.intercept_numerically_small.sum()),
                median_intercept_variance=float(ok.fitted_intercept_variance.median()),
                median_residual_variance=float(ok.fitted_residual_variance.median()),
                median_fitted_rho=float(ok.fitted_rho.median())
                if bool(key[3])
                else None,
                median_curve_RMSE=float(ok.curve_RMSE.median()),
            )
        )
    report = dict(
        status="SYNTHETIC_DEVELOPMENT_CHECKPOINTS_VERIFIED",
        created_utc=datetime.now(timezone.utc).isoformat(),
        verifier_sha256=sha(Path(__file__)),
        run_directory=str(run),
        run_manifest_sha256=sha(run / "manifest.json"),
        tasks=len(journal),
        DGP_datasets=len(pairs),
        fit_status=dict(counts),
        journal_payload_request_input_and_snapshot_hashes="PASS",
        paired_model_inputs="PASS",
        max_saved_curve_RMSE_difference=maxrmse,
        max_VarCorr_printed_rounding_difference=maxvar,
        generator_warnings=warning_messages,
        summary=summary,
        confirmation=False,
        real_data_used=False,
    )
    write_new(output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "summary"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    verify(a.run.resolve(), a.output.resolve())
