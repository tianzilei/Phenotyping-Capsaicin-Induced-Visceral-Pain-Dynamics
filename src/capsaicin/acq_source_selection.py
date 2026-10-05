"""Apply a hashed ACQ ownership/source registry; never infer identity aliases."""

import json
from pathlib import Path
from .fnirs_source_selection import sha


def apply_acq_registry(rows, registry, hash_file=sha):
    def key(sid, path):
        return sid, str(Path(path).resolve()).casefold()

    decisions = {key(d["person_id"], d["path"]): d for d in registry["decisions"]}
    if len(decisions) != len(registry["decisions"]):
        raise ValueError("Duplicate ACQ decisions")
    selected = []
    audit = []
    cache = {}
    for row in rows:
        k = key(row["current_subject_id"], row["path"])
        if k not in decisions:
            raise ValueError("Unadjudicated ACQ mapping added")
        d = decisions[k]
        if k[1] not in cache:
            cache[k[1]] = hash_file(row["path"])
        if cache[k[1]] != d["sha256"]:
            raise ValueError("Adjudicated ACQ changed")
        audit.append(dict(d))
        if d["selected"]:
            selected.append(row)
    # Different labels must never survive on the same physical path.
    owners = {}
    for row in selected:
        p = key("", row["path"])[1]
        sid = row["current_subject_id"]
        if p in owners and owners[p] != sid:
            raise ValueError("Registry retains multiple owners")
        owners[p] = sid
    return selected, audit


def adjudicate_acq(rows, pointer):
    path = Path(pointer["registry"])
    if sha(path) != pointer["registry_sha256"]:
        raise ValueError("ACQ registry changed")
    registry = json.loads(path.read_text(encoding="utf-8"))
    selected, audit = apply_acq_registry(rows, registry)
    return selected, audit, [path, Path(__file__)]
