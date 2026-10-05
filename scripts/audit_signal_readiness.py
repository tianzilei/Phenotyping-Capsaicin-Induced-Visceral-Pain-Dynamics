"""Read linked signal metadata and numeric validity; never certify artifact QC."""

import collections
import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
import importlib.metadata
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import h5py
import bioread
from path_resolver import resolve_external_path, execution_config, relocation_evidence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.signal_time import expand_snirf_time


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(p, rows):
    if not rows:
        return
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def scalar(group, name):
    if name not in group:
        return ""
    v = group[name][()]
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, np.ndarray):
        return str(v.tolist())
    return str(v)


def main():
    cp = execution_config(ROOT / "config/remaining_analysis_v1.json")
    cfg = json.loads(cp.read_text(encoding="utf-8"))["signal_audit"]
    mapping = ROOT / cfg["mapping"]
    with mapping.open(encoding="utf-8-sig") as f:
        links = list(csv.DictReader(f))
    assert all(r["stage"] in cfg["allowed_stages"] for r in links)
    paths = sorted(
        {
            r["path"]
            for r in links
            if Path(r["path"]).suffix.lower() in {".acq", ".snirf"}
            and not Path(r["path"]).name.startswith("._")
        }
    )
    out = (
        ROOT
        / "02_quality_control"
        / (
            "signal_readiness_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "recordings_private.csv")],
        cwd=ROOT,
        check=True,
    )
    state = dict(
        status="running",
        config=cfg,
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        input_sha256={
            str(mapping): sha(mapping),
            str(cp): sha(cp),
            str(Path(__file__).resolve()): sha(Path(__file__)),
            str(ROOT / "src/capsaicin/signal_time.py"): sha(
                ROOT / "src/capsaicin/signal_time.py"
            ),
        },
        signals_sha256={},
    )
    state["input_sha256"].update(
        {
            str(p): sha(p)
            for p in relocation_evidence() + [ROOT / "scripts/path_resolver.py"]
        }
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    print(out, flush=True)
    started = time.monotonic()
    records = []
    channels = []
    try:
        for idx, name in enumerate(paths, 1):
            if time.monotonic() - started > 3600:
                raise TimeoutError(
                    "Signal audit exceeded one hour; partial results retained"
                )
            p = resolve_external_path(name)
            if p is None:
                raise FileNotFoundError(name)
            r = dict(
                path=name,
                kind=p.suffix.lower(),
                bytes=p.stat().st_size,
                status="ok",
                detail="",
                n_channels="",
                n_samples="",
                duration_s="",
                sampling_rate_hz="",
                time_unit="",
                duration_native="",
                rate_per_native_time_unit="",
                time_monotonic="",
                nonfinite_values="",
                units="",
                data_types="",
                has_positions="",
                stim_groups="",
                full_signal_artifact_qc="not_performed",
                challenge_alignment="unverified",
            )
            try:
                state["signals_sha256"][name] = sha(p)
                if p.suffix.lower() == ".acq":
                    # Public read_headers consumes some parse exceptions; use the
                    # pinned reader's strict header path so failed reads stay failed.
                    with p.open("rb") as handle:
                        reader = bioread.reader.Reader(handle)
                        reader._read_headers()
                        data = reader.datafile
                    if data is None or not data.channels:
                        raise ValueError("No BIOPAC channels parsed")
                    r["n_channels"] = len(data.channels)
                    for k, c in enumerate(data.channels):
                        rate = getattr(c, "samples_per_second", None)
                        n = getattr(c, "point_count", None)
                        if n is None:
                            n = getattr(getattr(c, "header", None), "point_count", None)
                        channels.append(
                            dict(
                                path=name,
                                channel=k,
                                label=c.name,
                                units=c.units,
                                sampling_rate_hz=rate,
                                n_samples=n,
                                data_type="biopac_header",
                                nonfinite_values="",
                                flat_channel="not_scanned",
                            )
                        )
                    r["n_samples"] = ";".join(str(c.point_count) for c in data.channels)
                    r["duration_s"] = ";".join(
                        str((c.point_count - 1) / c.samples_per_second)
                        for c in data.channels
                    )
                    r["time_unit"] = "s_from_biopac_header"
                    r["units"] = ";".join(str(c.units) for c in data.channels)
                    r["sampling_rate_hz"] = ";".join(
                        str(c.samples_per_second) for c in data.channels
                    )
                else:
                    with h5py.File(p, "r") as f:
                        group = f["nirs"]
                        meta = group.get("metaDataTags", {})
                        r["time_unit"] = scalar(meta, "TimeUnit")
                        r["units"] = scalar(meta, "LengthUnit") + "|" + r["time_unit"]
                        r["has_positions"] = str(
                            any(
                                k in group.get("probe", {})
                                for k in (
                                    "sourcePos3D",
                                    "detectorPos3D",
                                    "sourcePos2D",
                                    "detectorPos2D",
                                )
                            )
                        )
                        r["stim_groups"] = sum(k.startswith("stim") for k in group)
                        data = group["data1"]
                        y = data["dataTimeSeries"]
                        t = np.array(
                            expand_snirf_time(
                                np.asarray(data["time"]).reshape(-1), y.shape[0]
                            )
                        )
                        dt = np.diff(t)
                        r.update(
                            n_channels=y.shape[1],
                            n_samples=y.shape[0],
                            duration_native=float(t[-1] - t[0]),
                            time_monotonic=bool(np.all(dt > 0)),
                            rate_per_native_time_unit=float(1 / np.median(dt))
                            if np.all(dt > 0)
                            else "",
                        )
                        if r["time_unit"].lower() in {"s", "second", "seconds"}:
                            r["duration_s"] = r["duration_native"]
                            r["sampling_rate_hz"] = r["rate_per_native_time_unit"]
                        nonfinite = np.zeros(y.shape[1], dtype=np.int64)
                        lo = np.full(y.shape[1], np.inf)
                        hi = -lo
                        for start in range(0, y.shape[0], 10000):
                            a = np.asarray(y[start : start + 10000])
                            good = np.isfinite(a)
                            nonfinite += (~good).sum(axis=0)
                            lo = np.minimum(
                                lo, np.min(np.where(good, a, np.inf), axis=0)
                            )
                            hi = np.maximum(
                                hi, np.max(np.where(good, a, -np.inf), axis=0)
                            )
                        types = []
                        for k in range(y.shape[1]):
                            ml = data.get("measurementList" + str(k + 1), {})
                            typ = (
                                scalar(ml, "dataType")
                                + ":"
                                + scalar(ml, "dataTypeLabel")
                            )
                            types.append(typ)
                            channels.append(
                                dict(
                                    path=name,
                                    channel=k,
                                    label=scalar(ml, "sourceIndex")
                                    + "-"
                                    + scalar(ml, "detectorIndex"),
                                    units=scalar(ml, "dataUnit"),
                                    sampling_rate_hz=r["sampling_rate_hz"],
                                    n_samples=y.shape[0],
                                    data_type=typ,
                                    nonfinite_values=int(nonfinite[k]),
                                    flat_channel=bool(hi[k] == lo[k]),
                                )
                            )
                        r["data_types"] = ";".join(sorted(set(types)))
                        r["nonfinite_values"] = int(sum(nonfinite))
            except Exception as e:
                r.update(status="inspection_failed", detail=f"{type(e).__name__}: {e}")
            records.append(r)
            if idx % 10 == 0 or idx == len(paths):
                print(idx, "/", len(paths), "inspected", flush=True)
                write(out / "recordings_private.csv", records)
                write(out / "channels_private.csv", channels)
                save()
        summary = dict(
            link_rows=len(links),
            unique_files=len(paths),
            status=dict(collections.Counter(r["status"] for r in records)),
            types=dict(collections.Counter(r["kind"] for r in records)),
            fnirs_data_types=dict(
                collections.Counter(
                    r["data_types"] for r in records if r["kind"] == ".snirf"
                )
            ),
            fnirs_units=dict(
                collections.Counter(
                    c["units"] for c in channels if c["data_type"] != "biopac_header"
                )
            ),
        )
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        (out / "environment.txt").write_text(
            "\n".join(
                sorted(
                    f"{d.metadata['Name']}=={d.version}"
                    for d in importlib.metadata.distributions()
                )
            ),
            encoding="utf-8",
        )
        report = [
            "# 生理信号就绪审计",
            "",
            "本轮读取全部已映射ACQ/SNIRF，排除文件名T阶段；重复路径仅检查一次，保留原映射。此为格式、采样和数值有效性审计，不是伪迹验收，不证明设备与给药时间同步或身份访视已核对。",
            "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            "",
            "逐文件和逐通道表仅本地保存。ACQ只读取原头部采样率/单位；SNIRF扫描整个data1矩阵的非有限值和全程常数通道。SNIRF时间单位unknown时仅报告原生数值时长/倒数步长，不报告为秒或Hz。恒定通道或有限值均不能替代运动/饱和/头皮血流质控。SNIRF已转换容器须核对转换来源和原单位；坐标存在不等于ROI已核验，刺激标记存在不等于给药标记。",
            "",
            "未开展R峰、HRV、胃电谱峰、血氧关联或跨模态耦合；这些仍需明确的信号与科学验收条件。",
        ]
        (out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
        state["status"] = "completed_format_audit_not_scientifically_ready"
    except Exception as e:
        state.update(status="failed", error=str(e))
        raise
    finally:
        state["outputs_sha256"] = {
            p.name: sha(p)
            for p in out.iterdir()
            if p.is_file() and p.name != "run_manifest.json"
        }
        save()


if __name__ == "__main__":
    main()
