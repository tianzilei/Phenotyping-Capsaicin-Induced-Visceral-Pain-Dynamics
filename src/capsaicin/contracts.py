"""Strict, non-imputing ingestion of scheduled-minute VAS wide tables."""

import csv
import math
import re
from pathlib import Path


class ContractError(ValueError):
    """Input cannot be interpreted without an explicit data decision."""


def read_wide(path, config):
    cfg = config["data"]
    lower, upper = cfg.get("vas_min"), cfg.get("vas_max")
    if (
        type(lower) not in (int, float)
        or type(upper) not in (int, float)
        or not math.isfinite(lower)
        or not math.isfinite(upper)
        or lower >= upper
    ):
        raise ContractError("VAS 量纲未确定：请在配置中填写有限的 vas_min < vas_max。")
    minutes = cfg["expected_minutes"]
    if (
        not minutes
        or any(type(t) is not int or t < 0 for t in minutes)
        or minutes != sorted(set(minutes))
    ):
        raise ContractError("expected_minutes 必须为严格递增、不重复的非负整数。")
    if cfg.get("termination_tokens") != ["E", "T"]:
        raise ContractError("当前适配器只支持明确的 E/T 标记。其他编码需要新适配器。")
    missing = {str(t).strip().upper() for t in cfg["missing_tokens"]}
    if missing & {"E", "T"}:
        raise ContractError("缺失值编码不能包含终止标记。")
    pattern = re.compile(cfg["vas_column_pattern"])
    output, seen = [], set()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise ContractError("表头包含重复字段。")
        if cfg["id_column"] not in fields:
            raise ContractError("缺少研究编号列。")
        columns = {}
        for name in fields:
            match = pattern.fullmatch(name)
            if match:
                minute = int(match.group(1))
                if minute in columns:
                    raise ContractError("多个评分列映射到相同分钟。")
                columns[minute] = name
        if sorted(columns) != minutes:
            raise ContractError(
                "VAS 列集合与 expected_minutes 不一致；不得静默补列或丢列。"
            )
        for row_no, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ContractError(f"第 {row_no} 行字段数量与表头不一致。")
            sid = row[cfg["id_column"]].strip()
            if not sid or sid in seen:
                raise ContractError(f"第 {row_no} 行研究编号为空或重复。")
            seen.add(sid)
            termination = ""
            for minute in minutes:
                raw = row[columns[minute]]
                token = raw.strip().upper()
                vas = None
                if token in {"E", "T"}:
                    if termination and token != termination:
                        raise ContractError(f"第 {row_no} 行存在混合 E/T 标记。")
                    termination = token
                    status = "termination_" + token
                elif token in missing:
                    status = "post_termination" if termination else "missing"
                else:
                    try:
                        vas = float(raw)
                    except ValueError as exc:
                        raise ContractError(
                            f"第 {row_no} 行、第 {minute} 分钟存在未知评分文本。"
                        ) from exc
                    if not math.isfinite(vas) or not lower <= vas <= upper:
                        raise ContractError(
                            f"第 {row_no} 行、第 {minute} 分钟评分不在已声明量纲内。"
                        )
                    if termination:
                        raise ContractError(
                            f"第 {row_no} 行在终止标记之后仍有数字评分，需核验原始记录。"
                        )
                    status = "observed"
                output.append(
                    dict(
                        subject_id=sid,
                        time_min=minute,
                        vas=vas,
                        status=status,
                        raw_token=raw,
                        termination_code=termination,
                    )
                )
    if not seen:
        raise ContractError("表格没有受试者记录。")
    return output
