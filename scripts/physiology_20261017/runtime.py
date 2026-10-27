"""Explicit controlled locations for the retained physiological programs."""

import json
import os
from pathlib import Path
import shutil

REPOSITORY = Path(__file__).resolve().parents[2]


def locations(kind):
    """Require private inputs and outputs; importing does not create a run."""
    root = Path(os.environ["CAPSAICIN_ANALYSIS_ROOT"]).resolve()
    variable = {
        "inference": "CAPSAICIN_PHYSIOLOGY_RUN",
        "extension": "CAPSAICIN_EXTENSION_RUN",
    }[kind]
    output = Path(os.environ[variable]).resolve()
    if output.is_relative_to(REPOSITORY) or output == root:
        raise ValueError("Individual outputs require a separate controlled directory")
    config_path = Path(
        os.environ.get(
            f"CAPSAICIN_{kind.upper()}_CONFIG",
            REPOSITORY / f"config/physiology_{kind}_20261017_v1.json",
        )
    ).resolve()
    return root, output, json.loads(config_path.read_text()), config_path


def start_run(output, configuration, roster=None):
    """Never overwrite a prior execution or silently reuse an existing directory."""
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(configuration, output / "frozen_config.json")
    if roster:
        shutil.copyfile(REPOSITORY / roster, output / "planned_core_tests_54.csv")


def require_missing(output, names):
    for name in names:
        if (output / name).exists():
            raise FileExistsError(output / name)
