"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import collections
import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def close(actual, expected):
    if actual in ("", None):
        if expected is not None:
            raise AssertionError("Missing defined value")
    elif expected is None or abs(float(actual) - expected) > 1e-12:
        raise AssertionError("Numeric mismatch")


def verify_tables(raw, syn, summ, baseline, synthetic_summary):
    groups = collections.defaultdict(dict)
    for r in raw:
        key = (r["path"], r["channel"], r["window_index"])
        a = int(r["amplitude_multiplier"])
        e = int(r["energy_multiplier"])
        if a != e or a in groups[key] or a not in (2, 3, 4, 5):
            raise AssertionError("Duplicate/invalid scenario key")
        groups[key][a] = r
        aa = int(r["amplitude_candidates"])
        ee = int(r["energy_candidates"])
        mm = int(r["matched"])
        if not 0 <= mm <= min(aa, ee):
            raise AssertionError("Invalid matched count")
        close(r["agreement"], 2 * mm / (aa + ee) if aa + ee else None)
    if any((set(g) != {2, 3, 4, 5} for g in groups.values())):
        raise AssertionError("Missing scenario")
    base = {(r["path"], r["channel"], r["window_index"]): r for r in baseline}
    if len(base) != len(baseline) or set(base) != set(groups):
        raise AssertionError("Baseline support differs")
    for key, b in base.items():
        r = groups[key][3]
        for s, t in [
            ("amplitude_candidates", "amplitude_candidate_count"),
            ("energy_candidates", "energy_candidate_count"),
            ("matched", "matched"),
        ]:
            if int(r[s]) != int(b[t]):
                raise AssertionError("Baseline count mismatch")
        close(r["agreement"], float(b["agreement"]) if b["agreement"] else None)
    if len(summ) != 4 or {int(r["amplitude_multiplier"]) for r in summ} != {2, 3, 4, 5}:
        raise AssertionError("Summary scenarios differ")
    for s in summ:
        a = int(s["amplitude_multiplier"])
        g = [v[a] for v in groups.values()]
        if int(s["energy_multiplier"]) != a or int(s["channel_windows"]) != len(g):
            raise AssertionError("Summary support differs")
        for col in ("amplitude_candidates", "energy_candidates"):
            if int(s[col]) != sum((int(r[col]) for r in g)):
                raise AssertionError("Summary total mismatch")
        values = [float(r["agreement"]) for r in g if r["agreement"] != ""]
        close(s["median_agreement"], statistics.median(values) if values else None)
        close(
            s["low_agreement_fraction"],
            sum((v < 0.5 for v in values)) / len(values) if values else None,
        )
    keys = set()
    sg = collections.defaultdict(list)
    for r in syn:
        key = (
            r["case"],
            r["replicate"],
            r["amplitude_multiplier"],
            r["energy_multiplier"],
            r["method"],
        )
        if key in keys:
            raise AssertionError("Duplicate synthetic key")
        keys.add(key)
        n = int(r["candidate_count"])
        truth = int(r["truth_count"])
        matched = int(r["matched"])
        if (
            not 0 <= matched <= min(n, truth)
            or int(r["false_candidates"]) != n - matched
        ):
            raise AssertionError("Invalid synthetic counts")
        close(r["precision"], matched / n if n else None)
        close(r["recall"], matched / truth if truth else None)
        sg[r["case"], r["amplitude_multiplier"], r["energy_multiplier"]].append(r)
    if len(synthetic_summary) != len(sg):
        raise AssertionError("Synthetic summary support differs")
    for s in synthetic_summary:
        g = sg[s["case"], s["amplitude_multiplier"], s["energy_multiplier"]]
        for method in ("amplitude", "energy"):
            selected = [r for r in g if r["method"] == method]
            for field, source in [
                (method + "_candidates", "candidate_count"),
                ("false_" + method, "false_candidates"),
            ]:
                if int(s[field]) != sum((int(r[source]) for r in selected)):
                    raise AssertionError("Synthetic summary mismatch")
    increases = []
    for key, g in groups.items():
        for a in (2, 3, 4):
            for method in ("amplitude", "energy"):
                delta = int(g[a + 1][method + "_candidates"]) - int(
                    g[a][method + "_candidates"]
                )
                if delta > 0:
                    increases.append(
                        dict(
                            path=key[0],
                            channel=key[1],
                            window_index=key[2],
                            method=method,
                            from_multiplier=a,
                            count_increase=delta,
                        )
                    )
    return (
        dict(
            channel_windows=len(groups),
            raw_rows=len(raw),
            synthetic_rows=len(syn),
            baseline_window_matches=len(base),
            observed_count_increases=len(increases),
        ),
        increases,
    )
