"""Contracts for identity-aware, actual-time exploratory reanalysis."""

from collections import defaultdict
import math
import numpy as np


def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def source_mapping_admission(row, admission):
    """Classify a source mapping row under the frozen filename/matcher rule.

    This is a data-format admission decision only.  It does not certify
    physiological quality or scientific validity.
    """
    status = str(row.get("match_status", "") or "")
    accepted = set(admission.get("accepted_match_statuses", []))
    reason = "algorithmically_accepted"
    if status not in accepted:
        # Later accepted-link pipelines use explicit evidence instead of match_status.
        # An explicit rejected/unresolved status must never use this fallback.
        rules = admission.get("accepted_blank_status_rules", []) if not status else []
        matches = [
            rule
            for rule in rules
            if row.get("basis") in rule["bases"]
            and all(
                str(row.get(k, "")).lower() == str(v).lower()
                for k, v in rule.get("equals", {}).items()
            )
            and all(
                str(row.get(k, "") or "").strip()
                for k in rule.get("required_fields", [])
            )
            and all(
                row.get(k) == row.get(v) and row.get(k)
                for k, v in rule.get("equal_fields", {}).items()
            )
        ]
        if not matches:
            return False, "match_status_not_accepted"
        reason = "algorithmically_accepted:" + matches[0]["name"]
    for field in admission.get("required_fields", []):
        if not str(row.get(field, "") or "").strip():
            return False, f"missing_required_field:{field}"
    if str(row.get("stage", "")).strip() not in set(
        admission.get("eligible_stages", [])
    ):
        return False, "stage_not_eligible"
    filename = str(row.get("filename", "") or "")
    if filename.startswith("._"):
        return False, "appledouble_ignored"
    return True, reason


def normalize_source_mapping_row(row):
    """Recover a missing format field from the filename; retain all evidence."""
    from pathlib import Path

    result = dict(row)
    if not result.get("extension"):
        result["extension"] = Path(result.get("filename", "")).suffix.lower()
    return result


def acquisition_date_status(selected):
    """Keep unknown dates distinct from demonstrated date conflicts."""
    if not selected:
        return "no_admitted_Hb"
    values = [r["same_date"] for r in selected]
    if any(v is None for v in values):
        return "unknown_acquisition_date"
    if all(values):
        return "same_date_all"
    return "mixed_dates" if any(values) else "different_dates_all"


def _subject_id_sort_key(subject_id):
    """Sort research IDs by their numeric suffix, with a stable text fallback."""
    import re

    text = str(subject_id)
    match = re.search(r"(\d+)$", text)
    if match:
        return (0, int(match.group(1)), text)
    return (1, text)


def unify_people(rows, aliases, conflict_policy="missing"):
    """Consolidate confirmed aliases while preserving an auditable conflict rule.

    ``missing`` is the conservative default used by older runs.  The current
    adjudication can explicitly request ``smallest_numeric_id``; in that mode
    every conflicting field is taken from the source row with the smallest
    numeric research ID and the decision is recorded in ``conflicts``.
    """
    if conflict_policy not in {"missing", "smallest_numeric_id"}:
        raise ValueError(f"Unknown conflict policy: {conflict_policy}")
    groups = defaultdict(list)
    for row in rows:
        groups[aliases.get(row["ID"], row["ID"])].append(row)
    result, conflicts, registry = [], [], []
    vas = [f"VAS_{i}min" for i in range(1, 21)]
    for person, copies in sorted(groups.items()):
        copies = sorted(copies, key=lambda r: _subject_id_sort_key(r["ID"]))
        base = dict(copies[0])
        for field in vas:
            if len({r[field] for r in copies}) != 1:
                raise ValueError("Confirmed aliases have conflicting VAS")
        for field in base:
            if field == "ID" or field in vas:
                continue
            if len({r[field] for r in copies}) > 1:
                selected = (
                    copies[0] if conflict_policy == "smallest_numeric_id" else None
                )
                for row in copies:
                    conflicts.append(
                        dict(
                            person_id=person,
                            source_alias=row["ID"],
                            field=field,
                            value=row[field],
                            selected_source_alias=selected["ID"] if selected else "",
                            selection_rule=conflict_policy,
                            selected_value=selected[field] if selected else "",
                        )
                    )
                base[field] = selected[field] if selected else ""
        base["ID"] = person
        result.append(base)
        registry.extend(dict(person_id=person, source_alias=r["ID"]) for r in copies)
    return result, conflicts, registry


def vas_support(row, block, spec):
    minutes = list(range(block * 5 + 1, block * 5 + 6))
    valid = [m for m in minutes if numeric(row.get(f"VAS_{m}min")) is not None]
    if spec == "A":
        selected = minutes if valid == minutes else []
    elif spec == "B":
        runs = []
        for m in valid:
            if not runs or m != runs[-1][-1] + 1:
                runs.append([])
            runs[-1].append(m)
        selected = max(runs, key=len, default=[])
        if len(selected) < 3:
            selected = []
    else:
        raise ValueError("Unknown support specification")
    if not selected:
        return None
    return dict(
        block=block,
        support_spec=spec,
        minutes=";".join(map(str, selected)),
        start_s=60 * (selected[0] - 1),
        end_s=60 * selected[-1],
        vas_mean=float(np.mean([numeric(row[f"VAS_{m}min"]) for m in selected])),
    )


def match_peaks(a, b, tolerance):
    """Maximum cardinality, then minimum absolute error; monotone one-to-one.

    Sparse dynamic program over feasible edges, preserving the original indices.
    Each row is committed after all its edges to prevent reusing an a peak.
    """
    a, b = np.asarray(a), np.asarray(b)
    if np.any(np.diff(a) <= 0) or np.any(np.diff(b) <= 0):
        raise ValueError("Peaks must be unique and ordered")
    tree = [None] * (len(b) + 1)
    nodes = []

    def better(x, y):
        if x is None:
            return y
        if y is None:
            return x
        return x if (nodes[x][0], -nodes[x][1]) >= (nodes[y][0], -nodes[y][1]) else y

    def query(k):
        value = None
        while k:
            value = better(value, tree[k])
            k -= k & -k
        return value

    for i, t in enumerate(a):
        pending = []
        for j in range(
            np.searchsorted(b, t - tolerance),
            np.searchsorted(b, t + tolerance, side="right"),
        ):
            parent = query(j)
            n, cost = (0, 0.0) if parent is None else nodes[parent][:2]
            nodes.append((n + 1, cost + abs(t - b[j]), parent, i, j))
            pending.append((j + 1, len(nodes) - 1))
        for k, value in pending:
            while k < len(tree):
                tree[k] = better(tree[k], value)
                k += k & -k
    node = query(len(b))
    pairs = []
    while node is not None:
        _, _, parent, i, j = nodes[node]
        pairs.append((i, j))
        node = parent
    return list(reversed(pairs))


def rr_metrics(peaks, good):
    peaks = np.asarray(peaks, float)
    good = np.asarray(good, bool)
    rr = np.diff(peaks)
    ok = good[:-1] & good[1:] & (rr >= 0.3) & (rr <= 2)
    pairs = ok[:-1] & ok[1:]
    return dict(
        hr_bpm=float(60 / np.mean(rr[ok])) if ok.any() else None,
        rr_rmssd_ms=float(1000 * np.sqrt(np.mean(np.diff(rr)[pairs] ** 2)))
        if pairs.any()
        else None,
        rr_count=int(ok.sum()),
        rr_pairs=int(pairs.sum()),
        valid_rr_seconds=float(rr[ok].sum()),
    )


def time_weights(t, start, end):
    """Right-endpoint interval support, never integrate across a time gap."""
    t = np.asarray(t, float)
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Invalid time axis")
    dt = np.median(np.diff(t))
    left = np.r_[t[0] - dt, t[:-1]]
    gap = t - left > 1.5 * dt
    w = np.maximum(0, np.minimum(t, end) - np.maximum(left, start))
    w[gap] = 0
    return w
