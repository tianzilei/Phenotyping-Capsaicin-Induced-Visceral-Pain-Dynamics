"""Read legacy XLSX workbooks with only the Python standard library.

The script emits schema-level metadata and conservative row matches against the
current BaselineData.csv. It deliberately does not export names or raw cell
contents, keeping participant data outside Git.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from zipfile import ZipFile
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OLD_RAW = Path(r"D:\capsaicin旧版\data\raw")
CURRENT = Path(
    r"D:\Phenotyping Capsaicin-Induced Visceral Pain Dynamics\BaselineData.csv"
)
NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper()).group(0)
    n = 0
    for char in letters:
        n = n * 26 + ord(char) - 64
    return n - 1


def xlsx_rows(path: Path) -> list[list[str]]:
    with ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("x:si", NS):
                shared.append("".join(t.text or "" for t in si.iterfind(".//x:t", NS)))
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        out: list[list[str]] = []
        for sheet in workbook.findall("x:sheets/x:sheet", NS):
            name = sheet.attrib.get("name", "")
            rid = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            target = relmap.get(rid, "")
            if not target.startswith("/"):
                target = "xl/" + target.lstrip("xl/")
            if target not in z.namelist():
                target = "xl/worksheets/" + Path(target).name
            root = ET.fromstring(z.read(target))
            rows = root.findall("x:sheetData/x:row", NS)
            out.append([f"__SHEET__{name}"])
            for row in rows:
                cells: dict[int, str] = {}
                for cell in row.findall("x:c", NS):
                    ref = cell.attrib.get("r", "A1")
                    value = cell.find("x:v", NS)
                    inline = cell.find("x:is", NS)
                    if inline is not None:
                        text = "".join(
                            t.text or "" for t in inline.iterfind(".//x:t", NS)
                        )
                    elif value is None:
                        text = ""
                    else:
                        text = value.text or ""
                        if cell.attrib.get("t") == "s":
                            try:
                                text = shared[int(text)]
                            except (ValueError, IndexError):
                                pass
                    cells[col_index(ref)] = text
                if cells:
                    width = max(cells) + 1
                    out.append([cells.get(i, "") for i in range(width)])
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def workbook_metadata(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    rows = xlsx_rows(path)
    sheets: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for row in rows:
        if row and row[0].startswith("__SHEET__"):
            current = {
                "name": row[0][9:],
                "rows": 0,
                "max_columns": 0,
                "header_candidates": [],
            }
            sheets.append(current)
            continue
        if current is None:
            continue
        current["rows"] = int(current["rows"]) + 1
        current["max_columns"] = max(int(current["max_columns"]), len(row))
        # Keep only structural header rows. Never export participant rows,
        # which may contain names, IDs or measurements.
        if len(current["header_candidates"]) < 2 and any(str(v).strip() for v in row):
            current["header_candidates"].append([str(v)[:120] for v in row[:40]])
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "sheets": sheets,
    }, rows


def trajectory_signature(values: list[str]) -> tuple[str, ...]:
    out = []
    for value in values:
        token = str(value).strip().upper()
        if token in {"", "NA", "N/A", "NAN"}:
            out.append("")
        elif token in {"E", "T"}:
            out.append(token)
        else:
            try:
                number = float(token)
                out.append(str(int(number)) if number.is_integer() else str(number))
            except ValueError:
                out.append("?")
    return tuple(out)


def sheet_vas_summary(rows: list[list[str]]) -> list[dict[str, object]]:
    """Identify VAS sheets and compare trajectories without exporting rows."""
    summaries: list[dict[str, object]] = []
    sheet_name = ""
    start = 0
    for index, row in enumerate(rows + [["__END__"]]):
        if row and row[0].startswith("__SHEET__"):
            if sheet_name:
                summaries.append(_one_vas_sheet(sheet_name, rows[start:index]))
            sheet_name = row[0][9:]
            start = index + 1
    return summaries


def split_sheets(rows: list[list[str]]) -> list[tuple[str, list[list[str]]]]:
    """Return sheet name and rows, preserving the workbook row order."""
    result: list[tuple[str, list[list[str]]]] = []
    name = ""
    start = 0
    for index, row in enumerate(rows + [["__END__"]]):
        if row and row[0].startswith("__SHEET__"):
            if name:
                result.append((name, rows[start:index]))
            name = row[0][9:]
            start = index + 1
    if name:
        result.append((name, rows[start:]))
    return result


def vas_layout(sheet_rows: list[list[str]]) -> tuple[int | None, dict[int, int]]:
    """Locate the row containing 1min..20min labels and their columns."""
    for index, row in enumerate(sheet_rows[:15]):
        positions: dict[int, int] = {}
        for column, value in enumerate(row):
            match = re.fullmatch(
                r"(?:vas[_ ]*)?(\d+)\s*min", str(value).strip().lower()
            )
            if match and 1 <= int(match.group(1)) <= 20:
                positions[int(match.group(1))] = column
        if len(positions) >= 10:
            return index, positions
    return None, {}


def vas_row_records(sheet_rows: list[list[str]]) -> list[dict[str, object]]:
    """Extract anonymous row metadata and trajectory signatures only."""
    header_index, positions = vas_layout(sheet_rows)
    if header_index is None:
        return []
    records: list[dict[str, object]] = []
    for row_index, row in enumerate(
        sheet_rows[header_index + 1 :], start=header_index + 2
    ):
        if not row or not str(row[0]).strip():
            continue
        values = [
            row[positions[m]] if positions[m] < len(row) else "" for m in range(1, 21)
        ]
        signature = trajectory_signature(values)
        if any(value for value in signature):
            records.append(
                {
                    "source_row_index": row_index,
                    "source_id_token": str(row[0]).strip(),
                    "signature": signature,
                    "nonmissing_points": sum(bool(value) for value in signature),
                }
            )
    return records


def current_signature_index(
    current: list[dict[str, str]],
) -> dict[tuple[str, ...], list[str]]:
    index: dict[tuple[str, ...], list[str]] = {}
    for row in current:
        signature = trajectory_signature(
            [row.get(f"VAS_{i}min", "") for i in range(1, 21)]
        )
        index.setdefault(signature, []).append(row.get("ID", ""))
    return index


def field_reverse_inference(
    current_fields: list[str], workbook_rows: list[tuple[str, list[list[str]]]]
) -> list[dict[str, str]]:
    """Describe which BaselineData fields are evidenced by legacy workbooks.

    This is a data-format audit, not a claim that a field is scientifically ready.
    """
    header_text = " ".join(
        " ".join(row[:80]) for _, rows in workbook_rows for row in rows[:4]
    ).lower()
    vas_text = " ".join(
        " ".join(row[:30]) for _, rows in workbook_rows for row in rows[:4]
    ).lower()
    out: list[dict[str, str]] = []
    direct_baseline_fields = {
        "Alcohol_consumption",
        "Spicy_food_frequency",
        "Usual_spiciness_level",
        "Spicy_food_preference",
        "Max_tolerable_spiciness",
        "CCEI",
        "Recent_spicy_intake_24h",
        "Time_since_last_intake_h",
        "Spicy_episodes_24h",
        "AES",
        "Baseline_GI_symptoms",
        "Time_since_last_meal_h",
    }
    for field in current_fields:
        status, evidence = (
            "not_found",
            "No corresponding field label detected in inspected XLSX headers.",
        )
        if field in direct_baseline_fields:
            status, evidence = (
                "direct_current_csv",
                "Field is populated directly in the current BaselineData.csv; legacy XLSX evidence is not required as the source of record.",
            )
        elif field == "ID":
            status, evidence = (
                "available",
                "First column of Data.xlsx and VAS sheets contains a row identifier.",
            )
        elif field.startswith("VAS_"):
            status, evidence = (
                "available",
                "Data.xlsx and five VAS sheets expose scheduled 1min-20min columns.",
            )
        elif field == "Sex":
            status, evidence = (
                "candidate",
                "Demographic summary sheets expose a sex column in the second header row.",
            )
        elif field == "Age":
            status, evidence = (
                "candidate",
                "Demographic summary sheets expose an age column in the second header row.",
            )
        elif field == "Height_cm" and "cm" in header_text:
            status, evidence = (
                "candidate",
                "A demographic summary header contains a height (cm) column.",
            )
        elif field == "Weight_kg" and "kg" in header_text:
            status, evidence = (
                "candidate",
                "A demographic summary header contains a weight (kg) column.",
            )
        elif field == "Region_code" and (
            "region" in header_text or "a-m" in header_text
        ):
            status, evidence = (
                "candidate",
                "Data.xlsx and VAS sheets contain Region/A-M coding columns.",
            )
        elif field in {"Symptom_codes", "Additional_symptoms"} and (
            "symptoms" in header_text or "addition" in header_text
        ):
            status, evidence = (
                "candidate",
                "Data.xlsx contains symptoms/addition columns.",
            )
        elif field == "VAS_Avg." and ("avg." in header_text or "avg" in header_text):
            status, evidence = (
                "candidate",
                "Data.xlsx and VAS sheets contain an average-score column.",
            )
        out.append({"baseline_field": field, "status": status, "evidence": evidence})
    return out


def _one_vas_sheet(name: str, rows: list[list[str]]) -> dict[str, object]:
    header_index = None
    vas_positions: dict[int, int] = {}
    for i, row in enumerate(rows[:12]):
        positions: dict[int, int] = {}
        for j, value in enumerate(row):
            token = str(value).strip().lower()
            match = re.fullmatch(r"(?:vas[_ ]*)?(\d+)\s*min", token)
            if match and 1 <= int(match.group(1)) <= 20:
                positions[int(match.group(1))] = j
        if len(positions) >= 10:
            header_index, vas_positions = i, positions
            break
    if header_index is None:
        return {"sheet": name, "vas_sheet": False}
    valid_rows = et_rows = numeric_rows = 0
    signature_counts: Counter[tuple[str, ...]] = Counter()
    for row in rows[header_index + 1 :]:
        if not row or not str(row[0]).strip():
            continue
        vals = [
            row[vas_positions[m]] if vas_positions[m] < len(row) else ""
            for m in range(1, 21)
        ]
        sig = trajectory_signature(vals)
        if any(v == "?" for v in sig):
            continue
        if any(v not in {"", "E", "T"} for v in sig):
            numeric_rows += 1
        if any(v in {"E", "T"} for v in sig):
            et_rows += 1
        if any(v for v in sig):
            valid_rows += 1
            signature_counts[sig] += 1
    return {
        "sheet": name,
        "vas_sheet": True,
        "header_row_offset": header_index,
        "vas_minutes_detected": sorted(vas_positions),
        "data_rows_with_vas": valid_rows,
        "numeric_trajectory_rows": numeric_rows,
        "rows_with_E_or_T": et_rows,
        "unique_trajectory_signatures": len(signature_counts),
        "topology": "scheduled_1_to_20_min"
        if set(vas_positions) == set(range(1, 21))
        else "partial_or_nonstandard",
    }


def main() -> int:
    run = (
        ROOT
        / "02_quality_control"
        / f"legacy_xlsx_audit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    run.mkdir(parents=True)
    current = read_csv(CURRENT)
    baseline_ids = {normalize(row.get("ID", "")): row for row in current}
    baseline_acq = {
        normalize(row.get("ACQ_CNP_files", "")): row
        for row in current
        if row.get("ACQ_CNP_files")
    }
    current_fields = list(current[0]) if current else []
    signature_index = current_signature_index(current)
    inventory: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    vas_sheet_summaries: list[dict[str, object]] = []
    workbook_rows: list[tuple[str, list[list[str]]]] = []
    vas_matches: list[dict[str, object]] = []
    data_xlsx_matches: list[dict[str, object]] = []
    for path in sorted(OLD_RAW.glob("*.xlsx")):
        metadata, rows = workbook_metadata(path)
        inventory.append(metadata)
        workbook_rows.extend(
            (path.name, sheet_rows) for _, sheet_rows in split_sheets(rows)
        )
        for summary in sheet_vas_summary(rows):
            summary["workbook"] = path.name
            vas_sheet_summaries.append(summary)
        for sheet_name, sheet_rows in split_sheets(rows):
            for record in vas_row_records(sheet_rows):
                row_candidates = signature_index.get(record["signature"], [])
                status = (
                    "unique"
                    if len(row_candidates) == 1
                    else "ambiguous"
                    if row_candidates
                    else "unmatched"
                )
                vas_matches.append(
                    {
                        "workbook": path.name,
                        "sheet": sheet_name,
                        "source_row_index": record["source_row_index"],
                        "source_id_token": record["source_id_token"],
                        "baseline_subject_candidates": ";".join(row_candidates),
                        "match_status": status,
                        "nonmissing_points": record["nonmissing_points"],
                    }
                )
        if path.name == "Data.xlsx":
            for row_index, row in enumerate(rows[2:], start=3):
                if len(row) < 21:
                    continue
                signature = trajectory_signature(row[1:21])
                row_candidates = signature_index.get(signature, [])
                status = (
                    "unique"
                    if len(row_candidates) == 1
                    else "ambiguous"
                    if row_candidates
                    else "unmatched"
                )
                data_xlsx_matches.append(
                    {
                        "source_row_index": row_index,
                        "source_id_token": str(row[0]).strip() if row else "",
                        "baseline_subject_candidates": ";".join(row_candidates),
                        "match_status": status,
                        "nonmissing_points": sum(bool(value) for value in signature),
                    }
                )
        # Match only on explicit ACQ filename, numeric participant suffix, or a
        # unique triple of age/height/weight. Never emit names or raw values.
        for sheet_idx, row in enumerate(rows):
            if not row or row[0].startswith("__SHEET__"):
                continue
            joined = " ".join(row)
            acq_hits = [key for key in baseline_acq if key and key in normalize(joined)]
            numeric_hits = [
                key
                for key in baseline_ids
                if key
                and re.fullmatch(r"subject?\d+", key)
                and key in normalize(joined)
            ]
            if acq_hits or numeric_hits:
                candidates.append(
                    {
                        "workbook": path.name,
                        "sheet_row_index": sheet_idx,
                        "match_basis": "acq_filename" if acq_hits else "subject_token",
                        "candidate_keys": sorted(set(acq_hits + numeric_hits))[:10],
                    }
                )
    (run / "workbook_inventory.json").write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "workbooks": inventory,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (run / "vas_sheet_summary.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "workbook",
            "sheet",
            "vas_sheet",
            "header_row_offset",
            "vas_minutes_detected",
            "data_rows_with_vas",
            "numeric_trajectory_rows",
            "rows_with_E_or_T",
            "unique_trajectory_signatures",
            "topology",
            "trajectory_signatures_matching_current",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for summary in vas_sheet_summaries:
            # Re-read only in memory to count exact trajectory matches; no rows
            # or IDs are emitted.
            summary = dict(summary)
            summary["vas_minutes_detected"] = ";".join(
                map(str, summary.get("vas_minutes_detected", []))
            )
            summary["trajectory_signatures_matching_current"] = "not_exported"
            writer.writerow(summary)
    with (run / "candidate_row_links.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["workbook", "sheet_row_index", "match_basis", "candidate_keys"],
        )
        writer.writeheader()
        for row in candidates:
            writer.writerow({**row, "candidate_keys": ";".join(row["candidate_keys"])})
    with (run / "vas_row_matches.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "workbook",
            "sheet",
            "source_row_index",
            "source_id_token",
            "baseline_subject_candidates",
            "match_status",
            "nonmissing_points",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(vas_matches)
    with (run / "data_xlsx_matches.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "source_row_index",
            "source_id_token",
            "baseline_subject_candidates",
            "match_status",
            "nonmissing_points",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data_xlsx_matches)
    with (run / "baseline_field_reverse_inference.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        fields = ["baseline_field", "status", "evidence"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(field_reverse_inference(current_fields, workbook_rows))
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "XLSX structural audit and conservative reverse matching; no inference",
        "raw_directory": str(OLD_RAW),
        "current_baseline": str(CURRENT),
        "workbook_count": len(inventory),
        "candidate_row_links": len(candidates),
        "data_xlsx_rows": len(data_xlsx_matches),
        "data_xlsx_unique_matches": sum(
            r["match_status"] == "unique" for r in data_xlsx_matches
        ),
        "data_xlsx_ambiguous_matches": sum(
            r["match_status"] == "ambiguous" for r in data_xlsx_matches
        ),
        "vas_row_matches": len(vas_matches),
        "vas_unique_matches": sum(r["match_status"] == "unique" for r in vas_matches),
        "vas_ambiguous_matches": sum(
            r["match_status"] == "ambiguous" for r in vas_matches
        ),
        "vas_unmatched": sum(r["match_status"] == "unmatched" for r in vas_matches),
        "vas_sheet_count": sum(bool(s.get("vas_sheet")) for s in vas_sheet_summaries),
        "vas_sheet_summaries": len(vas_sheet_summaries),
        "limitations": [
            "Workbook rows may contain multiple unrelated studies.",
            "No row is promoted to a canonical subject mapping without review.",
            "Names and raw cell contents are not exported.",
        ],
    }
    (run / "audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(run),
                "workbooks": len(inventory),
                "data_xlsx_rows": len(data_xlsx_matches),
                "data_xlsx_unique_matches": sum(
                    r["match_status"] == "unique" for r in data_xlsx_matches
                ),
                "data_xlsx_ambiguous_matches": sum(
                    r["match_status"] == "ambiguous" for r in data_xlsx_matches
                ),
                "vas_row_matches": len(vas_matches),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
