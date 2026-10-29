"""Explicit logical random streams using canonical input bytes as entropy."""

import json
import numpy as np


def sequence(*parts):
    raw = json.dumps(
        parts, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    padded = raw + bytes((-len(raw)) % 4)
    entropy = [len(raw), *np.frombuffer(padded, dtype="<u4").tolist()]
    return np.random.SeedSequence(entropy)


def generator(*parts):
    return np.random.default_rng(sequence(*parts))


def integer_seed(*parts):
    return int(sequence(*parts).generate_state(1, dtype=np.uint32)[0])
