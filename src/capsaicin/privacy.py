"""Create restricted, Git-external pseudonymized copies; never edit inputs."""

import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE_FIELDS = [
    "ID",
    "Sex",
    "Age",
    "Height_cm",
    "Weight_kg",
    "BMI",
    *[f"VAS_{t}min" for t in range(1, 21)],
    "VAS_Avg.",
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
    "Region_code",
    "Symptom_codes",
]
IDENTIFIER_FIELDS = {
    "id",
    "subject_id",
    "person_id",
    "participant_id",
    "source_subject",
}
BLOCKED_FIELD = re.compile(
    "name|姓名|phone|telephone|email|address|birth|date|file|path|free_text|additional_symptoms|备注|身份证",
    re.I,
)


class PrivacyError(ValueError):
    pass


def read_table(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        if not fields or len(set(fields)) != len(fields):
            raise PrivacyError("Missing or duplicate CSV headers")
        rows = list(reader)
    if any(
        (None in row or any((value is None for value in row.values())) for row in rows)
    ):
        raise PrivacyError("CSV row width differs from its header")
    return (fields, rows)


def canonical_id(value, aliases):
    seen = set()
    while value in aliases and aliases[value] != value:
        if value in seen:
            raise PrivacyError("Cyclic identity aliases")
        seen.add(value)
        value = aliases[value]
    if not value:
        raise PrivacyError("Blank canonical identifier")
    return value


def outside_git(output):
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(ROOT):
        raise PrivacyError(
            "Individual records and mappings must be outside this repository"
        )
    parent = output
    while not parent.exists():
        parent = parent.parent
    for ancestor in [parent, *parent.parents]:
        if (ancestor / ".git").exists():
            raise PrivacyError("Output is inside a Git checkout")
    return output


def deidentify(tables, output, aliases=None):
    """Use explicit field allowlists and one random mapping for linked tables.

    Each table specifies input, output_name, keep_columns, id_columns, and
    optionally primary_id. Aliases must be confirmed upstream; this function
    does not infer identity or consolidate rows. Unknown foreign keys fail.
    """
    output = outside_git(output)
    if output.exists():
        raise PrivacyError("Output exists; choose a new versioned directory")
    if not tables:
        raise PrivacyError("No tables requested")
    aliases = dict(aliases or {})
    for key in aliases:
        canonical_id(key, aliases)
    loaded, identifiers, names = ([], set(), set())
    for spec in tables:
        source = Path(spec["input"]).expanduser().resolve(strict=True)
        name = Path(spec["output_name"])
        if (
            name.is_absolute()
            or ".." in name.parts
            or name.suffix != ".csv"
            or (str(name) in names)
        ):
            raise PrivacyError("Output names must be unique relative CSV paths")
        names.add(str(name))
        original_bytes = source.read_bytes()
        fields, rows = read_table(source)
        keep = list(spec["keep_columns"])
        id_columns = list(spec["id_columns"])
        primary = spec.get("primary_id")
        if not keep or len(keep) != len(set(keep)) or (not set(keep) <= set(fields)):
            raise PrivacyError("Invalid explicit field allowlist")
        if not set(id_columns) <= set(keep) or (primary and primary not in id_columns):
            raise PrivacyError("Identifier columns must be selected and declared")
        if any(
            (BLOCKED_FIELD.search(field) and field not in id_columns for field in keep)
        ):
            raise PrivacyError(
                "Direct identifiers, paths, dates, or free text cannot be retained"
            )
        if any(
            (
                field.lower() in IDENTIFIER_FIELDS and field not in id_columns
                for field in keep
            )
        ):
            raise PrivacyError("Undeclared identifier column")
        if primary:
            for row in rows:
                if not row[primary].strip():
                    raise PrivacyError("Blank primary identifier")
                identifiers.add(row[primary])
        for row in rows:
            for field in keep:
                if re.search(
                    "(?:[A-Za-z]:[\\\\/]|/(?:Users|Volumes|home)/|\\.(?:acq|snirf|omm|cnp)\\b)",
                    row[field],
                    re.I,
                ):
                    raise PrivacyError("Source path found in a retained field")
        loaded.append((spec, source, original_bytes, fields, rows))
    if not identifiers:
        raise PrivacyError("Declare at least one primary identifier table")
    canonical = {sid: canonical_id(sid, aliases) for sid in identifiers}
    tokens = {}
    for sid in sorted(set(canonical.values())):
        token = "P_" + secrets.token_hex(12)
        while token in tokens.values():
            token = "P_" + secrets.token_hex(12)
        tokens[sid] = token
    mapping = {sid: tokens[cid] for sid, cid in canonical.items()}
    for spec, source, original_bytes, fields, rows in loaded:
        for row in rows:
            for field in spec["id_columns"]:
                raw = row[field]
                if not raw:
                    continue
                cid = canonical_id(raw, aliases)
                if cid not in tokens:
                    raise PrivacyError(
                        "Unresolved foreign identifier; no row-index identity inference"
                    )
                mapping[raw] = tokens[cid]
    output.parent.mkdir(parents=True, exist_ok=True, mode=448)
    temporary = Path(
        tempfile.mkdtemp(prefix=".pending_deidentified_", dir=output.parent)
    )
    os.chmod(temporary, 448)
    try:
        records = []
        for spec, source, original_bytes, fields, rows in loaded:
            keep = spec["keep_columns"]
            exported = [
                {
                    field: mapping[row[field]]
                    if field in spec["id_columns"] and row[field]
                    else row[field]
                    for field in keep
                }
                for row in rows
            ]
            secrets.SystemRandom().shuffle(exported)
            target = temporary / spec["output_name"]
            target.parent.mkdir(parents=True, exist_ok=True, mode=448)
            with target.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=keep)
                writer.writeheader()
                writer.writerows(exported)
            os.chmod(target, 384)
            if source.read_bytes() != original_bytes:
                raise PrivacyError("Source changed while exporting")
            records.append(
                dict(
                    input=str(source),
                    output=spec["output_name"],
                    rows=len(rows),
                    kept_columns=keep,
                    id_columns=spec["id_columns"],
                    removed_columns=[f for f in fields if f not in keep],
                )
            )
        with (temporary / "identity_mapping_PRIVATE.csv").open(
            "x", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["source_id", "canonical_source_id", "pseudonym"])
            writer.writerows(
                (
                    (sid, canonical_id(sid, aliases), token)
                    for sid, token in sorted(mapping.items())
                )
            )
        packages = sorted(
            (
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
            )
        )
        manifest = dict(
            version="pseudonymization_v1",
            status="restricted_pseudonymized_not_anonymous",
            created_utc=datetime.now(timezone.utc).isoformat(),
            python=sys.version,
            software=packages,
            tables=records,
            canonical_people=len(tokens),
            row_order="independently shuffled per table",
            numeric_values_markers_missingness_minutes="preserved as original CSV tokens",
            source_mutation=False,
            scientific_readiness="not assessed",
        )
        (temporary / "manifest_PRIVATE.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
        (temporary / "README.md").write_text(
            "# Restricted pseudonymized data\n\nThese are real individual records, not synthetic data or anonymous public data.\nKeep this entire directory, especially the identity mapping, outside Git.\nRandom identifiers and shuffled rows do not remove reidentification risk from exact trajectories and demographics.\nDirect source links/free text are removed; retained values, E/T, missing tokens and minutes are unchanged.\nConfirmed aliases share a token; original rows are retained, not merged or repaired.\nThe run record lists field policy and software versions.\n"
        )
        for path in temporary.rglob("*"):
            os.chmod(path, 448 if path.is_dir() else 384)
        if any(
            (
                source.read_bytes() != prior_bytes
                for _, source, prior_bytes, _, _ in loaded
            )
        ):
            raise PrivacyError("Source changed before publication")
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest
