"""Copy a pinned source plan into local BIDS storage and verify every byte.

No identity inference, signal conversion, or source mutation is performed.
Private manifests and source paths stay inside the ignored dataset.
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import path_key


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def js(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(p)


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows, delimiter=","):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


def subject_label(s):
    if not s.startswith("SUBJECT") or not s[7:].isdigit():
        raise ValueError("Unexpected research ID")
    return "sub-" + s[7:]


def behavior_rows(row):
    result = []
    for minute in range(1, 21):
        original = row.get(f"VAS_{minute}min", "")
        token = original.strip()
        if token in ("E", "T"):
            rating = "n/a"
            status = token
        elif token in ("", "NA", "N/A", "NaN"):
            rating = "n/a"
            status = "missing"
        else:
            value = float(token)
            if not 0 <= value <= 10:
                raise ValueError("VAS out of range")
            rating = token
            status = "observed"
        result.append(
            dict(
                time_min=minute,
                vas=rating,
                original_token=original or "n/a",
                observation_status=status,
            )
        )
    return result


def copy_verified(source, target):
    source = Path(source)
    target = Path(target)
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        a = sha(source)
        b = sha(target)
        if a != b:
            raise ValueError(f"Existing destination differs: {target}")
    else:
        h = hashlib.sha256()
        pending = target.with_name(target.name + ".partial")
        # Own partial file can be replaced on resume; completed files never overwritten.
        with source.open("rb") as f, pending.open("wb") as g:
            while chunk := f.read(8 * 1024 * 1024):
                h.update(chunk)
                g.write(chunk)
        a = h.hexdigest()
        b = sha(pending)
        if a != b:
            raise ValueError("Destination hash mismatch")
        pending.rename(target)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during copy")
    return a, before.st_size


def plan(cfg, dest):
    sources = {}
    owners = defaultdict(set)

    def add(p, reason):
        p = Path(p)
        if p.name.startswith("._") or not p.is_file():
            if not p.name.startswith("._"):
                raise FileNotFoundError(p)
            return
        key = path_key(p.resolve())
        if key not in sources:
            sources[key] = dict(
                source=str(p.resolve()), bytes=p.stat().st_size, reasons=[]
            )
        if reason not in sources[key]["reasons"]:
            sources[key]["reasons"].append(reason)

    links = read(ROOT / cfg["mapping"])
    for r in links:
        p = Path(r["path"])
        add(p, "accepted_mapping")
        owners[path_key(p)].add(r["current_subject_id"])
    for rel in cfg["path_manifests"]:
        add(ROOT / rel, "source_manifest")
        for r in read(ROOT / rel):
            add(r["path"], "signal_or_timing_manifest")
    for root in cfg["additional_trees"]:
        for p in Path(root).rglob("*"):
            if (
                p.is_file()
                and p.suffix.lower() in cfg["additional_extensions"]
                and not p.name.startswith("._")
            ):
                add(p, "mapping_completion_and_timing_archive")
    for p in (ROOT / cfg["protocol_tree"]).rglob("*"):
        if p.is_file() and not p.name.startswith("._"):
            add(p, "protocol")
    add(ROOT / cfg["mapping"], "original_mapping")
    add(ROOT / cfg["vas"], "current_vas")
    # Capture data/config provenance inputs already on D:, not derived full waveforms.
    for p in (ROOT / "01_data/processed/e_coded_20260916T144438Z_5c144eb7").iterdir():
        if p.is_file() and not p.name.startswith("._"):
            add(p, "vas_provenance")
    extra = (
        ROOT
        / "02_quality_control/external_source_audit_20260925T080037Z_6f54cde3/external_file_inventory.csv"
    )
    for r in read(extra):
        p = Path(r["path"])
        if p.is_file():
            add(p, "clinical_source_or_legacy_mapping")
    # Preserve historical raw hash evidence and associated files needed by current runners.
    for rel in [
        "02_quality_control/waveform_provenance_20260918T100523Z_0c21f681",
        "02_quality_control/event_clocks_20260918T104330Z_f5feb319",
    ]:
        for p in (ROOT / rel).iterdir():
            if p.is_file() and not p.name.startswith("._"):
                add(p, "prior_time_and_hash_evidence")
    for item in sources.values():
        p = Path(item["source"])
        own = sorted(owners[path_key(p)])
        if len(own) == 1:
            # Session labels are archive group identifiers, not verified visits.
            branch = Path("sourcedata") / subject_label(own[0]) / "records"
        else:
            branch = Path("sourcedata") / ("ambiguous" if own else "unassigned")
        ident = hashlib.sha256(path_key(p.parent).encode()).hexdigest()[:16]
        item.update(
            destination=(branch / ident / p.name).as_posix(),
            candidate_subject_ids=own,
            identity_status="candidate_mapping_only"
            if len(own) == 1
            else "unassigned_or_ambiguous",
        )
    items = sorted(sources.values(), key=lambda x: path_key(x["source"]))
    assert len({x["destination"].casefold() for x in items}) == len(items)
    total = sum(x["bytes"] for x in items)
    if shutil.disk_usage(ROOT).free < total * 1.1:
        raise OSError("Insufficient free space with 10% margin")
    js(
        dest / "sourcedata/migration/plan_private.json",
        dict(config=cfg, files=items, total_bytes=total),
    )
    print(
        json.dumps(
            dict(planned_files=len(items), bytes=total, gib=round(total / 2**30, 2)),
            ensure_ascii=True,
        ),
        flush=True,
    )


def finish(cfg, dest, items, ledger):
    index = {path_key(r["source"]): str(dest / r["destination"]) for r in ledger}
    js(dest / "sourcedata/migration/path_index_private.json", index)
    vas = read(ROOT / cfg["vas"])
    ids = [subject_label(r["ID"]) for r in vas]
    assert len(set(ids)) == len(ids)
    js(
        dest / "dataset_description.json",
        dict(
            Name="Capsaicin challenge observed pain and multimodal source archive",
            BIDSVersion=cfg["bids_version"],
            DatasetType="raw",
            Authors=["Capsaicin study team"],
        ),
    )
    write(dest / "participants.tsv", [dict(participant_id=s) for s in ids], "\t")
    js(
        dest / "participants.json",
        dict(
            participant_id=dict(
                Description="Pseudonymous current research identifier; physical source-record linkage remains separately audited."
            )
        ),
    )
    schema = dict(
        TaskName="capsaicin",
        TaskDescription="Observed VAS at scheduled minutes; recording start defines dose time by investigator statement.",
        time_min=dict(
            Description="Scheduled VAS minute relative to recording start; not verified exact event timestamp.",
            Units="min",
        ),
        vas=dict(
            Description="Observed VAS on 0-10 scale. E/T and missing cells remain n/a.",
            Units="arbitrary",
        ),
        original_token=dict(
            Description="Original processed analysis-table token; E/T retained. Empty source cells are n/a."
        ),
        observation_status=dict(
            Description="Observation or termination coding; E/T not counted as serious adverse events.",
            Levels=dict(
                observed="Numeric VAS",
                E="Pain-free stopping rule code",
                T="Termination code",
                missing="Missing cell",
            ),
        ),
    )
    js(dest / "task-capsaicin_beh.json", schema)
    for row, sid in zip(vas, ids):
        write(
            dest / sid / "beh" / f"{sid}_task-capsaicin_beh.tsv",
            behavior_rows(row),
            "\t",
        )
    # Relocated mapping preserves the original logical key for historical joins/hashes.
    mapping = read(ROOT / cfg["mapping"])
    for r in mapping:
        r["source_path"] = r["path"]
        r["local_path"] = index[path_key(r["path"])]
    write(
        dest / "sourcedata/migration/subject_to_files_with_local_paths_private.csv",
        mapping,
    )
    localmap = [dict(r, path=r["local_path"]) for r in mapping]
    write(dest / "sourcedata/migration/subject_to_files_D_private.csv", localmap)
    config_overrides = {}

    def relocate(value):
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        if isinstance(value, str):
            p = Path(value)
            absolute = p if p.is_absolute() else ROOT / p
            return index.get(path_key(value), index.get(path_key(absolute), value))
        return value

    for p in (ROOT / "config").glob("*.json"):
        if p.name in ["data_locations.json", "local.json"]:
            continue
        original = json.loads(p.read_text(encoding="utf-8-sig"))
        moved = relocate(original)
        if moved != original:
            moved["_data_relocation"] = dict(
                original_config=str(p),
                original_sha256=sha(p),
                migration_version=cfg["version"],
            )
            target = dest / "code/config" / p.name
            js(target, moved)
            config_overrides[path_key(p)] = str(target)
    text = """# Local capsaicin BIDS archive

The root contains 216 pseudonymous behavioral records in BIDS layout. Observed VAS values, actual scheduled minutes, E/T and missingness are preserved. No baseline zero or post-stop value was added.

Original signals, protocol documents, TTL/PsychoPy logs, original clinical tables and linkage evidence are byte-preserved under sourcedata. Candidate single-owner files use sourcedata/sub-*/records/<source-folder-id>; ambiguous and unassigned files remain separate. This placement does not adjudicate participant identity or repeat visits. Original filenames/content can contain identifiers: this dataset is private and is not an anonymized public release.

ACQ/OMM and vendor Hb TXT/SNIRF exports are source archives, not newly validated BIDS raw NIRS recordings. No processed Hb values were re-labelled optical intensity; missing units, acquisition identity, and 1000/2000 Hz provenance remain unresolved. Formal physiological conversion is pending these metadata checks. BIDS validation of the behavioral root does not certify sourcedata or scientific readiness.

All copied files have SHA256 verification in sourcedata/migration/copy_ledger_private.csv. Both original source paths and local paths are retained. No source file was deleted. The files copied from additional fNIRS/log directories are candidates for mapping completion, not extra enrolled participants.
"""
    (dest / "README").write_text(text, encoding="utf-8")
    (dest / ".bidsignore").write_text("sourcedata/\ncode/\n", encoding="utf-8")
    settings = dict(
        version="data_locations_v1",
        active=True,
        dataset_root=str(dest),
        path_index=str(dest / "sourcedata/migration/path_index_private.json"),
        mapping=str(dest / "sourcedata/migration/subject_to_files_D_private.csv"),
        logical_mapping=str(
            dest / "sourcedata/migration/subject_to_files_with_local_paths_private.csv"
        ),
        vas=index[path_key(ROOT / cfg["vas"])],
        config_overrides=config_overrides,
        external_fallback=False,
    )
    js(ROOT / "config/data_locations.json", settings)
    js(
        ROOT / "config/local.json",
        dict(
            sources=dict(
                baseline_csv=settings["vas"],
                subject_manifest=settings["mapping"],
                bids_directory=str(dest),
                signal_events=str(
                    dest / "sourcedata/migration/path_index_private.json"
                ),
            ),
            note="D: migration active; source archive includes private identities. See data_locations.json.",
        ),
    )
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    cp = ROOT / "config/data_migration_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    dest = (ROOT / cfg["destination"]).resolve()
    if not dest.is_relative_to((ROOT / "01_data").resolve()):
        raise ValueError("Destination outside private workspace data")
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(dest / "participants.tsv")],
        cwd=ROOT,
        check=True,
    )
    if args.plan:
        if (dest / "sourcedata/migration/plan_private.json").exists():
            raise FileExistsError("Plan already exists")
        plan(cfg, dest)
        return
    pp = dest / "sourcedata/migration/plan_private.json"
    data = json.loads(pp.read_text(encoding="utf-8"))
    if data["config"] != cfg:
        raise ValueError("Migration config changed after planning")
    items = data["files"]
    ledger = []
    start = time.monotonic()
    done = 0
    lp = dest / "sourcedata/migration/copy_ledger_private.csv"
    state = dict(
        status="copying",
        created_utc=datetime.now(timezone.utc).isoformat(),
        config_sha256=sha(cp),
        plan_sha256=sha(pp),
        code_sha256=sha(Path(__file__)),
        python=platform.python_version(),
        revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    )
    for n, item in enumerate(items, 1):
        digest, size = copy_verified(item["source"], dest / item["destination"])
        ledger.append(
            dict(
                source=item["source"],
                destination=item["destination"],
                bytes=size,
                sha256=digest,
                verified=True,
            )
        )
        done += size
        if n % 25 == 0 or n == len(items):
            write(lp, ledger)
            state.update(
                files_copied=n,
                files_planned=len(items),
                bytes_copied=done,
                elapsed_seconds=round(time.monotonic() - start, 1),
            )
            js(dest / "sourcedata/migration/run_manifest.json", state)
            print(
                json.dumps(
                    {
                        k: state[k]
                        for k in [
                            "files_copied",
                            "files_planned",
                            "bytes_copied",
                            "elapsed_seconds",
                        ]
                    }
                ),
                flush=True,
            )
    finish(cfg, dest, items, ledger)
    state.update(
        status="copied_verified_local_paths_activated",
        copy_ledger_sha256=sha(lp),
        finished_utc=datetime.now(timezone.utc).isoformat(),
        bids_validation="pending",
    )
    js(dest / "sourcedata/migration/run_manifest.json", state)
    print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
