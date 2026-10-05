"""Native Python stability and training repeats; physiological inference stays closed."""

from __future__ import annotations
import warnings
import numpy as np
from .distributed_development import canonical, digest
from .distributed_observation import index_stream
from .distributed_prediction import seed
from .distributed_cluster_legacy import dtw, pam, fuzzy
from .completion import select_shapelets, shapelet_distances, solve_fe

_DISTANCES = {}
_REFERENCES = {}


def fit_partition(x, method, k, s, distances=None, full=False):
    from sklearn.cluster import KMeans
    from scipy.spatial.distance import cdist

    if method == "euclidean_kmeans":
        fit = KMeans(k, n_init=20 if full else 5, random_state=s).fit(x)
        return dict(centers=fit.cluster_centers_, labels=fit.labels_)
    if method == "dtw_pam":
        med, labels = pam(distances, k, s)
        return dict(medoids=np.asarray(med), labels=labels)
    centers, labels, u = fuzzy(x, k, s)
    return dict(centers=centers, labels=labels, membership=u)


def assignments(x, fit, method, distances=None):
    from scipy.spatial.distance import cdist

    if method == "dtw_pam":
        return np.argmin(distances, axis=1), None
    distance = cdist(x, fit["centers"])
    if method == "fuzzy_cmeans":
        u = np.maximum(distance, 1e-12) ** -2
        u /= u.sum(axis=1, keepdims=True)
        return u.argmax(axis=1), u
    return distance.argmin(axis=1), None


def distance_matrix(x, key):
    if key not in _DISTANCES:
        matrix = np.zeros((len(x), len(x)))
        for i in range(len(x)):
            for j in range(i):
                matrix[i, j] = matrix[j, i] = dtw(x[i], x[j], radius=2)
        _DISTANCES[key] = matrix
    return _DISTANCES[key]


def partition_metrics(reference, predicted, oob, k, u=None):
    from sklearn.metrics import adjusted_rand_score
    from scipy.optimize import linear_sum_assignment

    ari = float(adjusted_rand_score(reference, predicted))
    ari_oob = (
        float(adjusted_rand_score(reference[oob], predicted[oob]))
        if len(oob) >= 2
        else np.nan
    )
    table = np.zeros((k, k), int)
    np.add.at(table, (reference, predicted), 1)
    union = table.sum(axis=1)[:, None] + table.sum(axis=0)[None, :] - table
    jaccard = np.divide(
        table, union, out=np.zeros_like(table, dtype=float), where=union > 0
    )
    a, b = linear_sum_assignment(-jaccard)
    matched = float(np.mean(jaccard[a, b]))
    if u is None:
        entropy = entropy_oob = np.nan
    else:
        ent = -np.sum(u * np.log(np.maximum(u, np.finfo(float).tiny)), axis=1)
        entropy = float(ent.mean())
        entropy_oob = float(ent[oob].mean()) if len(oob) else np.nan
    flags = dict(
        oob_people=len(oob),
        oob_reference_classes=len(np.unique(reference[oob])),
        oob_fitted_classes=len(np.unique(predicted[oob])),
        collapsed_fit=len(np.unique(predicted)) < k,
    )
    return [ari, ari_oob, matched, entropy, entropy_oob], flags


def cluster_batch(config, data, job):
    x = data["x"]
    cell = job["cell"]
    k = cell["k"]
    method = cell["method"]
    n = len(x)
    distance_key = digest(
        [config["prepared_input_sha256"][cell["data_key"]], config["dtw_radius"]]
    )
    dd = distance_matrix(x, distance_key) if method == "dtw_pam" else None
    ref_key = digest([distance_key, method, k, config["reference_seed"]])
    if ref_key not in _REFERENCES:
        _REFERENCES[ref_key] = fit_partition(
            x, method, k, config["reference_seed"], dd, full=True
        )
    reference = _REFERENCES[ref_key]["labels"]
    rows = []
    indices = []
    flags = []
    failures = []
    for rep in range(job["start"], job["stop"]):
        w, h = index_stream(
            config["master_seed"], "cluster_" + cell["interval_key"], rep, n
        )
        take = np.repeat(np.arange(n), w)
        # Preserve the logical draw order for initialization-dependent medoid methods.
        key = f"{config['master_seed']}|cluster_{cell['interval_key']}|{rep}|subject_multiplicity".encode()
        import hashlib

        rng = np.random.default_rng(
            np.random.SeedSequence(
                np.frombuffer(hashlib.sha256(key).digest(), dtype="<u4").tolist()
            )
        )
        take = rng.integers(0, n, size=n)
        s = seed(config, "cluster_" + cell["id"], rep, "fit")
        try:
            fit = fit_partition(
                x[take],
                method,
                k,
                s,
                dd[np.ix_(take, take)] if dd is not None else None,
            )
            pred, u = assignments(
                x, fit, method, dd[:, take[fit["medoids"]]] if dd is not None else None
            )
            row, flag = partition_metrics(reference, pred, np.flatnonzero(w == 0), k, u)
            rows.append(row)
            flags.append(flag)
            failures.append(None)
        except (ValueError, np.linalg.LinAlgError) as exc:
            rows.append([np.nan] * 5)
            flags.append(
                dict(
                    oob_people=int(np.sum(w == 0)),
                    collapsed_fit=None,
                    oob_reference_classes=None,
                    oob_fitted_classes=None,
                )
            )
            failures.append(type(exc).__name__ + ": " + str(exc))
        indices.append(h)
    return dict(
        statistics=rows,
        index_sha256=indices,
        flags=flags,
        failures=failures,
        reference_cluster_sizes=np.bincount(reference, minlength=k).tolist(),
    )


def classifier_metrics(reference, predicted, k):
    from sklearn.metrics import f1_score

    reference, predicted = np.asarray(reference), np.asarray(predicted)
    if not len(reference):
        return [np.nan] * 3
    present = np.unique(reference)
    recall = [float(np.mean(predicted[reference == c] == c)) for c in present]
    return [
        float(np.mean(reference == predicted)),
        float(np.mean(recall)),
        float(
            f1_score(
                reference,
                predicted,
                labels=np.arange(k),
                average="macro",
                zero_division=0,
            )
        ),
    ]


def training_fold(config, data, job):
    from sklearn.model_selection import KFold
    from sklearn.cluster import KMeans
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.impute import SimpleImputer
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    import pandas as pd

    cell = job["cell"]
    x = data["x"]
    k = cell["k"]
    repeat = job["repeat"]
    fold = job["fold"]
    stage = job["stage"]
    cfg = config["baseline_recovery"] if stage == "baseline" else config["recovery"]
    if len(x) < cfg["folds"] + k:
        return dict(
            status="inestimable",
            reason="too_few_complete_development_people",
            n_people=len(x),
            metrics=[],
            test_rows=[],
        )
    splits = list(
        KFold(
            cfg["folds"],
            shuffle=True,
            random_state=seed(
                config, stage + "_" + cell["interval_key"], repeat, "outer"
            ),
        ).split(x)
    )
    tr, te = splits[fold]
    partition = KMeans(
        k,
        n_init=20,
        random_state=seed(config, stage + "_" + cell["id"], repeat, "partition", fold),
    ).fit(x[tr])
    labels = partition.labels_
    reference = partition.predict(x[te])
    sizes = np.bincount(labels, minlength=k)
    if sizes.min() < (
        cfg["minimum_training_members_per_class"] if stage == "baseline" else 1
    ):
        return dict(
            status="inestimable",
            reason="training_class_support",
            n_people=len(x),
            metrics=[],
            test_rows=te.tolist(),
            train_rows=tr.tolist(),
            training_class_sizes=sizes.tolist(),
        )
    majority = int(sizes.argmax())
    metrics = []
    predictions = []
    origins_out = []
    preprocessing = []

    def record(prefix, name, predicted):
        metrics.append(
            dict(
                prefix=prefix,
                model=name,
                values=classifier_metrics(reference, predicted, k),
                n_test=len(te),
                missing_reference_classes=sorted(set(range(k)) - set(reference)),
            )
        )
        predictions.append(
            dict(prefix=prefix, model=name, predicted=np.asarray(predicted).tolist())
        )

    if stage == "recovery":
        for prefix in cfg["prefixes"]:
            record(prefix, "training_majority", np.full(len(te), majority))
            raw = make_pipeline(
                StandardScaler(), LogisticRegression(C=1, max_iter=2000)
            ).fit(x[tr, :prefix], labels)
            record(prefix, "raw_prefix_logistic", raw.predict(x[te, :prefix]))
            if prefix in cfg["shapelet_prefixes"]:
                shapes, origins = select_shapelets(
                    x[tr, :prefix],
                    labels,
                    cfg["length"],
                    cfg["maximum_candidates_per_training_class"],
                    seed(config, "shapelet_" + cell["id"], repeat, "selection", fold),
                )
                a, b = (
                    shapelet_distances(x[tr, :prefix], shapes),
                    shapelet_distances(x[te, :prefix], shapes),
                )
                model = make_pipeline(
                    StandardScaler(), LogisticRegression(C=1, max_iter=2000)
                ).fit(a, labels)
                record(prefix, "trained_shapelet_logistic", model.predict(b))
                for origin in origins:
                    row = int(tr[origin["training_row"]])
                    start = int(origin["start_index"])
                    if row in te or start < 0 or start + cfg["length"] > prefix:
                        raise ValueError("Shapelet training/prefix leakage")
                    origins_out.append(
                        dict(
                            prefix=prefix,
                            source_row=row,
                            start_index=start,
                            training_class=int(origin["training_class"]),
                        )
                    )
    else:
        numeric, categorical = (
            cfg["numeric_questionnaire"],
            cfg["categorical_questionnaire"],
        )
        rest = cfg["rest_features"]
        frame = pd.DataFrame(data["numeric"], columns=numeric + rest)
        for j, name in enumerate(categorical):
            frame[name] = pd.Series(data["categorical"][:, j]).replace("", np.nan)
        for name, extra in [
            ("questionnaire", []),
            ("questionnaire_plus_rest_candidates", rest),
        ]:
            transformer = ColumnTransformer(
                [
                    (
                        "numeric",
                        make_pipeline(
                            SimpleImputer(strategy="median"), StandardScaler()
                        ),
                        numeric + extra,
                    ),
                    (
                        "categorical",
                        make_pipeline(
                            SimpleImputer(strategy="most_frequent"),
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                        categorical,
                    ),
                ]
            )
            model = make_pipeline(
                transformer, LogisticRegression(C=1, max_iter=2000)
            ).fit(frame.iloc[tr], labels)
            record(None, name, model.predict(frame.iloc[te]))
            imputer = model[0].named_transformers_["numeric"][0]
            preprocessing.append(
                dict(
                    model=name,
                    features=numeric + extra,
                    training_imputer=[
                        float(v) if np.isfinite(v) else None
                        for v in imputer.statistics_
                    ],
                )
            )
        record(None, "training_majority", np.full(len(te), majority))
    return dict(
        status="estimated_training_partition_recovery",
        metrics=metrics,
        predictions=predictions,
        reference=reference.tolist(),
        train_rows=tr.tolist(),
        test_rows=te.tolist(),
        training_class_sizes=sizes.tolist(),
        shapelet_origins=origins_out,
        preprocessing=preprocessing,
        split_seed=seed(config, stage + "_" + cell["interval_key"], repeat, "outer"),
        n_people=len(x),
    )


def old_candidate_fit(data, counts):
    gram = data["gram"]
    total = np.einsum("i,ijk->jk", counts, gram)
    if counts @ data["row_counts"] < 5:
        return None
    z = total[2:, 2:]
    xy = total[1, 0]
    den = total[1, 1]
    if len(z):
        if np.linalg.matrix_rank(z) < len(z):
            return None
        den -= total[1, 2:] @ np.linalg.solve(z, total[2:, 1])
        xy -= total[1, 2:] @ np.linalg.solve(z, total[2:, 0])
    if den < 1e-10:
        return None
    return dict(coefficients=np.asarray([xy / den]))


def candidate_batch(config, data, job):
    cell = job["cell"]
    n = len(data["gram"])
    rows = []
    indices = []
    failures = []
    for rep in range(job["start"], job["stop"]):
        w, h = index_stream(config["master_seed"], "candidate_" + cell["id"], rep, n)
        indices.append(h)
        try:
            fit = (
                old_candidate_fit(data, w)
                if cell["kind"] == "planned24"
                else solve_fe(dict(gram=data["gram"], p=cell["p"]), w)
            )
            if fit is None:
                raise ValueError("inestimable_design_rank_or_exposure")
            row = fit["coefficients"].tolist()
            if cell["kind"] == "joint22":
                base = solve_fe(dict(gram=data["base_gram"], p=2), w)
                if base is None:
                    raise ValueError("inestimable_base_design_rank")
                reduction = base["sse"] - fit["sse"]
                if reduction < -1e-7:
                    raise ValueError("nested_SSE_identity")
                row.append(float(max(0.0, reduction)))
            rows.append(row)
            failures.append(None)
        except (ValueError, np.linalg.LinAlgError) as exc:
            rows.append([np.nan] * (cell["p"] + (cell["kind"] == "joint22")))
            failures.append(str(exc))
    return dict(statistics=rows, index_sha256=indices, failures=failures)


def execute(config, data, job):
    from threadpoolctl import threadpool_limits
    import os
    import platform
    import time
    import psutil

    started = time.monotonic()
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        if job["stage"] == "cluster":
            result = cluster_batch(config, data, job)
        elif job["stage"] in ("recovery", "baseline"):
            result = training_fold(config, data, job)
        elif job["stage"] == "candidate":
            result = candidate_batch(config, data, job)
        else:
            raise ValueError("Unknown native Python stage")

    # JSON null preserves undefined values and failed replicates.
    def clean(x):
        if isinstance(x, (float, np.floating)):
            return float(x) if np.isfinite(x) else None
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        return x

    payload = clean(
        dict(
            task=job["id"],
            stage=job["stage"],
            cell=job["cell"]["id"],
            job=job,
            result=result,
            warnings=sorted(set(str(w.message) for w in caught)),
            config_sha256=digest(config),
            input_sha256=config["prepared_input_sha256"][job["cell"]["data_key"]],
        )
    )
    return dict(
        payload=payload,
        payload_sha256=digest(payload),
        execution=dict(
            host=platform.node(),
            pid=os.getpid(),
            seconds=time.monotonic() - started,
            rss_bytes=psutil.Process().memory_info().rss,
        ),
    )
