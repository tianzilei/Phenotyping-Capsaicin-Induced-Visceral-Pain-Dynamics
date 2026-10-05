"""Verify migration using D: only; never reopen the original F: source tree."""

import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import DataLocator, path_key
from migrate_data_to_bids import behavior_rows, subject_label, sha


def read(path, delimiter=","):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


def main():
    def deny_external_reads(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            value = args[0].decode() if isinstance(args[0], bytes) else args[0]
            if path_key(value).startswith("f:/"):
                raise RuntimeError("Verification must not access F:")

    sys.addaudithook(deny_external_reads)
    loc = DataLocator()
    assert loc.settings.get("active")
    dest = Path(loc.settings["dataset_root"])
    archive = dest / "sourcedata/migration"
    manifest = json.loads((archive / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "copied_verified_local_paths_activated"
    plan = json.loads((archive / "plan_private.json").read_text(encoding="utf-8"))
    ledger = read(archive / "copy_ledger_private.csv")
    assert len(ledger) == len(plan["files"]) == manifest["files_planned"]
    assert (
        sum(int(r["bytes"]) for r in ledger)
        == plan["total_bytes"]
        == manifest["bytes_copied"]
    )
    assert sha(archive / "copy_ledger_private.csv") == manifest["copy_ledger_sha256"]
    assert sha(archive / "plan_private.json") == manifest["plan_sha256"]
    assert sha(ROOT / "config/data_migration_v1.json") == manifest["config_sha256"]
    assert sha(ROOT / "scripts/migrate_data_to_bids.py") == manifest["code_sha256"]
    by_source = {path_key(r["source"]): r for r in ledger}
    assert len(by_source) == len(ledger)
    for item in plan["files"]:
        row = by_source[path_key(item["source"])]
        assert row["destination"] == item["destination"]
        target = loc.resolve(item["source"])
        assert target == dest / row["destination"]
        assert target.is_relative_to(dest) and target.drive.casefold() == "d:"
        assert target.stat().st_size == int(row["bytes"]) == item["bytes"]
        assert row["verified"] == "True" and len(row["sha256"]) == 64
    assert not list(dest.rglob("*.partial"))
    auxiliary = archive / "auxiliary_provenance_v1"
    extra = (
        json.loads((auxiliary / "copy_ledger_private.json").read_text(encoding="utf-8"))
        if auxiliary.exists()
        else []
    )
    for row in extra:
        target = loc.resolve(row["source"])
        assert str(target) == row["destination"] and target.is_relative_to(dest)
        assert target.stat().st_size == row["bytes"] and sha(target) == row["sha256"]

    original_mapping = read(loc.resolve(ROOT / plan["config"]["mapping"]))
    local_mapping = read(loc.settings["mapping"])
    assert len(original_mapping) == len(local_mapping)
    for old, new in zip(original_mapping, local_mapping):
        assert new["source_path"] == old["path"]
        assert new["path"] == str(loc.resolve(old["path"])) == new["local_path"]
        assert all(new[k] == v for k, v in old.items() if k != "path")

    vas_path = loc.resolve(ROOT / plan["config"]["vas"])
    vas = read(vas_path)
    participants = read(dest / "participants.tsv", "\t")
    assert [r["participant_id"] for r in participants] == [
        subject_label(r["ID"]) for r in vas
    ]
    status = Counter()
    zeroes = 0
    for source in vas:
        sid = subject_label(source["ID"])
        rows = read(dest / sid / "beh" / f"{sid}_task-capsaicin_beh.tsv", "\t")
        expected = [
            {k: str(v) for k, v in row.items()} for row in behavior_rows(source)
        ]
        assert rows == expected
        status.update(r["observation_status"] for r in rows)
        zeroes += sum(
            r["observation_status"] == "observed" and float(r["vas"]) == 0 for r in rows
        )
    assert len(list(dest.glob("sub-*/beh/*_beh.tsv"))) == len(vas)

    def relocate(value):
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        if isinstance(value, str):
            p = Path(value)
            absolute = p if p.is_absolute() else ROOT / p
            row = by_source.get(path_key(value)) or by_source.get(path_key(absolute))
            return str(dest / row["destination"]) if row else value
        return value

    for old, new in loc.settings["config_overrides"].items():
        before = json.loads(Path(old).read_text(encoding="utf-8-sig"))
        after = json.loads(Path(new).read_text(encoding="utf-8"))
        info = after.pop("_data_relocation")
        assert info["original_sha256"] == sha(old)
        assert after == relocate(before), "Scientific config changed during relocation"

    # Historical raw hashes retain original logical source keys.
    previous = json.loads(
        loc.resolve(
            ROOT
            / "02_quality_control/waveform_provenance_20260918T100523Z_0c21f681/run_manifest.json"
        ).read_text(encoding="utf-8")
    )
    historical = previous["signals_sha256"]
    for source, digest in historical.items():
        assert by_source[path_key(source)]["sha256"] == digest

    # Smoke-read real headers locally, with no filtering, conversion or inference.
    import bioread
    import h5py

    acq = next(
        loc.resolve(r["source"])
        for r in ledger
        if Path(r["source"]).suffix.lower() == ".acq"
    )
    with acq.open("rb") as handle:
        reader = bioread.reader.Reader(handle)
        reader._read_headers()
        channels = len(reader.datafile.channels)
        assert channels > 0
    snirf = next(
        loc.resolve(r["source"])
        for r in ledger
        if Path(r["source"]).suffix.lower() == ".snirf"
    )
    with h5py.File(snirf, "r") as handle:
        assert "nirs" in handle
    txt = next(
        loc.resolve(r["source"])
        for r in ledger
        if Path(r["source"]).suffix.lower() == ".txt"
    )
    with txt.open("rb") as handle:
        assert handle.read(1024)
    psycho = read(loc.resolve(ROOT / plan["config"]["path_manifests"][1]))
    assert read(loc.resolve(psycho[0]["path"]))

    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(dest / "participants.tsv")],
        cwd=ROOT,
        check=True,
    )
    assert not subprocess.check_output(
        git + ["ls-files", "--", str(dest)], cwd=ROOT, text=True
    ).strip()
    evidence = [
        Path(__file__),
        ROOT / "scripts/migrate_data_to_bids.py",
        ROOT / "src/capsaicin/data_locations.py",
        ROOT / "config/data_locations.json",
        archive / "path_index_private.json",
        archive / "copy_ledger_private.csv",
        archive / "plan_private.json",
    ]
    report = dict(
        status="passed",
        created_utc=datetime.now(timezone.utc).isoformat(),
        files=len(ledger) + len(extra),
        bytes=plan["total_bytes"] + sum(r["bytes"] for r in extra),
        main_plan_files=len(ledger),
        auxiliary_files=len(extra),
        mapping_rows=len(local_mapping),
        participants=len(vas),
        behavior_rows=sum(status.values()),
        behavior_status_counts=dict(status),
        numeric_zeroes_preserved=zeroes,
        historical_acq_hashes_matched=len(historical),
        config_overlays_checked=len(loc.settings["config_overrides"]),
        acq_smoke_header_channels=channels,
        snirf_txt_psychopy_smoke_read=True,
        data_inputs_opened_on_D_with_F_reads_blocked=True,
        verification_scope="Every copy was source-hashed and destination-rehashed by migration; this audit checks ledger, all sizes, mappings, behavior, historical hashes, configs and representative local headers. Physiological BIDS conversion is not claimed.",
        python=platform.python_version(),
        software={p: importlib.metadata.version(p) for p in ["bioread", "h5py"]},
        revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        evidence_sha256={str(p): sha(p) for p in evidence},
    )
    output = archive / (
        "verification_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
        + ".json"
    )
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "evidence_sha256"},
            ensure_ascii=True,
            indent=2,
        )
    )
    print(output)


if __name__ == "__main__":
    main()
