"""
Shared label maps, abbreviation helpers, and color palettes for visualization.
"""

from analysis.constants import CLUSTER_COLORS

# =========================================================
# Cluster Labels
# =========================================================
CLUSTER_LABEL_MAP = {
    0: "Cluster 1",
    1: "Cluster 2",
    2: "Cluster 3",
}

CLUSTER_COLOR_MAP = {
    0: CLUSTER_COLORS[0],
    1: CLUSTER_COLORS[1],
    2: CLUSTER_COLORS[2],
}

# =========================================================
# Disease Short Names
# =========================================================
DISEASE_SHORT_MAP = {
    "Functional Heartburn": "Heartburn",
    "Belching Disorder": "Belching",
    "Chronic Nausea Vomiting Syndrome": "Nausea/Vomiting",
    "Functional Dyspepsia - PDS-like": "Dyspepsia-PDS",
    "Functional Dyspepsia - EPS-like": "Dyspepsia-EPS",
    "Irritable Bowel Syndrome-like": "IBS-like",
    "Functional Abdominal Bloating/Distension-like": "Bloating/Distension",
    "Functional Constipation / Defecatory Disorder-like": "Constipation",
    "Biliary Pain-like": "Biliary Pain",
    "Unspecified Functional GI Symptom Pattern": "Unspecified GI",
}

# =========================================================
# Region Short Names
# =========================================================
REGION_SHORT_MAP = {
    "epigastrium": "Epi",
    "right hypochondrium": "R-Hypo",
    "left hypochondrium": "L-Hypo",
    "umbilical": "Umb",
    "hypogastrium": "Hypo",
    "right lumbar": "R-Lumb",
    "left lumbar": "L-Lumb",
    "right inguinal": "R-Ingu",
    "left inguinal": "L-Ingu",
}

# =========================================================
# Symptom Short Names
# =========================================================
SYMPTOM_SHORT_MAP = {
    "abdominal pain": "Abd Pain",
    "bloating": "Bloating",
    "abdominal distension": "Distension",
    "heartburn": "Heartburn",
    "acid regurgitation": "Acid Reflux",
    "belching": "Belching",
    "nausea": "Nausea",
    "vomiting": "Vomiting",
    "loss of appetite": "Appetite Loss",
    "tenesmus": "Tenesmus",
    "palpitations": "Palpitations",
    "irritability": "Irritability",
}


# =========================================================
# Helper Functions
# =========================================================
def norm_text(x: str) -> str:
    """Normalize text: strip and lowercase."""
    if not isinstance(x, str):
        return ""
    return x.strip().lower()


def short_disease(name: str) -> str:
    """Get short disease name."""
    return DISEASE_SHORT_MAP.get(name, name[:20])


def short_region(name: str) -> str:
    """Get short region name."""
    return REGION_SHORT_MAP.get(name, name[:10])


def short_symptom(name: str) -> str:
    """Get short symptom name."""
    return SYMPTOM_SHORT_MAP.get(name, name[:12])


def pretty_cluster(k: int) -> str:
    """Get pretty cluster label (1-based)."""
    return CLUSTER_LABEL_MAP.get(k, f"Cluster {k}")
