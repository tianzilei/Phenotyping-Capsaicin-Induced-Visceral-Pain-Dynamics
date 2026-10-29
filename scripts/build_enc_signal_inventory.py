"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = {"E": "capsaicin_trial", "N": "pre_capsaicin_rest", "C": "pre_capsaicin_rest"}


def clean_code(value: object) -> str:
    match = re.search("\\d+", str(value or ""))
    return str(int(match.group())) if match else ""


def vas_signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        (str(row.get(f"VAS_{minute}min", "")).strip() for minute in range(1, 21))
    )


def parse_recording_name(name: str) -> dict[str, str] | None:
    """Parse a recording filename without guessing a person's identity."""
    stem = Path(name).stem
    if stem.lower().endswith("_egg"):
        stem = stem[:-4]
    match = PREFIX.match(stem)
    if not match:
        return None
    acquisition_token = match.group("tail").split("_")[0]
    phase_letters = re.findall("[A-Za-z]", acquisition_token)
    phase = phase_letters[-1].upper() if phase_letters else ""
    return {
        "date": match.group("date"),
        "recording_code": clean_code(match.group("code")),
        "filename_abbr": match.group("abbr").upper(),
        "phase": phase,
        "stage": phase if phase in STAGES else "",
        "filename_tail": acquisition_token,
    }


def read_csv_any(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return list(csv.DictReader(raw.decode(encoding).splitlines()))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def classify_file(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    text = str(path).lower().replace("/", "\\")
    if ext == ".acq":
        return ("electrophysiology", "raw_biopac")
    if ext == ".csv" and path.parent.name.lower() == "biopac_csv":
        return ("electrophysiology_multichannel", "full_biopac_csv")
    if ext == ".csv" and "biopac_csv" in text and ("\\ecg\\" in text):
        return ("electrophysiology_ecg", "derived_split_csv")
    if ext == ".csv" and "biopac_csv" in text and ("\\egg\\" in text):
        return ("electrophysiology_egg", "derived_split_csv")
    if ext == ".csv" and "biopac_csv" in text and ("\\emg\\" in text):
        return ("electrophysiology_emg", "derived_split_csv")
    if ext in {".omm", ".ext", ".pat", ".asc", ".wl1", ".wl2", ".hdr"}:
        return ("fnirs", "raw_or_companion")
    if ext in {".snirf", ".nirs"}:
        return ("fnirs", "converted_container")
    if ext in {".txt", ".csv"} and ("fnirs" in text or "nirs" in text):
        return ("fnirs", "converted_text_or_metadata")
    return ("unknown", "candidate_companion")


def scan_f() -> list[dict[str, object]]:
    output = []
    for root, _, files in os.walk("F:/"):
        for name in files:
            path = Path(root) / name
            if name.startswith("._") or path.suffix.lower() not in SIGNAL_EXTS:
                continue
            parsed = parse_recording_name(name)
            if not parsed or parsed["stage"] not in STAGES:
                continue
            modality, source_level = classify_file(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            output.append(
                {
                    "path": str(path),
                    "filename": name,
                    "extension": path.suffix.lower(),
                    "bytes": stat.st_size,
                    "modified_utc": datetime.fromtimestamp(
                        stat.st_mtime, timezone.utc
                    ).isoformat(),
                    "date": parsed["date"],
                    "recording_code": parsed["recording_code"],
                    "filename_abbr": parsed["filename_abbr"],
                    "filename_tail": parsed["filename_tail"],
                    "stage": parsed["stage"],
                    "stage_meaning": STAGES[parsed["stage"]],
                    "modality": modality,
                    "source_level": source_level,
                }
            )
    return output


def write_csv(
    path: Path, rows: list[dict[str, object]], fields: list[str] | None = None
) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


SIGNAL_EXTS = {
    ".acq",
    ".omm",
    ".ext",
    ".pat",
    ".asc",
    ".txt",
    ".csv",
    ".snirf",
    ".nirs",
    ".hdr",
    ".wl1",
    ".wl2",
}
PREFIX = re.compile(
    "^(?P<date>20\\d{6})(?P<code>\\d{2,3})(?P<abbr>[A-Za-z]{4})(?P<tail>[^.]*)$", re.I
)
SIGNAL_EXTS = {
    ".acq",
    ".omm",
    ".ext",
    ".pat",
    ".asc",
    ".txt",
    ".csv",
    ".snirf",
    ".nirs",
    ".hdr",
    ".wl1",
    ".wl2",
}
PREFIX = re.compile(
    "^(?P<date>20\\d{6})(?P<code>\\d{2,3})(?P<abbr>[A-Za-z]{4})(?P<tail>[^.]*)$", re.I
)
