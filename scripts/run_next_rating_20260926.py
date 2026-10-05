"""Nested person-held-out next-minute prediction; never learn from stopped tails."""

import sys
import json
import uuid
from pathlib import Path
from collections import defaultdict
import numpy as np
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import balanced_accuracy_score, f1_score
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.reanalysis import numeric


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("next_rating_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cp = ROOT / "config/reanalysis_supplement_20260926_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))["next_rating"]
    (out / "frozen_config.json").write_bytes(cp.read_bytes())
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())
    rows = read(run / "BaselineData_person_private.csv")
    observations = []
    risk = []
    for r in rows:
        for t in range(3, 20):
            history = [numeric(r[f"VAS_{i}min"]) for i in range(t - 2, t + 1)]
            target = numeric(r[f"VAS_{t + 1}min"])
            reason = (
                "included"
                if all(v is not None for v in history) and target is not None
                else "next_unobserved"
                if all(v is not None for v in history)
                else "history_gap_or_stopped"
            )
            risk.append(
                dict(
                    person_id=r["ID"],
                    time_min=t,
                    status=reason,
                    next_token=r[f"VAS_{t + 1}min"],
                )
            )
            if reason == "included":
                observations.append(
                    dict(person_id=r["ID"], time_min=t, history=history, target=target)
                )
    x = np.array([r["history"] + [r["time_min"]] for r in observations])
    y = np.array([r["target"] for r in observations])
    groups = np.array([r["person_id"] for r in observations])
    pred = []
    choices = []
    for fold, (train, test) in enumerate(
        GroupKFold(5, shuffle=True, random_state=cfg["seed"]).split(x, y, groups)
    ):
        assert not set(groups[train]) & set(groups[test])
        inner = GroupKFold(4, shuffle=True, random_state=cfg["seed"] + fold)
        models = [
            (
                "ridge",
                make_pipeline(StandardScaler(), Ridge()),
                {"ridge__alpha": cfg["ridge_alpha"]},
            ),
            (
                "random_forest",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=10,
                    n_jobs=1,
                    random_state=cfg["seed"],
                ),
                {"max_depth": cfg["forest_depth"]},
            ),
        ]

        def save(name, values):
            for j, v in zip(test, values):
                pred.append(
                    dict(
                        person_id=groups[j],
                        time_min=observations[j]["time_min"],
                        fold=fold,
                        model=name,
                        current=x[j, 2],
                        observed=y[j],
                        predicted=float(v),
                    )
                )

        save("last_value", x[test, 2])
        for name, model, params in models:
            fit = GridSearchCV(
                model, params, cv=inner, scoring="neg_mean_absolute_error", n_jobs=1
            ).fit(x[train], y[train], groups=groups[train])
            save(name, fit.predict(x[test]))
            choices.append(
                dict(model=name, fold=fold, parameters=json.dumps(fit.best_params_))
            )
        print("next rating outer fold", fold + 1, flush=True)
    write(out / "predictions_private.csv", pred)
    write(out / "risk_set_private.csv", risk)
    write(out / "parameters.csv", choices)
    summary = []
    rng = np.random.default_rng(cfg["seed"])
    unique = np.unique(groups)
    for model in cfg["models"]:
        rr = [r for r in pred if r["model"] == model]
        per = defaultdict(list)
        for r in rr:
            per[r["person_id"]].append(abs(r["observed"] - r["predicted"]))
        sums = np.array([sum(per[s]) for s in unique])
        counts = np.array([len(per[s]) for s in unique])
        boots = []
        for _ in range(2000):
            take = rng.integers(len(unique), size=len(unique))
            boots.append(sums[take].sum() / counts[take].sum())
        truth = [r["observed"] < r["current"] for r in rr]
        direction = [r["predicted"] < r["current"] for r in rr]
        summary.append(
            dict(
                model=model,
                n_people=len(unique),
                n_windows=len(rr),
                mae=float(sums.sum() / counts.sum()),
                mae_low=float(np.quantile(boots, 0.025)),
                mae_high=float(np.quantile(boots, 0.975)),
                rmse=float(
                    np.sqrt(
                        np.mean([(r["observed"] - r["predicted"]) ** 2 for r in rr])
                    )
                ),
                direction_balanced_accuracy=float(
                    balanced_accuracy_score(truth, direction)
                ),
                direction_macro_f1=float(
                    f1_score(truth, direction, average="macro", zero_division=0)
                ),
                interval_role="whole-person resampling of fixed out-of-fold predictions",
            )
        )
    write(out / "summary.csv", summary)
    dump(
        out / "manifest.json",
        dict(
            status="completed",
            config_sha256=sha(cp),
            input_sha256=sha(run / "BaselineData_person_private.csv"),
            code_sha256=sha(__file__),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )


if __name__ == "__main__":
    main()
