"""Loopback-only manual review of frozen development tasks; no inference."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import secrets
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "web/review"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def display_points(t, y, limit=6000):
    """Min/max display only; insert breaks before time gaps/nonfinite samples."""
    t, y = np.asarray(t), np.asarray(y)
    if len(t) == 0:
        return [], False
    step = np.median(np.diff(t)) if len(t) > 1 else 0
    cut = (
        np.flatnonzero(
            (np.diff(t) > step * 1.5) | ~np.isfinite(y[:-1]) | ~np.isfinite(y[1:])
        )
        + 1
    )
    bounds = np.r_[0, cut, len(t)]
    stride = max(1, math.ceil(len(t) / (limit / 2)))
    points = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if points:
            points.append([float(t[a]), None])
        for start in range(a, b, stride):
            end = min(b, start + stride)
            values = y[start:end]
            finite = np.flatnonzero(np.isfinite(values))
            if not len(finite):
                points.append([float(t[start]), None])
                continue
            indexes = {
                start,
                end - 1,
                start + int(finite[np.argmin(values[finite])]),
                start + int(finite[np.argmax(values[finite])]),
            }
            for index in sorted(indexes):
                points.append(
                    [
                        float(t[index]),
                        float(y[index]) if np.isfinite(y[index]) else None,
                    ]
                )
    return points, stride > 1


def validate_review(data, task):
    if data.get("status") not in (
        "draft",
        "reviewed",
        "uncertain",
        "unreadable",
        "insufficient",
    ):
        raise ValueError("请选择审核状态")
    if not isinstance(data.get("reviewer"), str) or not data["reviewer"].strip():
        raise ValueError("请填写审核者姓名或代号")
    if len(data["reviewer"]) > 100 or len(str(data.get("notes", ""))) > 10000:
        raise ValueError("文本过长")
    if (
        data["status"] in ("uncertain", "unreadable", "insufficient")
        and not str(data.get("notes", "")).strip()
    ):
        raise ValueError("请在备注中说明原因")
    events = data.get("events", [])
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("事件列表无效")
    lo, hi = task["start"], min(task["end"], task["support_end"])
    peaks = set()
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in (
            "r_peak",
            "artifact",
            "gap",
            "uncertain_interval",
        ):
            raise ValueError("事件类型无效")
        a, b = event.get("start"), event.get("end")
        if not all(
            isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
            for v in (a, b)
        ):
            raise ValueError("事件时间必须为有限数字")
        if not lo <= a <= b <= hi:
            raise ValueError("事件超出任务的实际支持范围")
        if event["type"] == "r_peak":
            if (
                task["signal"] != "ECG"
                or a != b
                or event.get("beat") not in ("normal", "abnormal", "uncertain")
            ):
                raise ValueError("R 峰须为 ECG 点事件并填写搏动类型")
            if a in peaks:
                raise ValueError("同一时间存在重复 R 峰")
            peaks.add(a)
        elif a == b:
            raise ValueError("区间终点须晚于起点")
    return dict(
        status=data["status"],
        reviewer=data["reviewer"].strip(),
        notes=str(data.get("notes", "")),
        events=events,
    )


class ReviewStore:
    def __init__(self, folder, tasks):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.tasks = tasks
        self.lock = threading.Lock()
        self.latest = {}
        for path in sorted(self.folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data["key"] not in tasks
                or data["source_sha256"] != tasks[data["key"]]["source_sha256"]
            ):
                raise ValueError("历史审核与当前任务不匹配")
            self.latest[data["key"]] = data

    def save(self, key, data):
        task = self.tasks[key]
        clean = validate_review(data, task)
        with self.lock:
            current = self.latest.get(key, {})
            if data.get("revision", "") != current.get("revision", ""):
                raise RuntimeError("审核已在另一页面更新，请重新载入后保存")
            clean.update(
                key=key,
                task_id=task["task_id"],
                signal=task["signal"],
                channel=task["channel"],
                source_sha256=task["source_sha256"],
                task_metadata_sha256=task["metadata_sha256"],
                saved_at=utc(),
                revision=uuid.uuid4().hex,
                previous_revision=current.get("revision", ""),
                scope="single_reviewer_development",
            )
            name = (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                + "_"
                + clean["revision"]
            )
            temp = self.folder / (name + ".tmp")
            with temp.open("x", encoding="utf-8") as stream:
                json.dump(clean, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temp.rename(self.folder / (name + ".json"))
            self.latest[key] = clean
            return clean


class Application:
    def __init__(self, handoff):
        self.handoff = handoff
        file = handoff / "development_tasks_private.csv"
        manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
        if digest(file) != manifest["outputs_sha256"][file.name]:
            raise ValueError("任务清单哈希不一致")
        with file.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows or any(row["pool"] != "development" for row in rows):
            raise ValueError("Only development tasks are supported")
        self.tasks = {}
        for row in rows:
            channels = (
                range(1, 43) if row["modality"] == "Hb" else [int(row["channel"])]
            )
            signals = (
                ("HbO", "HbR", "HbT")
                if row["modality"] == "Hb"
                else ("ECG" if row["label"] == "ECG100C" else "EGG",)
            )
            for channel in channels:
                for signal in signals:
                    key = f"{row['task_id']}_{channel}_{signal}"
                    self.tasks[key] = dict(
                        key=key,
                        task_id=row["task_id"],
                        channel=channel,
                        signal=signal,
                        start=float(row["start_s"]),
                        end=float(row["end_s"]),
                        support_end=float(row["recording_support_end_s"]),
                        full_window=row["full_window"] == "True",
                        source_sha256=row["sha256"],
                        metadata_sha256=hashlib.sha256(
                            json.dumps(row, sort_keys=True).encode()
                        ).hexdigest(),
                        row=row,
                    )
        self.store = ReviewStore(handoff / "web_reviews/revisions", self.tasks)
        self.token = secrets.token_urlsafe(32)
        self.cache = None
        self.ecg_groups = {}
        for task in self.tasks.values():
            if task["signal"] == "ECG":
                self.ecg_groups.setdefault(task["task_id"], []).append(task)
        for group in self.ecg_groups.values():
            group.sort(key=lambda task: task["channel"])
        self.ecg_candidate_cache = {}
        self.lock = threading.Lock()

    def public_tasks(self):
        return [
            {
                **{
                    k: v
                    for k, v in t.items()
                    if k not in ("row", "source_sha256", "metadata_sha256")
                },
                "status": self.store.latest.get(key, {}).get("status", "pending"),
            }
            for key, t in self.tasks.items()
        ]

    def series(self, key):
        task = self.tasks[key]
        row = task["row"]
        path = Path(row["path"])
        signature = (str(path), path.stat().st_size, path.stat().st_mtime_ns)
        if self.cache is None or self.cache[0] != signature:
            if digest(path) != row["sha256"]:
                raise ValueError("源文件哈希不匹配，停止显示")
            if row["modality"] == "Hb":
                from run_reanalysis_signals import load_hb

                data = load_hb(path)
            else:
                import bioread

                with path.open("rb") as stream:
                    reader = bioread.reader.Reader(stream)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
            self.cache = signature, data
        data = self.cache[1]
        if row["modality"] == "Hb":
            t, x, groups, _ = data
            index = [ch for ch, _ in groups].index(f"ch-{task['channel']}")
            y = x[:, index, ("HbO", "HbR", "HbT").index(task["signal"])]
            units = "原厂导出值（单位未核实）"
        else:
            ch = data.channels[task["channel"]]
            fs = ch.samples_per_second
            if ch.name != row["label"] or fs != float(row["sampling_hz"]):
                raise ValueError("通道名称或采样率不匹配")
            origin = int(row["source_segment_start_sample"])
            first, last = (
                int(row["source_window_start_sample"]),
                int(row["source_window_end_sample"]),
            )
            if (
                not 0
                <= origin
                <= first
                <= last
                <= int(row["source_segment_end_sample"])
                <= len(ch.data)
            ):
                raise ValueError("样本边界错误")
            t = (np.arange(first, last, dtype=float) - origin) / fs
            y = np.asarray(ch.data[first:last], dtype=float)
            units = ch.units
        mask = (t >= task["start"]) & (t < task["end"])
        return t[mask], y[mask], units

    def trace(self, key, start, end):
        if not (math.isfinite(start) and math.isfinite(end) and start < end):
            raise ValueError("显示时间范围无效")
        task = self.tasks[key]
        start, end = max(start, task["start"]), min(end, task["end"])
        with self.lock:
            t, y, units = self.series(key)
            selected = (t >= start) & (t < end)
            points, compressed = display_points(t[selected], y[selected])
        return dict(
            points=points,
            compressed=compressed,
            samples=int(selected.sum()),
            units=units,
            start=start,
            end=end,
            source_verified=True,
            first_sample=float(t[0]) if len(t) else None,
            last_sample=float(t[-1]) if len(t) else None,
        )

    def ecg_group(self, task_id, start, end):
        """Return all ECG leads plus deterministic, non-adjudicated candidates."""
        if task_id not in self.ecg_groups:
            raise KeyError(task_id)
        group = self.ecg_groups[task_id]
        lo = max(float(task["start"]) for task in group)
        hi = min(float(task["end"]) for task in group)
        if not math.isfinite(start) or not math.isfinite(end) or start >= end:
            raise ValueError("显示时间范围无效")
        start, end = max(start, lo), min(end, hi)
        cache_key = (
            task_id,
            tuple((task["key"], task["source_sha256"]) for task in group),
        )
        if cache_key not in self.ecg_candidate_cache:
            from capsaicin.ecg_candidates import detect_candidates, detect_multilead
            from capsaicin.signal_spectra import resample_exact

            cfg = json.loads(
                (ROOT / "config/ecg_candidates_v1.json").read_text(encoding="utf-8")
            )
            multilead_cfg = json.loads(
                (ROOT / "config/ecg_multilead_v1.json").read_text(encoding="utf-8")
            )
            channels = []
            all_candidates = []
            lead_arrays = []
            for lead_number, task in enumerate(group, 1):
                t, y, units = self.series(task["key"])
                fs = float(task["row"]["sampling_hz"])
                if not len(t) or not np.isfinite(y).all():
                    raise ValueError("ECG 窗口包含缺失或非有限样本，未进行填补")
                sampled = resample_exact(y, fs, cfg["target_rate_hz"])
                lead_arrays.append(sampled)
                # Display-only morphology cleaning. Candidate detection remains
                # on its separate 5-25 Hz spatial-energy branch.
                morphology = multilead_cfg["morphology_reference"]
                band = signal.butter(
                    4,
                    [
                        float(morphology["baseline_highpass_hz"]),
                        float(morphology["lowpass_hz"]),
                    ],
                    btype="bandpass",
                    fs=cfg["target_rate_hz"],
                    output="sos",
                )
                notch_b, notch_a = signal.iirnotch(
                    float(morphology["notch_hz"]) / (cfg["target_rate_hz"] / 2),
                    float(morphology["notch_quality_factor"]),
                )
                notch = signal.tf2sos(notch_b, notch_a)
                display_y = signal.sosfiltfilt(notch, signal.sosfiltfilt(band, sampled))
                display_y = signal.medfilt(
                    display_y,
                    kernel_size=int(
                        morphology["display_median_window_samples_at_250_hz"]
                    ),
                )
                detected = detect_candidates(sampled, cfg["target_rate_hz"], cfg)
                trim = detected["offset_samples"] / cfg["target_rate_hz"]
                amp = (
                    (detected["amplitude"] / cfg["target_rate_hz"]) + float(t[0]) + trim
                )
                energy = (
                    (detected["energy"] / cfg["target_rate_hz"]) + float(t[0]) + trim
                )
                candidates = []
                for method, values in (("amplitude", amp), ("energy", energy)):
                    for value in values:
                        candidates.append(dict(time=float(value), method=method))
                candidates.sort(key=lambda item: item["time"])
                dedup = []
                for item in candidates:
                    if (
                        dedup
                        and item["time"] - dedup[-1]["time"]
                        <= cfg["matching_tolerance_seconds"]
                    ):
                        dedup[-1]["methods"].add(item["method"])
                    else:
                        dedup.append(dict(time=item["time"], methods={item["method"]}))
                for item in dedup:
                    item.update(
                        channel=task["channel"],
                        lead_number=lead_number,
                        method_agreement=len(item["methods"]) == 2,
                    )
                    all_candidates.append(item)
                display_t = (
                    float(t[0])
                    + np.arange(len(display_y), dtype=float) / cfg["target_rate_hz"]
                )
                channels.append(
                    dict(
                        task=task,
                        t=t,
                        y=y,
                        display_t=display_t,
                        display_y=display_y,
                        units=units,
                        candidates=dedup,
                        lead_number=lead_number,
                    )
                )
            multilead = detect_multilead(
                np.asarray(lead_arrays),
                cfg["target_rate_hz"],
                json.loads(
                    (ROOT / "config/ecg_multilead_v1.json").read_text(encoding="utf-8")
                ),
            )
            multilead_times = (multilead["peaks"] / cfg["target_rate_hz"]) + float(
                channels[0]["t"][0]
            )
            # Mark single-lead candidates against the spatial-energy candidate list.
            for channel in channels:
                for item in channel["candidates"]:
                    item["spatial_consensus"] = bool(
                        np.any(
                            np.abs(multilead_times - item["time"])
                            <= cfg["matching_tolerance_seconds"]
                        )
                    )
            all_candidates.sort(key=lambda item: item["time"])
            clusters = []
            for candidate in all_candidates:
                if (
                    clusters
                    and candidate["time"] - clusters[-1]["center"]
                    <= cfg["matching_tolerance_seconds"]
                ):
                    cluster = clusters[-1]
                    cluster["items"].append(candidate)
                    cluster["center"] = float(
                        np.mean([item["time"] for item in cluster["items"]])
                    )
                else:
                    clusters.append(dict(center=candidate["time"], items=[candidate]))
            for cluster in clusters:
                lead_count = len({item["channel"] for item in cluster["items"]})
                method_count = sum(
                    item["method_agreement"] for item in cluster["items"]
                )
                spatial = bool(
                    np.any(
                        np.abs(multilead_times - cluster["center"])
                        <= cfg["matching_tolerance_seconds"]
                    )
                )
                confidence = (
                    "high"
                    if spatial and lead_count >= 2 and method_count >= 1
                    else "medium"
                    if spatial or lead_count >= 2 or method_count
                    else "low"
                )
                cluster["lead_count"] = lead_count
                cluster["confidence"] = confidence
                for item in cluster["items"]:
                    item["confidence"] = confidence
                    item["review_priority"] = confidence != "high"
            self.ecg_candidate_cache[cache_key] = (channels, clusters, multilead_times)
        channels, clusters, multilead_times = self.ecg_candidate_cache[cache_key]
        response_channels = []
        for channel in channels:
            selected = (channel["display_t"] >= start) & (channel["display_t"] < end)
            points, compressed = display_points(
                channel["display_t"][selected], channel["display_y"][selected]
            )
            candidates = [
                dict(
                    time=item["time"],
                    methods=sorted(item["methods"]),
                    method_agreement=item["method_agreement"],
                    confidence=item.get("confidence", "low"),
                    review_priority=item.get("review_priority", True),
                    channel=channel["task"]["channel"],
                )
                for item in channel["candidates"]
                if start <= item["time"] < end
            ]
            response_channels.append(
                dict(
                    channel=channel["task"]["channel"],
                    lead_number=channel["lead_number"],
                    points=points,
                    compressed=compressed,
                    samples=int(selected.sum()),
                    units=channel["units"],
                    candidates=candidates,
                    display_preprocessing="display only: 250 Hz; 4th-order zero-phase bandpass 0.5-45 Hz plus 50 Hz IIR notch Q=30; 5-sample (20 ms) median de-spike",
                )
            )
        consensus = [
            dict(
                time=float(cluster["center"]),
                lead_count=cluster["lead_count"],
                confidence=cluster["confidence"],
                review_priority=cluster["confidence"] != "high",
            )
            for cluster in clusters
            if start <= cluster["center"] < end
        ]
        spatial_consensus = [
            dict(time=float(value), method="three_lead_spatial_energy")
            for value in multilead_times
            if start <= value < end
        ]
        return dict(
            task_id=task_id,
            start=start,
            end=end,
            channels=response_channels,
            consensus=consensus,
            algorithm="ecg_candidates_v1; candidate-only; human review required",
            spatial_consensus=spatial_consensus,
            preprocessing="display: 2000→250 Hz; 4th-order zero-phase 0.5–45 Hz plus 50 Hz notch Q=30 and 5-sample (20 ms) median de-spike. candidates: separate 3rd-order zero-phase SOS 5–25 Hz spatial-energy branch; 120 ms smoothing; 600 ms background; 250 ms refractory; search-back",
            source_verified=True,
        )


def handler_class(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def reply(
            self, value, code=200, content_type="application/json; charset=utf-8"
        ):
            payload = (
                value
                if isinstance(value, bytes)
                else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def allowed(self, write=False):
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                raise PermissionError("Invalid host")
            if write and (
                self.headers.get("Origin") not in (None, "http://" + expected)
                or self.headers.get("X-Review-Token") != app.token
            ):
                raise PermissionError("Invalid review token")

        def do_GET(self):
            try:
                self.allowed()
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path in ("/", "/app.js", "/style.css"):
                    name = {
                        "/": "index.html",
                        "/app.js": "app.js",
                        "/style.css": "style.css",
                    }[parsed.path]
                    mime = {
                        "/": "text/html",
                        "/app.js": "text/javascript",
                        "/style.css": "text/css",
                    }[parsed.path]
                    return self.reply(
                        (ASSETS / name).read_bytes(),
                        content_type=mime + "; charset=utf-8",
                    )
                if parsed.path == "/api/tasks":
                    return self.reply(dict(tasks=app.public_tasks(), token=app.token))
                if parsed.path == "/api/review":
                    key = query["key"][0]
                    if key not in app.tasks:
                        raise KeyError(key)
                    return self.reply(
                        app.store.latest.get(
                            key,
                            dict(
                                revision="",
                                status="draft",
                                reviewer="",
                                notes="",
                                events=[],
                            ),
                        )
                    )
                if parsed.path == "/api/trace":
                    return self.reply(
                        app.trace(
                            query["key"][0],
                            float(query["start"][0]),
                            float(query["end"][0]),
                        )
                    )
                if parsed.path == "/api/ecg_group":
                    return self.reply(
                        app.ecg_group(
                            query["task"][0],
                            float(query["start"][0]),
                            float(query["end"][0]),
                        )
                    )
                if parsed.path == "/api/export":
                    with app.store.lock:
                        reviews = list(app.store.latest.values())
                    return self.reply(
                        dict(
                            exported_at=utc(),
                            scope="single_reviewer_development",
                            reviews=reviews,
                        )
                    )
                self.reply(dict(error="Not found"), 404)
            except PermissionError as exc:
                self.reply(dict(error=str(exc)), 403)
            except Exception as exc:
                self.reply(dict(error=str(exc)), 400)

        def do_POST(self):
            try:
                self.allowed(write=True)
                if self.path != "/api/review":
                    return self.reply(dict(error="Not found"), 404)
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0 or length > 2000000:
                    raise ValueError("Request size invalid")
                data = json.loads(self.rfile.read(length))
                self.reply(app.store.save(data["key"], data))
            except RuntimeError as exc:
                self.reply(dict(error=str(exc)), 409)
            except PermissionError as exc:
                self.reply(dict(error=str(exc)), 403)
            except Exception as exc:
                self.reply(dict(error=str(exc)), 400)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    app = Application(args.handoff.resolve())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_class(app))
    session = (
        app.handoff
        / "web_reviews"
        / (
            "session_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:6]
        )
    )
    session.mkdir()
    code = [
        Path(__file__),
        *ASSETS.iterdir(),
        ROOT / "scripts/run_reanalysis_signals.py",
        ROOT / "scripts/run_fnirs_variable_length_roi.py",
        ROOT / "src/capsaicin/ecg_candidates.py",
        ROOT / "src/capsaicin/signal_spectra.py",
        ROOT / "config/ecg_candidates_v1.json",
        ROOT / "config/ecg_multilead_v1.json",
    ]
    for path in code:
        shutil.copyfile(path, session / path.name)
    import importlib.metadata
    import subprocess

    manifest = dict(
        started_at=utc(),
        scope="single_reviewer_development_only",
        url=f"http://127.0.0.1:{args.port}",
        task_sha256=digest(app.handoff / "development_tasks_private.csv"),
        python=sys.version,
        platform=platform.platform(),
        versions={
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "bioread")
        },
        git_revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        code_sha256={str(p.relative_to(ROOT)): digest(p) for p in code},
        persistence="immutable revision files; optimistic concurrency; no source writes",
    )
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(manifest["url"], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
