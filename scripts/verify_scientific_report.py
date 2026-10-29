"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def r_lock_check(packages, versions):
    import json
    import os
    import subprocess

    lib = "/home/fedora/project/.r-library-20261003-v1"
    expression = (
        ".libPaths(c("
        + json.dumps(lib)
        + ", .libPaths())); pk <- c("
        + ",".join((json.dumps(p) for p in packages))
        + '); v <- vapply(pk, function(p) as.character(utils::packageDescription(p,fields="Version")), character(1)); cat(jsonlite::toJSON(list(R=as.character(getRversion()),library=.libPaths()[1],versions=as.list(v)),auto_unbox=TRUE))'
    )
    env = os.environ.copy()
    env.update(
        R_LIBS_USER=lib,
        LC_ALL="C",
        LANG="C",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    p = subprocess.run(
        ["/usr/bin/Rscript", "--vanilla", "-e", expression],
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    result = json.loads(p.stdout)
    assert result["R"] == "4.6.1" and result["library"] == lib
    assert result["versions"] == dict(zip(packages, versions))
    return result
