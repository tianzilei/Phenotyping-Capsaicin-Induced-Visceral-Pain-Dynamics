"""Render reviewed aggregate tables in the final figure layout without fitting, resampling or imputation.

Python is the sole graphics backend. Outputs are versioned by the caller and
existing output directories are refused. All presentation settings live here.
"""

from pathlib import Path
import argparse
import json
import shutil
import sys
import textwrap
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.font_manager import findfont, FontProperties
from PIL import Image

WIDTH_MM = 165.1
DPI = 600
FONT = "DejaVu Sans"
COLORS = ["#0072B2", "#D55E00", "#6F4C9B", "#00765E", "#343434"]
LINES = ["-", "--", "-.", ":", (0, (5, 2, 1, 2))]
MARKERS = ["o", "s", "^", "v", "D"]
NAMES = [
    "FigureS6_observation_support",
    "Figure1_temporal_sensation",
    "Figure3_symptoms_regions",
    "Figure2_temporal_patterns",
    "Figure4_future_score_prediction",
    "FigureS1_FPCA_stability_reconstruction",
    "FigureS2_GAMM_numerical_diagnostics",
    "FigureS3_candidate_support_diagnostics",
    "FigureS4_bounds_all_MC_status",
    "FigureS5_partition_recovery_baseline",
]
STYLE = {
    "font.family": FONT,
    "font.size": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.titlesize": 8.5,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "lines.linewidth": 1.2,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "text.color": "#222222",
    "axes.labelcolor": "#222222",
}


def dump(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def canvas(height_mm):
    f = plt.figure(figsize=(WIDTH_MM / 25.4, height_mm / 25.4), layout="constrained")
    f.get_layout_engine().set(w_pad=0.055, h_pad=0.055, wspace=0.09, hspace=0.09)
    return f


def axis(a, letter, title, x="", y=""):
    a.set_title(f"{letter}  {title}", pad=8)
    a.set_xlabel(x)
    a.set_ylabel(y)
    a.set_axisbelow(True)
    a.grid(axis="y", color="#E2E2E2", lw=0.4)


def legend(a, **kwargs):
    return a.legend(
        frameon=False,
        handlelength=1.6,
        borderaxespad=0.2,
        labelspacing=0.3,
        columnspacing=0.9,
        **kwargs,
    )


def intervals(a, x, point, lo, hi, color, statuses=None, marker="o", connect=True):
    x, point, lo, hi = map(np.asarray, (x, point, lo, hi))
    assert len(x) == len(point) == len(lo) == len(hi)
    a.vlines(x, lo, hi, color=color, lw=0.9, zorder=2)
    if connect:
        a.plot(x, point, color=color, lw=0.8)
    for i in range(len(x)):
        face = (
            color if statuses is None or statuses[i] == "MC_PRECISION_MET" else "white"
        )
        a.plot(
            x[i],
            point[i],
            marker=marker,
            ms=3.5,
            color=color,
            mfc=face,
            mew=0.9,
            zorder=4,
        )


def repeat_cloud(a, values, position, color, marker="o", horizontal=False):
    values = np.asarray(values, dtype=float)
    jitter = np.linspace(-0.13, 0.13, len(values))
    if horizontal:
        a.scatter(
            values,
            position + jitter,
            s=11,
            marker=marker,
            color=color,
            alpha=0.72,
            linewidths=0.3,
        )
        a.plot(
            [values.min(), values.max()], [position, position], color="#222222", lw=0.8
        )
        a.plot(np.median(values), position, "D", color="black", ms=3.8)
    else:
        a.scatter(
            position + jitter,
            values,
            s=11,
            marker=marker,
            color=color,
            alpha=0.72,
            linewidths=0.3,
        )
        a.plot(
            [position, position], [values.min(), values.max()], color="#222222", lw=0.8
        )
        a.plot(position, np.median(values), "D", color="black", ms=3.8)


def build(data, output, *, names=None, physiological_label="Earlier"):
    figure_names = NAMES if names is None else names
    if output.exists():
        raise FileExistsError(output)
    (output / "figures").mkdir(parents=True)
    (output / "qa").mkdir()
    font_path = findfont(FontProperties(family=FONT), fallback_to_default=False)
    before = {
        p.name: p.read_bytes()
        for p in data.iterdir()
        if p.is_file() and (not p.name.startswith("._"))
    }
    tables = {}

    def table(name):
        if name not in tables:
            tables[name] = pd.read_csv(data / (name + ".csv"))
        return tables[name]

    metadata = []
    text_bounds = []

    def save(f, name):
        f.canvas.draw()
        renderer = f.canvas.get_renderer()
        outside = []
        unused_ticks = set()
        for ax in f.axes:
            for values, texts, limits in [
                (ax.get_xticks(), ax.get_xticklabels(), ax.get_xlim()),
                (ax.get_yticks(), ax.get_yticklabels(), ax.get_ylim()),
            ]:
                lo, hi = sorted(limits)
                unused_ticks.update(
                    (id(t) for v, t in zip(values, texts) if not lo <= v <= hi)
                )
        for t in f.findobj(matplotlib.text.Text):
            if not t.get_visible() or not t.get_text() or id(t) in unused_ticks:
                continue
            box = t.get_window_extent(renderer)
            if (
                box.x0 < -0.5
                or box.y0 < -0.5
                or box.x1 > f.bbox.width + 0.5
                or (box.y1 > f.bbox.height + 0.5)
            ):
                outside.append(t.get_text())
        text_bounds.append({"figure": name, "outside_canvas_text": outside})
        for suffix in ["pdf", "svg", "png"]:
            f.savefig(
                output / "figures" / f"{name}.{suffix}", dpi=DPI, bbox_inches=None
            )
            if suffix == "svg":
                from .vector_ids import normalize

                vector = output / "figures" / f"{name}.svg"
                vector.write_text(
                    normalize(vector.read_text(encoding="utf-8")), encoding="utf-8"
                )
        preview = Image.open(output / "figures" / f"{name}.png").convert("RGB")
        preview.thumbnail((1300, 1800))
        rgb = np.asarray(preview) / 255.0
        linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        gray = (
            0.2126 * linear[:, :, 0]
            + 0.7152 * linear[:, :, 1]
            + 0.0722 * linear[:, :, 2]
        )
        simulated = [("gray", np.repeat(gray[:, :, None], 3, axis=2))]
        for tag, matrix in [
            (
                "deuteranopia",
                [
                    [0.367322, 0.860646, -0.227968],
                    [0.280085, 0.672501, 0.047413],
                    [-0.01182, 0.04294, 0.968881],
                ],
            ),
            (
                "protanopia",
                [
                    [0.152286, 1.052583, -0.204868],
                    [0.114503, 0.786281, 0.099216],
                    [-0.003882, -0.048116, 1.051998],
                ],
            ),
        ]:
            values = np.stack(
                [
                    sum((matrix[c][k] * linear[:, :, k] for k in range(3)))
                    for c in range(3)
                ],
                axis=2,
            )
            assert np.isfinite(values).all()
            simulated.append((tag, values))
        for tag, values in simulated:
            values = np.clip(values, 0, 1)
            values = np.where(
                values <= 0.0031308, 12.92 * values, 1.055 * values ** (1 / 2.4) - 0.055
            )
            im = Image.fromarray((np.clip(values, 0, 1) * 255).astype("uint8"))
            im.thumbnail((1300, 1800))
            im.save(output / "qa" / f"{name}_{tag}.png")
        root = ET.parse(output / "figures" / f"{name}.svg").getroot()
        im = Image.open(output / "figures" / f"{name}.png")
        metadata.append(
            {
                "id": name,
                "width_mm": WIDTH_MM,
                "height_mm": f.get_size_inches()[1] * 25.4,
                "png_pixels": im.size,
                "png_dpi": im.info.get("dpi"),
                "opaque": im.convert("RGBA").getchannel("A").getextrema() == (255, 255),
                "svg_text_nodes": len(
                    root.findall(".//{http://www.w3.org/2000/svg}text")
                ),
                "svg_raster_nodes": len(
                    root.findall(".//{http://www.w3.org/2000/svg}image")
                ),
                "min_font_pt": min(
                    (
                        t.get_fontsize()
                        for t in f.findobj(matplotlib.text.Text)
                        if t.get_visible() and t.get_text()
                    )
                ),
                "font": FONT,
            }
        )
        plt.close(f)

    with plt.rc_context(STYLE):
        obs = table("Table2_minute_support_composition_finite_rates")
        markers = table("marker_distribution")
        f = canvas(112)
        axes = f.subplots(2, 1)
        a, b = axes
        a.bar(obs.start_minute, obs.observed_people, width=0.7, color=COLORS[0])
        for t, n in zip(obs.start_minute, obs.observed_people):
            a.text(t, n + 4, str(int(n)), ha="center", fontsize=7.5)
        axis(a, "A", "Participants with recorded ratings", y="Participants")
        a.set_ylim(0, 280)
        a.set_xticks(range(1, 21))
        a.set_xlabel("Minute")
        a.text(
            0.02,
            0.94,
            "Complete 1–10 min: 206   |   Complete 1–20 min: 56",
            transform=a.transAxes,
            va="top",
            fontsize=7.5,
        )
        b.bar(
            markers.time_min,
            markers.n_first_E,
            color=COLORS[0],
            label="E (150)",
            width=0.75,
        )
        b.bar(
            markers.time_min,
            markers.n_first_T,
            bottom=markers.n_first_E,
            color=COLORS[1],
            edgecolor="#222222",
            linewidth=0.3,
            hatch="///",
            label="T (9)",
            width=0.75,
        )
        axis(
            b,
            "B",
            "First recorded stopping codes",
            "First coded minute",
            "Participants",
        )
        b.set_xticks(range(1, 21))
        b.set_ylim(0, 55)
        legend(b, loc="upper left", ncol=2)
        b.text(
            0.99,
            0.96,
            "No E/T code: 56",
            ha="right",
            va="top",
            transform=b.transAxes,
            fontsize=7.5,
        )
        save(f, figure_names[0])
        f = canvas(175)
        g = f.add_gridspec(3, 3, height_ratios=[1, 1.15, 1])
        a = f.add_subplot(g[0, :])
        b = f.add_subplot(g[1, :])
        a.fill_between(
            obs.start_minute,
            obs.resampling_lower,
            obs.resampling_upper,
            color=COLORS[0],
            alpha=0.18,
        )
        a.plot(obs.start_minute, obs.mean_observed, "o-", color=COLORS[0], ms=3)
        axis(
            a,
            "A",
            "Mean among participants observed at each minute",
            "Minute",
            "Sensation score (0–10)",
        )
        a.set_ylim(0, 10)
        a.set_xticks(range(1, 21))
        legend(
            a,
            handles=[
                Line2D(
                    [], [], color=COLORS[0], marker="o", ms=3, label="Observed mean"
                ),
                Patch(facecolor=COLORS[0], alpha=0.18, label="Resampling range"),
            ],
            ncol=2,
            loc="upper right",
        )
        x = obs.start_minute.to_numpy()
        w = 0.24
        for i, (col, label) in enumerate(
            [
                ("paired_observed_change", "Paired change"),
                ("composition_total", "Composition term"),
                ("observed_mean_change", "Observed-mean change"),
            ]
        ):
            b.bar(
                x + (i - 1) * w,
                obs[col],
                w,
                color=COLORS[i],
                hatch=["", "///", "..."][i],
                edgecolor="#333333",
                linewidth=0.25,
                label=label,
            )
        b.axhline(0, color="#333333", lw=0.7)
        axis(
            b,
            "B",
            "Adjacent change and observation composition",
            "Start minute (t to t + 1)",
            "Score change",
        )
        b.set_xticks(range(1, 20))
        legend(b, ncol=3, loc="upper right")
        for i, h in enumerate([1, 2, 5]):
            a = f.add_subplot(g[2, i])
            d = obs[obs[f"h{h}_mean_rate"].notna()]
            intervals(
                a,
                d.start_minute,
                d[f"h{h}_mean_rate"],
                d[f"h{h}_lower"],
                d[f"h{h}_upper"],
                COLORS[i],
                d[f"h{h}_MC_status"].tolist(),
            )
            axis(a, chr(67 + i), f"{h} min", "Start minute", "Rate (score/min)")
            a.axhline(0, color="#555555", lw=0.7)
            a.set_ylim(-0.55, 1.25)
            a.set_xticks([1, 5, 10, 15, 19])
            a.set_xlim(0.5, 20)
            a.text(
                0.99,
                0.96,
                f"n = {int(d[f'h{h}_people'].iloc[0])}–{int(d[f'h{h}_people'].iloc[-1])}",
                transform=a.transAxes,
                ha="right",
                va="top",
                fontsize=7.5,
            )
        save(f, figure_names[1])
        s = table("TableS2_recorded_codes_all139")
        margins = {k: s[s.kind == k].copy() for k in ["symptom", "region"]}
        f = canvas(214)
        g = f.add_gridspec(3, 1, height_ratios=[1.02, 0.82, 1.3])
        for i, kind in enumerate(["symptom", "region"]):
            a = f.add_subplot(g[i])
            d = margins[kind]
            yy = np.arange(len(d))
            a.barh(yy, d.point * 100, height=0.6, color=COLORS[i], alpha=0.9)
            a.hlines(
                yy,
                100 * d.lower_estimate,
                100 * d.upper_estimate,
                color="#222222",
                lw=0.8,
            )
            a.set_yticks(yy, [f"{r.code}  {r.label}" for r in d.itertuples()])
            a.invert_yaxis()
            for y, r in zip(yy, d.itertuples()):
                a.text(
                    100 * r.upper_estimate + 1,
                    y,
                    f"{int(r.count)}"
                    + (" †" if r.status != "MC_PRECISION_MET" else ""),
                    va="center",
                    fontsize=7.5,
                )
            axis(
                a,
                chr(65 + i),
                f"Recorded {kind}s (n = 209)",
                "Participants listing code (%)",
            )
            a.set_xlim(0, 100)
            a.set_xticks([0, 25, 50, 75, 100])
        a = f.add_subplot(g[2])
        pairs = s[s.kind == "symptom_region_pair"].set_index("code")
        sm, rg = (margins["symptom"], margins["region"])
        count = np.array(
            [
                [int(pairs.loc[f"{sc}_{rc}", "count"]) for rc in rg.code]
                for sc in sm.code
            ]
        )
        cmap = plt.get_cmap("Blues")
        vmax = count.max() / 204 * 100
        for (i, j), n in np.ndenumerate(count):
            color = cmap(n / count.max())
            a.add_patch(
                Rectangle(
                    (j - 0.5, i - 0.5), 1, 1, facecolor=color, edgecolor="white", lw=0.5
                )
            )
            row = pairs.loc[f"{sm.iloc[i].code}_{rg.iloc[j].code}"]
            a.text(
                j,
                i,
                str(n) + ("†" if row.status != "MC_PRECISION_MET" else ""),
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if n > count.max() * 0.58 else "#222222",
            )
        a.set_xlim(-0.5, 8.5)
        a.set_ylim(11.5, -0.5)
        a.set_yticks(range(12), [f"{r.code}  {r.label}" for r in sm.itertuples()])
        a.set_xticks(range(9), rg.code.tolist())
        a.set_xlabel("Region code (defined in B)")
        a.set_title("C  Symptom–region co-occurrence (n = 204)", pad=8)
        a.tick_params(length=0)
        a.spines[["left", "bottom"]].set_visible(False)
        cb = f.colorbar(
            matplotlib.cm.ScalarMappable(
                norm=matplotlib.colors.Normalize(0, vmax), cmap=cmap
            ),
            ax=a,
            fraction=0.035,
            pad=0.025,
        )
        cb.set_label("Both listed (% of 204)", fontsize=7.5)
        cb.solids.set_rasterized(False)
        cb.solids.set_edgecolor("face")
        save(f, figure_names[2])
        fp = table("TableS4_FPCA_all24_diagnostics")
        basis = table("TableS14_FPCA_FVE_and_basis")
        f = canvas(182)
        axes = f.subplots(3, 2)
        for j, (cell, end, n) in enumerate([("F10", 10, 206), ("F20", 20, 56)]):
            d = fp[(fp.cell == cell) & (fp.metric == "cumulative_fve")].sort_values(
                "index"
            )
            intervals(
                axes[0, j],
                d["index"],
                d.reference_cumulative_FVE * 100,
                d.lower_estimate * 100,
                d.upper_estimate * 100,
                COLORS[j],
                d.status.tolist(),
                marker=MARKERS[j],
            )
            axis(
                axes[0, j],
                chr(65 + j),
                f"1–{end} min (n = {n})",
                "Components",
                "Cumulative variance (%)",
            )
            axes[0, j].set_ylim(0, 103)
            axes[0, j].set_xticks(range(1, 5))
            for k in range(1, 5):
                d = basis[(basis.cell == cell) & (basis.PC == k)].sort_values("minute")
                axes[1, j].plot(
                    d.minute,
                    d.phi,
                    color=COLORS[k - 1],
                    ls=LINES[k - 1],
                    label=f"PC{k}",
                )
            axis(
                axes[1, j],
                chr(67 + j),
                f"Component functions, 1–{end} min",
                "Minute",
                "Basis (min$^{-1/2}$)",
            )
            axes[1, j].axhline(0, color="#555555", lw=0.6)
            axes[1, j].set_ylim(-0.65, 1.02)
            legend(axes[1, j], ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.04))
            axes[1, j].set_xticks([1, 5, 10] if end == 10 else [1, 5, 10, 15, 20])
        for k in range(1, 3):
            a = axes[2, k - 1]
            d = basis[(basis.cell == "F10") & (basis.PC == k)].sort_values("minute")
            delta = np.sqrt(d.eigenvalue) * d.phi
            a.plot(d.minute, d["mean"], color="#333333", label="Mean")
            a.plot(
                d.minute,
                d["mean"] + delta,
                color=COLORS[0],
                ls="--",
                label="Mean + 1 SD",
            )
            a.plot(
                d.minute,
                d["mean"] - delta,
                color=COLORS[1],
                ls=":",
                label="Mean − 1 SD",
            )
            axis(
                a,
                chr(68 + k),
                f"PC{k} score variation (n = 206)",
                "Minute",
                "Sensation score",
            )
            a.set_ylim(0, 8)
            a.set_xticks([1, 5, 10])
            legend(a, loc="upper right")
        save(f, figure_names[3])
        rep = table("TableS13_prediction_all20_repeats")
        f = canvas(155)
        axes = f.subplots(2, 2)
        for j, (task, weight, title, n) in enumerate(
            [
                ("next_rating", "window_equal", "Next rating", 213),
                ("five_to_ten", "person_equal", "Minute 5 to 10", 206),
            ]
        ):
            for diff in [False, True]:
                a = axes[j, int(diff)]
                models = (
                    ["ridge", "random_forest"]
                    if diff
                    else ["last_value", "ridge", "random_forest"]
                )
                labels = []
                for i, (metric, model) in enumerate(
                    ((m, mo) for m in ["MAE", "RMSE"] for mo in models)
                ):
                    name = metric + "_" + model + ("_minus_last_value" if diff else "")
                    d = rep[
                        (rep.task == task)
                        & (rep.weighting == weight)
                        & (rep.metric == name)
                    ].sort_values("repeat")
                    assert len(d) == 20
                    mi = ["last_value", "ridge", "random_forest"].index(model)
                    repeat_cloud(
                        a, d.value, i, COLORS[mi], MARKERS[mi], horizontal=True
                    )
                    labels.append(
                        metric
                        + " "
                        + {
                            "last_value": "last value",
                            "ridge": "ridge",
                            "random_forest": "RF",
                        }[model]
                    )
                a.set_yticks(range(len(labels)), labels)
                a.invert_yaxis()
                a.set_ylim(len(labels) - 0.5, -0.6)
                axis(
                    a,
                    chr(65 + 2 * j + int(diff)),
                    "Paired differences" if diff else f"{title} (n = {n})",
                    "Model − last value (score)" if diff else "Error (score)",
                )
                if diff:
                    a.axvline(0, color="#777777", lw=0.7)
                else:
                    a.set_xlim((0.55, 1.02) if j == 0 else (1.15, 2.3))
        save(f, figure_names[4])
        f = canvas(148)
        axes = f.subplots(2, 2)
        for j, metric in enumerate(
            ["subspace_angle_degree", "matched_abs_inner_product"]
        ):
            if metric not in fp.metric.unique():
                metric = next(
                    (
                        m
                        for m in fp.metric.unique()
                        if ("angle" in m if j == 0 else "inner" in m)
                    )
                )
            a = axes[0, j]
            for k, cell in enumerate(["F10", "F20"]):
                d = fp[(fp.cell == cell) & (fp.metric == metric)].sort_values("index")
                x = d["index"].to_numpy() + (-0.1 if k == 0 else 0.1)
                a.vlines(x, d.lower_estimate, d.upper_estimate, color=COLORS[k], lw=1.4)
                for xx, r in zip(x, d.itertuples()):
                    for value in [r.lower_estimate, r.upper_estimate]:
                        a.plot(
                            xx,
                            value,
                            marker=MARKERS[k],
                            ms=3.5,
                            color=COLORS[k],
                            mfc=COLORS[k]
                            if r.status == "MC_PRECISION_MET"
                            else "white",
                            mew=0.9,
                        )
                a.plot(
                    [],
                    [],
                    color=COLORS[k],
                    marker=MARKERS[k],
                    ms=3,
                    label=f"1–{(10 if k == 0 else 20)} min",
                )
            axis(
                a,
                chr(65 + j),
                "Subspace angle" if j == 0 else "Matched component agreement",
                "Subspace dimension" if j == 0 else "Component",
                "Angle (degrees)" if j == 0 else "|Weighted inner product|",
            )
            a.set_xticks(range(1, 5))
            a.set_xlim(0.65, 4.35)
            legend(a, loc="lower left" if j else "upper left")
            a.set_ylim((0, 90) if j == 0 else (0, 1.05))
        cv = table("TableS15_FPCA_reconstruction_all_repeats")
        for j, cell in enumerate(["F10", "F20"]):
            a = axes[1, j]
            for k in range(5):
                d = cv[(cv.cell == cell) & (cv.components == k)].sort_values("repeat")
                assert len(d) == 20
                repeat_cloud(a, d.paired_difference, k, COLORS[k], MARKERS[k])
            axis(
                a,
                chr(67 + j),
                f"Complete 1–{(10 if j == 0 else 20)} min",
                "Components",
                "Paired RMSE change (score)",
            )
            a.axhline(0, color="#555555", lw=0.7)
            a.set_xticks(range(5))
            a.set_ylim(-0.9, 0.8)
        save(f, figure_names[5])
        diagnostics = json.loads((data / "GAMM_reference_curves.json").read_text())
        diag = table("TableS16_GAMM_reference_diagnostics")
        labels = {
            "G10_common_k6": "Observed 10 min",
            "G10_complete_k6": "Complete 10 min",
            "G20_complete_k6": "Complete 20 min",
            "G20_independent_k6": "Independent errors",
            "G20_k4": "Spline k = 4",
            "G20_k8": "Spline k = 8",
            "G20_primary_k6": "Primary k = 6",
        }
        f = canvas(178)
        axes = f.subplots(2, 2, gridspec_kw={"height_ratios": [1, 1.1]})
        for j, end in enumerate([10, 20]):
            a = axes[0, j]
            ds = [r for r in diagnostics if len(r["curve"]) == end]
            for k, r in enumerate(ds):
                a.plot(
                    range(1, end + 1),
                    r["curve"],
                    color=COLORS[k],
                    ls=LINES[k],
                    label=labels[r["cell"]],
                )
            axis(
                a,
                chr(65 + j),
                f"Reference curves: {end} min",
                "Minute",
                "Fitted sensation score",
            )
            a.set_ylim(0, 10)
            a.set_xticks([1, 5, 10] if end == 10 else [1, 5, 10, 15, 20])
            legend(a, loc="upper right")
        yy = np.arange(len(diag))
        a = axes[1, 0]
        a.barh(yy, diag.bootstrap_apVar_finite, color=COLORS[0], label="Finite")
        a.barh(
            yy,
            diag.bootstrap_apVar_nonfinite,
            left=diag.bootstrap_apVar_finite,
            color=COLORS[1],
            hatch="///",
            edgecolor="#333333",
            linewidth=0.25,
            label="Nonfinite",
        )
        a.set_yticks(yy, [labels[x] for x in diag.cell])
        a.set_xlim(0, 5000)
        axis(a, "C", "Covariance diagnostics", "Fits per configuration")
        legend(a, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.04))
        a.set_ylim(-0.5, len(diag) + 0.2)
        a = axes[1, 1]
        for i, r in enumerate(diag.itertuples()):
            if pd.notna(r.apVar_condition):
                a.plot(r.apVar_condition, i, "o", color=COLORS[0], ms=4)
            else:
                a.text(1200, i, "Nonfinite", va="center", fontsize=7.5, color="#555555")
        a.set_xscale("log")
        a.set_xlim(1000.0, 10000000.0)
        a.set_ylim(-0.5, len(diag) + 0.2)
        a.set_yticks(yy, [labels[x] for x in diag.cell])
        axis(a, "D", "Covariance conditioning", "Condition number (log scale)")
        save(f, figure_names[6])
        cand = table("TableS9_candidate_summary").drop_duplicates("cell")
        ct = table("TableS18_candidate_support_diagnostics")
        kinds = ["planned24", "joint22", "egg66"]
        pretty = [f"{physiological_label} (24)", "Joint (22)", "EGG–Hb (66)"]
        f = canvas(144)
        g = f.add_gridspec(2, 2)
        a = f.add_subplot(g[0, :])
        offset = 0
        for k, kind in enumerate(kinds):
            d = cand[cand.cell_kind == kind].sort_values("cell")
            a.scatter(
                np.arange(offset, offset + len(d)),
                d.eligible_people,
                s=11,
                color=COLORS[k],
                marker=MARKERS[k],
                label=pretty[k],
            )
            offset += len(d)
        axis(
            a,
            "A",
            "Participant support in all 112 model configurations",
            "Model index",
            "Participants",
        )
        a.set_ylim(0, 180)
        legend(a, ncol=3, loc="lower left")
        a = f.add_subplot(g[1, 0])
        d = ct.set_index("kind").loc[kinds]
        yy = np.arange(3)
        a.barh(yy, d.MC_met, color=COLORS[0], label="Met")
        a.barh(
            yy,
            d.MC_insufficient,
            left=d.MC_met,
            color=COLORS[1],
            hatch="///",
            edgecolor="#333333",
            linewidth=0.25,
            label="Insufficient",
        )
        a.set_yticks(yy, pretty)
        axis(a, "B", "All 178 statistics", "Statistics")
        legend(a, ncol=2, loc="lower right")
        a = f.add_subplot(g[1, 1])
        a.bar(
            yy,
            d.failed_fits,
            color=COLORS[1],
            edgecolor="#333333",
            linewidth=0.25,
            hatch="///",
        )
        a.set_xticks(yy, [physiological_label, "Joint", "EGG–Hb"])
        axis(a, "C", "Rank failures retained", y="Failed fits")
        for i, v in enumerate(d.failed_fits):
            a.text(i, v + 2, str(int(v)), ha="center", fontsize=7.5)
        a.set_ylim(0, 140)
        save(f, figure_names[7])
        bounds = table("bounded_means")
        mc = table("TableS6_all1255_MC_statistics")
        group_labels = {
            ("completion", "symptoms_summary.json"): "Recorded codes",
            ("completion", "finite_changes_summary.json"): "Finite changes",
            ("FPCA_precision", "complete_summary.json"): "Complete FPCA",
            ("R_main", "sparse_summary.json"): "Sparse FPCA",
            ("R_main", "gamm_summary.json"): "Additive mixed models",
            ("variability", "U06_variability_summary.json"): "Variability / burden",
            ("python_remaining", "candidate_summary.json"): "Physiological candidates",
            ("python_remaining", "cluster_summary.json"): "Trajectory partitions",
            ("observations", "VAS_observation_summary.json"): "Observed ratings",
            ("observations", "five_to_ten_summary.json"): "Fixed OOF: 5 to 10 min",
            ("observations", "next_rating_summary.json"): "Fixed OOF: next rating",
        }
        f = canvas(178)
        axes = f.subplots(2, 1, gridspec_kw={"height_ratios": [1, 1.5]})
        a = axes[0]
        a.fill_between(
            bounds.time_min,
            bounds.cohort_mean_lower,
            bounds.cohort_mean_upper,
            color=COLORS[1],
            alpha=0.2,
        )
        a.plot(obs.start_minute, obs.mean_observed, color=COLORS[0], marker="o", ms=2.5)
        axis(a, "A", "Full-cohort algebraic bounds", "Minute", "Sensation score (0–10)")
        a.set_ylim(0, 10)
        a.set_xticks([1, 5, 10, 15, 20])
        legend(
            a,
            handles=[
                Line2D([], [], color=COLORS[0], label="Observed-set mean"),
                Patch(facecolor=COLORS[1], alpha=0.2, label="Scale bounds"),
            ],
            ncol=2,
            loc="upper left",
        )
        a = axes[1]
        groups = []
        for key, d in mc.groupby(["source_role", "source_file"], sort=False):
            groups.append(
                (group_labels[key], len(d), int((d.status == "MC_PRECISION_MET").sum()))
            )
        yy = np.arange(len(groups))
        a.barh(yy, [x[2] for x in groups], color=COLORS[0], label="Met")
        a.barh(
            yy,
            [x[1] - x[2] for x in groups],
            left=[x[2] for x in groups],
            color=COLORS[1],
            hatch="///",
            edgecolor="#333333",
            linewidth=0.25,
            label="Insufficient",
        )
        a.set_yticks(yy, [x[0] for x in groups])
        a.invert_yaxis()
        for i, r in enumerate(groups):
            a.text(r[1] + 4, i, f"{r[2]}/{r[1]}", va="center", fontsize=7.5)
        a.set_xlim(0, 420)
        axis(a, "B", "Precision inventory: 1,255 statistics", "Statistics")
        legend(a, ncol=2, loc="lower right")
        save(f, figure_names[8])
        recovery = table("TableS10_partition_recovery_and_baseline")
        f = canvas(205)
        g = f.add_gridspec(2, 1, height_ratios=[1.2, 1])
        for j, analysis in enumerate(["partition_recovery", "baseline_development"]):
            a = f.add_subplot(g[j])
            d = recovery[recovery.analysis == analysis]
            rows = d[d.metric == "balanced_accuracy_equal_fold_mean"]
            roster = d[
                (d.metric == "balanced_accuracy_equal_fold_mean") | d.metric.isna()
            ]
            keys = sorted(
                {
                    (r.cell, 0 if pd.isna(r.prefix) else int(r.prefix))
                    for r in roster.itertuples()
                }
            )
            model_names = (
                [
                    "raw_prefix_logistic",
                    "trained_shapelet_logistic",
                    "training_majority",
                ]
                if j == 0
                else [
                    "questionnaire",
                    "questionnaire_plus_rest_candidates",
                    "training_majority",
                ]
            )
            display = (
                ["Prefix logistic", "Trained shapelet", "Training majority"]
                if j == 0
                else ["Questionnaire", "+ Rest candidates", "Training majority"]
            )
            for mi, model in enumerate(model_names):
                for i, (cell, prefix) in enumerate(keys):
                    dd = rows[(rows.cell == cell) & (rows.model == model)]
                    if j == 0:
                        dd = dd[dd.prefix == prefix]
                    if len(dd) == 0 or dd["median"].isna().all():
                        continue
                    r = dd.iloc[0]
                    x = i + (mi - 1) * 0.21
                    a.vlines(x, r.minimum, r.maximum, color=COLORS[mi], lw=0.9)
                    a.plot(x, r["median"], marker=MARKERS[mi], ms=3.5, color=COLORS[mi])
                a.plot(
                    [],
                    [],
                    color=COLORS[mi],
                    marker=MARKERS[mi],
                    ms=3.5,
                    label=display[mi],
                )
            labels = []
            for i, (cell, prefix) in enumerate(keys):
                dd = rows[rows.cell == cell]
                if j == 0:
                    dd = dd[dd.prefix == prefix]
                k = int(cell.split("_k")[1])
                complete = int(dd.complete_repeats.min()) if len(dd) else 0
                labels.append(f"k{k}\np{prefix}" if j == 0 else f"k{k}\n{complete}/20")
                if not len(dd) or dd["median"].isna().all():
                    a.text(i, 0.12, "NE", ha="center", fontsize=7.5, color="#555555")
            a.set_xticks(range(len(keys)), labels)
            a.set_xlim(-0.7, len(keys) - 0.3)
            a.set_ylim(-0.15, 1.15)
            boundary = next(
                (
                    i
                    for i, k in enumerate(keys)
                    if k[0].startswith("R20" if j == 0 else "B20")
                )
            )
            a.axvline(boundary - 0.5, color="#999999", lw=0.6, ls=":")
            for lo, hi, txt in [
                (0, boundary - 1, "1–10 min"),
                (boundary, len(keys) - 1, "1–20 min"),
            ]:
                a.text((lo + hi) / 2, -0.135, txt, ha="center", fontsize=8)
            axis(
                a,
                chr(65 + j),
                "Prefix and shapelet recovery"
                if j == 0
                else "Baseline development (n = 21 / 6)",
                "k: groups; p: prefix minutes"
                if j == 0
                else "Complete repeats / 20; NE: not estimable",
                "Balanced accuracy",
            )
            legend(a, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.04))
        save(f, figure_names[9])
    assert before == {
        p.name: p.read_bytes()
        for p in data.iterdir()
        if p.is_file() and (not p.name.startswith("._"))
    }
    dump(output / "metadata.json", metadata)
    dump(output / "qa/text_bounds.json", text_bounds)
    dump(
        output / "render_manifest.json",
        {
            "backend": "python",
            "python": sys.version,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
            "style": STYLE,
            "new_inference": False,
            "new_exclusions": False,
            "seed": "No random generation; deterministic display offsets",
        },
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "figures": len(metadata),
                "outside_canvas": text_bounds,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    build(args.data, args.output)
