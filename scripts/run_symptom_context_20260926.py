"""Recalculate coded symptom cooccurrence; rule alignment is never diagnosis."""

import sys
import json
import uuid
import re
import ast
import importlib.util
from pathlib import Path
from collections import Counter
import numpy as np
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

LEGACY = ROOT / "resources/legacy_codebook"


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("symptom_context_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cp = LEGACY / "constants.json"
    if not cp.exists():
        cp = LEGACY / "analysis/config/constants.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    sym = cfg["symptom_code_map"]
    reg = cfg["region_code_map"]
    composite = cfg["composite_region_codes"]
    # Load only the reviewed pure matching module; never the legacy CLI/repair pipeline.
    mp = LEGACY / "analysis/rome_matcher.py"
    spec = importlib.util.spec_from_file_location("reviewed_rome_matcher", mp)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rp = LEGACY / "analysis/rome_rules.py"
    tree = ast.parse(rp.read_text(encoding="utf-8"))
    rules = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ROME_RULES" for t in n.targets)
    )
    rows = read(run / "BaselineData_person_private.csv")
    marginal = Counter()
    edges = Counter()
    patterns = Counter()
    mapping = []
    unknown = []
    for r in rows:
        ss = set(re.sub(r"[;,|/\s]+", "", r["Symptom_codes"]))
        raw = re.sub(r"\.0+$", "", r["Region_code"])
        rr = set(composite.get(raw, list(raw)))
        if ss - set(sym) or rr - set(reg):
            unknown.append(
                dict(
                    person_id=r["ID"],
                    symptoms="".join(sorted(ss - set(sym))),
                    regions="".join(sorted(rr - set(reg))),
                )
            )
        ss &= set(sym)
        rr &= set(reg)
        for s in ss:
            marginal[("symptom", s, sym[s])] += 1
        for v in rr:
            marginal[("region", v, reg[v])] += 1
        for s in ss:
            for v in rr:
                edges[(s, v)] += 1
        if r["Symptom_codes"] and r["Region_code"]:
            matches = module.rome_map([sym[s] for s in ss], [reg[v] for v in rr], rules)
            for match in matches:
                patterns[match["disease"]] += 1
                mapping.append(
                    dict(
                        person_id=r["ID"],
                        pattern=match["disease"],
                        score=match["score"],
                        interpretation="rule_alignment_only_not_diagnosis",
                    )
                )
    write(
        out / "marginal_counts.csv",
        [
            dict(
                kind=k[0],
                code=k[1],
                label=k[2],
                count=n,
                cohort_denominator=len(rows),
                field_observed_denominator=sum(
                    bool(r["Symptom_codes"] if k[0] == "symptom" else r["Region_code"])
                    for r in rows
                ),
            )
            for k, n in sorted(marginal.items())
        ],
    )
    write(
        out / "symptom_region_cooccurrence.csv",
        [
            dict(
                symptom=sym[s],
                region=reg[v],
                count=n,
                paired_observed_denominator=sum(
                    bool(r["Symptom_codes"] and r["Region_code"]) for r in rows
                ),
                interpretation="same-person set cooccurrence, no symptom-specific location claim",
            )
            for (s, v), n in sorted(edges.items())
        ],
    )
    write(
        out / "rome_alignment_counts.csv",
        [
            dict(
                pattern=k,
                count=n,
                role="descriptive_legacy_rule_alignment_not_diagnosis",
            )
            for k, n in patterns.items()
        ],
    )
    write(out / "rome_alignment_private.csv", mapping)
    write(out / "unknown_codes_private.csv", unknown)
    baseline = []
    for field in ["Age", "Height_cm", "Weight_kg", "BMI", "CCEI", "AES"]:
        values = []
        for r in rows:
            try:
                v = float(r[field])
                if np.isfinite(v):
                    values.append(v)
            except ValueError:
                pass
        baseline.append(
            dict(
                field=field,
                n=len(values),
                missing=len(rows) - len(values),
                mean=float(np.mean(values)),
                sd=float(np.std(values, ddof=1)),
                median=float(np.median(values)),
                q25=float(np.quantile(values, 0.25)),
                q75=float(np.quantile(values, 0.75)),
            )
        )
    write(out / "baseline_continuous.csv", baseline)
    cats = []
    for field in [
        "Sex",
        "Alcohol_consumption",
        "Baseline_GI_symptoms",
        "Spicy_food_frequency",
        "Additional_symptoms",
    ]:
        for value, n in Counter(r[field] for r in rows).items():
            cats.append(dict(field=field, value=value, count=n, denominator=len(rows)))
    write(out / "baseline_categorical.csv", cats)
    for p in [cp, mp, rp, Path(__file__)]:
        (out / p.name).write_bytes(p.read_bytes())
    dump(
        out / "manifest.json",
        dict(
            status="completed_descriptive",
            sources_sha256={
                str(p): sha(p)
                for p in [
                    cp,
                    mp,
                    rp,
                    run / "BaselineData_person_private.csv",
                    Path(__file__),
                ]
            },
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out, flush=True)


if __name__ == "__main__":
    main()
