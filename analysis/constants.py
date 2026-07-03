"""Shared configuration loaded from ``analysis/config/constants.json``."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_CACHE_ROOT = Path(tempfile.gettempdir())

os.environ.setdefault("MPLCONFIGDIR", str(_CACHE_ROOT / "matplotlib-capsaicin"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_ROOT / "fontconfig-capsaicin"))
os.makedirs(os.environ["XDG_CACHE_HOME"], exist_ok=True)

import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_CONFIG_FILE = PROJECT_ROOT / "constants.json"
PACKAGE_CONFIG_FILE = Path(__file__).resolve().parent / "config" / "constants.json"
CONFIG_FILE = ROOT_CONFIG_FILE if ROOT_CONFIG_FILE.exists() else PACKAGE_CONFIG_FILE


def _load_config() -> dict:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = _load_config()


def _project_path(relative_path: str) -> str:
    return str(PROJECT_ROOT / relative_path)


_paths = CONFIG["paths"]
DATA_DIR = _project_path(_paths["data_dir"])
RAW_DATA_DIR = _project_path(_paths["raw_data_dir"])
PROCESSED_DATA_DIR = _project_path(_paths["processed_data_dir"])
ECG_EGG_DATA_DIR = _project_path(_paths["ecg_egg_data_dir"])
METRICS_DIR = _project_path(_paths["metrics_dir"])
RESULTS_DIR = METRICS_DIR
FIGURES_DIR = _project_path(_paths["figures_dir"])

SUBJECT_INFO_FILE = _project_path(_paths["subject_info_file"])
VAS_DATA_FILE = SUBJECT_INFO_FILE
SYMPTOMS_DATA_FILE = SUBJECT_INFO_FILE

SYMPTOM_CODE_MAP = CONFIG["symptom_code_map"]
VALID_SYMPTOM_CODES = set(SYMPTOM_CODE_MAP.keys())

REGION_CODE_MAP = CONFIG["region_code_map"]
VALID_REGION_CODES = set(REGION_CODE_MAP.keys())
COMPOSITE_REGION_CODES = CONFIG["composite_region_codes"]

_ecg = CONFIG["ecg"]
ECG_FS = _ecg["fs"]
ECG_DURATION = _ecg["duration_seconds"]
ECG_N_SAMPLES = ECG_FS * ECG_DURATION
ECG_LOW = _ecg["low_hz"]
ECG_HIGH = _ecg["high_hz"]
ECG_FILTER_ORDER = _ecg["filter_order"]

_egg = CONFIG["egg"]
EGG_FILTER_ORDER = _egg["filter_order"]
EGG_BROAD_LOW = _egg["broad_low_hz"]
EGG_BROAD_HIGH = _egg["broad_high_hz"]
EGG_NORM_LOW = _egg["norm_low_hz"]
EGG_NORM_HIGH = _egg["norm_high_hz"]
EGG_FULL_LOW = _egg["full_low_hz"]
EGG_FULL_HIGH = _egg["full_high_hz"]

NORMOGASTRIA = tuple(_egg["normogastria_hz"])
BRADYGASTRIA = tuple(_egg["bradygastria_hz"])
TACHYGASTRIA = tuple(_egg["tachygastria_hz"])

_hrv = CONFIG["hrv"]
LF_BAND = tuple(_hrv["lf_band_hz"])
HF_BAND = tuple(_hrv["hf_band_hz"])

_sqi = CONFIG["sqi"]
SQI_HIGH = _sqi["high"]
SQI_LOW = _sqi["low"]

CLUSTER_LABEL_MAP = {int(k): v for k, v in CONFIG["cluster_label_map"].items()}

_colors = CONFIG["colors"]
CLUSTER_COLORS = _colors["cluster"]
PRIMARY_COLOR = _colors["primary"]
SECONDARY_COLOR = _colors["secondary"]
TERTIARY_COLOR = _colors["tertiary"]
NODE_COLOR_SYMPTOM = _colors["node_symptom"]
NODE_COLOR_REGION = _colors["node_region"]
NODE_COLOR_DISEASE = _colors["node_disease"]

HEATMAP_CMAP = sns.color_palette(_colors["heatmap_palette"], as_cmap=True)
CONFUSION_CMAP = sns.color_palette(_colors["confusion_palette"], as_cmap=True)

os.makedirs(METRICS_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)
