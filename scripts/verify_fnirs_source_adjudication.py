"""Verify all six user decisions at the actual extraction selection boundary."""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import resolve_input
from capsaicin.fnirs_source_selection import adjudicate_mapping, choose_latest, sha


def main():
    pointer = ROOT / "config/fnirs_source_adjudication_active.json"
    cfg = json.loads(pointer.read_text(encoding="utf-8"))
    rp = Path(cfg["registry"])
    registry = json.loads(rp.read_text(encoding="utf-8"))
    p = resolve_input(
        ROOT
        / "02_quality_control/time_enc_20260916T123124Z_d4ff4af0/accepted_subject_to_files_private.csv"
    )
    with p.open(encoding="utf-8-sig") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r.get("stage") == "E" and r.get("extension", "").lower() == ".txt"
        ]
    result, audit, evidence = adjudicate_mapping(rows)
    decisions = registry["decisions"]
    for sid, d in decisions.items():
        assert choose_latest(d["candidates"]) == d["selected"]
        selected = [r for r in result if r["current_subject_id"] == sid]
        if d["analysis_status"] == "accepted_unique_owner":
            assert (
                len(selected) == 1
                and str(resolve_input(selected[0]["path"]))
                == d["selected"]["local_path"]
            )
        else:
            assert not selected
    assert len({d["selected"]["sha256"] for d in decisions.values()}) == 5
    assert all(r in result for r in rows if r["current_subject_id"] not in decisions)
    summary = dict(
        status="passed",
        input_E_TXT_links=len(rows),
        remaining_links=len(result),
        decided_labels=len(decisions),
        accepted_unique_participants=5,
        rejected_old_links=sum(
            r["reason"] == "older_file_rejected_by_investigator" for r in audit
        ),
        duplicate_alias_latest_links_excluded=sum(
            r["reason"] == "alias_of_same_participant_do_not_count_twice" for r in audit
        ),
        unaffected_links_preserved=True,
        registry_sha256=sha(rp),
        code_sha256=sha(Path(__file__)),
        inference_rerun=False,
    )
    target = rp.parent / "verification.json"
    if target.exists():
        raise FileExistsError("Verification already exists")
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
