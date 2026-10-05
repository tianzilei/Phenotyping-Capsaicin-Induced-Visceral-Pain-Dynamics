"""Explicitly authorized coding in a copy, restricted by the prior private audit."""

import copy
import math
from .contracts import ContractError


def is_numeric_zero(value):
    try:
        return math.isfinite(float(value)) and float(value) == 0
    except (TypeError, ValueError):
        return False


def recode_connected_zeros(wide):
    """Normalize the full zero run attached to E; stop at gaps/nonzero/T.

    Does not infer new stopping events in records without E. Idempotent.
    """
    if len({r["ID"] for r in wide}) != len(wide):
        raise ContractError("Duplicate source IDs")
    output = copy.deepcopy(wide)
    changes = []
    for row in output:
        tokens = [row[f"VAS_{t}min"].strip().upper() for t in range(1, 21)]
        if "T" in tokens or "E" not in tokens:
            continue
        end = tokens.index("E") + 1
        start = end
        while start > 1 and is_numeric_zero(row[f"VAS_{start - 1}min"]):
            start -= 1
        for t in range(start, end):
            field = f"VAS_{t}min"
            changes.append(
                dict(
                    subject_id=row["ID"],
                    field=field,
                    time_min=t,
                    old_raw_value=row[field],
                    new_raw_value="E",
                    old_first_E_min=end,
                    new_first_E_min=start,
                    reason="contiguous_zero_run_attached_to_processed_E",
                    rule_version="e_zero_recode_v2",
                )
            )
            row[field] = "E"
    return output, changes


def recode_pending_zeros(wide, audit, config):
    expected = config["expected_subjects"]
    selected = {
        r["subject_id"]: int(r["first_marker_min"])
        for r in audit
        if r["E_recorded_support"] == "two_preceding_recorded_zeros"
    }
    if len(selected) != expected:
        raise ContractError(
            "Prior audit selected count differs from frozen authorization"
        )
    ids = [r["ID"] for r in wide]
    if len(set(ids)) != len(ids) or not set(selected) <= set(ids):
        raise ContractError("Missing or duplicate source IDs")
    output = copy.deepcopy(wide)
    changes = []
    for row in output:
        if row["ID"] not in selected:
            continue
        t = selected[row["ID"]]
        marker = next(
            (
                j
                for j in range(1, 21)
                if row[f"VAS_{j}min"].strip().upper() in ("E", "T")
            ),
            None,
        )
        if t < 3 or marker != t or row[f"VAS_{t}min"].strip().upper() != "E":
            raise ContractError("Prior audit no longer matches first E")
        for j in (t - 2, t - 1):
            field = f"VAS_{j}min"
            old = row[field]
            try:
                zero = float(old) == 0
            except (TypeError, ValueError):
                zero = False
            if not zero:
                raise ContractError("Authorized cell is no longer numeric zero")
            changes.append(
                dict(
                    subject_id=row["ID"],
                    field=field,
                    time_min=j,
                    old_raw_value=old,
                    new_raw_value="E",
                    old_first_E_min=t,
                    new_first_E_min=t - 2,
                    reason="user_confirmed_unprocessed_two_zero_cells",
                    rule_version=config["version"],
                )
            )
            row[field] = "E"
    if len(changes) != config["expected_changed_cells"]:
        raise ContractError("Changed-cell count differs from authorization")
    return output, changes
