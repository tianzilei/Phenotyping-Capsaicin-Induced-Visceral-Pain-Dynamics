"""Portable, isolated R subprocess execution; no implicit R or library discovery."""

from __future__ import annotations
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
import psutil


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def run_process(command, *, cwd, env, timeout, rss_limit):
    """Dask's worker RSS omits R children; bound the subprocess tree separately."""
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    peak = 0
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                parent = psutil.Process(process.pid)
                processes = [parent, *parent.children(recursive=True)]
                rss = sum(p.memory_info().rss for p in processes if p.is_running())
                peak = max(peak, rss)
                if rss > rss_limit:
                    raise MemoryError("R subprocess tree exceeded frozen RSS limit")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                if process.poll() is None:
                    raise
            try:
                stdout, stderr = process.communicate(
                    timeout=min(0.5, timeout - elapsed)
                )
                result = subprocess.CompletedProcess(
                    command, process.returncode, stdout, stderr
                )
                result.peak_sampled_R_RSS = peak
                return result
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        try:
            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True):
                child.kill()
        except psutil.NoSuchProcess:
            pass
        if process.poll() is None:
            process.kill()
        process.communicate()
        raise


def execute_r(runtime, assets, expected_hashes, request):
    """Infrastructure errors raise; estimator failures are recorded by the R backend.

    Requests contain explicit subject indices and logical seeds. Each invocation
    gets an exclusive directory; neither old scripts nor prior outputs are run.
    """
    rscript = Path(runtime["rscript"])
    library = Path(runtime["library"])
    if not rscript.is_file() or not library.is_dir():
        raise ValueError("Explicit Rscript or R library is unavailable")
    if set(assets) != set(expected_hashes):
        raise ValueError("R asset roster mismatch")
    for name, data in assets.items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe R asset path")
        if sha_bytes(data) != expected_hashes[name]:
            raise ValueError("R asset hash mismatch: " + name)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="capsaicin-r-") as tmp:
        directory = Path(tmp)
        for name, data in assets.items():
            p = directory / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("xb") as handle:
                handle.write(data)
        request_bytes = canonical(request)
        with (directory / "request.json").open("xb") as handle:
            handle.write(request_bytes)
        env = dict(
            os.environ,
            R_LIBS_USER=str(library),
            LC_ALL="C",
            LANG="C",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            BLIS_NUM_THREADS="1",
            NUMEXPR_NUM_THREADS="1",
        )
        process = run_process(
            [
                str(rscript),
                "--vanilla",
                "R/distributed_vas_backend.R",
                "request.json",
                "result.json",
                str(library),
            ],
            cwd=directory,
            env=env,
            timeout=runtime.get("timeout_seconds", 1800),
            rss_limit=runtime.get("subprocess_rss_limit_bytes", 1536 * 1024**2),
        )
        if process.returncode:
            raise RuntimeError("R process failed: " + process.stderr[-4000:])
        result_path = directory / "result.json"
        if not result_path.is_file():
            raise RuntimeError("R process produced no result")
        result = json.loads(result_path.read_bytes())
        if result.get("task") != request["task"]:
            raise ValueError("R result task mismatch")
        return dict(
            task=request["task"],
            request_sha256=sha_bytes(request_bytes),
            assets_sha256=expected_hashes,
            result=result,
            stdout=process.stdout,
            stderr=process.stderr,
            peak_sampled_R_RSS=process.peak_sampled_R_RSS,
            seconds=time.monotonic() - started,
        )
