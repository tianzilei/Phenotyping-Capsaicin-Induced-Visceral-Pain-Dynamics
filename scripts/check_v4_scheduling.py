"""Synthetic equivalence check: serial vs per-replicate scheduling, same seeds."""

import csv
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "02_quality_control" / f"v4_scheduling_check_{uuid.uuid4().hex[:8]}"
out.mkdir(parents=True, exist_ok=False)
base = ["C:/Program Files/R/R-4.6.1/bin/Rscript.exe"]
for name, script, rep in [
    ("serial", "run_derivative_bootstrap_v4.R", None),
    ("one", "derivative_v4_one_replicate.R", "1"),
    ("two", "derivative_v4_one_replicate.R", "2"),
]:
    cell = out / name
    cell.mkdir()
    cmd = base + [
        str(root / "scripts" / script),
        str(root),
        str(cell),
        "curved_dropout",
        "40",
        "2",
        "9",
        "818112",
        "100",
    ]
    if rep:
        cmd.append(rep)
    p = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (cell / "execution.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode:
        raise RuntimeError("Scheduling check execution failed")
for name in ("replicates.csv", "pointwise.csv", "bootstrap_status.csv"):

    def rows(folder):
        with (out / folder / name).open(encoding="utf-8", newline="") as h:
            return list(csv.DictReader(h))

    if rows("serial") != rows("one") + rows("two"):
        raise AssertionError(f"Scheduling changed numerical results: {name}")
sources = [
    root / "scripts/derivative_v4_one_replicate.R",
    root / "scripts/run_derivative_bootstrap_v4.R",
    Path(__file__).resolve(),
]
manifest = dict(
    status="passed_exact_table_equality",
    synthetic=True,
    bootstrap=9,
    note="Small engineering test; no coverage claim; numerical scenario is not development/validation data",
    sources_sha256={
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    },
    outputs_sha256={
        str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file()
    },
)
(out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(out)
