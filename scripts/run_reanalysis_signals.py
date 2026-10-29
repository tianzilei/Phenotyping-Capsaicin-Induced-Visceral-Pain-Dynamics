"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from run_fnirs_variable_length_roi import parse_channel_groups

ROOT = Path(__file__).resolve().parents[1]


def load_hb(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        header = [f.readline().rstrip("\r\n") for _ in range(35)]
        groups = parse_channel_groups(header[33].split("\t"))
        matrix = np.genfromtxt(f, delimiter="\t", invalid_raise=True)
    t = matrix[:, 0]
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("invalid_Hb_time")
    x = np.stack([matrix[:, j : j + 3] for ch, j in groups], axis=1)
    return (t, x, groups, header)


def scenarios(cfg):
    return [(s, 0) for s in cfg["windows"]["offset_seconds"]] + [
        (0, d) for d in cfg["windows"]["drift_ppm"] if d
    ]
