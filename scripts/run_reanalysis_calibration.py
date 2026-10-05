import sys
import subprocess
import json
import os
import uuid
from pathlib import Path
from prepare_reanalysis_20260926 import ROOT, dump, sha


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("cr2_calibration_" + uuid.uuid4().hex[:8])
    out.mkdir()
    sources = [
        ROOT / "scripts/calibrate_reanalysis_CR2.R",
        ROOT / "config/reanalysis_supplement_20260926_v1.json",
        Path(__file__),
    ]
    for p in sources:
        (out / p.name).write_bytes(p.read_bytes())
    state = dict(status="running", inputs_sha256={str(p): sha(p) for p in sources})
    dump(out / "manifest.json", state)
    with (out / "execution.log").open("w", encoding="utf-8") as log:
        p = subprocess.run(
            [
                "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
                "--vanilla",
                "scripts/calibrate_reanalysis_CR2.R",
                str(out),
            ],
            cwd=ROOT,
            env=dict(os.environ, LC_ALL="C", LANG="C"),
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=21600,
        )
    state.update(
        status="completed" if p.returncode == 0 else "failed",
        exit_code=p.returncode,
        outputs_sha256={
            p.name: sha(p)
            for p in out.iterdir()
            if p.is_file() and p.name != "manifest.json"
        },
    )
    dump(out / "manifest.json", state)
    print(out, p.returncode, flush=True)


if __name__ == "__main__":
    main()
