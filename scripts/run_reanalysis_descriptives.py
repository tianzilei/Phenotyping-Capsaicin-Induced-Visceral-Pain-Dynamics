"""Person-level observation support, variability, bounded sensitivity, prediction."""

import json
import sys
import subprocess
import os
import time
import uuid
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.contracts import read_wide
from capsaicin.stopping import (
    audit_stopping,
    stopping_distribution,
    observed_bootstrap,
    bounded_means,
    area_bounds,
    grouped_observed,
)
from capsaicin.missingness import classify_all, adjacent_composition
from capsaicin.variability import window_metrics


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("descriptives_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cfg = json.loads((run / "frozen_config.json").read_text(encoding="utf-8"))
    dc = json.loads((run / "vas_config.json").read_text(encoding="utf-8"))
    rows = read_wide(run / "BaselineData_person_private.csv", dc)
    audit = audit_stopping(rows, processed_E=True)
    groups = defaultdict(list)
    for r in rows:
        groups[r["subject_id"]].append(r)
    write(out / "stopping_audit_private.csv", audit)
    write(out / "marker_distribution.csv", stopping_distribution(audit, range(1, 21)))
    write(
        out / "observed_curve.csv",
        observed_bootstrap(
            rows, range(1, 21), cfg["vas"]["descriptive_bootstrap"], cfg["seed"]
        ),
    )
    bounds = bounded_means(rows, list(range(1, 21)), 0, 10)
    write(out / "bounded_means.csv", bounds)
    write(out / "area_bounds.csv", [area_bounds(bounds)])
    write(out / "observed_by_marker.csv", grouped_observed(rows, audit, range(1, 21)))
    classified = classify_all(rows)
    write(out / "missingness_private.csv", classified)
    write(out / "adjacent_composition.csv", adjacent_composition(rows))
    metrics = []
    for sid, rs in groups.items():
        marker = next(
            (r["termination_code"] for r in rs if r["termination_code"]), "none"
        )
        for a, b in [(1, 20), (1, 10), (1, 5), (6, 10), (11, 15), (16, 20)]:
            metrics.append(
                dict(
                    subject_id=sid,
                    marker=marker,
                    window=f"{a}_{b}",
                    **window_metrics(rs, a, b),
                )
            )
    write(out / "window_metrics_private.csv", metrics)
    summary = dict(
        persons=len(groups),
        observed=sum(r["status"] == "observed" for r in rows),
        markers=dict(Counter(r["eventual_marker"] for r in audit)),
        complete_1_20=sum(
            window_metrics(rs, 1, 20)["complete"] for rs in groups.values()
        ),
        complete_1_10=sum(
            window_metrics(rs, 1, 10)["complete"] for rs in groups.values()
        ),
    )
    dump(out / "summary.json", summary)
    # Each row is one confirmed person; nested folds fit preprocessing and tuning on training only.
    from sklearn.model_selection import KFold, GridSearchCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import RandomForestRegressor

    predcfg = cfg["prediction"]
    ids = []
    xx = []
    yy = []
    for sid, rs in sorted(groups.items()):
        vals = {r["time_min"]: r["vas"] for r in rs if r["status"] == "observed"}
        if all(i in vals for i in [1, 2, 3, 4, 5, 10]):
            ids.append(sid)
            xx.append([vals[i] for i in range(1, 6)])
            yy.append(vals[10])
    x = np.array(xx)
    y = np.array(yy)
    predictions = []
    choices = []
    for fold, (train, test) in enumerate(
        KFold(5, shuffle=True, random_state=cfg["seed"]).split(x)
    ):
        inner = KFold(4, shuffle=True, random_state=cfg["seed"] + fold)
        candidates = [
            (
                "ridge",
                make_pipeline(StandardScaler(), Ridge()),
                {"ridge__alpha": predcfg["ridge_alpha"]},
            ),
            (
                "random_forest",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=5,
                    random_state=cfg["seed"],
                    n_jobs=1,
                ),
                {"max_depth": predcfg["forest_depth"]},
            ),
        ]
        for j in test:
            predictions.append(
                dict(
                    person_id=ids[j],
                    fold=fold,
                    model="last_value",
                    observed=y[j],
                    predicted=x[j, -1],
                )
            )
        for name, model, params in candidates:
            search = GridSearchCV(
                model, params, cv=inner, scoring="neg_mean_absolute_error", n_jobs=1
            ).fit(x[train], y[train])
            choices.append(
                dict(fold=fold, model=name, parameters=json.dumps(search.best_params_))
            )
            for j, p in zip(test, search.predict(x[test])):
                predictions.append(
                    dict(
                        person_id=ids[j],
                        fold=fold,
                        model=name,
                        observed=y[j],
                        predicted=float(p),
                    )
                )
    write(out / "prediction_private.csv", predictions)
    write(out / "prediction_parameters.csv", choices)
    ps = []
    rng = np.random.default_rng(cfg["seed"])
    for model in predcfg["models"]:
        rr = [r for r in predictions if r["model"] == model]
        error = np.array([r["predicted"] - r["observed"] for r in rr])
        bootstrap = np.array(
            [
                np.mean(np.abs(rng.choice(error, len(error), replace=True)))
                for _ in range(2000)
            ]
        )
        ps.append(
            dict(
                model=model,
                n=len(rr),
                mae=float(np.mean(abs(error))),
                rmse=float(np.sqrt(np.mean(error**2))),
                mae_low=float(np.quantile(bootstrap, 0.025)),
                mae_high=float(np.quantile(bootstrap, 0.975)),
                interval_role="person resampling of fixed out-of-fold predictions; no training uncertainty",
            )
        )
    write(out / "prediction_summary.csv", ps)
    env = dict(
        os.environ,
        RENV_CONFIG_AUTOLOADER_ENABLED="FALSE",
        R_LIBS_USER=str(ROOT / "renv/library/sparse-fpca"),
        LC_ALL="C",
        LANG="C",
    )
    tasks = [
        (
            "variability",
            ["scripts/variability_followup.R", str(out), "2000", str(cfg["seed"])],
        ),
        (
            "remaining",
            [
                "scripts/run_remaining_descriptives.R",
                str(run / "remaining"),
                str(run / "remaining_analysis_config.json"),
            ],
        ),
        (
            "sparse",
            [
                "scripts/run_sparse_fpca.R",
                str(run / "sparse"),
                str(run / "sparse_fpca_config.json"),
            ],
        ),
    ]
    statuses = []
    for label, args in tasks:
        if label != "variability":
            (run / label).mkdir()
        with (out / f"{label}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                ["C:/Program Files/R/R-4.6.1/bin/Rscript.exe", "--vanilla"] + args,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=cfg["timeout_seconds_per_module"],
            )
        statuses.append(dict(module=label, exit_code=result.returncode))
        write(out / "execution_status.csv", statuses)
        print(label, result.returncode, flush=True)
    dump(
        out / "manifest.json",
        dict(
            config_sha256=sha(run / "frozen_config.json"),
            input_sha256=sha(run / "BaselineData_person_private.csv"),
            code_sha256=sha(__file__),
            status="completed"
            if all(r["exit_code"] == 0 for r in statuses)
            else "completed_with_failures",
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
