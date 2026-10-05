"""Create a new byte-level baseline; retain historical claims and differences."""

import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import DataLocator, path_key


def sha(p):
    before = p.stat()
    with p.open("rb") as f:
        value = hashlib.file_digest(f, "sha256").hexdigest()
    after = p.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("File changed during hashing")
    return value


def write(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def table(p, rows):
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=list(dict.fromkeys(k for r in rows for k in r))
        )
        w.writeheader()
        w.writerows(rows)


def main():
    cfg = json.loads((ROOT / "config/hash_baseline_v1.json").read_text())
    out = (
        ROOT
        / "02_quality_control"
        / (
            "hash_baseline_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    loc = DataLocator()
    paths = set()
    for root in cfg["roots"]:
        for p in (ROOT / root).rglob("*"):
            if (
                not p.is_file()
                or p.is_relative_to(out)
                or p.name.startswith("._")
                or p.name.endswith((".pyc", ".partial"))
            ):
                continue
            if any(
                n in cfg["exclude_directory_names"] for n in p.relative_to(ROOT).parts
            ):
                continue
            if p.name == "hash_baseline_active.json":
                continue
            paths.add(p.resolve())
    paths.update([ROOT / "README.md", ROOT / ".gitignore"])
    entries = {}
    by_hash = defaultdict(list)
    size = 0
    for n, p in enumerate(sorted(paths), 1):
        h = sha(p)
        s = p.stat().st_size
        entries[path_key(p)] = dict(path=str(p), sha256=h, bytes=s)
        by_hash[h].append(str(p))
        size += s
        if n % 500 == 0:
            print(json.dumps(dict(hashed=n, total=len(paths), bytes=size)), flush=True)
    write(out / "files_private.json", entries)

    # Exact aliases include verified F: relocation and known prior workspace roots.
    def target(name, mp, field):
        if field == "outputs_sha256" or field == "files":
            return mp.parent / name
        s = str(name).replace("\\", "/")
        for prefix in [
            "/workspace/capsaicin_analysis_2026-09-13/",
            "/workspace/",
            "/app/",
        ]:
            if s.startswith(prefix):
                return ROOT / s[len(prefix) :]
        if "/capsaicin_analysis_2026-09-13/" in s and not s.lower().startswith("d:"):
            return ROOT / s.split("/capsaicin_analysis_2026-09-13/", 1)[1]
        try:
            return loc.resolve(name)
        except FileNotFoundError:
            return Path(name)

    refs = []
    scalar = []
    manifests = [
        p
        for p in paths
        if p.suffix == ".json"
        and "manifest" in p.name
        and "bids_capsaicin" not in str(p)
    ]
    # Documentation source/output paths are relative to different explicit roots.
    for mp in sorted(manifests):
        try:
            m = json.loads(mp.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError):
            continue
        if not isinstance(m, dict):
            continue
        mh = entries[path_key(mp)]["sha256"]
        for field, values in m.items():
            if not ("sha256" in field or field in ("source_hashes", "files")):
                continue
            if isinstance(values, str) and re.fullmatch("[0-9a-f]{64}", values):
                scalar.append(
                    dict(
                        manifest=str(mp),
                        field=field,
                        expected=values,
                        matching_current_files=by_hash.get(values, []),
                    )
                )
            if not isinstance(values, dict):
                continue
            for name, expected in values.items():
                if not isinstance(expected, str) or not re.fullmatch(
                    "[0-9a-f]{64}", expected
                ):
                    continue
                if mp.name == "documentation_manifest.json":
                    p = (
                        ROOT / "docs/unified_study_20260925"
                        if field == "outputs_sha256"
                        else ROOT
                    ) / name
                else:
                    p = target(name, mp, field)
                entry = entries.get(path_key(p))
                actual = entry["sha256"] if entry else None
                candidates = by_hash.get(expected, [])
                if actual == expected:
                    status = "matched"
                elif candidates:
                    status = "historical_bytes_available_at_other_path"
                elif (
                    actual
                    and field not in ("outputs_sha256", "files")
                    and p.suffix.lower() in (".py", ".r", ".md")
                ):
                    status = "current_code_or_document_version"
                elif actual:
                    status = "historical_content_differs_current_baseline"
                else:
                    status = "historical_reference_unavailable"
                refs.append(
                    dict(
                        manifest=str(mp),
                        manifest_sha256=mh,
                        field=field,
                        name=name,
                        expected_sha256=expected,
                        current_path=str(p),
                        current_sha256=actual or "",
                        status=status,
                        matching_bytes_paths=json.dumps(candidates, ensure_ascii=False),
                    )
                )
    table(out / "historical_references_private.csv", refs)
    write(out / "scalar_hash_claims_private.json", scalar)
    summary = dict(
        status="current_baseline_frozen_historical_claims_classified",
        created_utc=datetime.now(timezone.utc).isoformat(),
        files=len(entries),
        bytes=size,
        manifest_count=len(manifests),
        historical_references=len(refs),
        reference_status_counts=dict(Counter(r["status"] for r in refs)),
        scalar_claims=len(scalar),
        unmatched_scalar_claims=sum(not r["matching_current_files"] for r in scalar),
        python=platform.python_version(),
        revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        config_sha256=sha(ROOT / "config/hash_baseline_v1.json"),
        code_sha256=sha(Path(__file__)),
        files_index_sha256=sha(out / "files_private.json"),
        historical_ledger_sha256=sha(out / "historical_references_private.csv"),
        scope="Current byte integrity baseline only. Historical configuration, missing provenance and participant identity are not certified by rebasing.",
    )
    write(out / "summary.json", summary)
    print(out)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
