"""Independently check a delivery and its signal inputs without changing any run."""

import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import resolve_input
from capsaicin.hash_baseline import check_reference


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    delivery = (ROOT / sys.argv[1]).resolve()
    output = (
        ROOT
        / "02_quality_control"
        / (
            "delivery_verification_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    output.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(output / "verification.json")],
        cwd=ROOT,
        check=True,
    )
    counts = {}
    evidence = {}
    provenance_status_counts = {}

    def check_manifest(path, fields):
        evidence[str(path)] = sha(path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for field in fields:
            for name, digest in manifest.get(field, {}).items():
                target = (
                    path.parent / name
                    if field == "outputs_sha256"
                    else resolve_input(name)
                )
                status = check_reference(path, field, name, digest, target)
                provenance_status_counts[status] = (
                    provenance_status_counts.get(status, 0) + 1
                )
                counts[field] = counts.get(field, 0) + 1
        return manifest

    check_manifest(delivery / "run_manifest.json", ["sources_sha256", "outputs_sha256"])
    index = json.loads((delivery / "module_index.json").read_text(encoding="utf-8"))
    for module in index:
        run = ROOT / module["path"]
        manifest = run / "run_manifest.json"
        if not manifest.exists():
            manifest = run / "review_manifest.json"
        check_manifest(
            manifest,
            ["input_sha256", "inputs_sha256", "outputs_sha256", "signals_sha256"],
        )
    links = re.findall(
        r"\]\(([^)]+)\)", (delivery / "REPORT.md").read_text(encoding="utf-8")
    )
    for link in links:
        if not (delivery / link).exists():
            raise RuntimeError(f"Missing report link: {link}")
    residual = ROOT / next(
        m["path"] for m in index if m["module"] == "remaining_descriptives"
    )
    verifier = ROOT / "scripts/verify_remaining_descriptives.py"
    evidence[str(verifier)] = sha(verifier)
    completed = subprocess.run(
        [sys.executable, str(verifier), str(residual)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    result = dict(
        status="passed",
        created_utc=datetime.now(timezone.utc).isoformat(),
        delivery=str(delivery),
        checked_hashes=counts,
        provenance_status_counts=provenance_status_counts,
        checked_report_links=len(links),
        residual_independent_verification=json.loads(completed.stdout),
        scope="Integrity and numerical agreement; not scientific readiness",
    )
    target = output / "verification.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    evidence[str(Path(__file__).resolve())] = sha(__file__)
    manifest = dict(
        status="completed",
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256=evidence,
        outputs_sha256={"verification.json": sha(target)},
    )
    (output / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    print(output)


if __name__ == "__main__":
    main()
