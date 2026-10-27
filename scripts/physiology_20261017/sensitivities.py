from analyse import *

if __name__ == "__main__":
    require_missing(
        OUT,
        [
            "timing_support_sensitivity.csv",
            "timing_reproduction_check.csv",
            "Hb_QC_sensitivity.csv",
            "sensitivity_manifest.json",
        ],
    )
    cols = [
        "person_id",
        "block",
        "support_spec",
        "offset_s",
        "drift_ppm",
        "mad",
        "guard_s",
        "coverage_threshold",
        "roi_fraction",
        "roi",
        "metric",
        "value",
        "vas_mean",
        "algorithm_candidate_pass",
        "n_common",
        "n_prespecified",
    ]
    hbpath = S["hb"] / "features_private.csv"
    epath = S["ecg_egg"] / "features_private.csv"
    # Hash both processed feature containers before reading selected rows.
    for path in [hbpath, epath]:
        digest = sha(path)
        manifest = json.loads((path.parent / "manifest.json").read_text())
        wanted = manifest["outputs_sha256"][path.name]
        assert digest == wanted
        INPUTS[str(path)] = digest
    parts = []
    for chunk in pd.read_csv(hbpath, usecols=cols, chunksize=150000):
        d = chunk[
            (chunk.mad == 6)
            & (chunk.guard_s == 2)
            & chunk.algorithm_candidate_pass.astype(str).str.lower().eq("true")
        ]
        parts.append(d)
    h = pd.concat(parts, ignore_index=True)
    e = pd.read_csv(epath, low_memory=False)
    e = e[
        e.metric.isin(["HR", "candidate_RR_RMSSD"])
        & e.algorithm_candidate_pass.astype(str).str.lower().eq("true")
    ].copy()
    e["roi"] = "ECG"
    print(
        "Retained feature rows",
        len(h),
        len(e),
        "coverage",
        sorted(h.coverage_threshold.unique()),
        "ROI fraction",
        sorted(h.roi_fraction.unique()),
        flush=True,
    )
    records = []
    nominal = pd.read_csv(OUT / "all_161_results.csv")
    original = pd.read_csv(S["associations"] / "timing_scenarios.csv")
    compare = []
    for kind, data in [("Hb", h), ("ECG", e)]:
        if kind == "Hb":
            data = data[(data.coverage_threshold == 0.9) & (data.roi_fraction == 0.5)]
        for (roi, metric, spec, offset, drift), d in data.groupby(
            ["roi", "metric", "support_spec", "offset_s", "drift_ppm"]
        ):
            counts = d.groupby("person_id").block.nunique()
            d = d[d.person_id.isin(counts[counts >= 2].index)].copy()
            if kind == "Hb":
                d["value"] = (
                    d.value - d.groupby("person_id").value.transform("mean")
                ) / d.groupby("person_id").value.transform("std")
                d = d[np.isfinite(d.value)]
            p = prepare(d, "value", ["vas_mean"])
            r = fit(p, include_loo=False)
            row = dict(
                roi=roi,
                metric=metric,
                support_spec=spec,
                offset_s=offset,
                drift_ppm=drift,
                n_people=p["G"],
                n_blocks=p["N"],
                beta=r["b"][0],
                ci95_low=r["low"][0],
                ci95_high=r["high"][0],
                p_CR1=r["p"][0],
            )
            records.append(row)
            old = original[
                (original.roi == roi)
                & (original.metric == metric)
                & (original.support_spec == spec)
                & (original.offset_s == offset)
                & (original.drift_ppm == drift)
            ]
            if len(old):
                diff = abs(old.iloc[0].candidate_beta - r["b"][0])
                assert diff < 1e-9
                compare.append(
                    dict(
                        **{
                            k: row[k]
                            for k in [
                                "roi",
                                "metric",
                                "support_spec",
                                "offset_s",
                                "drift_ppm",
                            ]
                        },
                        abs_point_difference=diff,
                    )
                )
    write("timing_support_sensitivity.csv", records)
    write("timing_reproduction_check.csv", compare)
    qc = []
    d = h[(h.support_spec == "A") & (h.offset_s == 0) & (h.drift_ppm == 0)]
    for (roi, metric, coverage, fraction), sub in d.groupby(
        ["roi", "metric", "coverage_threshold", "roi_fraction"]
    ):
        counts = sub.groupby("person_id").block.nunique()
        sub = sub[sub.person_id.isin(counts[counts >= 2].index)].copy()
        sub["value"] = (
            sub.value - sub.groupby("person_id").value.transform("mean")
        ) / sub.groupby("person_id").value.transform("std")
        sub = sub[np.isfinite(sub.value)]
        p = prepare(sub, "value", ["vas_mean"])
        r = fit(p)
        qc.append(
            dict(
                roi=roi,
                metric=metric,
                coverage_threshold=coverage,
                roi_fraction=fraction,
                **row_of(p, r),
            )
        )
    write("Hb_QC_sensitivity.csv", qc)
    print("DONE", len(records), "timing", len(qc), "QC fits", flush=True)
    (OUT / "sensitivity_manifest.json").write_text(
        json.dumps(
            {
                "input_sha256": INPUTS,
                "code_sha256": sha(__file__),
                "output_sha256": {
                    n: sha(OUT / n)
                    for n in [
                        "timing_support_sensitivity.csv",
                        "timing_reproduction_check.csv",
                        "Hb_QC_sensitivity.csv",
                    ]
                },
            },
            indent=2,
        )
    )
