"""Conservative helpers for participant schedule and identity matching."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re


PARTICIPANT_LINE = re.compile(
    r"^\s*(?P<code>[Zz]?\d{3})(?!\d)\s*(?P<name>[\u3400-\u9fff·]{2,8})"
)
MONTH_DAY = re.compile(
    r"(?<!\d)(?P<month>1[0-2]|0?[1-9])\s*[月.]\s*(?P<day>3[01]|[12]\d|0?[1-9])\s*日?"
)
GROUP_SUFFIXES = ("辣椒素组", "非辣组", "健康2", "治神", "健康", "推拿", "受针", "预")


def normalize_name(value: str) -> str:
    """Remove notes and non-name characters without guessing a spelling."""
    value = re.sub(r"[（(].*?[）)]", "", value or "")
    value = re.sub(r"终止|排除", "", value)
    return "".join(re.findall(r"[\u3400-\u9fff·]", value))


def strip_group_suffix(value: str) -> str:
    value = normalize_name(value)
    changed = True
    while changed:
        changed = False
        for suffix in GROUP_SUFFIXES:
            if value.endswith(suffix) and len(value) > len(suffix) + 1:
                value = value[: -len(suffix)]
                changed = True
    return value


def parse_participant_line(line: str) -> dict[str, str] | None:
    """Parse a schedule line beginning with a three-digit participant code."""
    match = PARTICIPANT_LINE.match(line or "")
    if not match:
        return None
    remainder = line[match.end() :]
    # Participant schedule/correction lines carry an assignment, condition,
    # reservation, or T-session marker. This excludes ordinary chat such as
    # Storage-location notes, without depending on a list of names.
    if not re.search(r"(?:--?|—|（预|\(预|[Tt][12]?|[AaBb][123]?)", remainder):
        return None
    raw_name = match.group("name")
    name = strip_group_suffix(raw_name)
    if len(name) < 2:
        return None
    upper = line.upper()
    group = ""
    for token in ("FD", "健康2", "健康", "治神", "推拿", "辣椒素"):
        if token.upper() in upper:
            group = token
            break
    planned = "预" in line or ("待定" in line and "--" not in line)
    return {
        "code_raw": match.group("code"),
        "code_numeric": str(int(re.sub(r"\D", "", match.group("code")))),
        "name_raw": raw_name,
        "name": name,
        "group": group,
        "mention_type": "reservation" if planned else "assigned_or_recorded",
        "line": line.strip(),
    }


def infer_target_date(
    content: str,
    message_datetime: datetime,
    previous_target: date | None = None,
    previous_message_datetime: datetime | None = None,
) -> tuple[date, str]:
    """Infer the intended experiment date and state the evidence used."""
    message_date = message_datetime.date()
    candidates = []
    for match in MONTH_DAY.finditer(content or ""):
        try:
            candidate = date(
                message_date.year, int(match.group("month")), int(match.group("day"))
            )
        except ValueError:
            continue
        candidates.append(candidate)
    if candidates:
        candidate = candidates[0]
        if abs((candidate - message_date).days) <= 2:
            return candidate, "explicit_month_day"
        # A far-away copied date is treated as stale when the message says
        # tomorrow/today; the discrepancy remains visible in the audit output.
        if "明天" in content:
            return message_date + timedelta(
                days=1
            ), "stale_explicit_date_message_plus_one"
        if "今日" in content or "今天" in content:
            return message_date, "stale_explicit_date_message_day"
        return candidate, "explicit_month_day_far_from_message"
    if "明天" in (content or ""):
        return message_date + timedelta(days=1), "message_plus_one_day"
    if (
        previous_target is not None
        and previous_message_datetime is not None
        and message_datetime - previous_message_datetime <= timedelta(hours=30)
        and any(word in (content or "") for word in ("调整", "更正"))
    ):
        return previous_target, "inherited_recent_adjustment_date"
    return message_date, "message_day"


def levenshtein(left: str, right: str) -> int:
    """Return Unicode code-point edit distance."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, start=1):
        current = [i]
        for j, char_right in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (char_left != char_right),
                )
            )
        previous = current
    return previous[-1]


def normalized_vas_token(value: object) -> str:
    token = str(value or "").strip().upper()
    if token in {"", "E", "T", "NA", "N/A", "NAN"}:
        return ""
    try:
        number = float(token)
    except ValueError:
        return "?"
    return str(int(number)) if number.is_integer() else format(number, ".12g")
