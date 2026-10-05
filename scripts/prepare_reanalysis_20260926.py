"""Freeze an identity-aware run without changing source or historical outputs."""

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.reanalysis import unify_people, vas_support


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def dump(p, obj):
    Path(p).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )


def main():
    import numpy as np

    cfg = json.loads(
        (ROOT / "config/reanalysis_20260926_v1.json").read_text(encoding="utf-8")
    )
    admission_ptr_path = ROOT / "config/source_mapping_admission_active.json"
    admission_ptr = json.loads(admission_ptr_path.read_text(encoding="utf-8"))
    admission_path = Path(admission_ptr["config"])
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    acq_path = ROOT / "config/acq_source_selection_active.json"
    acq_pointer = (
        json.loads(acq_path.read_text(encoding="utf-8")) if acq_path.exists() else None
    )
    acq_inputs = []
    if acq_pointer:
        acq_registry = Path(acq_pointer["registry"])
        if sha(acq_registry) != acq_pointer["registry_sha256"]:
            raise ValueError("ACQ registry changed")
        cfg["acq_source_selection"] = acq_pointer
        acq_inputs = [acq_path, acq_registry, acq_registry.parent / "manifest.json"]
    adjudication_path = ROOT / "config/covariate_adjudication_active.json"
    adjudication = (
        json.loads(adjudication_path.read_text(encoding="utf-8"))
        if adjudication_path.exists()
        else {"version": "legacy_missing_conflicts", "policy": "missing"}
    )
    loc = json.loads((ROOT / "config/data_locations.json").read_text(encoding="utf-8"))
    ptr = json.loads(
        (ROOT / "config/fnirs_source_adjudication_active.json").read_text(
            encoding="utf-8"
        )
    )
    cfg["fnirs_source_adjudication"] = ptr
    registry = Path(ptr["registry"])
    if sha(registry) != ptr["registry_sha256"]:
        raise ValueError("Registry changed")
    decisions = json.loads(registry.read_text(encoding="utf-8"))
    aliases = decisions["confirmed_subject_aliases"]
    rows, conflicts, people = unify_people(
        read(loc["vas"]),
        aliases,
        conflict_policy=adjudication["policy"],
    )
    out = (
        ROOT
        / "08_outputs"
        / (
            "reanalysis_20260926_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "people_private.csv")],
        check=True,
        cwd=ROOT,
    )
    out.mkdir()
    write(out / "BaselineData_person_private.csv", rows)
    write(out / "people_private.csv", people)
    write(out / "covariate_conflicts_private.csv", conflicts)
    cfg["covariate_adjudication"] = adjudication
    cfg["source_mapping_admission"] = admission_ptr
    cfg["source_mapping_admission_config"] = admission
    dump(out / "frozen_config.json", cfg)
    dump(out / "aliases_private.json", aliases)
    windows = [
        dict(person_id=r["ID"], **s)
        for r in rows
        for b in range(4)
        for spec in ["A", "B"]
        if (s := vas_support(r, b, spec))
    ]
    write(out / "vas_window_contract_private.csv", windows)
    rng = np.random.default_rng(cfg["seed"])
    ids = sorted(r["ID"] for r in rows)
    rng.shuffle(ids)
    dev = cfg["reference"]["development_people"]
    nval = int((len(ids) - dev) * cfg["reference"]["validation_fraction_remaining"])
    split = []
    for i, sid in enumerate(ids):
        pool = (
            "development"
            if i < dev
            else "sealed_validation"
            if i < dev + nval
            else "application"
        )
        split.append(
            dict(
                person_id=sid,
                pool=pool,
                representative_block=int(rng.integers(4)),
                selection_probability_development=dev / len(ids),
                annotation_status="not_annotated",
            )
        )
    write(out / "reference_split_private.csv", split)
    cfgvas = json.loads(
        (ROOT / "config/provisional_vas_v3.json").read_text(encoding="utf-8")
    )
    cfgvas["execution_version"] = "person_vas_20260926_v1"
    cfgvas["gamm"]["bootstrap_subjects"] = cfg["vas"]["gamm_bootstrap"]
    cfgvas["gamm"]["bootstrap_role"] = (
        "subject stability; derivative bands not scientifically accepted"
    )
    cfgvas["execution"]["timeout_seconds"] = cfg["timeout_seconds_per_module"]
    cfgvas["estimand"]["target_population"] = (
        "unique persons after confirmed alias consolidation"
    )
    dump(out / "vas_config.json", cfgvas)
    for name in ["sparse_fpca", "remaining_analysis"]:
        c = json.loads((ROOT / f"config/{name}_v1.json").read_text(encoding="utf-8"))
        c["input_run"] = str(out / "vas_models")
        c["bootstrap"]["unit"] = "unique person"
        dump(out / f"{name}_config.json", c)
    snapshot = out / "code_snapshot"
    snapshot.mkdir()
    files = []
    for folder in ["src", "scripts", "R", "config", "tests"]:
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.suffix in [".py", ".R", ".json", ".csv"]
            and not p.name.startswith("._")
            and "__pycache__" not in p.parts
        )
    files += [
        ROOT / p
        for p in [
            "README.md",
            "AGENTS.md",
            "docs/analysis_plan.md",
            "docs/decision_log.md",
            "docs/analysis_plan_20260926_algorithmic_qc_v1.md",
            "docs/analysis_plan_20260926_algorithmic_qc_v2.md",
            "renv.lock",
            "pyproject.toml",
            ".Rprofile",
        ]
    ]
    for p in files:
        target = snapshot / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    (out / "environment.txt").write_text(
        platform.platform()
        + "\n"
        + sys.version
        + "\n"
        + "\n".join(
            sorted(
                f"{d.metadata['Name']}=={d.version}"
                for d in importlib.metadata.distributions()
            )
        ),
        encoding="utf-8",
    )
    (out / "git_diff.patch").write_bytes(
        subprocess.check_output(git + ["diff", "--binary"], cwd=ROOT)
    )
    state = dict(
        status="prepared",
        created_utc=datetime.now(timezone.utc).isoformat(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        git_status=subprocess.check_output(
            git + ["status", "--porcelain"], cwd=ROOT, text=True
        ),
        input_sha256={
            str(p): sha(p)
            for p in [
                Path(loc["vas"]),
                registry,
                adjudication_path,
                admission_ptr_path,
                admission_path,
                ROOT / "config/data_locations.json",
                Path(loc["mapping"]),
                Path(loc["path_index"]),
            ]
            + acq_inputs
        },
        code_snapshot_sha256={
            str(p.relative_to(snapshot)): sha(p)
            for p in snapshot.rglob("*")
            if p.is_file()
        },
        summary=dict(
            source_rows=len(people),
            unique_persons=len(rows),
            conflicting_fields=len({r["field"] for r in conflicts}),
            support_A=sum(r["support_spec"] == "A" for r in windows),
            support_B=sum(r["support_spec"] == "B" for r in windows),
        ),
    )
    dump(out / "run_manifest.json", state)
    print(out, flush=True)
    print(json.dumps(state["summary"]), flush=True)


if __name__ == "__main__":
    main()
