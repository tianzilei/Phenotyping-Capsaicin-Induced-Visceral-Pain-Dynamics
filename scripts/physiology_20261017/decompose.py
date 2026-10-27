"""Separate sample restriction, re-scaling and time changes; no new tests."""

from pathlib import Path
import importlib.util
import sys
import json

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
from runtime import locations, start_run, require_missing

ROOT, OUT, CFG, CONFIG_PATH = locations("extension")
s = importlib.util.spec_from_file_location(
    "ext", Path(__file__).with_name("run_extension.py")
)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
require_missing(
    OUT, ["sample_scale_timing_decomposition.csv", "decomposition_manifest.json"]
)
h, e = m.scenario_data()
old = pd.read_csv(m.OUT / "fixed_support_timing.csv")
nominal = m.read(m.S["associations"] / "model_input_private.csv")
records = []
for frame in [h, e]:
    for (roi, metric), data in frame.groupby(["roi", "metric"]):
        base = data[
            (data.support_spec == "A") & (data.offset_s == 0) & (data.drift_ppm == 0)
        ].copy()
        base = m.keep_people(base, ["value", "vas_mean"])
        original = nominal[(nominal.roi == roi) & (nominal.metric == metric)][
            ["person_id", "block", "value"]
        ].rename(columns={"value": "inherited_scale_value"})
        base = base.merge(original, on=["person_id", "block"], validate="one_to_one")
        for (spec, offset, drift), scene in data.groupby(
            ["support_spec", "offset_s", "drift_ppm"]
        ):
            record = dict(
                roi=roi,
                metric=metric,
                support_spec=spec,
                offset_s=offset,
                drift_ppm=drift,
            )
            ref = old[
                (old.roi == roi)
                & (old.metric == metric)
                & (old.support_spec == spec)
                & (old.offset_s == offset)
                & (old.drift_ppm == drift)
            ].iloc[0]
            if ref.status != "estimated":
                records.append(dict(**record, status="not_estimable"))
                continue
            z = base.merge(
                scene,
                on=["person_id", "block"],
                suffixes=("_n", "_s"),
                validate="one_to_one",
            )
            z = z[
                np.isclose(z.vas_mean_n, z.vas_mean_s, atol=1e-12)
                & z.minutes_n.eq(z.minutes_s)
            ]
            z = m.keep_people(
                z, ["value_n", "value_s", "vas_mean_n", "inherited_scale_value"]
            )
            if roi != "ECG":
                sd = z.groupby("person_id").value_n.transform("std")
                z = m.keep_people(z.assign(eligible_scale=1 / sd), ["eligible_scale"])
            d = z[["person_id", "block"]].copy()
            d["value"] = z.inherited_scale_value
            d["vas_mean"] = z.vas_mean_n
            r, _ = m.estimate(d, loo=False)
            assert (
                r["n_people"] == ref.common_people
                and r["n_blocks"] == ref.common_blocks
            )
            records.append(
                dict(
                    **record,
                    status="estimated",
                    common_people=r["n_people"],
                    common_blocks=r["n_blocks"],
                    beta_original=ref.beta_nominal_original,
                    beta_common_inherited_scale=r["beta"],
                    beta_common_fixed_common_scale=ref.beta_nominal_common,
                    beta_shifted_same_common_scale=ref.beta_shifted_common,
                    delta_sample_restriction=r["beta"] - ref.beta_nominal_original,
                    delta_scale=ref.beta_nominal_common - r["beta"],
                    delta_timing=ref.delta_timing_fixed_scale,
                    ci95_common_inherited_low=r["ci95_low"],
                    ci95_common_inherited_high=r["ci95_high"],
                )
            )
m.save("sample_scale_timing_decomposition.csv", records)
(m.OUT / "decomposition_manifest.json").write_text(
    json.dumps(
        {
            "code_sha256": m.sha(__file__),
            "inputs_sha256": m.INPUTS,
            "role": "descriptive decomposition; no new hypotheses; support matches frozen B intersections",
            "output_sha256": m.sha(m.OUT / "sample_scale_timing_decomposition.csv"),
            "rows": len(records),
        },
        indent=2,
    )
    + "\n"
)
print("Sample/scale/time decomposition completed:", len(records))
