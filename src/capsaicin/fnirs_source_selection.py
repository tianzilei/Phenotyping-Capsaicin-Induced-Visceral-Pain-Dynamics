"""User-authorized fNIRS source choices with strict dates and unique ownership."""

import json
from datetime import datetime
from pathlib import Path
from .data_locations import ROOT, path_key, resolve_input, local_path


def measured_date(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for _ in range(35):
            parts = stream.readline().rstrip("\r\n").split("\t")
            if parts[0].strip() == "Measured Date":
                return datetime.strptime(parts[1].strip(), "%Y/%m/%d %H:%M:%S")
    raise ValueError("Missing vendor Measured Date")


def choose_latest(candidates):
    """Each candidate must carry an acquisition datetime and explicit local path."""
    if not candidates:
        raise ValueError("Empty candidate set")
    dated = [(datetime.fromisoformat(r["measured_date"]), r) for r in candidates]
    newest = max((date for date, _ in dated))
    winners = [r for date, r in dated if date == newest]
    if len({str(Path(r["local_path"]).resolve()).casefold() for r in winners}) != 1:
        raise ValueError("Different files have tied acquisition dates")
    return winners[0]


def adjudicate_mapping(rows, pointer=None):
    cp = (
        None
        if isinstance(pointer, dict)
        else Path(pointer)
        if pointer
        else ROOT / "config/fnirs_source_adjudication_active.json"
    )
    if cp is not None and (not cp.exists()):
        return (rows, [], [])
    cfg = (
        pointer
        if isinstance(pointer, dict)
        else json.loads(cp.read_text(encoding="utf-8"))
    )
    if not cfg.get("active"):
        return (rows, [], [])
    rp = local_path(cfg["registry"])
    registry = json.loads(rp.read_text(encoding="utf-8"))
    rows = list(rows)
    existing = {
        (r["current_subject_id"], path_key(resolve_input(r["path"]))) for r in rows
    }
    for row in registry.get("additional_mapping_rows", []):
        k = (row["current_subject_id"], path_key(resolve_input(row["path"])))
        if k not in existing:
            rows.append(row)
            existing.add(k)
    result = []
    audit = []
    cache = {}
    for row in rows:
        sid = row["current_subject_id"]
        decision = registry["decisions"].get(sid)
        if not decision:
            ownership = registry.get("file_owners", {}).get(
                path_key(resolve_input(row["path"]))
            )
            if ownership:
                if sid != ownership["owner"]:
                    audit.append(
                        dict(
                            subject_id=sid,
                            path=row["path"],
                            accepted_for_analysis=False,
                            reason="shared_Hb_smaller_subject_owner",
                        )
                    )
                    continue
            result.append(row)
            continue
        key = path_key(resolve_input(row["path"]))
        candidate = next(
            (
                c
                for c in decision["candidates"]
                if path_key(local_path(c["local_path"])) == key
            ),
            None,
        )
        if candidate is None:
            raise ValueError("Unadjudicated candidate added for a decided subject")
        selected = key == path_key(local_path(decision["selected"]["local_path"]))
        accepted = selected and decision["analysis_status"] == "accepted_unique_owner"
        ownership = registry.get("file_owners", {}).get(key)
        if ownership and sid != ownership["owner"]:
            accepted = False
        if accepted:
            result.append(row)
        audit.append(
            dict(
                subject_id=sid,
                path=row["path"],
                local_path=candidate["local_path"],
                measured_date=candidate["measured_date"],
                selected_source=selected,
                selection_policy=registry.get("version", ""),
                accepted_for_analysis=accepted,
                reason="alternative_source_rejected_by_investigator"
                if not selected
                else decision["analysis_status"],
            )
        )
    return (result, audit, ([cp] if cp is not None else []) + [rp, Path(__file__)])
