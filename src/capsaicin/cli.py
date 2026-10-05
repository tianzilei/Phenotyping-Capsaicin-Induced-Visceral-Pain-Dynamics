"""Publication inventory, synthetic QC and explicitly provisional model commands."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import uuid

from . import __version__
from .contracts import ContractError, read_wide
from .qc import time_counts, subject_descriptives

ROOT = Path(__file__).resolve().parents[2]


def resolve(value):
    from .data_locations import resolve_input

    return resolve_input(Path(value).expanduser())


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_csv(path, rows):
    if not rows:
        raise ContractError("拒绝输出没有字段定义的空表。")
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def git_revision():
    if not shutil.which("git"):
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def validate(input_path, config_path, output=None, synthetic=False):
    input_path, config_path = resolve(input_path), resolve(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not synthetic and config.get("status") == "synthetic_only":
        raise ContractError("synthetic_only 配置仅可用于 demo，不用于真实文件验证。")
    input_hash, config_hash = digest(input_path), digest(config_path)
    rows = read_wide(input_path, config)
    if digest(input_path) != input_hash or digest(config_path) != config_hash:
        raise ContractError("读取期间输入或配置发生变化，请固定来源后重新验证。")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = (
        ("synthetic_" if synthetic else "validation_")
        + stamp
        + "_"
        + uuid.uuid4().hex[:8]
    )
    destination = resolve(output) if output else ROOT / "02_quality_control" / name
    if destination.exists():
        raise ContractError("输出目录已存在；指定新目录以保留既有运行。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Publish the run atomically only once all output files are complete.
    temporary = Path(tempfile.mkdtemp(prefix=".pending_", dir=destination.parent))
    try:
        write_csv(temporary / "vas_long.csv", rows)
        write_csv(temporary / "time_counts.csv", time_counts(rows))
        write_csv(temporary / "subject_descriptives.csv", subject_descriptives(rows))
        write_json(
            temporary / "run_manifest.json",
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "version": __version__,
                "status": "synthetic_validation_passed"
                if synthetic
                else "format_validation_passed",
                "scope": "wide-table format and descriptive QC only; not scientific readiness",
                "input": str(input_path),
                "input_sha256": input_hash,
                "config": str(config_path),
                "config_sha256": config_hash,
                "git_commit": git_revision(),
                "python": platform.python_version(),
                "synthetic": synthetic,
                "n_subjects": len({r["subject_id"] for r in rows}),
                "n_scheduled_rows": len(rows),
                "files": {
                    p.name: digest(p) for p in temporary.iterdir() if p.is_file()
                },
            },
        )
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    print(
        json.dumps(
            {
                "output": str(destination),
                "synthetic": synthetic,
                "status": "format_validation_passed",
            },
            ensure_ascii=False,
        )
    )
    return 0


def doctor():
    result = {
        "python": platform.python_version(),
        "core_dependencies": "standard_library_only",
        "python_supported": tuple(map(int, platform.python_version_tuple()[:2]))
        >= (3, 11),
        "git_available": bool(shutil.which("git")),
        "Rscript": shutil.which("Rscript"),
        "models": "implemented_working_models_with_separate_scientific_gates",
        "unsupported_inference": [
            "validated_instantaneous_derivatives",
            "clinical_Markov",
            "phase_directionality",
            "independent_physiology_validation",
        ],
    }
    if result["Rscript"]:
        expression = (
            'cat(R.version.string,"\\n"); '
            'for (p in c("renv","mgcv","nlme","fdapace","jsonlite")) '
            'cat(p, if(requireNamespace(p,quietly=TRUE)) as.character(packageVersion(p)) else "MISSING", "\\n")'
        )
        process = subprocess.run(
            [result["Rscript"], "-e", expression],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result["R_check_exit_code"] = process.returncode
        result["R_packages"] = process.stdout.strip()
        if process.returncode:
            result["R_error"] = process.stderr.strip()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["python_supported"] else 2


def inventory():
    manifest = json.loads(
        (ROOT / "docs/release_inventory.json").read_text(encoding="utf-8")
    )
    result = []
    for name, record in manifest["aggregate_files"].items():
        path = ROOT / name
        result.append(
            {
                "file": name,
                "exists": path.is_file(),
                "sha256_matches_release": digest(path) == record["published_sha256"]
                if path.is_file()
                else False,
            }
        )
    passed = all(row["exists"] and row["sha256_matches_release"] for row in result)
    print(
        json.dumps(
            {
                "status": "PASS" if passed else "FAIL",
                "scope": "current public aggregate files only",
                "files": len(result),
                "history_checked": False,
                "issues": [
                    row
                    for row in result
                    if not row["exists"] or not row["sha256_matches_release"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="辣椒素分析仓库：规划、文件核验与合成演示"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "inventory", "plan"):
        commands.add_parser(name)
    demo = commands.add_parser("demo", help="仅使用仓库内的明确合成样例")
    demo.add_argument("--output", help="新的输出目录，不能已存在")
    check = commands.add_parser("validate", help="只检查宽表，保留 E/T；不拟合模型")
    check.add_argument("--input", required=True)
    check.add_argument("--config", default="config/analysis.json")
    check.add_argument("--output")
    analysis = commands.add_parser(
        "analyze", help="Run versioned provisional VAS models and readiness report"
    )
    analysis.add_argument("--input", required=True)
    analysis.add_argument("--config", default="config/provisional_vas_v3.json")
    analysis.add_argument("--output")
    analysis.add_argument("--rscript")
    analysis.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor()
        if args.command == "inventory":
            return inventory()
        if args.command == "plan":
            modules = json.loads(
                (ROOT / "config/modules.json").read_text(encoding="utf-8")
            )
            print(
                json.dumps(
                    {"execution": "plan_only", "modules": modules},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "demo":
            return validate(
                "tests/fixtures/synthetic_vas.csv",
                "config/synthetic.json",
                args.output,
                synthetic=True,
            )
        if args.command == "analyze":
            from .analysis import run_analysis

            return run_analysis(
                args.input, args.config, args.output, args.rscript, args.evidence
            )
        return validate(args.input, args.config, args.output)
    except (
        ContractError,
        OSError,
        ValueError,
        KeyError,
        subprocess.TimeoutExpired,
    ) as exc:
        parser.exit(2, f"检查未通过：{exc}\n")
