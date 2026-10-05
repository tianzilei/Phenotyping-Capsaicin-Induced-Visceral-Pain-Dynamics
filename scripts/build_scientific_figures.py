"""Render reviewed aggregate reporting sources, without new inference or fitting."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
import uuid
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def sha(p):
    with Path(p).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_new(p, value):
    with Path(p).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


COLORS = ["#137c8b", "#dd8033", "#7652a0", "#57744e", "#9a5867"]


def load(p):
    return json.loads(p.read_bytes())


def flat(rows):
    result = []
    for row in rows:
        r = {k: v for k, v in row.items() if not isinstance(v, (dict, list))}
        for side in ["lower", "upper"]:
            for k, v in row.get(side, {}).items():
                r[side + "_" + k] = v
        for k, v in row.get("cell_description", {}).items():
            r["cell_" + k] = (
                json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            )
        result.append(r)
    return pd.DataFrame(result)


def figure(title, size=(12, 8), foot=""):
    fig = plt.figure(figsize=size, layout="constrained")
    fig.get_layout_engine().set(rect=(0, 0.045, 1, 0.875))
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.985)
    if foot:
        fig.text(0.025, 0.012, foot, fontsize=9, color="#444444", va="bottom")
    return fig


def style(ax, title, x="", y=""):
    ax.set_title(title, loc="left", fontweight="bold", fontsize=11, pad=12)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.15)
    ax.set_axisbelow(True)


def save(fig, out, name, caption, records):
    for suffix in ["png", "pdf", "svg"]:
        p = out / "figures" / (name + "." + suffix)
        if p.exists():
            raise FileExistsError(p)
        fig.savefig(p, dpi=300, facecolor="white")
    records.append(dict(id=name, caption=caption))
    plt.close(fig)


def interval_points(ax, rows, color):
    for s in rows:
        t = s.get("start_minute", s.get("index"))
        v = s["point"]
        ax.plot(
            [t, t],
            [s["lower"]["estimate"], s["upper"]["estimate"]],
            color=color,
            lw=1.5,
            alpha=0.65,
        )
        ax.scatter(
            t,
            v,
            s=26,
            facecolors=color if s["status"] == "MC_PRECISION_MET" else "white",
            edgecolors=color,
            zorder=4,
        )
    ax.plot(
        [s.get("start_minute", s.get("index")) for s in rows],
        [s["point"] for s in rows],
        color=color,
        lw=1,
    )


def build(config_path, output=None):
    cfg = load(config_path)
    source = Path(cfg["source_bundle"])
    source = source if source.is_absolute() else ROOT / source
    sm = load(source / "manifest.json")
    assert sha(source / "manifest.json") == cfg["source_manifest_sha256"]
    for name, h in sm["outputs_sha256"].items():
        assert sha(source / name) == h, name
    out = (
        Path(output).expanduser().resolve()
        if output
        else ROOT
        / cfg.get("default_output_root", "08_outputs/public_render")
        / (
            "scientific_report_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    if out.is_relative_to(source.resolve()) or out.is_relative_to(
        (ROOT / "data/published").resolve()
    ):
        raise ValueError(
            "Choose a fresh render directory outside published data and source bundles"
        )
    out.mkdir(parents=True, exist_ok=False)
    for name in ["figures", "tables", "snapshot"]:
        (out / name).mkdir()
    shutil.copyfile(config_path, out / "snapshot" / config_path.name)
    shutil.copyfile(Path(__file__), out / "snapshot" / Path(__file__).name)
    shutil.copyfile(
        source / "manifest.json", out / "snapshot/source_bundle_manifest.json"
    )
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 10,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    records = []
    tables = {}
    extra_sources = {}

    def table(name, frame, title, note):
        frame.to_csv(out / "tables" / (name + ".csv"), index=False)
        tables[name] = dict(title=title, note=note, frame=frame)

    obs = pd.read_csv(source / "observed_algebra/observed_curve_latest.csv")
    markers = pd.read_csv(source / "observed_algebra/marker_distribution.csv")
    comp = pd.read_csv(source / "observed_algebra/adjacent_composition.csv")
    symptoms = load(source / "completion/symptoms_summary.json")
    spoint = load(source / "completion/symptoms_point.json")
    for s, p in zip(symptoms, spoint):
        s["count"] = p["count"]
    finite = load(source / "completion/finite_changes_summary.json")
    supports = load(source / "completion/supports.json")
    fpc = load(source / "FPCA_precision/complete_summary.json")
    refs = {
        cell: load(
            source / "FPCA_precision/references" / ("reference__" + cell + ".json")
        )
        for cell in ["F10", "F20"]
    }
    cv = load(source / "R_main/reconstruction_summary.json")
    repeats = pd.read_csv(source / "prediction_all_repeat_metrics.csv")
    ps = pd.read_csv(source / "prediction_summary.csv")
    allmc = pd.read_csv(source / "all_current_MC_statistics.csv")
    # Main tables: the rating count column refers only to the indicated interval.
    t1 = pd.DataFrame(
        [
            dict(
                analysis_set="All observed records",
                people=215,
                interval_minute="1–20",
                numeric_ratings_in_interval=3424,
                first_E_people=150,
                first_T_people=9,
                no_marker_people=56,
                symptom_recorded=209,
                region_recorded=209,
                both_recorded=204,
            ),
            dict(
                analysis_set="Complete minutes 1–10",
                people=206,
                interval_minute="1–10",
                numeric_ratings_in_interval=2060,
            ),
            dict(
                analysis_set="Complete minutes 1–20",
                people=56,
                interval_minute="1–20",
                numeric_ratings_in_interval=1120,
            ),
            dict(
                analysis_set="Next actual rating",
                people=213,
                interval_minute="origins 3–19; targets 4–20",
                numeric_ratings_in_interval=2781,
                count_definition="eligible prediction windows, not all ratings",
            ),
            dict(
                analysis_set="Minute 5 prefix to minute 10",
                people=206,
                interval_minute="inputs 1–5; target 10",
                numeric_ratings_in_interval=206,
                count_definition="prediction targets, not all ratings",
            ),
        ]
    )
    table(
        "Table1_cohort_and_analysis_sets",
        t1,
        "表1：队列、观察集与任务支持",
        "研究者确认剂量10% w/v × 10 μL = 1 mg。2060/1120为指定区间数值；预测行数量为窗口/目标数。未核实的子集编码与问卷人数留空。首次E/T为记录代码，非精确事件时刻。",
    )
    t2 = obs.copy().rename(columns={"minute": "start_minute"})
    t2 = t2.merge(
        comp[
            [
                "start_min",
                "observed_mean_change",
                "paired_observed_change",
                "composition_total",
            ]
        ],
        left_on="start_minute",
        right_on="start_min",
        how="left",
    ).drop(columns="start_min")
    for h in [1, 2, 5]:
        rows = [
            s for s in finite if s["h_minutes"] == h and s["statistic"] == "mean_rate"
        ]
        temp = pd.DataFrame(
            [
                dict(
                    start_minute=s["start_minute"],
                    **{
                        f"h{h}_{k}": v
                        for k, v in dict(
                            end_minute=s["end_minute"],
                            people=s["people"],
                            mean_rate=s["point"],
                            lower=s["lower"]["estimate"],
                            upper=s["upper"]["estimate"],
                            MC_status=s["status"],
                        ).items()
                    },
                )
                for s in rows
            ]
        )
        t2 = t2.merge(temp, on="start_minute", how="left")
    table(
        "Table2_minute_support_composition_finite_rates",
        t2,
        "表2：逐分钟支持、观察构成和有限区间平均变化率",
        "范围为200,000整人重抽q.025–q.975描述范围，非校准人口CI。每个跨度有独立分母，跨度内全部实际分钟有数值；空格表示超出20分钟。MC状态针对展示统计量。构成分解只有点值，没有新增构成项重抽范围。",
    )
    t3 = []

    def formatted(task, weight, metric):
        r = ps[
            (ps.task == task) & (ps.weighting == weight) & (ps.metric == metric)
        ].iloc[0]
        return f"{r['median']:.4f} [{r['min']:.4f}, {r['max']:.4f}]"

    for task, weight, n, windows in [
        ("next_rating", "window_equal", 213, 2781),
        ("five_to_ten", "person_equal", 206, 206),
    ]:
        for metric in ["MAE", "RMSE"]:
            row = dict(
                task=task,
                weighting=weight,
                people=n,
                target_rows=windows,
                metric=metric,
            )
            for model in ["last_value", "ridge", "random_forest"]:
                row[model] = formatted(task, weight, metric + "_" + model)
            for model in ["ridge", "random_forest"]:
                row[model + "_minus_last_value"] = formatted(
                    task, weight, metric + "_" + model + "_minus_last_value"
                )
            t3.append(row)
    table(
        "Table3_prediction_primary_paired",
        pd.DataFrame(t3),
        "表3：全部20重复内部预测性能",
        "单位VAS；中位数[min,max]为划分/训练敏感性，非CI。5外层/4内层均按受试者分离；下一评分窗口等权为主，按人敏感性见S5。成对差为每次同样本同权模型减持续值。",
    )
    table(
        "TableS1_all18_modules",
        pd.read_csv(source / "all_18_modules.csv"),
        "表S1：全部18模块及未解除门槛",
        "计算完成与科学有效性分开；U16/U17未生成真实分析，主要生理p/q为空，封存样本关闭。",
    )
    table(
        "TableS2_recorded_codes_all139",
        flat(symptoms),
        "表S2：症状、部位、全部共现及历史规则139项",
        "边际分母209；共现及历史规则分母204。包含零计数。规则匹配不等于诊断；字段缺失为unrecorded；135/139 MC达标。",
    )
    table(
        "TableS3_finite_changes_all364",
        flat(finite),
        "表S3：52区间×7有限变化指标",
        "变化VAS、变化率VAS/minute、正负零比例；均值、中位数及三比例，没有显著性时段。336/364 MC达标，其余28项完整保留。",
    )
    fpc_table = flat(fpc)
    fpc_table["reference_cumulative_FVE"] = [
        float(np.cumsum(refs[s["cell"]]["fve"])[s["index"] - 1])
        if s["metric"] == "cumulative_fve"
        else np.nan
        for s in fpc
    ]
    table(
        "TableS4_FPCA_all24_diagnostics",
        fpc_table,
        "表S4：完整FPCA全部24项重抽诊断",
        "每区间100,000次，FVE8/8、子空间角4/8、轴内积0/8 MC达标；不足不自动说明科学效应或轴不稳定。",
    )
    table(
        "TableS5_prediction_all_weights",
        ps,
        "表S5：预测两种权重全部指标",
        "按人RMSE=sqrt(mean(person MSE))。重复范围非CI；绝不与旧固定一次OOF重抽混同。",
    )
    table(
        "TableS6_all1255_MC_statistics",
        allmc,
        "表S6：唯一当前MC统计量1255项",
        "完整FPCA采用最新100,000批次，排除已替代旧24项，其他当前批次全部保留。旧一次固定OOF重抽范围仍以独立来源角色保留，不作为20次重训练区间。",
    )
    for number, role, filename, title in [
        ("7", "python_remaining", "cluster_summary.json", "分区敏感性全部176项"),
        (
            "8",
            "variability",
            "U06_variability_summary.json",
            "观察支持下波动/负担全部96项",
        ),
        ("9", "python_remaining", "candidate_summary.json", "生理候选稳定性全部178项"),
    ]:
        rows = load(source / role / filename)
        frame = flat(rows)
        if number == "9":
            point_file = source / "candidate_reference_points.csv"
            extra_sources[str(point_file.relative_to(source))] = sha(point_file)
            points = pd.read_csv(point_file).set_index(["cell", "statistic"])[
                "reference_point"
            ]
            frame["reference_point"] = [
                float(points.loc[(s["cell"], s["statistic"])]) for s in rows
            ]
        table(
            "TableS" + number + "_" + filename[:-5],
            frame,
            "表S" + number + "：" + title,
            "完整保留失败、未定义、支持、MC状态和统计量量纲；仅描述性重抽范围，不能作临床/机制验证。",
        )
    recovery = load(source / "python_remaining/recovery_summary.json")
    baseline = load(source / "python_remaining/baseline_summary.json")
    table(
        "TableS10_partition_recovery_and_baseline",
        pd.concat(
            [
                flat(recovery).assign(analysis="partition_recovery"),
                flat(baseline).assign(analysis="baseline_development"),
            ],
            ignore_index=True,
        ),
        "表S10：前缀/shapelet恢复与基线开发",
        "训练定义分区，仅折内评价；缺类/不可估计保留；21人基线开发不等于封存集验证。",
    )
    table(
        "TableS11_baseline_descriptive",
        pd.read_csv(source / "cohort.csv"),
        "表S11：已记录基线描述",
        "数值项中位数[Q1,Q3]；缺失单列。量表基线VAS未填零。",
    )
    table(
        "TableS12_FPCA_redundancy",
        pd.read_csv(source / "FPCA_precision/redundancy.csv"),
        "表S12：历史审核过的FPCA冗余描述",
        "源签名/轴符号按该历史参考固定，不与新绘图任意翻转混用；相关非独立生理机制证据。",
    )
    table(
        "TableS13_prediction_all20_repeats",
        repeats,
        "表S13：全部20重复的配对指标",
        "重复不是独立受试者，不做跨折t检验；全部指标和权重均保留。",
    )
    # Fig1: bars only for code counts, not a survival plot.
    fig = figure(
        "Figure 1 | Observation support and first recorded codes",
        (12, 7),
        "215 people | 3,424 numeric ratings | first coded minute is a record, not an exact event time",
    )
    ax = fig.subplots(2, 1)
    ax[0].bar(obs.minute, obs.observed_people, color=COLORS[0], width=0.7)
    for t, n in zip(obs.minute, obs.observed_people):
        ax[0].text(t, n + 3, str(n), ha="center", fontsize=8)
    style(
        ax[0],
        "A  Numeric observations at each actual minute",
        "Actual minute",
        "People",
    )
    ax[0].set_ylim(0, 255)
    ax[0].set_xticks(range(1, 21))
    ax[0].text(
        0.02,
        0.93,
        "Complete 1–10 min: n=206     Complete 1–20 min: n=56",
        transform=ax[0].transAxes,
        fontsize=10,
    )
    ax[1].bar(
        markers.time_min,
        markers.n_first_E,
        color=COLORS[0],
        label="First E (150 people)",
    )
    ax[1].bar(
        markers.time_min,
        markers.n_first_T,
        bottom=markers.n_first_E,
        color=COLORS[1],
        label="First T (9 people)",
    )
    style(ax[1], "B  First recorded code counts", "First coded minute", "People")
    ax[1].set_xticks(range(1, 21))
    ax[1].legend(frameon=False, loc="upper left")
    ax[1].set_ylim(0, 55)
    ax[1].text(
        0.99,
        0.92,
        "56 people without E/T by minute 20",
        ha="right",
        transform=ax[1].transAxes,
    )
    save(
        fig,
        out,
        "Figure1_observation_support",
        "图1：逐分钟实测人数和首次E/T编码频数。曲线晚期人数下降必须与VAS均值同时解释；不是生存/真实中止时刻或安全发生率。",
        records,
    )
    # Fig2: descriptive empirical ranges, composition algebra, strict spans.
    fig = figure(
        "Figure 2 | Observed ratings, composition and finite changes",
        (13, 11),
        "Ranges: q.025–q.975 from 200,000 whole-person draws; descriptive, not calibrated CIs. Hollow: MC target unmet.",
    )
    gs = fig.add_gridspec(3, 3, height_ratios=[1.2, 1.15, 1])
    a = fig.add_subplot(gs[0, :])
    b = fig.add_subplot(gs[1, :])
    a.fill_between(
        obs.minute,
        obs.resampling_lower,
        obs.resampling_upper,
        color=COLORS[0],
        alpha=0.18,
        label="Descriptive resampling range",
    )
    a.plot(
        obs.minute,
        obs.mean_observed,
        "o-",
        color=COLORS[0],
        ms=4,
        label="Mean among observed people",
    )
    style(
        a,
        "A  Different observed populations at each minute",
        "Actual minute",
        "VAS (0–10)",
    )
    a.set_ylim(0, 10)
    a.set_xticks(range(1, 21))
    a.legend(frameon=False, loc="upper right")
    x = comp.start_min.to_numpy()
    w = 0.24
    b.bar(
        x - w,
        comp.paired_observed_change,
        w,
        color=COLORS[0],
        label="Common-observer change",
    )
    b.bar(
        x,
        comp.composition_total,
        w,
        color=COLORS[1],
        label="Start/end composition total",
    )
    b.bar(
        x + w,
        comp.observed_mean_change,
        w,
        color=COLORS[2],
        label="Observed mean change",
    )
    b.axhline(0, color="#555555", lw=0.8)
    style(
        b,
        "B  Observed mean change = common-observer change + composition total",
        "Start minute t (interval t to t+1)",
        "Change (VAS)",
    )
    b.set_xticks(range(1, 20))
    b.legend(frameon=False, ncol=3, fontsize=9)
    for i, h in enumerate([1, 2, 5]):
        a = fig.add_subplot(gs[2, i])
        rows = [
            s for s in finite if s["h_minutes"] == h and s["statistic"] == "mean_rate"
        ]
        interval_points(a, rows, COLORS[i])
        a.axhline(0, color="#777777", lw=0.8)
        style(
            a,
            f"{chr(67 + i)}  h={h} min; all h+1 values required",
            "Start minute",
            "Mean change / h (VAS/min)",
        )
        a.set_ylim(-0.55, 1.25)
        a.set_xticks(range(1, 21, 3))
        a.text(
            0.98,
            0.95,
            f"n: {rows[0]['people']} to {rows[-1]['people']}",
            ha="right",
            transform=a.transAxes,
            fontsize=9,
        )
    save(
        fig,
        out,
        "Figure2_VAS_composition_finite_changes",
        "图2：A为每分钟自身观察集的均值及200,000重抽描述范围；人数见图1/表2。B为代数恒等式，构成项非退出因果效应且没有bootstrap范围。C–E为不同支持人群的有限变化率，跨度内全部分钟均需数值；空心为该均值速率MC不足（h=1，13→14分钟）。这些不是瞬时导数或显著恢复区。",
        records,
    )
    # Fig3: retain code order and all zero co-occurrence cells.
    fig = figure(
        "Figure 3 | Recorded symptom and perceived-region context",
        (14, 12),
        "Marginals: n=209 per recorded field; joint cells: n=204 with both fields. Counts in cells; colour = joint %.",
    )
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.5])
    margins = {}
    for i, kind in enumerate(["symptom", "region"]):
        a = fig.add_subplot(gs[0, i])
        rows = [s for s in symptoms if s["kind"] == kind]
        margins[kind] = rows
        yy = np.arange(len(rows))
        a.barh(yy, [s["point"] * 100 for s in rows], color=COLORS[i], alpha=0.8)
        a.set_yticks(yy, [s["code"] + " " + s["label"] for s in rows])
        a.invert_yaxis()
        a.set_xlim(0, 100)
        for y, s in zip(yy, rows):
            a.plot(
                [100 * s["lower"]["estimate"], 100 * s["upper"]["estimate"]],
                [y, y],
                color="#333333",
                lw=0.8,
            )
            a.text(
                s["upper"]["estimate"] * 100 + 1,
                y,
                str(s["count"]) + (" †" if s["status"] != "MC_PRECISION_MET" else ""),
                va="center",
                fontsize=8,
            )
        style(
            a,
            f"{chr(65 + i)}  {kind.title()} codes (recorded n=209)",
            "Listed in recorded field (%)",
        )
    a = fig.add_subplot(gs[1, :])
    counts = np.zeros((12, 9), int)
    for i, s in enumerate(margins["symptom"]):
        for j, r in enumerate(margins["region"]):
            counts[i, j] = next(
                x["count"]
                for x in symptoms
                if x["kind"] == "symptom_region_pair"
                and x["code"] == s["code"] + "_" + r["code"]
            )
    image = a.imshow(
        counts / 204 * 100,
        cmap="Blues",
        vmin=0,
        vmax=max(1, counts.max() / 204 * 100),
        aspect="auto",
    )
    for (i, j), n in np.ndenumerate(counts):
        code = margins["symptom"][i]["code"] + "_" + margins["region"][j]["code"]
        s = next(
            x
            for x in symptoms
            if x["kind"] == "symptom_region_pair" and x["code"] == code
        )
        a.text(
            j,
            i,
            str(n) + ("†" if s["status"] != "MC_PRECISION_MET" else ""),
            ha="center",
            va="center",
            fontsize=9,
            color="white" if n > counts.max() * 0.55 else "#222222",
        )
    a.set_yticks(range(12), [s["code"] + " " + s["label"] for s in margins["symptom"]])
    a.set_xticks(
        range(9),
        [r["code"] + "\n" + textwrap.fill(r["label"], 14) for r in margins["region"]],
        fontsize=9,
    )
    a.set_title(
        "C  All 108 symptom–region co-occurrences (both fields recorded n=204)",
        loc="left",
        fontweight="bold",
        fontsize=11,
        pad=12,
    )
    fig.colorbar(image, ax=a, label="Both codes listed (% of 204)", shrink=0.85)
    save(
        fig,
        out,
        "Figure3_symptoms_regions_cooccurrence",
        "图3：源英文术语与代码保留，bloating和abdominal distension不合并。边际各209、共现204；两字段各6人缺失且不是同一组人。热图包含全部零格，不条件化于某一个症状。边际线为200,000整人重抽描述范围，†为对应MC不足；未列出不等于临床阴性。",
        records,
    )
    # Fig4: separate FVE, basis and mode illustration.
    fig = figure(
        "Figure 4 | Complete-curve FPCA",
        (12, 11),
        "100,000 draws per interval | FVE MC: 8/8 met; subspace angles: 4/8; axis inner products: 0/8. No biological labels.",
    )
    ax = fig.subplots(3, 2)
    fve_rows = []
    basis_rows = []
    for j, (cell, n, end) in enumerate([("F10", 206, 10), ("F20", 56, 20)]):
        ref = refs[cell]
        point = np.cumsum(ref["fve"])
        rows = sorted(
            [s for s in fpc if s["cell"] == cell and s["metric"] == "cumulative_fve"],
            key=lambda s: s["index"],
        )
        for s, v in zip(rows, point):
            s = dict(s, point=float(v))
            fve_rows.append(s)
        interval_points(
            ax[0, j], [dict(s, point=float(v)) for s, v in zip(rows, point)], COLORS[j]
        )
        style(
            ax[0, j],
            f"{chr(65 + j)}  1–{end} min; n={n}",
            "Number of components",
            "Cumulative explained variance",
        )
        ax[0, j].set_ylim(0, 1.02)
        ax[0, j].set_xticks(range(1, 5))
        phi = np.asarray(ref["phi"])
        tt = np.arange(1, end + 1)
        for k in range(4):
            ax[1, j].plot(tt, phi[:, k], color=COLORS[k], label="PC" + str(k + 1))
            for t, v in zip(tt, phi[:, k]):
                basis_rows.append(
                    dict(
                        cell=cell,
                        people=n,
                        minute=int(t),
                        PC=k + 1,
                        phi=float(v),
                        mean=ref["mean"][t - 1],
                        eigenvalue=ref["eigenvalue"][k],
                    )
                )
        ax[1, j].axhline(0, color="#777777", lw=0.8)
        style(
            ax[1, j],
            f"{chr(67 + j)}  Weighted bases, 1–{end} min",
            "Actual minute",
            r"Basis amplitude (min$^{-1/2}$)",
        )
        ax[1, j].legend(frameon=False, ncol=4, fontsize=8, loc="upper center")
        ax[1, j].set_xticks([1, 3, 5, 7, 10] if end == 10 else [1, 5, 10, 15, 20])
    ref = refs["F10"]
    phi = np.asarray(ref["phi"])
    mean = np.asarray(ref["mean"])
    tt = np.arange(1, 11)
    for k in range(2):
        a = ax[2, k]
        delta = np.sqrt(ref["eigenvalue"][k]) * phi[:, k]
        a.plot(tt, mean, color="#222222", label="Mean")
        a.plot(tt, mean + delta, "--", color=COLORS[0], label="Mean + 1 score SD")
        a.plot(tt, mean - delta, ":", color=COLORS[1], label="Mean − 1 score SD")
        style(
            a,
            f"{chr(69 + k)}  PC{k + 1} model mode (not a CI), n=206",
            "Actual minute",
            "VAS",
        )
        a.legend(frameon=False, fontsize=8)
    table(
        "TableS14_FPCA_FVE_and_basis",
        pd.DataFrame(basis_rows),
        "表S14：FPCA均值、特征值和基函数",
        "加权分钟度量归一化；显示符号为数学约定。参考曲线与特征轴不是临床机制。",
    )
    save(
        fig,
        out,
        "Figure4_complete_FPCA",
        "图4：两完整者人群分别206/56人。A–B累计FVE及100,000重抽描述范围，不是轴方向检验。C–D原参考四个加权基函数。E–F均值±sqrt(λ)φ为1评分SD的模型模式示意，非CI/实测极限/生理过程；轴符号任意。",
        records,
    )
    # Fig5: all 20 metric repetitions, exact median and min/max, paired within repeat.
    fig = figure(
        "Figure 5 | Internal future-rating evaluation",
        (13, 9),
        "All 20 whole-person nested-CV repeats | points = repeats; black = median; line = min/max. Not population CIs.",
    )
    ax = fig.subplots(2, 2)

    def repeat_plot(a, task, weight, difference=False):
        metric_names = [
            metric + "_" + model + ("_minus_last_value" if difference else "")
            for metric in ["MAE", "RMSE"]
            for model in (
                ["ridge", "random_forest"]
                if difference
                else ["last_value", "ridge", "random_forest"]
            )
        ]
        for i, name in enumerate(metric_names):
            vals = (
                repeats[
                    (repeats.task == task)
                    & (repeats.weighting == weight)
                    & (repeats.metric == name)
                ]
                .sort_values("repeat")
                .value.to_numpy()
            )
            assert len(vals) == 20
            y = i + np.linspace(-0.13, 0.13, 20)
            color = COLORS[i % (2 if difference else 3)]
            a.scatter(vals, y, s=14, color=color, alpha=0.55)
            a.plot([min(vals), max(vals)], [i, i], color="#222222", lw=1.5)
            a.scatter(np.median(vals), i, color="black", marker="D", s=22, zorder=5)
        labels = [
            name.replace("_minus_last_value", " − persistence")
            .replace("random_forest", "RF")
            .replace("last_value", "persistence")
            .replace("_", " ")
            for name in metric_names
        ]
        a.set_yticks(range(len(labels)), labels)
        a.invert_yaxis()
        a.set_ylim(len(labels) - 0.4, -0.6)
        if difference:
            a.axvline(0, color="#777777", lw=1)

    for i, (task, weight, scope) in enumerate(
        [
            ("next_rating", "window_equal", "Next rating: 213 people / 2,781 windows"),
            ("five_to_ten", "person_equal", "Minute 5 to 10: 206 people"),
        ]
    ):
        repeat_plot(ax[i, 0], task, weight)
        repeat_plot(ax[i, 1], task, weight, True)
        style(
            ax[i, 0],
            f"{chr(65 + i * 2)}  {scope}\n{weight.replace('_', ' ')}",
            "Error (VAS)",
        )
        style(
            ax[i, 1],
            f"{chr(66 + i * 2)}  Same-repeat paired differences",
            "Model error − persistence (VAS)",
        )
    save(
        fig,
        out,
        "Figure5_internal_prediction",
        "图5：全部20重复；点是重复的综合OOF指标，黑菱形中位数、线min/max；重复并非独立样本，范围为划分与训练敏感性。外5内4折均整人划分。下一评分窗口等权：ridge/RF的MAE高于持续值而RMSE较低；5→10任务两指标均降低。任务样本/目标不同，不作预测间隔因果比较。",
        records,
    )
    # Supplement S1: actual stability and the all-person paired reconstruction metric.
    fig = figure(
        "Supplement S1 | FPCA stability and whole-curve reconstruction",
        (12, 9),
        "Stability: 100,000 subject draws per interval. Reconstruction: test curve participates in projection; not forecasting.",
    )
    ax = fig.subplots(2, 2)
    for j, metric in enumerate(["subspace_angle_degree", "matched_abs_inner_product"]):
        available = sorted({s["metric"] for s in fpc})
        if metric not in available:
            metric = next(
                m for m in available if ("angle" in m if j == 0 else "inner" in m)
            )
        for i, cell in enumerate(["F10", "F20"]):
            rows = sorted(
                [s for s in fpc if s["cell"] == cell and s["metric"] == metric],
                key=lambda s: s["index"],
            )
            for s in rows:
                x = s["index"] + (-0.09 if i == 0 else 0.09)
                lo = s["lower"]["estimate"]
                hi = s["upper"]["estimate"]
                ax[0, j].plot([x, x], [lo, hi], color=COLORS[i], lw=3, alpha=0.8)
                ax[0, j].scatter(
                    [x, x],
                    [lo, hi],
                    s=20,
                    facecolors=COLORS[i]
                    if s["status"] == "MC_PRECISION_MET"
                    else "white",
                    edgecolors=COLORS[i],
                )
            ax[0, j].plot(
                [],
                [],
                color=COLORS[i],
                label=cell + " (n=" + str(206 if i == 0 else 56) + ")",
            )
        style(
            ax[0, j],
            "A  Maximum subspace angle"
            if j == 0
            else "B  Matched absolute axis inner product",
            "Subspace dimension" if j == 0 else "Matched component",
            "Degrees" if j == 0 else "|Weighted inner product|",
        )
        ax[0, j].set_xticks(range(1, 5))
        ax[0, j].legend(frameon=False, fontsize=8)
    cv_rows = []
    for j, cell in enumerate(cv):
        a = ax[1, j]
        rows = cell["complete_repeats"]
        assert len(rows) == 20
        for k in range(5):
            vals = np.array([r["paired_difference"][k] for r in rows])
            a.scatter(
                k + np.linspace(-0.08, 0.08, 20),
                vals,
                s=14,
                color=COLORS[k],
                alpha=0.45,
            )
            a.plot([k, k], [vals.min(), vals.max()], color="#333333")
            a.scatter(k, np.median(vals), s=25, color="black", marker="D")
            for r in rows:
                cv_rows.append(
                    dict(
                        cell=cell["cell"],
                        repeat=r["repeat"],
                        components=k,
                        mean_person_RMSE=r["mean_rmse"][k],
                        person_constant_RMSE=r["person_constant_rmse"],
                        paired_difference=r["paired_difference"][k],
                    )
                )
        a.axhline(0, color="#777777", lw=0.8)
        style(
            a,
            f"{chr(67 + j)}  {cell['cell']}; all 20 repeats",
            "Retained components",
            "Mean paired individual RMSE difference (VAS)",
        )
        a.set_xticks(range(5))
    table(
        "TableS15_FPCA_reconstruction_all_repeats",
        pd.DataFrame(cv_rows),
        "表S15：全曲线重建全部重复",
        "同人同权梯形个人常数基准。差为每人RMSE差的均值，不是未来评分误差；20划分范围非CI。",
    )
    save(
        fig,
        out,
        "FigureS1_FPCA_stability_reconstruction",
        "图S1：上排为100,000重抽范围端点，空心端点代表该统计量MC不足。角度与内积均不能仅由MC不足推断轴不稳定。下排为全部20重复、0–4维同权个人常数基准的平均个体RMSE差；测试全轨迹参与投影，属于重建。",
        records,
    )
    # S2 uses the already independently verified original diagnostics.
    diagnostic = source / "GAMM_diagnostics"
    conditional = load(diagnostic / "GAMM_conditional_diagnostics.json")
    grows = []
    for p in sorted(diagnostic.glob("reference_diagnostics__*.json")):
        d = load(p)["result"]
        cell = p.stem.replace("reference_diagnostics__", "")
        extra_sources[str(p.relative_to(source))] = sha(p)
        counts = {
            r["apVar_finite_matrix"]: r["n"]
            for r in conditional
            if r["cell"] == cell and r["metric"] == "edf"
        }
        grows.append(
            dict(
                cell=cell,
                curve=d["curve"],
                apVar_finite=d["apVar_finite_matrix"],
                apVar_condition=d["apVar_covariance_condition_number"],
                bootstrap_apVar_nonfinite=counts.get(False, 0),
                bootstrap_apVar_finite=counts.get(True, 0),
                apVar_message=d["apVar_message"],
                optimizer_exit_code=d["optimizer_exit_code"],
                role="working model; no likelihood-profile identifiability proof",
            )
        )
    assert sum(r["bootstrap_apVar_nonfinite"] for r in grows) == 15651
    gtable = pd.DataFrame([{k: v for k, v in r.items() if k != "curve"} for r in grows])
    table(
        "TableS16_GAMM_reference_diagnostics",
        gtable,
        "表S16：7个GAMM参考数值诊断",
        "近似协方差不是Hessian；未保存退出码为NULL。非有限apVar未作为曲线失败删除。0/120端点MC达标。",
    )
    table(
        "TableS17_GAMM_conditional_diagnostics",
        flat(conditional),
        "表S17：拟合后apVar条件诊断",
        "条件组不是随机分配，不能证明因果或人口覆盖；各组次数来自已保存全部35,000重抽。",
    )
    fig = figure(
        "Supplement S2 | GAMM working models and numerical diagnostics",
        (13, 9),
        "35,000 successful fits; 15,651 nonfinite apVar retained. Curve endpoints: MC 0/120 met; covariance is not a Hessian.",
    )
    ax = fig.subplots(2, 2)
    for i, end in enumerate([10, 20]):
        for j, r in enumerate([r for r in grows if len(r["curve"]) == end]):
            ax[0, i].plot(
                range(1, end + 1), r["curve"], color=COLORS[j], label=r["cell"]
            )
        style(
            ax[0, i],
            f"{chr(65 + i)}  {end}-minute reference curves",
            "Actual minute",
            "Fitted VAS",
        )
        ax[0, i].set_ylim(0, 10)
        ax[0, i].legend(frameon=False, fontsize=8)
        ax[0, i].set_xticks([1, 3, 5, 7, 10] if end == 10 else [1, 5, 10, 15, 20])
    xx = np.arange(len(grows))
    ax[1, 0].barh(
        xx,
        [r["bootstrap_apVar_finite"] for r in grows],
        color=COLORS[0],
        label="Finite apVar",
    )
    ax[1, 0].barh(
        xx,
        [r["bootstrap_apVar_nonfinite"] for r in grows],
        left=[r["bootstrap_apVar_finite"] for r in grows],
        color=COLORS[1],
        label="Nonfinite apVar",
    )
    ax[1, 0].set_yticks(xx, [r["cell"] for r in grows])
    style(ax[1, 0], "C  apVar records per 5,000-fit cell", "Successful fits")
    ax[1, 0].set_ylim(-0.6, len(grows) + 0.3)
    ax[1, 0].legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    a = ax[1, 1]
    for i, r in enumerate(grows):
        if r["apVar_condition"] is not None:
            a.scatter(r["apVar_condition"], i, color=COLORS[0], s=35)
        else:
            a.text(
                1.12e3,
                i,
                "not finite / unavailable",
                fontsize=8,
                va="center",
                color="#8d4629",
            )
    a.set_xscale("log")
    a.set_xlim(1e3, 1e7)
    a.set_ylim(-0.6, len(grows) - 0.4)
    a.set_yticks(xx, [r["cell"] for r in grows])
    style(a, "D  Approximate covariance conditioning", "Condition number (log scale)")
    save(
        fig,
        out,
        "FigureS2_GAMM_numerical_diagnostics",
        "图S2：7种参考并非全部同一人群；G10_common为同当前观察支持、G10/G20_complete为完整者、其余G20为全观察工作模型。重拟合参考与旧曲线最大差0。非有限apVar为近似协方差警示，不证明不可辨识、脊线或原因，全部保留。",
        records,
    )
    # Candidate plots show support and diagnostics, avoiding incompatible coefficient scales.
    candidate = load(source / "python_remaining/candidate_summary.json")
    unique = {s["cell"]: s for s in candidate}
    cells = sorted(
        unique.values(), key=lambda s: (s["cell_description"]["kind"], s["cell"])
    )
    kinds = ["planned24", "joint22", "egg66"]
    ct = []
    for kind in kinds:
        rows = [s for s in candidate if s["cell_description"]["kind"] == kind]
        un = [s for s in cells if s["cell_description"]["kind"] == kind]
        ct.append(
            dict(
                kind=kind,
                models=len(un),
                statistics=len(rows),
                MC_met=sum(s["status"] == "MC_PRECISION_MET" for s in rows),
                MC_insufficient=sum(s["status"] != "MC_PRECISION_MET" for s in rows),
                failed_fits=sum(s["failed_replicates"] for s in un),
                people_min=min(s["eligible_people"] for s in un),
                people_max=max(s["eligible_people"] for s in un),
            )
        )
    assert (
        sum(r["models"] for r in ct) == 112 and sum(r["failed_fits"] for r in ct) == 122
    )
    table(
        "TableS18_candidate_support_diagnostics",
        pd.DataFrame(ct),
        "表S18：候选模型支持与失败",
        "112模型共178统计量；共同模型22个有3系数及同样本SSE减量，不能视作OOF预测增益。122次rank失败保留。主要p/q NULL。",
    )
    fig = figure(
        "Supplement S3 | Candidate-model support and retained diagnostics",
        (13, 7),
        "Unvalidated ECG / Hb / EGG targets | 112 model cells, 178 statistics | primary p/q NULL; no clinical or mechanism claim",
    )
    ax = fig.subplots(1, 3, gridspec_kw={"width_ratios": [1.6, 1, 1]})
    offset = 0
    for j, kind in enumerate(kinds):
        ss = [s for s in cells if s["cell_description"]["kind"] == kind]
        xx = np.arange(offset, offset + len(ss))
        ax[0].scatter(
            xx, [s["eligible_people"] for s in ss], color=COLORS[j], s=15, label=kind
        )
        offset += len(ss)
    style(
        ax[0],
        "A  Subject support in every model cell",
        "Model index (grouped by family)",
        "Eligible people",
    )
    ax[0].legend(frameon=False, fontsize=8)
    yy = np.arange(3)
    ax[1].barh(yy, [r["MC_met"] for r in ct], color=COLORS[0], label="MC met")
    ax[1].barh(
        yy,
        [r["MC_insufficient"] for r in ct],
        left=[r["MC_met"] for r in ct],
        color=COLORS[1],
        label="MC insufficient",
    )
    ax[1].set_yticks(yy, kinds)
    style(ax[1], "B  All 178 statistics", "Statistics")
    ax[1].legend(frameon=False, fontsize=8)
    ax[2].bar(yy, [r["failed_fits"] for r in ct], color=COLORS[1])
    ax[2].set_xticks(yy, kinds, rotation=25)
    style(
        ax[2],
        "C  Rank failures retained",
        "Model family",
        "Failed fits / 20,000 per cell",
    )
    save(
        fig,
        out,
        "FigureS3_candidate_support_diagnostics",
        "图S3：只展示未验证候选的实际支持和诊断。不同单位系数不合并森林图；所有系数/同样本SSE描述范围见S9及原结果目录。112模型2.24M次拟合，122rank失败，25/178 MC达标。不是正式生理假设检验。",
        records,
    )
    # S4: algebraic missing bounds and all source families, with fixed-OOF ranges separated.
    fig = figure(
        "Supplement S4 | Missing-rating algebra and MC status",
        (13, 8),
        "Algebraic bounds are not imputation or CIs. MC describes endpoint calculation precision, not scientific validity.",
    )
    ax = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1, 1.4]})
    bounds = pd.read_csv(source / "observed_algebra/bounded_means.csv")
    ax[0].fill_between(
        bounds.time_min,
        bounds.cohort_mean_lower,
        bounds.cohort_mean_upper,
        color=COLORS[1],
        alpha=0.23,
        label="0–10 algebraic bounds",
    )
    ax[0].plot(
        obs.minute, obs.mean_observed, color=COLORS[0], label="Observed-set mean"
    )
    style(ax[0], "A  Algebraic full-cohort mean bounds", "Actual minute", "VAS")
    ax[0].set_ylim(0, 10)
    ax[0].set_xticks([1, 5, 10, 15, 20])
    ax[0].legend(frameon=False, fontsize=8)
    groups = []
    for (role, filename), d in allmc.groupby(
        ["source_role", "source_file"], sort=False
    ):
        label = (
            "Fixed OOF: next rating"
            if role == "observations" and filename == "next_rating_summary.json"
            else "Fixed OOF: minute 5 to 10"
            if role == "observations" and filename == "five_to_ten_summary.json"
            else role + "/" + filename.replace("_summary.json", "").replace(".json", "")
        )
        groups.append((label, len(d), sum(d.status == "MC_PRECISION_MET")))
    yy = np.arange(len(groups))
    ax[1].barh(yy, [x[2] for x in groups], color=COLORS[0], label="MC met")
    ax[1].barh(
        yy,
        [x[1] - x[2] for x in groups],
        left=[x[2] for x in groups],
        color=COLORS[1],
        label="MC insufficient",
    )
    ax[1].set_yticks(yy, [textwrap.fill(x[0], 38) for x in groups], fontsize=8)
    for i, g in enumerate(groups):
        ax[1].text(g[1] + 2, i, f"{g[2]}/{g[1]}", va="center", fontsize=8)
    ax[1].set_xlim(0, max(g[1] for g in groups) * 1.18)
    style(
        ax[1], "B  All 1,255 current statistics; superseded FPCA excluded", "Statistics"
    )
    ax[1].legend(frameon=False, fontsize=8, loc="lower right")
    save(
        fig,
        out,
        "FigureS4_bounds_all_MC_status",
        "图S4：A仅将未观测VAS限制在0–10生成代数上下界，不补任何个体数据。B为所有当前批次的MC状态，旧FPCA被替代的24项不重复计入；两个旧固定OOF重抽来源单独显示，不代替新20重复预测评价。",
        records,
    )
    # S5: all recovery cells; baseline development distinct, missing cells remain absent.
    fig = figure(
        "Supplement S5 | Training-partition recovery and baseline development",
        (14, 10),
        "20 repeats attempted; ranges conditional on complete repeats. Undefined/incomplete retained; no clinical phenotypes or CIs.",
    )
    ax = fig.subplots(2, 1)
    for a, rows, title in [
        (ax[0], recovery, "A  Prefix and trained-shapelet recovery"),
        (
            ax[1],
            baseline,
            "B  Baseline development: 1–10 min n=21; 1–20 min n=6; sealed closed",
        ),
    ]:
        roster = [
            r
            for r in rows
            if r.get("metric") in ["balanced_accuracy_equal_fold_mean", None]
        ]
        keys = sorted({(r["cell"], r.get("prefix") or 0) for r in roster})
        rows = [
            r
            for r in roster
            if r.get("metric") is not None and r.get("median") is not None
        ]
        models = sorted({r["model"] for r in rows})
        for j, model in enumerate(models):
            for i, key in enumerate(keys):
                rr = [
                    r
                    for r in rows
                    if (r["cell"], r.get("prefix") or 0) == key and r["model"] == model
                ]
                if not rr:
                    continue
                r = rr[0]
                x = i + (j - (len(models) - 1) / 2) * 0.18
                a.plot(
                    [x, x],
                    [r["minimum"], r["maximum"]],
                    color=COLORS[j],
                    lw=1,
                    alpha=0.7,
                )
                a.scatter(x, r["median"], s=17, color=COLORS[j])
            a.plot([], [], color=COLORS[j], marker="o", ms=4, label=model)
        labels = []
        for i, key in enumerate(keys):
            rr = [r for r in rows if (r["cell"], r.get("prefix") or 0) == key]
            complete = min((r["complete_repeats"] for r in rr), default=0)
            labels.append(
                key[0]
                + (f"/p{key[1]}" if key[1] else "")
                + (f" [{complete}/20]" if a == ax[1] else "")
            )
            if not rr:
                a.text(
                    i,
                    0.15,
                    "no complete\nrepeat",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="#8d4629",
                )
        a.set_xticks(range(len(keys)), labels, rotation=65, ha="right", fontsize=8)
        a.set_xlim(-0.5, len(keys) - 0.5)
        style(a, title, "Frozen cell / prefix", "Balanced accuracy (equal-fold mean)")
        a.set_ylim(0, 1.02)
        a.legend(frameon=False, fontsize=8, ncol=max(1, len(models)))
    save(
        fig,
        out,
        "FigureS5_partition_recovery_baseline",
        "图S5：全部冻结cell的balanced accuracy摘要，指标按原冻结折等权；非临床代码本或临床预测。20次计划重复的范围仅条件于完整重复，不是CI。基线1–10分钟21人：k2完整20、k3完整18、k4完整9、k5完整0；1–20分钟6人，各k均不可估计，图中保留空位/说明。各模型实际状态及失败见S10；无封存或外部验证。",
        records,
    )
    # Publish an artifact index without manuscript text or interpreted results.
    index = ["# Aggregate figures and tables", "", "## Figures", ""]
    for record in records:
        name = record["id"]
        index.append(
            f"- [{name}](figures/{name}.png): [PDF](figures/{name}.pdf), [SVG](figures/{name}.svg)"
        )
    index.extend(["", "## Tables", ""])
    for name in tables:
        index.append(f"- [{name}](tables/{name}.csv)")
    index.extend(["", "[Combined figure PDF](figure_review.pdf)", ""])
    (out / "README.md").write_text("\n".join(index), encoding="utf-8")
    # Re-open each vector figure into the combined review book using their original SVG-free PNGs.
    with PdfPages(out / "figure_review.pdf") as book:
        for r in records:
            img = plt.imread(out / "figures" / (r["id"] + ".png"))
            fig = plt.figure(figsize=(12, 12 * img.shape[0] / img.shape[1]))
            a = fig.add_axes([0, 0, 1, 1])
            a.imshow(img)
            a.axis("off")
            book.savefig(fig, dpi=150)
            plt.close(fig)
    for name, h in sm["outputs_sha256"].items():
        assert sha(source / name) == h, "Source altered during reporting"
    write_new(out / "figure_index.json", records)
    write_new(
        out / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            config_sha256=sha(config_path),
            source_manifest_sha256=sha(source / "manifest.json"),
            extra_source_sha256=extra_sources,
            code_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            python=sys.version,
            software=dict(
                numpy=np.__version__,
                pandas=pd.__version__,
                matplotlib=matplotlib.__version__,
            ),
            main_figures=5,
            supplement_figures=5,
            main_tables=3,
            supplement_tables=18,
            primary_p_q=None,
            sealed_people_used=0,
            original_full_scientific_objective_complete=False,
            outputs_sha256={
                str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
            },
        ),
    )
    print(
        json.dumps(
            dict(output=str(out), figures=len(records), tables=len(tables)),
            ensure_ascii=False,
        ),
        flush=True,
    )
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config", type=Path, default=ROOT / "config/public_figures_20261005_v1.json"
    )
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    build(a.config, a.output)
