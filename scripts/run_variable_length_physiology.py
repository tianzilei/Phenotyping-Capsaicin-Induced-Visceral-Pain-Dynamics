"""Run the frozen NeuroKit2 pipeline for the variable-length VAS cohort."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "scripts/run_complete_physiology.py").read_text(encoding="utf-8")
src = src.replace(
    "from capsaicin.sync_verification import complete_vas, cluster_edges, audit_offsets",
    'from capsaicin.sync_verification import cluster_edges, audit_offsets\n\ndef variable_vas(row):\n    vals=[]\n    for minute in range(1,21):\n        try:\n            x=float(row.get(f"VAS_{minute}min", ""))\n            if not (0 <= x <= 10): return False\n            vals.append(x)\n        except (ValueError, TypeError):\n            continue\n    return bool(vals)\ncomplete_vas = variable_vas',
)
src = src.replace(
    "config/physiology_complete_v1.json", "config/physiology_variable_length_v1.json"
)
src = src.replace(
    "config/physiology_complete_v2.json", "config/physiology_variable_length_v1.json"
)
src = src.replace("('complete_physiology_'+", "('variable_length_physiology_'+")
src = src.replace("complete_vas(r)", "variable_vas(r)")
src = src.replace("complete_vas subjects", "variable-length VAS subjects")
ns = {
    "__name__": "__main__",
    "__file__": str(ROOT / "scripts/run_variable_length_physiology.py"),
}
exec(compile(src, str(ROOT / "scripts/run_complete_physiology.py"), "exec"), ns)
