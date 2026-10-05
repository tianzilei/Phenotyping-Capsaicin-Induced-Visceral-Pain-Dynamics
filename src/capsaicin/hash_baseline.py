"""Strict current-byte checks with explicitly registered historical code evolution."""

import csv

csv.field_size_limit(100_000_000)
import hashlib
import json
from pathlib import Path
from .data_locations import ROOT, resolve_input, path_key


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class HashBaseline:
    def __init__(self, settings=None):
        cp = Path(settings) if settings else ROOT / "config/hash_baseline_active.json"
        self.settings = (
            json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
        )
        self.records = None

    def check(self, manifest, field, name, expected, target=None):
        """Return provenance status, never equate new source code with old source code."""
        mp = Path(manifest)
        if Path(name).name.startswith("._"):
            return "ignored_appledouble_metadata"
        p = (
            Path(target)
            if target is not None
            else (
                mp.parent / name
                if field in ("outputs_sha256", "files")
                else resolve_input(name)
            )
        )
        actual = digest(p) if p.is_file() else None
        if actual == expected:
            return "matched"
        if not self.settings.get("active"):
            raise ValueError(f"Hash mismatch: {field}: {p}")
        if self.records is None:
            ledger = Path(self.settings["historical_ledger"])
            if digest(ledger) != self.settings["historical_ledger_sha256"]:
                raise ValueError("Baseline ledger changed")
            with ledger.open(encoding="utf-8", newline="") as f:
                self.records = {
                    (path_key(r["manifest"]), r["field"], r["name"]): r
                    for r in csv.DictReader(f)
                }
        r = self.records.get((path_key(mp), field, str(name)))
        if (
            r
            and digest(mp) == r["manifest_sha256"]
            and expected == r["expected_sha256"]
        ):
            if r["status"] == "historical_bytes_available_at_other_path":
                candidates = json.loads(r["matching_bytes_paths"])
                for candidate in candidates:
                    q = Path(candidate)
                    if q.is_file() and digest(q) == expected:
                        return "historical_bytes_verified_at_other_path"
            if actual is None and r["status"] == "matched":
                q = Path(r["current_path"])
                if q.is_file() and digest(q) == expected:
                    return "matched_relocated_path"
        # Only an exact, previously audited code/document transition can pass
        # historical input review. Changed outputs, signals and configs never do.
        if (
            r
            and r["status"] == "current_code_or_document_version"
            and field not in ("outputs_sha256", "files")
            and p.suffix.lower() in (".py", ".r", ".md")
            and digest(mp) == r["manifest_sha256"]
            and expected == r["expected_sha256"]
            and actual == r["current_sha256"]
            and path_key(p) == path_key(r["current_path"])
        ):
            import warnings

            warnings.warn(
                "Historical code/document differs from current baseline; data hashes remain strict: "
                + str(p),
                RuntimeWarning,
                stacklevel=2,
            )
            return "registered_historical_code_or_document_version"
        raise ValueError(f"Unregistered hash mismatch: {field}: {p}")


_baseline = None


def check_reference(manifest, field, name, expected, target=None):
    global _baseline
    if _baseline is None:
        _baseline = HashBaseline()
    return _baseline.check(manifest, field, name, expected, target)
