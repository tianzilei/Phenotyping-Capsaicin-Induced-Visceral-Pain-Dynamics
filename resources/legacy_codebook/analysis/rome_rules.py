"""
ROME IV-informed rules with region constraints.
Symptom-pattern alignment only, not formal diagnosis.
Requires symptom + region compatibility.
"""

ROME_RULES = {
    # Upper GI / esophageal-like
    "Functional Heartburn": {
        "required_any": ["heartburn", "acid regurgitation"],
        "supportive": ["belching", "nausea"],
        "required_region_any": ["epigastrium"],
        "supportive_region_any": ["right hypochondrium", "left hypochondrium"],
    },
    "Belching Disorder": {
        "required_any": ["belching"],
        "supportive": ["acid regurgitation", "bloating"],
        "required_region_any": ["epigastrium"],
        "supportive_region_any": [
            "right hypochondrium",
            "left hypochondrium",
            "umbilical",
        ],
    },
    "Chronic Nausea Vomiting Syndrome": {
        "required_any": ["nausea", "vomiting"],
        "supportive": ["loss of appetite", "abdominal pain"],
        "required_region_any": ["epigastrium"],
        "supportive_region_any": [
            "right hypochondrium",
            "left hypochondrium",
            "umbilical",
        ],
    },
    # Gastroduodenal
    "Functional Dyspepsia - PDS-like": {
        "required_any": ["loss of appetite", "nausea"],
        "supportive": [
            "belching",
            "bloating",
            "acid regurgitation",
            "abdominal distension",
        ],
        "required_region_any": ["epigastrium"],
        "supportive_region_any": [
            "right hypochondrium",
            "left hypochondrium",
            "umbilical",
        ],
    },
    "Functional Dyspepsia - EPS-like": {
        "required_any": ["abdominal pain", "heartburn"],
        "supportive": ["nausea", "belching", "acid regurgitation", "bloating"],
        "required_region_any": ["epigastrium"],
        "supportive_region_any": ["right hypochondrium", "left hypochondrium"],
    },
    # Bowel
    "Irritable Bowel Syndrome-like": {
        "required_all": ["abdominal pain"],
        "required_any": ["bloating", "tenesmus", "abdominal distension"],
        "supportive": [],
        "required_region_any": [
            "umbilical",
            "hypogastrium",
            "right lumbar",
            "left lumbar",
        ],
        "supportive_region_any": ["right inguinal", "left inguinal"],
    },
    "Functional Abdominal Bloating/Distension-like": {
        "required_any": ["bloating", "abdominal distension"],
        "supportive": ["abdominal pain"],
        "required_region_any": ["umbilical", "epigastrium", "hypogastrium"],
        "supportive_region_any": ["right lumbar", "left lumbar"],
    },
    "Functional Constipation / Defecatory Disorder-like": {
        "required_any": ["tenesmus"],
        "supportive": ["abdominal pain", "bloating", "abdominal distension"],
        "required_region_any": ["hypogastrium", "right inguinal", "left inguinal"],
        "supportive_region_any": ["umbilical"],
    },
    # Biliary / upper right abdomen
    "Biliary Pain-like": {
        "required_any": ["abdominal pain", "nausea", "vomiting"],
        "supportive": ["loss of appetite"],
        "required_region_any": ["right hypochondrium", "epigastrium"],
        "supportive_region_any": ["left hypochondrium"],
    },
    # Non-specific autonomic / affective pattern
    "Unspecified Functional GI Symptom Pattern": {
        "required_any": ["palpitations", "irritability"],
        "supportive": [],
        "required_region_any": ["epigastrium", "umbilical", "hypogastrium"],
        "supportive_region_any": [],
    },
}

# Cluster-to-phenotype name mapping
CLUSTER_NAME_MAP = {
    1: "Cluster 1",
    2: "Cluster 2",
    3: "Cluster 3",
}
