import sys
import json
import uuid
import os
import subprocess
from pathlib import Path
from prepare_reanalysis_20260926 import ROOT, dump, sha


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("fpca_followup_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cfg = dict(
        bootstrap=500,
        repeats=10,
        folds=5,
        seed=20260926,
        intervals=[[1, 20], [1, 10]],
        role="heldout full-curve reconstruction and complete-case stability, not forecasting",
    )
    dump(out / "frozen_config.json", cfg)
    sources = [
        ROOT / "scripts/run_fpca_followup.R",
        ROOT / "R/fpca_followup.R",
        ROOT / "R/vas_models.R",
        run / "vas_models/vas_long.csv",
    ]
    for p in sources:
        (out / p.name).write_bytes(p.read_bytes())
    with (out / "execution.log").open("w", encoding="utf-8") as log:
        p = subprocess.run(
            [
                "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
                "--vanilla",
                "scripts/run_fpca_followup.R",
                str(run / "vas_models"),
                str(out),
                "500",
                "10",
                "5",
                "20260926",
            ],
            cwd=ROOT,
            env=dict(
                os.environ,
                R_LIBS_USER=str(ROOT / "renv/library/sparse-fpca"),
                LC_ALL="C",
                LANG="C",
            ),
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=3600,
        )
    dump(
        out / "manifest.json",
        dict(
            status="completed" if p.returncode == 0 else "failed",
            exit_code=p.returncode,
            source_sha256={str(p): sha(p) for p in sources},
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out, p.returncode, flush=True)


if __name__ == "__main__":
    main()
