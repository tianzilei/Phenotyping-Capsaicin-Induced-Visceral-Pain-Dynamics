"""Training-defined complete-trajectory partition recoverability, not disease prediction."""

import sys
import json
import uuid
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.reanalysis import numeric


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("prefix_recoverability_" + uuid.uuid4().hex[:8])
    out.mkdir()
    # Freeze this exact secondary task before fitting; no tuning across k or prefixes.
    cfg = dict(
        version="prefix_recoverability_v1",
        intervals=[10, 20],
        k=[2, 3, 4, 5],
        prefixes=[3, 5, 8],
        folds=5,
        seed=20260926,
        model="training-standardized multinomial logistic C=1",
        labels="KMeans fitted only on outer training complete trajectories; held-out reference nearest training center",
        baseline="training majority cluster",
        role="descriptive recovery of training-defined retrospective partition; not disease truth",
        baseline_covariates="not included: no frozen pre-dose physiological feature definitions",
    )
    dump(out / "frozen_config.json", cfg)
    rows = read(run / "BaselineData_person_private.csv")
    pred = []
    summary = []
    motifs = []
    for end in cfg["intervals"]:
        complete = [
            r
            for r in rows
            if all(numeric(r[f"VAS_{i}min"]) is not None for i in range(1, end + 1))
        ]
        x = np.array(
            [[float(r[f"VAS_{i}min"]) for i in range(1, end + 1)] for r in complete]
        )
        ids = [r["ID"] for r in complete]
        for k in cfg["k"]:
            for fold, (tr, te) in enumerate(
                KFold(5, shuffle=True, random_state=cfg["seed"]).split(x)
            ):
                cluster = KMeans(k, n_init=20, random_state=cfg["seed"]).fit(x[tr])
                truth = cluster.predict(x[te])
                majority = int(np.bincount(cluster.labels_).argmax())
                for prefix in cfg["prefixes"]:
                    model = make_pipeline(
                        StandardScaler(), LogisticRegression(C=1, max_iter=2000)
                    ).fit(x[tr, :prefix], cluster.labels_)
                    output = model.predict(x[te, :prefix])
                    summary.append(
                        dict(
                            end_min=end,
                            k=k,
                            fold=fold,
                            prefix=prefix,
                            n_test=len(te),
                            balanced_accuracy=float(
                                balanced_accuracy_score(truth, output)
                            ),
                            macro_f1=float(
                                f1_score(
                                    truth, output, average="macro", zero_division=0
                                )
                            ),
                            majority_accuracy=float(np.mean(truth == majority)),
                            accuracy=float(np.mean(truth == output)),
                        )
                    )
                    pred.extend(
                        dict(
                            person_id=ids[j],
                            end_min=end,
                            k=k,
                            fold=fold,
                            prefix=prefix,
                            training_partition_reference=int(a),
                            predicted=int(b),
                        )
                        for j, a, b in zip(te, truth, output)
                    )
            full = KMeans(k, n_init=20, random_state=cfg["seed"]).fit(x)
            for c in range(k):
                candidates = np.flatnonzero(full.labels_ == c)
                best = None
                for start in range(end - 4):
                    distances = (
                        (
                            x[candidates, start : start + 5]
                            - full.cluster_centers_[c, start : start + 5]
                        )
                        ** 2
                    ).sum(axis=1)
                    j = int(np.argmin(distances))
                    candidate = (float(distances[j]), start, int(candidates[j]))
                    if best is None or candidate < best:
                        best = candidate
                distance, start, j = best
                motifs.append(
                    dict(
                        end_min=end,
                        k=k,
                        cluster=c,
                        person_id=ids[j],
                        start_min=start + 1,
                        values=";".join(map(str, x[j, start : start + 5])),
                        distance_squared=distance,
                        role="observed_representative_motif_not_learned_discriminative_shapelet",
                    )
                )
    write(out / "fold_metrics.csv", summary)
    write(out / "predictions_private.csv", pred)
    write(out / "representative_motifs_private.csv", motifs)
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())
    dump(
        out / "manifest.json",
        dict(
            status="completed_exploratory",
            config_sha256=sha(out / "frozen_config.json"),
            input_sha256=sha(run / "BaselineData_person_private.csv"),
            code_sha256=sha(__file__),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out, flush=True)


if __name__ == "__main__":
    main()
