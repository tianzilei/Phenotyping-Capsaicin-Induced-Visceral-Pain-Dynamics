"""Export the final numbered tables from reviewed aggregates without inference."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_inputs(root, config):
    """Reject changed or external inputs before creating an output directory."""
    root = Path(root).resolve()
    for relative, expected in config["input_sha256"].items():
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Input is outside the reviewed repository")
        if sha(path) != expected:
            raise ValueError(f"Reviewed input hash differs: {relative}")


def early_recognition(rows):
    """Select accuracy, preserving the historical equal-fold definition."""
    selected = []
    for row in rows:
        if row["analysis"] != "partition_recovery" or row["cell_k"] != "3":
            continue
        if row["metric"] != "accuracy_equal_fold_mean":
            continue
        if int(float(row["complete_repeats"])) != 20:
            raise ValueError(
                "Incomplete repetition set for the final recognition table"
            )
        interval = int(row["cell_end"])
        selected.append(
            dict(
                interval=interval,
                people={10: 206, 20: 56}[interval],
                groups=3,
                prefix=int(float(row["prefix"])),
                model=row["model"],
                median=row["median"],
                minimum=row["minimum"],
                maximum=row["maximum"],
                complete_repeats=int(float(row["complete_repeats"])),
            )
        )
    order = {
        "training_majority": 0,
        "raw_prefix_logistic": 1,
        "trained_shapelet_logistic": 2,
    }
    selected.sort(key=lambda x: (x["interval"], x["prefix"], order[x["model"]]))
    keys = {(x["interval"], x["prefix"], x["model"]) for x in selected}
    if len(selected) != 16 or len(keys) != 16:
        raise ValueError("Expected all 16 three-group recognition results")
    return selected


def group_sizes(summaries):
    cells = {}
    for source in summaries:
        description = source["cell_description"]
        sizes = source["reference_cluster_sizes"]
        row = dict(
            cell=source["cell"],
            interval_minutes=description["end"],
            transformation=description["transformation"],
            method=description["method"],
            k=description["k"],
            n_people=sum(sizes),
            group_sizes=" / ".join(map(str, sizes)),
        )
        if len(sizes) != row["k"]:
            raise ValueError("Reference group count differs")
        if row["cell"] in cells and cells[row["cell"]] != row:
            raise ValueError("Reference sizes disagree across statistics")
        cells[row["cell"]] = row
    if len(cells) != 48:
        raise ValueError("Expected all 48 reference group specifications")
    return list(cells.values())


def symptom_rules(code, summaries):
    """Read static definitions without importing or executing historical code."""
    tree = ast.parse(code)
    rules = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ROME_RULES" for t in node.targets)
    )
    counts = {x["code"]: x for x in summaries if x["kind"] == "legacy_rule_pattern"}
    if set(counts) != set(rules):
        raise ValueError("Rule definitions and aggregate results differ")
    result = []
    for name, rule in rules.items():
        source = counts[name]
        result.append(
            dict(
                rule=name,
                required_all="; ".join(rule.get("required_all", [])),
                required_any="; ".join(rule.get("required_any", [])),
                required_region_any="; ".join(rule.get("required_region_any", [])),
                supportive_symptoms="; ".join(rule.get("supportive", [])),
                supportive_regions="; ".join(rule.get("supportive_region_any", [])),
                count=source["count"],
                denominator_people=source["denominator_people"],
                proportion=source["point"],
            )
        )
    return result


def cohort_table(supports, baseline):
    lookup = {row["characteristic"]: row for row in baseline}
    sets = {row["analysis_set"]: row for row in supports}
    all_people = sets["All observed records"]
    integer = lambda value: str(int(float(value)))
    result = []

    def add(label, value, observations=""):
        result.append(
            dict(
                characteristic=label,
                participants_or_value=value,
                recorded_scores_or_predictions=observations,
            )
        )

    add(
        "Unique analytic participants",
        all_people["people"],
        f"{all_people['numeric_ratings_in_interval']} ratings, minutes 1–20",
    )
    add(
        "Female / male participants",
        f"{lookup['Recorded sex: 女']['n']} / {lookup['Recorded sex: 男']['n']}",
    )
    for field, label in [
        ("Age", "Age, years, median [first, third quartile]"),
        ("Weight_kg", "Weight, kg, median [first, third quartile]"),
        ("BMI", "Body mass index, kg/m², median [first, third quartile]"),
    ]:
        add(label, lookup[field]["summary"])
    add(
        "Recorded E / T / neither stopping code",
        " / ".join(
            integer(all_people[k])
            for k in ["first_E_people", "first_T_people", "no_marker_people"]
        ),
    )
    for name in ["Complete minutes 1–10", "Complete minutes 1–20"]:
        add(
            name,
            sets[name]["people"],
            f"{sets[name]['numeric_ratings_in_interval']} ratings",
        )
    for label, key in [
        ("Symptom information recorded", "symptom_recorded"),
        ("Region information recorded", "region_recorded"),
        ("Both types of information recorded", "both_recorded"),
    ]:
        add(label, integer(all_people[key]))
    for label, key in [
        ("Next-rating objective", "Next actual rating"),
        ("Minutes 1–5 to minute 10 objective", "Minute 5 prefix to minute 10"),
    ]:
        add(
            label,
            sets[key]["people"],
            f"{sets[key]['numeric_ratings_in_interval']} eligible predictions",
        )
    return result


def module_table(root, rows, budgets):
    """Separate historical plans, completed bootstrap draws and CV repetitions."""
    result = []
    for source in rows:
        row = {
            k: v
            for k, v in source.items()
            if k not in {"planned_replicates", "current_run"}
        }
        row["historical_planned_replicates"] = source["planned_replicates"]
        row["historical_run_reference"] = source["current_run"]
        budget = budgets.get(source["module_id"], {})
        row["actual_bootstrap_replicates_per_specification"] = ""
        row["actual_complete_fpca_replicates_per_interval"] = ""
        row["actual_sparse_fpca_replicates_per_specification"] = ""
        row["validation_repeats"] = budget.get("validation_repeats", "")
        for target, reference in budget.get("bootstrap_sources", {}).items():
            attempts = {x["attempted"] for x in load(root / reference)}
            if len(attempts) != 1:
                raise ValueError(
                    "Bootstrap budgets differ within a final specification family"
                )
            row[target] = attempts.pop()
        row["final_result_sources"] = "; ".join(budget.get("result_sources", []))
        row["final_method_configurations"] = "; ".join(
            budget.get("method_configurations", [])
        )
        result.append(row)
    return result


def export_tables(root, config, destination):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    prior = root / config["prior_tables"]
    aggregate = root / config["prior_aggregates"]
    for path in prior.glob("*.csv"):
        if path.name.startswith(("Table1_", "Table2_", "TableS1_")):
            continue
        shutil.copyfile(path, destination / path.name)
    write_rows(
        destination / "Table1_cohort_and_analysis_sets.csv",
        cohort_table(
            read_rows(prior / "Table1_cohort_and_analysis_sets.csv"),
            read_rows(prior / "TableS11_baseline_descriptive.csv"),
        ),
    )
    write_rows(
        destination / "Table2_early_group_recognition.csv",
        early_recognition(
            read_rows(prior / "TableS10_partition_recovery_and_baseline.csv")
        ),
    )
    write_rows(
        destination / "TableS19_reference_group_sizes.csv",
        group_sizes(load(aggregate / "python_remaining/cluster_summary.json")),
    )
    write_rows(
        destination / "TableS20_descriptive_symptom_region_rules.csv",
        symptom_rules(
            (root / config["rule_definitions"]).read_text(),
            read_rows(prior / "TableS2_recorded_codes_all139.csv"),
        ),
    )
    write_rows(
        destination / "TableS1_all18_modules.csv",
        module_table(
            root,
            read_rows(prior / "TableS1_all18_modules.csv"),
            config["module_reporting"],
        ),
    )
    if len(list(destination.glob("*.csv"))) != 23:
        raise ValueError("Expected three main tables and twenty supporting tables")


def build(root, config_path, output):
    """Render a new directory using only hash-checked, public aggregate inputs."""
    from .final_figures import build as render

    root = Path(root).resolve()
    output = Path(output).resolve()
    config_path = Path(config_path).resolve()
    config = load(config_path)
    if output.exists():
        raise FileExistsError(output)
    for relative in ["data/published", "data/aggregate_sources"]:
        protected = root / relative
        if output == protected or output in protected.parents:
            raise ValueError("Output would contain a protected data directory")
        if output.is_relative_to(root / "data/aggregate_sources"):
            raise ValueError("Outputs cannot replace reviewed inputs")
    verify_inputs(root, config)
    with tempfile.TemporaryDirectory(prefix="capsaicin-final-inputs-") as temporary:
        stage = Path(temporary)
        for path in (root / config["prior_tables"]).glob("*.csv"):
            shutil.copyfile(path, stage / path.name)
        for name in [
            "bounded_means.csv",
            "marker_distribution.csv",
            "GAMM_reference_curves.json",
        ]:
            shutil.copyfile(root / config["plot_inputs"] / name, stage / name)
        render(stage, output)
    export_tables(root, config, output / "tables")
    verify_inputs(root, config)
    metadata = load(output / "metadata.json")
    metadata.sort(
        key=lambda x: (
            x["id"].startswith("FigureS"),
            int(x["id"].split("_")[0].removeprefix("Figure").removeprefix("S")),
        )
    )
    mapping = config["figure_mapping"]
    index = [
        {
            "id": x["id"],
            "prior_id": mapping[x["id"]],
            "png": f"figures/{x['id']}.png",
            "pdf": f"figures/{x['id']}.pdf",
            "svg": f"figures/{x['id']}.svg",
        }
        for x in metadata
    ]
    (output / "figure_index.json").write_text(json.dumps(index, indent=2) + "\n")
    lines = [
        "# Final aggregate figures and tables",
        "",
        "Artifact numbering follows the October 14, 2026 revision.",
        "",
        "## Figures",
        "",
    ]
    for row in index:
        name = row["id"]
        lines.append(
            f"- [{name}]({row['png']}): [PDF]({row['pdf']}), [SVG]({row['svg']})"
        )
    lines.extend(["", "## Tables", ""])
    for path in sorted((output / "tables").glob("*.csv")):
        lines.append(f"- [{path.stem}](tables/{path.name})")
    lines.extend(
        [
            "",
            "Table S1 separates historical plans from completed resampling and validation budgets.",
            "The prior minute-support table remains an input under the October 4 artifact version.",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(lines))
    manifest = dict(
        version=config["version"],
        target_revision=config["target_revision"],
        config_sha256=sha(config_path),
        input_sha256=config["input_sha256"],
        code_sha256={
            str(Path(__file__).relative_to(root)): sha(__file__),
            "src/capsaicin/final_figures.py": sha(
                root / "src/capsaicin/final_figures.py"
            ),
        },
        main_figures=4,
        supplement_figures=6,
        main_tables=3,
        supplement_tables=20,
        new_inference=False,
        individual_records_used=False,
        outputs_sha256={
            str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()
        },
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
