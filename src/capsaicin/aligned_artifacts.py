"""Rebuild the October 27 aggregate export, with no individual-level inference."""

import json
from pathlib import Path
import shutil
import tempfile
from .final_artifacts import load, verify_inputs


def export_tables(root, config, destination):
    destination.mkdir(exist_ok=False)
    sources = config["table_sources"]
    expected = {f"TableS{i}" for i in range(1, 30)} | {"Table1", "Table2"}
    identities = {Path(name).stem.split("_")[0] for name in sources}
    if identities != expected or len(sources) != 31:
        raise ValueError("Expected exactly Table 1-2 and Tables S1-S29")
    for name, source in sources.items():
        if Path(name).name != name or not name.endswith(".csv"):
            raise ValueError("Invalid table export name")
        shutil.copyfile(root / source, destination / name)


def build(root, config_path, output):
    """Verify all inputs and preserve the exact ten supplied PNGs."""
    from .final_figures import build as render
    from PIL import Image

    root = Path(root).resolve()
    output = Path(output).resolve()
    config_path = Path(config_path).resolve()
    config = load(config_path)
    if output.exists():
        raise FileExistsError(output)
    for protected in [root / "data/aggregate_sources", root / "data/published"]:
        if output == protected or protected.is_relative_to(output):
            raise ValueError("Output would contain a protected data directory")
    if output.is_relative_to(root / "data/aggregate_sources"):
        raise ValueError("Outputs cannot replace reviewed inputs")
    verify_inputs(root, config)
    with tempfile.TemporaryDirectory(prefix="capsaicin-aligned-") as directory:
        stage = Path(directory)
        for path in (root / config["prior_tables"]).glob("*.csv"):
            if not path.name.startswith("._"):
                shutil.copyfile(path, stage / path.name)
        for name in [
            "bounded_means.csv",
            "marker_distribution.csv",
            "GAMM_reference_curves.json",
        ]:
            shutil.copyfile(root / config["plot_inputs"] / name, stage / name)
        render(
            stage, output, names=config["figure_names"], physiological_label="Sensation"
        )
    export_tables(root, config, output / "tables")
    metadata = load(output / "metadata.json")
    for row in metadata:
        source = root / config["native_pngs"][row["id"]]
        shutil.copyfile(source, output / "figures" / (row["id"] + ".png"))
        with Image.open(source) as native:
            row["png_pixels"] = list(native.size)
            row["png_dpi"] = list(native.info.get("dpi", ()))
        row["png_origin"] = "reviewed native document image"
    metadata.sort(key=lambda x: ("S" in x["id"].split("_")[0], x["id"]))
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    index = [
        {
            "id": row["id"],
            **{kind: f"figures/{row['id']}.{kind}" for kind in ["png", "pdf", "svg"]},
        }
        for row in metadata
    ]
    (output / "figure_index.json").write_text(json.dumps(index, indent=2) + "\n")
    lines = [
        "# Aggregate figures and tables",
        "",
        "Numbering follows the October 27, 2026 revision.",
        "Four main figures, six supporting figures, two main tables and 29 supporting tables.",
        "Native PNGs match the supplied document images; editable SVG/PDF plots use the same reviewed aggregates.",
        "",
        "## Figures",
        "",
    ]
    for row in index:
        lines.append(
            f"- [{row['id']}]({row['png']}): [PDF]({row['pdf']}), [SVG]({row['svg']})"
        )
    lines.extend(["", "## Tables", ""])
    for name in sorted(config["table_sources"]):
        lines.append(f"- [{Path(name).stem}](tables/{name})")
    lines.extend(
        [
            "",
            "The earlier exports retain historical numbering and results.",
            "The 161-test and 54-test physiological families remain separate; CR1 is the main inference and CR2 a sensitivity.",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(lines))
    render_record = load(output / "render_manifest.json")
    (output / "render_manifest.json").write_text(
        json.dumps(render_record, indent=2) + "\n"
    )
    verify_inputs(root, config)
    manifest = {
        "version": config["version"],
        "target_revision": config["target_revision"],
        "analysis_as_of": config["analysis_as_of"],
        "main_figures": 4,
        "supplement_figures": 6,
        "main_tables": 2,
        "supplement_tables": 29,
        "new_inference": False,
        "individual_records_used": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
