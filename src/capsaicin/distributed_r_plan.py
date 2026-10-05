"""Whole-person R task roster and explicit, batch-independent random streams."""

import hashlib
import numpy as np
from sklearn.model_selection import KFold


def long_rows(values, rows, end):
    result = dict(person=[], time=[], vas=[])
    for row in rows:
        for minute in np.flatnonzero(np.isfinite(values[row, :end])):
            result["person"].append(f"p{int(row):04d}")
            result["time"].append(int(minute + 1))
            result["vas"].append(float(values[row, minute]))
    return result


def r_seed(master, label, replicate):
    value = hashlib.sha256(f"{master}|R_fit|{label}|{replicate}".encode()).digest()
    return int.from_bytes(value[:8], "little") % (2**31 - 1)


def subject_indices(master, frame, replicate, n):
    raw = hashlib.sha256(
        f"{master}|R_{frame}|{replicate}|subject_multiplicity".encode()
    ).digest()
    rng = np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(raw, dtype="<u4").tolist())
    )
    index = rng.integers(0, n, size=n)
    return index.tolist(), hashlib.sha256(index.astype("<i8").tobytes()).hexdigest()


def cells(config):
    result = []
    for c in config["gamm"]["cells"]:
        frame = ("complete" if c["cohort"] == "complete" else "observed") + str(
            c["end"]
        )
        result.append(dict(c, module="gamm", frame=frame))
    for end in config["complete"]["intervals"]:
        result.append(
            dict(id=f"F{end}", module="complete", end=end, frame=f"complete{end}")
        )
    for end in config["sparse"]["intervals"]:
        for mu, cov in config["sparse"]["bandwidths"]:
            result.append(
                dict(
                    id=f"S{end}_bw{mu}_{cov}",
                    module="sparse",
                    end=end,
                    frame=f"observed{end}",
                    bandwidth=[mu, cov],
                )
            )
    return result


def jobs(config):
    result = []
    roster = cells(config)
    for cell in roster:
        result.append(dict(id="reference__" + cell["id"], stage="reference", cell=cell))
    for module in ["gamm", "complete", "sparse"]:
        spec = config[module]
        for cell in [c for c in roster if c["module"] == module]:
            for start in range(0, spec["replicates"], spec["batch_size"]):
                result.append(
                    dict(
                        id=f"{module}__{cell['id']}__{start:05d}",
                        stage=module,
                        cell=cell,
                        start=start,
                        stop=min(start + spec["batch_size"], spec["replicates"]),
                    )
                )
    cv = config["complete"]["reconstruction"]
    for cell in [c for c in roster if c["module"] == "complete"]:
        for repeat in range(cv["repeats"]):
            for fold in range(cv["folds"]):
                result.append(
                    dict(
                        id=f"reconstruction__{cell['id']}__r{repeat:03d}__f{fold}",
                        stage="reconstruction",
                        cell=cell,
                        repeat=repeat,
                        fold=fold,
                    )
                )
    return sorted(result, key=lambda j: (config["sequence"].index(j["stage"]), j["id"]))


def request_for(config, data, job):
    cell = job["cell"]
    stage = job["stage"]
    module = cell["module"]
    frame = data[cell["frame"]]
    kind = module + ("_reference" if stage == "reference" else "_bootstrap")
    if stage == "reconstruction":
        kind = "complete_reconstruction"
    request = dict(
        task=job["id"],
        kind=kind,
        seed=r_seed(config["master_seed"], cell["id"], "reference"),
        grid=list(range(1, cell["end"] + 1)),
    )
    if module == "gamm":
        request.update(data=frame["long"], k=cell["k"], correlated=cell["correlated"])
    elif module == "complete":
        request["data"] = dict(y=frame["y"])
    else:
        options = dict(
            config["sparse"]["options"],
            userBwMu=cell["bandwidth"][0],
            userBwCov=cell["bandwidth"][1],
        )
        request.update(data=dict(Ly=frame["Ly"], Lt=frame["Lt"]), options=options)
    if stage in ["gamm", "complete", "sparse"]:
        draws = [
            subject_indices(
                config["master_seed"], cell["frame"], rep, frame["n_people"]
            )
            for rep in range(job["start"], job["stop"])
        ]
        request["draws"] = [x[0] for x in draws]
        request["replicate_seeds"] = [
            r_seed(config["master_seed"], cell["id"], rep)
            for rep in range(job["start"], job["stop"])
        ]
        request["indices_sha256"] = [x[1] for x in draws]
    elif stage == "reconstruction":
        cv = config["complete"]["reconstruction"]
        seed = r_seed(config["master_seed"], cell["frame"] + "_cv", job["repeat"])
        tr, te = list(
            KFold(cv["folds"], shuffle=True, random_state=seed).split(
                range(frame["n_people"])
            )
        )[job["fold"]]
        request.update(train=tr.tolist(), test=te.tolist(), seed=seed)
    return request
