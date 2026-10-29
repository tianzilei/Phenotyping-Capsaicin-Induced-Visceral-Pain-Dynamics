"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from datetime import datetime, timedelta
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def filename_time(name):
    m = re.search("_(20\\d{6})_(\\d{6})(?:\\D|$)", name)
    if not m:
        return None
    try:
        return datetime.strptime("".join(m.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def log_interval(rows):
    starts = {r.get("expStart", "") for r in rows} - {""}
    if len(starts) != 1:
        return None
    raw = next(iter(starts))
    try:
        start = datetime.strptime(raw.split(" +")[0], "%Y-%m-%d %Hh%M.%S.%f")
    except ValueError:
        return None
    elapsed = []
    for row in rows:
        for key, v in row.items():
            if key.endswith((".started", ".stopped")):
                try:
                    value = float(v)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(value) and value >= 0:
                    elapsed.append(value)
    return (start, start + timedelta(seconds=max(elapsed))) if elapsed else None


def interval_gap(time, interval):
    if interval[0] <= time <= interval[1]:
        return 0.0
    return min(
        abs((time - interval[0]).total_seconds()),
        abs((time - interval[1]).total_seconds()),
    )


def supported_time_match(
    chat_code, rest_anchor, own_intervals, competing_intervals, time, padding
):
    return bool(
        chat_code
        and rest_anchor
        and own_intervals
        and any((interval_gap(time, x) <= padding for x in own_intervals))
        and (not any((interval_gap(time, x) <= padding for x in competing_intervals)))
    )
