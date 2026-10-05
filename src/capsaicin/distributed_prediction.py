"""Repeated person-held-out nested CV; folds are never independent subjects."""

from __future__ import annotations
import hashlib
import numpy as np


def seed(config, stage, repeat, purpose, fold=None):
    from .distributed_development import canonical

    return int.from_bytes(
        hashlib.sha256(
            canonical([config["master_seed"], stage, repeat, purpose, fold])
        ).digest()[:4],
        "little",
    )


def prepare_arrays(values, stage):
    x, y, groups, minutes = [], [], [], []
    for person, row in enumerate(values):
        if stage == "next_rating":
            for t in range(3, 20):
                if np.isfinite(row[t - 3 : t + 1]).all():
                    x.append([*row[t - 3 : t], t])
                    y.append(row[t])
                    groups.append(person)
                    minutes.append(t)
        elif stage == "five_to_ten":
            if np.isfinite(row[:5]).all() and np.isfinite(row[9]):
                x.append(row[:5])
                y.append(row[9])
                groups.append(person)
                minutes.append(5)
        else:
            raise ValueError("Unknown future-rating task")
    return (
        np.asarray(x, float),
        np.asarray(y, float),
        np.asarray(groups, int),
        np.asarray(minutes, int),
    )


def fold_indices(config, prepared, stage, repeat, fold):
    from sklearn.model_selection import GroupKFold

    x, y, groups, _ = prepared
    if (
        len(np.unique(groups)) < config["outer_folds"]
        or not 0 <= fold < config["outer_folds"]
    ):
        raise ValueError("Insufficient outer subject support")
    splits = list(
        GroupKFold(
            config["outer_folds"],
            shuffle=True,
            random_state=seed(config, stage, repeat, "outer"),
        ).split(x, y, groups)
    )
    train, test = splits[fold]
    inner = list(
        GroupKFold(
            config["inner_folds"],
            shuffle=True,
            random_state=seed(config, stage, repeat, "inner", fold),
        ).split(x[train], y[train], groups[train])
    )
    if set(groups[train]) & set(groups[test]):
        raise ValueError("Outer person leakage")
    for a, b in inner:
        if set(groups[train[a]]) & set(groups[train[b]]):
            raise ValueError("Inner person leakage")
    return train, test, inner


def execute_fold(config, prepared, stage, repeat, fold):
    from .distributed_development import digest
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import GridSearchCV
    from threadpoolctl import threadpool_limits
    import os
    import platform
    import time
    import psutil

    began = time.monotonic()
    x, y, groups, minutes = prepared
    train, test, inner = fold_indices(config, prepared, stage, repeat, fold)
    predictions = [x[test, 2] if stage == "next_rating" else x[test, 4]]
    choices = []
    with threadpool_limits(limits=1):
        models = [
            (
                "ridge",
                make_pipeline(StandardScaler(), Ridge()),
                {"ridge__alpha": config["ridge_alpha"]},
            ),
            (
                "random_forest",
                RandomForestRegressor(
                    n_estimators=config["forest_trees"],
                    min_samples_leaf=config["minimum_leaf"][stage],
                    random_state=seed(config, stage, repeat, "forest", fold),
                    n_jobs=1,
                ),
                {"max_depth": config["forest_depth"]},
            ),
        ]
        for name, model, params in models:
            search = GridSearchCV(
                model,
                params,
                cv=inner,
                scoring="neg_mean_absolute_error",
                n_jobs=1,
                error_score="raise",
            ).fit(x[train], y[train])
            predictions.append(search.predict(x[test]))
            choices.append(
                dict(
                    model=name,
                    parameters=search.best_params_,
                    inner_best_MAE=float(-search.best_score_),
                )
            )
    payload = dict(
        stage=stage,
        repeat=repeat,
        fold=fold,
        config_sha256=digest(config),
        input_sha256=config["prepared_input_sha256"][stage],
        outer_seed=seed(config, stage, repeat, "outer"),
        inner_seed=seed(config, stage, repeat, "inner", fold),
        forest_seed=seed(config, stage, repeat, "forest", fold),
        test_row_indices=test.tolist(),
        test_person_indices=groups[test].tolist(),
        time_min=minutes[test].tolist(),
        observed=y[test].tolist(),
        predictions=np.column_stack(predictions).tolist(),
        choices=choices,
        n_train_people=int(len(np.unique(groups[train]))),
        n_test_people=int(len(np.unique(groups[test]))),
        inner_person_disjoint=True,
        outer_person_disjoint=True,
    )
    return dict(
        payload=payload,
        payload_sha256=digest(payload),
        execution=dict(
            host=platform.node(),
            pid=os.getpid(),
            seconds=time.monotonic() - began,
            rss_bytes=psutil.Process().memory_info().rss,
        ),
    )


def repeat_summary(payloads, prepared, config):
    from .distributed_observation import prediction_statistics

    x, y, groups, _ = prepared
    if (
        len(payloads) != config["outer_folds"]
        or sorted(p["fold"] for p in payloads) != list(range(config["outer_folds"]))
        or len({(p["stage"], p["repeat"]) for p in payloads}) != 1
    ):
        raise ValueError("OOF fold identities differ")
    row_indices = np.concatenate([p["test_row_indices"] for p in payloads])
    if sorted(row_indices.tolist()) != list(range(len(y))):
        raise ValueError("OOF rows omitted or duplicated")
    folds = {}
    for p in payloads:
        for g in p["test_person_indices"]:
            if g in folds and folds[g] != p["fold"]:
                raise ValueError("Person in multiple outer test folds")
            folds[g] = p["fold"]
    predicted = np.vstack([p["predictions"] for p in payloads])[np.argsort(row_indices)]
    observed = np.concatenate([p["observed"] for p in payloads])[
        np.argsort(row_indices)
    ]
    reported_groups = np.concatenate([p["test_person_indices"] for p in payloads])[
        np.argsort(row_indices)
    ]
    reported_times = np.concatenate([p["time_min"] for p in payloads])[
        np.argsort(row_indices)
    ]
    if not np.array_equal(observed, y):
        raise ValueError("OOF targets changed")
    if (
        not np.array_equal(reported_groups, groups)
        or not np.array_equal(reported_times, prepared[3])
        or predicted.shape != (len(y), 3)
        or not np.isfinite(predicted).all()
    ):
        raise ValueError("OOF person/time/prediction rows changed")
    unique, inverse = np.unique(groups, return_inverse=True)
    counts = np.bincount(inverse)
    absolute = np.zeros((len(unique), 3))
    squared = np.zeros_like(absolute)
    np.add.at(absolute, inverse, abs(predicted - y[:, None]))
    np.add.at(squared, inverse, (predicted - y[:, None]) ** 2)
    window = prediction_statistics(
        (counts, absolute, squared), np.ones(len(unique), int)
    )
    person = prediction_statistics(
        (counts, absolute, squared), np.ones(len(unique), int), True
    )
    models = config["models"]
    names = [metric + "_" + model for metric in ("MAE", "RMSE") for model in models] + [
        metric + "_" + model + "_minus_last_value"
        for metric in ("MAE", "RMSE")
        for model in models[1:]
    ]
    return dict(
        stage=payloads[0]["stage"],
        repeat=payloads[0]["repeat"],
        people=len(unique),
        target_rows=len(y),
        window_equal=dict(zip(names, map(float, window))),
        person_equal=dict(zip(names, map(float, person))),
        scope="20_repeat_training_and_split_sensitivity_no_independent_fold_test_or_population_CI",
    )
