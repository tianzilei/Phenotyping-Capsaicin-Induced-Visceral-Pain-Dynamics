"""Run state counts only with a separately frozen, justified threshold configuration."""

import argparse
import csv
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from run_fpca_followup import ROOT, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.states import describe_states


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cp = Path(args.config).resolve()
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    if (
        cfg.get("status") != "frozen_exploratory"
        or not cfg.get("version")
        or not cfg.get("threshold_rationale")
    ):
        raise ValueError(
            "A versioned frozen configuration and threshold rationale are required"
        )
    source = ROOT / cfg["input_long"]
    expected = cfg.get("input_sha256")
    if not expected or sha(source) != expected:
        raise ValueError("Frozen input hash required")
    with source.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["time_min"] = int(r["time_min"])
        r["vas"] = float(r["vas"]) if r["vas"] else None
    # Validation occurs before creating any output; E/T never become pain states.
    result = describe_states(rows, cfg.get("thresholds"), cfg["threshold_rationale"])
    out = (
        ROOT
        / "08_outputs"
        / (
            "state_descriptions_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "spells_private.csv")],
        check=True,
        cwd=ROOT,
    )
    for key, values in result.items():
        if values:
            with (out / (key + "_private.csv")).open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.DictWriter(f, fieldnames=list(values[0]))
                w.writeheader()
                w.writerows(values)
    manifest = dict(
        status="descriptive_only_no_transition_regression",
        config=cfg,
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={
            str(source): sha(source),
            str(cp): sha(cp),
            str(Path(__file__).resolve()): sha(Path(__file__)),
            str(ROOT / "src/capsaicin/states.py"): sha(
                ROOT / "src/capsaicin/states.py"
            ),
        },
        outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
    )
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)


if __name__ == "__main__":
    main()
