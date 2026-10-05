"""Full native ECG/EGG and official-Hb screening under frozen exploratory rules."""

import sys
import json
import os
import time
import uuid
import warnings
import hashlib
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
from scipy import signal
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import resolve_input
from capsaicin.fnirs_source_selection import adjudicate_mapping
from capsaicin.acq_source_selection import adjudicate_acq
from capsaicin.acq_segments import segment_bounds
from capsaicin.reanalysis import (
    match_peaks,
    rr_metrics,
    vas_support,
    time_weights,
    source_mapping_admission,
    normalize_source_mapping_row,
)
from capsaicin.reanalysis_signals import (
    derivative_flags,
    egg_spectrum,
    hb_mean,
    hb_means_matrix,
    longest_bad_seconds,
)
from capsaicin.signal_spectra import resample_exact
from run_fnirs_variable_length_roi import parse_channel_groups


def load_hb(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        header = [f.readline().rstrip("\r\n") for _ in range(35)]
        groups = parse_channel_groups(header[33].split("\t"))
        matrix = np.genfromtxt(f, delimiter="\t", invalid_raise=True)
    t = matrix[:, 0]
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("invalid_Hb_time")
    x = np.stack([matrix[:, j : j + 3] for ch, j in groups], axis=1)
    return t, x, groups, header


def scenarios(cfg):
    return [(s, 0) for s in cfg["windows"]["offset_seconds"]] + [
        (0, d) for d in cfg["windows"]["drift_ppm"] if d
    ]


def main():
    run = Path(sys.argv[1]).resolve()
    mode = sys.argv[2]
    out = run / (mode + "_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cfg = json.loads((run / "frozen_config.json").read_text(encoding="utf-8"))
    aliases = json.loads((run / "aliases_private.json").read_text(encoding="utf-8"))
    vas = {r["ID"]: r for r in read(run / "BaselineData_person_private.csv")}
    loc = json.loads((ROOT / "config/data_locations.json").read_text(encoding="utf-8"))
    admission = cfg.get("source_mapping_admission_config")
    if admission is None:
        raise ValueError("Prepare a run with frozen source admission first")
    all_mapping = [normalize_source_mapping_row(r) for r in read(loc["mapping"])]
    mapping_audit = []
    for row in all_mapping:
        ok, reason = source_mapping_admission(row, admission)
        mapping_audit.append(
            {
                **row,
                "admission_status": "main_analysis_candidate" if ok else "audit_only",
                "admission_reason": reason,
            }
        )
    mapping = [
        r for r in mapping_audit if r["admission_status"] == "main_analysis_candidate"
    ]
    wanted = ".txt" if mode == "hb" else ".acq"
    mapping = [r for r in mapping if r["extension"].lower() == wanted]
    # E and N/C are distinct acquisition stages.  The signal modules below
    # analyze the E-stage recording; retain the full E/N/C admission audit.
    mapping = [r for r in mapping if r["stage"] == "E"]
    if mode == "hb":
        mapping, decisions, evidence = adjudicate_mapping(
            mapping, cfg.get("fnirs_source_adjudication")
        )
    elif cfg.get("acq_source_selection"):
        mapping, decisions, evidence = adjudicate_acq(
            mapping, cfg["acq_source_selection"]
        )
    else:
        decisions = []
        evidence = []
    write(out / "adjudication_private.csv", decisions)
    segment_choices = {
        str(Path(d["path"]).resolve()).casefold(): d["selected_segment"]
        for d in decisions
        if d.get("selected") and d.get("selected_segment")
    }
    byperson = defaultdict(list)
    sources = {}
    audit = []
    features = []
    channels = []
    failures = []
    for r in mapping:
        person = aliases.get(r["current_subject_id"], r["current_subject_id"])
        if person not in vas:
            continue
        path = resolve_input(r["path"])
        byperson[person].append(path)
    # Shared physical files cannot be counted as independent people.
    owners = defaultdict(set)
    for sid, pp in byperson.items():
        for p in pp:
            owners[str(p)].add(sid)
    state = dict(
        status="running",
        mode=mode,
        started=time.time(),
        config_sha256=sha(run / "frozen_config.json"),
        source_admission_semantic_sha256=hashlib.sha256(
            json.dumps(admission, sort_keys=True).encode()
        ).hexdigest(),
        input_sha256={
            str(p): sha(p)
            for p in [
                run / "BaselineData_person_private.csv",
                Path(loc["mapping"]),
                run / "aliases_private.json",
                ROOT / "config/data_locations.json",
            ]
            + evidence
        },
        code_sha256={
            str(p): sha(p)
            for p in [
                Path(__file__),
                ROOT / "src/capsaicin/reanalysis_signals.py",
                ROOT / "src/capsaicin/reanalysis.py",
                ROOT / "src/capsaicin/acq_source_selection.py",
                ROOT / "src/capsaicin/acq_segments.py",
            ]
        },
        sources_sha256=sources,
        reference_validation="not_annotated",
    )
    for p in [
        Path(__file__),
        ROOT / "src/capsaicin/reanalysis_signals.py",
        ROOT / "src/capsaicin/reanalysis.py",
    ]:
        (out / p.name).write_bytes(p.read_bytes())
    dump(out / "frozen_config.json", cfg)

    def save():
        write(out / "source_mapping_admission_private.csv", mapping_audit)
        write(out / "record_audit_private.csv", audit)
        write(out / "features_private.csv", features)
        write(out / "channels_private.csv", channels)
        write(out / "failures_private.csv", failures)
        dump(out / "manifest.json", state)

    if mode == "hb":
        roi = defaultdict(set)
        for r in read(
            ROOT / "00_protocol/acquisition_qc_20260919/data/16_fnirs_channel_qc.csv"
        ):
            if r["roi_label"]:
                roi[r["channel_id"]].add(r["roi_label"])
        if any(len(v) != 1 for v in roi.values()):
            raise ValueError("Conflicting channel ROI")
        rois = defaultdict(list)
        for ch, labels in roi.items():
            rois[next(iter(labels))].append(ch)
    else:
        import neurokit2 as nk
        import bioread
    for number, (sid, paths) in enumerate(sorted(byperson.items()), 1):
        if time.time() - state["started"] > cfg["timeout_seconds_per_module"]:
            raise TimeoutError("Module timeout")
        try:
            unique = {}
            for p in sorted(set(paths)):
                if len(owners[str(p)]) > 1:
                    raise ValueError("unresolved_cross_person_file_ownership")
                h = sha(p)
                sources[str(p)] = h
                unique.setdefault(h, p)
            pp = list(unique.values())
            if mode == "hb":
                candidates = [(p, *load_hb(p)) for p in pp]
                candidates.sort(key=lambda z: len(z[1]), reverse=True)
                p, t, x, cgroups, header = candidates[0]
                for other, ot, ox, og, oh in candidates[1:]:
                    if (
                        og != cgroups
                        or not np.array_equal(t[: len(ot)], ot)
                        or not np.array_equal(x[: len(ot)], ox, equal_nan=True)
                    ):
                        raise ValueError("unresolved_nonidentical_Hb_sources")
                fs = 1 / np.median(np.diff(t))
                record = sources[str(p)][:16]
                audit.append(
                    dict(
                        person_id=sid,
                        recording_id=record,
                        path=str(p),
                        sha256=sources[str(p)],
                        status="read",
                        samples=len(t),
                        sampling_hz=fs,
                        start=t[0],
                        end=t[-1],
                        source_copies=len(paths),
                        canonical_rule="adjudication_then_verified_identical_prefix_longest",
                        units="official_relative_scale_unverified",
                        optical_quality="not_applicable_Hb_only",
                        software_metadata=" | ".join(header[:10]),
                    )
                )
                masks = {}
                # Candidate combinations pre-specified, never selected using VAS.
                for mad, guard in [(6, 2), (8, 2), (6, 5)]:
                    masks[(mad, guard)] = np.stack(
                        [
                            np.stack(
                                [
                                    derivative_flags(x[:, j, k], fs, mad, guard)
                                    for k in [0, 1]
                                ],
                                axis=1,
                            )
                            for j in range(x.shape[1])
                        ],
                        axis=1,
                    )
                gap = np.r_[False, np.diff(t) > 1.5 / fs]
                for m in masks.values():
                    m[gap, :, :] = True
                name_to_j = {ch: j for j, (ch, _) in enumerate(cgroups)}
                for spec in ["A", "B"]:
                    supports = [
                        s for b in range(4) if (s := vas_support(vas[sid], b, spec))
                    ]
                    for offset, drift in scenarios(cfg):
                        for mad, guard in [(6, 2), (8, 2), (6, 5)]:
                            mask = masks[(mad, guard)]
                            cache = {}
                            for s in supports:
                                a = (s["start_s"] + offset) * (1 + drift / 1e6)
                                b = (s["end_s"] + offset) * (1 + drift / 1e6)
                                if a < t[0] - 1 / fs or b > t[-1] + 1 / fs:
                                    continue
                                mm, cc, vv = hb_means_matrix(t, x, mask, a, b)
                                for j, (ch, _) in enumerate(cgroups):
                                    for k, metric in enumerate(["HbO", "HbR"]):
                                        z = dict(
                                            mean=float(mm[j, k])
                                            if np.isfinite(mm[j, k])
                                            else None,
                                            coverage=float(cc[j, k]),
                                        )
                                        cache[(s["block"], ch, metric)] = z
                                        if (
                                            offset == 0
                                            and drift == 0
                                            and spec == "A"
                                            and mad == 6
                                            and guard == 2
                                        ):
                                            channels.append(
                                                dict(
                                                    person_id=sid,
                                                    recording_id=record,
                                                    block=s["block"],
                                                    channel=ch,
                                                    metric=metric,
                                                    longest_bad_seconds=longest_bad_seconds(
                                                        ~vv[:, j, k], fs
                                                    ),
                                                    **z,
                                                )
                                            )
                            for coverage, fraction in [
                                (0.9, 0.5),
                                (0.95, 0.5),
                                (0.9, 0.75),
                            ]:
                                for label, members in rois.items():
                                    for metric in ["HbO", "HbR"]:
                                        valid_blocks = [
                                            s
                                            for s in supports
                                            if any(
                                                (s["block"], ch, metric) in cache
                                                for ch in members
                                            )
                                        ]
                                        common = (
                                            [
                                                ch
                                                for ch in members
                                                if all(
                                                    cache.get(
                                                        (s["block"], ch, metric), {}
                                                    ).get("coverage", 0)
                                                    >= coverage
                                                    for s in valid_blocks
                                                )
                                            ]
                                            if valid_blocks
                                            else []
                                        )
                                        minimum = int(np.ceil(fraction * len(members)))
                                        for s in valid_blocks:
                                            eligible = len(common) >= minimum
                                            values = (
                                                [
                                                    cache[(s["block"], ch, metric)][
                                                        "mean"
                                                    ]
                                                    for ch in common
                                                ]
                                                if eligible
                                                else []
                                            )
                                            features.append(
                                                dict(
                                                    person_id=sid,
                                                    recording_id=record,
                                                    **s,
                                                    offset_s=offset,
                                                    drift_ppm=drift,
                                                    mad=mad,
                                                    guard_s=guard,
                                                    coverage_threshold=coverage,
                                                    roi_fraction=fraction,
                                                    roi=label,
                                                    metric=metric,
                                                    value=float(np.mean(values))
                                                    if values
                                                    else None,
                                                    common_channels=";".join(common),
                                                    n_common=len(common),
                                                    n_prespecified=len(members),
                                                    algorithm_candidate_pass=eligible,
                                                    validation_status="not_independently_validated",
                                                    primary_inference_eligible=False,
                                                )
                                            )
            else:
                if len(pp) != 1:
                    raise ValueError(
                        "multiple_nonidentical_ACQ_sources_no_recording_choice"
                    )
                p = pp[0]
                record = sources[str(p)][:16]
                with p.open("rb") as f:
                    reader = bioread.reader.Reader(f)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
                ecgs = []
                eggs = []
                for j, ch in enumerate(data.channels):
                    if ch.name not in ["ECG100C", "EGG100C"]:
                        continue
                    fs = ch.samples_per_second
                    decision = segment_choices.get(str(p.resolve()).casefold())
                    starts = [
                        m.sample_index
                        for m in data.event_markers
                        if m.type_code == "apnd"
                    ]
                    first, last = segment_bounds(len(ch.data), fs, starts, decision)
                    raw = np.asarray(ch.data[first:last], float)
                    audit.append(
                        dict(
                            person_id=sid,
                            recording_id=record,
                            path=str(p),
                            sha256=sources[str(p)],
                            channel=j,
                            label=ch.name,
                            samples=len(raw),
                            sampling_hz=fs,
                            units=ch.units,
                            status="read",
                            origin="selected_challenge_segment_start"
                            if decision
                            else "recording_start_is_dose",
                            source_start_sample=first,
                            source_end_sample=last,
                        )
                    )
                    if (
                        ch.units != "mV"
                        or not np.isfinite(raw).all()
                        or np.ptp(raw) == 0
                    ):
                        failures.append(
                            dict(
                                person_id=sid,
                                channel=j,
                                reason="unit_nonfinite_or_constant",
                            )
                        )
                        continue
                    if ch.name == "ECG100C":
                        y = resample_exact(raw, fs, 250)
                        y, inversion = nk.ecg_invert(y, sampling_rate=250, force=False)
                        peaks = []
                        for method in cfg["ecg"]["methods"]:
                            clean = nk.ecg_clean(y, sampling_rate=250, method=method)
                            _, info = nk.ecg_peaks(
                                clean,
                                sampling_rate=250,
                                method=method,
                                correct_artifacts=False,
                            )
                            candidate = info["ECG_R_Peaks"] / 250
                            # Original-rate local absolute extremum; matched detections remain candidates.
                            refined = []
                            for tt in candidate:
                                center = int(round(tt * fs))
                                rad = int(0.05 * fs)
                                a = max(0, center - rad)
                                b = min(len(raw), center + rad + 1)
                                refined.append(
                                    (a + np.argmax(abs(raw[a:b] - np.median(raw[a:b]))))
                                    / fs
                                )
                            peaks.append(np.unique(refined))
                        pairs = match_peaks(*peaks, 0.05)
                        den = len(peaks[0]) + len(peaks[1])
                        f1 = 2 * len(pairs) / den if den else None
                        agree = np.zeros(len(peaks[0]), bool)
                        if pairs:
                            agree[[a for a, b in pairs]] = True
                        ecgs.append(
                            dict(
                                channel=j,
                                peaks=peaks[0],
                                good=agree,
                                agreement=f1,
                                duration=len(raw) / fs,
                            )
                        )
                        channels.append(
                            dict(
                                person_id=sid,
                                recording_id=record,
                                channel=j,
                                metric="ECG_detector_agreement",
                                agreement_50ms=f1,
                                agreement_25ms=2 * len(match_peaks(*peaks, 0.025)) / den
                                if den
                                else None,
                                peaks_primary=len(peaks[0]),
                                peaks_secondary=len(peaks[1]),
                                inverted=bool(inversion),
                            )
                        )
                        np.savez_compressed(
                            out / f"{record}_ecg_c{j}_peaks_private.npz",
                            primary=peaks[0],
                            secondary=peaks[1],
                            matched=agree,
                        )
                    else:
                        y = resample_exact(raw, fs, 10)
                        # Wide raw derivative screen propagated through antialiasing; no gastric-band QC.
                        raw_bad = derivative_flags(raw, fs, 8, 2)
                        bad = np.array(
                            [
                                raw_bad[
                                    int(k * fs / 10) : max(
                                        int((k + 1) * fs / 10), int(k * fs / 10) + 1
                                    )
                                ].any()
                                for k in range(len(y))
                            ]
                        )
                        eggs.append(
                            dict(channel=j, y=y, bad=bad, duration=len(raw) / fs)
                        )
                best = (
                    max(
                        ecgs,
                        key=lambda r: (
                            r["agreement"] if r["agreement"] is not None else -1,
                            -r["channel"],
                        ),
                    )
                    if ecgs
                    else None
                )
                for spec in ["A", "B"]:
                    for block in range(4):
                        s = vas_support(vas[sid], block, spec)
                        if not s:
                            continue
                        for offset, drift in scenarios(cfg):
                            a = (s["start_s"] + offset) * (1 + drift / 1e6)
                            b = (s["end_s"] + offset) * (1 + drift / 1e6)
                            base = dict(
                                person_id=sid,
                                recording_id=record,
                                **s,
                                offset_s=offset,
                                drift_ppm=drift,
                                validation_status="not_independently_validated",
                                primary_inference_eligible=False,
                            )
                            if best and a >= 0 and b <= best["duration"]:
                                select = (best["peaks"] > a) & (best["peaks"] <= b)
                                z = rr_metrics(
                                    best["peaks"][select], best["good"][select]
                                )
                                coverage = z["valid_rr_seconds"] / (b - a)
                                for metric, value in [
                                    ("HR", z["hr_bpm"]),
                                    ("candidate_RR_RMSSD", z["rr_rmssd_ms"]),
                                ]:
                                    eligible = (
                                        coverage >= 0.9
                                        and (best["agreement"] or 0) >= 0.9
                                        and (metric == "HR" or b - a >= 300)
                                    )
                                    features.append(
                                        dict(
                                            **base,
                                            channel=best["channel"],
                                            metric=metric,
                                            value=value,
                                            coverage=coverage,
                                            rr_count=z["rr_count"],
                                            rr_pairs=z["rr_pairs"],
                                            algorithm_candidate_pass=eligible,
                                            unit="bpm"
                                            if metric == "HR"
                                            else "ms_not_verified_NN",
                                        )
                                    )
                            for egg in eggs:
                                if a < 0 or b > egg["duration"]:
                                    continue
                                ix = (np.arange(len(egg["y"])) / 10 > a) & (
                                    np.arange(len(egg["y"])) / 10 <= b
                                )
                                for seconds in [128, 256]:
                                    z = egg_spectrum(
                                        egg["y"][ix], egg["bad"][ix], 10, seconds
                                    )
                                    features.append(
                                        dict(
                                            **base,
                                            channel=egg["channel"],
                                            metric="EGG",
                                            welch_seconds=seconds,
                                            coverage=float(1 - egg["bad"][ix].mean()),
                                            **z,
                                            algorithm_candidate_pass=False,
                                        )
                                    )
        except Exception as exc:
            failures.append(dict(person_id=sid, reason=f"{type(exc).__name__}: {exc}"))
        if number % 5 == 0 or number == len(byperson):
            save()
            print(
                mode,
                number,
                "/",
                len(byperson),
                "features",
                len(features),
                "failures",
                len(failures),
                flush=True,
            )
    state.update(
        status="completed_unvalidated_screen",
        finished=time.time(),
        summary=dict(
            mapped_people=len(byperson),
            processed_people=len({r["person_id"] for r in audit}),
            feature_rows=len(features),
            failures=len(failures),
            raw_files_hashed=len(sources),
            mapping_rows_total=len(mapping_audit),
            mapping_rows_main_candidate=sum(
                r["admission_status"] == "main_analysis_candidate"
                for r in mapping_audit
            ),
            mapping_rows_audit_only=sum(
                r["admission_status"] == "audit_only" for r in mapping_audit
            ),
            module_selected_mapping_rows=len(mapping),
        ),
    )
    save()
    state["outputs_sha256"] = {
        p.name: sha(p)
        for p in out.iterdir()
        if p.is_file() and p.name != "manifest.json"
    }
    dump(out / "manifest.json", state)
    print(out, flush=True)


if __name__ == "__main__":
    main()
