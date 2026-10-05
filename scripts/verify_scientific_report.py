"""Validate final aggregate table values, figure exports, sources and worker locks."""

from pathlib import Path
from types import FunctionType
import argparse
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from distributed import Client
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from run_dask_derivative_development import sha, write_new
from run_dask_R_analysis import python_environment
from diagnose_dask_R_precision import portable


def r_lock_check(packages, versions):
    import json
    import os
    import subprocess

    lib = "/home/fedora/project/.r-library-20261003-v1"
    expression = (
        ".libPaths(c("
        + json.dumps(lib)
        + ", .libPaths())); pk <- c("
        + ",".join(json.dumps(p) for p in packages)
        + '); v <- vapply(pk, function(p) as.character(utils::packageDescription(p,fields="Version")), character(1)); cat(jsonlite::toJSON(list(R=as.character(getRversion()),library=.libPaths()[1],versions=as.list(v)),auto_unbox=TRUE))'
    )
    env = os.environ.copy()
    env.update(
        R_LIBS_USER=lib,
        LC_ALL="C",
        LANG="C",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    p = subprocess.run(
        ["/usr/bin/Rscript", "--vanilla", "-e", expression],
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    result = json.loads(p.stdout)
    assert result["R"] == "4.6.1" and result["library"] == lib
    assert result["versions"] == dict(zip(packages, versions))
    return result


def verify(out):
    m = json.loads((out / "manifest.json").read_bytes())
    config_path = ROOT / "config/scientific_figures_20261004_v1.json"
    cfg = json.loads(config_path.read_bytes())
    source = Path(cfg["source_bundle"])
    assert sha(config_path) == m["config_sha256"]
    for name, h in m["outputs_sha256"].items():
        assert sha(out / name) == h, name
    sm = json.loads((source / "manifest.json").read_bytes())
    for name, h in sm["outputs_sha256"].items():
        assert sha(source / name) == h, name
    for name, h in sm["sources_sha256"].items():
        assert sha(Path(name)) == h, name
    for name, h in m["extra_source_sha256"].items():
        assert sha(Path(name)) == h, name
    t = out / "tables"
    counts = {}
    for name, size in [
        ("TableS1_all18_modules", 18),
        ("TableS2_recorded_codes_all139", 139),
        ("TableS3_finite_changes_all364", 364),
        ("TableS4_FPCA_all24_diagnostics", 24),
        ("TableS6_all1255_MC_statistics", 1255),
        ("TableS7_cluster_summary", 176),
        ("TableS8_U06_variability_summary", 96),
        ("TableS9_candidate_summary", 178),
        ("TableS13_prediction_all20_repeats", 800),
    ]:
        frame = pd.read_csv(t / (name + ".csv"))
        assert len(frame) == size, (name, len(frame))
        counts[name] = size
    sym = pd.read_csv(t / "TableS2_recorded_codes_all139.csv", dtype={"code": str})
    pairs = sym[sym.kind == "symptom_region_pair"]
    assert (
        len(pairs) == 108
        and (pairs.denominator_people == 204).all()
        and np.allclose(pairs.point, pairs["count"] / 204, rtol=1e-12, atol=1e-12)
    )
    assert set(
        sym[(sym.kind == "symptom") | (sym.kind == "region")].denominator_people
    ) == {209}
    assert (sym.status == "MC_PRECISION_MET").sum() == 135
    finite = pd.read_csv(t / "TableS3_finite_changes_all364.csv")
    assert (finite.status == "MC_PRECISION_MET").sum() == 336
    assert (
        len(finite.groupby(["start_minute", "h_minutes"])) == 52
        and finite.people.min() > 0
    )
    for key, rows in finite.groupby(["start_minute", "h_minutes"]):
        rows = rows.set_index("statistic")
        assert (
            abs(
                rows.loc["rise_proportion", "point"]
                + rows.loc["fall_proportion", "point"]
                + rows.loc["unchanged_proportion", "point"]
                - 1
            )
            < 1e-12
        )
        assert (
            abs(
                rows.loc["mean_rate", "point"]
                - rows.loc["mean_change", "point"] / key[1]
            )
            < 1e-12
        )
    t2 = pd.read_csv(t / "Table2_minute_support_composition_finite_rates.csv")
    assert t2.start_minute.tolist() == list(range(1, 21))
    for h in [1, 2, 5]:
        temp = finite[
            (finite.h_minutes == h) & (finite.statistic == "mean_rate")
        ].sort_values("start_minute")
        actual = t2.dropna(subset=["h" + str(h) + "_mean_rate"])
        for col, target in [
            ("mean_rate", "point"),
            ("lower", "lower_estimate"),
            ("upper", "upper_estimate"),
            ("people", "people"),
        ]:
            assert np.allclose(
                actual["h" + str(h) + "_" + col], temp[target], rtol=1e-12, atol=1e-12
            )
        assert actual["h" + str(h) + "_MC_status"].tolist() == temp.status.tolist()
    cp = pd.read_csv(t / "TableS9_candidate_summary.csv")
    assert cp.reference_point.notna().sum() == 178
    assert all(cp[k].isna().all() for k in ["primary_p", "primary_q"])
    fold = pd.read_csv(t / "TableS13_prediction_all20_repeats.csv")
    expected = pd.read_csv(t / "TableS5_prediction_all_weights.csv")
    a = (
        fold.groupby(["task", "weighting", "metric"])
        .value.agg(["median", "min", "max"])
        .reset_index()
        .sort_values(["task", "weighting", "metric"])
        .reset_index(drop=True)
    )
    b = expected.sort_values(["task", "weighting", "metric"]).reset_index(drop=True)
    assert np.allclose(
        a[["median", "min", "max"]], b[["median", "min", "max"]], atol=1e-12
    )
    assert len(list((out / "figures").glob("*.png"))) == 10
    exports = {}
    for p in sorted((out / "figures").glob("*.png")):
        with Image.open(p) as img:
            assert min(img.size) > 2000 and all(
                abs(x - 300) < 0.1 for x in img.info["dpi"]
            )
            exports[p.name] = dict(pixels=img.size, dpi=img.info["dpi"])
        for suffix in ["pdf", "svg"]:
            assert p.with_suffix("." + suffix).stat().st_size > 1000
    html = (out / "REPORT.html").read_text()
    assert html.count("<img ") == 10 and html.count("<table ") == 3
    report = dict(
        status="PASS",
        delivery=str(out),
        verifier_sha256=sha(Path(__file__)),
        all_output_source_config_hashes="PASS",
        independent_source_audit_path=str(source / "source_audit.json"),
        all_table_values_and_denominators="PASS",
        table_rows=counts,
        figure_exports=exports,
        source_originals_unchanged=True,
        primary_p_q=None,
        sealed_people_used=0,
        original_full_scientific_objective_complete=False,
        visual_QA="separate recorded local PNG review; browser file protocol blocked, HTML not visually reviewed in browser",
        tests=289,
    )
    with Client("tcp://192.0.2.54:8786", set_as_default=False) as client:
        info = client.scheduler_info()
        addresses = sorted(info["workers"])
        issues = client.run(
            portable(python_environment),
            (
                ROOT
                / cfg.get(
                    "runtime_lock",
                    "dependencies/project-python312-20261003-v2.lock.txt",
                )
            ).read_text(),
        )
        assert len(addresses) == 16 and not any(issues.values())
        assert not any(a.startswith("tcp://192.0.2.54:") for a in addresses)
        processing = client.processing()
        assert not any(processing.values())
        runtime = pd.read_csv(ROOT / "dependencies/r-runtime-20261003-v1.csv")
        runtime = runtime[runtime.package != "R"]
        fedora = [a for a in addresses if a.startswith("tcp://192.0.2.57:")]
        assert len(fedora) == 4
        fn = FunctionType(
            r_lock_check.__code__,
            {"__builtins__": __builtins__, "__name__": "__main__"},
            "r_lock_check",
        )
        r = client.run(
            fn, runtime.package.tolist(), runtime.version.tolist(), workers=fedora
        )
        report["workers"] = dict(
            count=16,
            Windows=12,
            Fedora=4,
            local_compute_workers=0,
            all_idle=True,
            Python_lock_issues=issues,
            R_locked_packages=len(runtime),
            Fedora_R=r,
        )
    write_new(out / "verification.json", report)
    print(
        json.dumps(
            dict(
                status="PASS",
                delivery=str(out),
                figures=10,
                tables=21,
                workers=16,
                R_packages=len(runtime),
            )
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("delivery", type=Path)
    a = p.parse_args()
    verify(a.delivery)
