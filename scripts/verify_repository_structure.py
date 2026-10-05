"""Check public file boundaries and English code comments without running analyses."""

import ast
import io
import json
from pathlib import Path
import re
import subprocess
import tokenize

ROOT = Path(__file__).resolve().parents[1]
NON_ENGLISH = re.compile(
    r"[\u0400-\u052f\u0600-\u06ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]"
)
UNPUBLISHED = re.compile(
    r"manuscript|supplementary_latest|submission_integration", re.I
)
WRITING_NAME = re.compile(
    r"(?:^|[._-])(?:paper|article|submission|draft)(?:[._-]|$)", re.I
)


def artifact_issue(name):
    """Exclude writing artifacts from the current public tree, not method plans."""
    path = Path(name)
    if UNPUBLISHED.search(path.name) or path.suffix.lower() in {
        ".doc",
        ".docx",
        ".tex",
    }:
        return "Unpublished writing artifact excluded from public tree"
    if path.suffix.lower() in {
        ".md",
        ".rst",
        ".txt",
        ".html",
        ".pdf",
        ".ipynb",
    } and WRITING_NAME.search(path.name):
        return "Unpublished writing artifact excluded from public tree"
    if any(
        part.lower() in {"drafts", "manuscripts", "submission"} for part in path.parts
    ):
        return "Unpublished writing directory excluded from public tree"
    return None


def r_comments(text):
    """Read R comments while skipping quoted names, strings, and raw strings."""
    index = 0
    line = 1
    closing = {"(": ")", "[": "]", "{": "}"}
    while index < len(text):
        raw = re.match(r"[rR]([\"'])(-*)([([{])", text[index:])
        if raw:
            end_token = closing[raw.group(3)] + raw.group(2) + raw.group(1)
            end = text.find(end_token, index + raw.end())
            if end < 0:
                raise ValueError("Unterminated R raw string")
            end += len(end_token)
            line += text[index:end].count("\n")
            index = end
        elif text[index] in {"'", '"', "`"}:
            quote = text[index]
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    line += text[index : index + 2].count("\n")
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    line += text[index] == "\n"
                    index += 1
            else:
                raise ValueError("Unterminated R string")
        elif text[index] == "#":
            end = text.find("\n", index)
            if end < 0:
                end = len(text)
            yield line, text[index:end]
            index = end
        else:
            line += text[index] == "\n"
            index += 1


def comment_issues(name, text):
    """Check prose in comments/docstrings while preserving multilingual data literals."""
    issues = []
    if Path(name).suffix == ".py":
        tree = ast.parse(text, filename=name)
        prose = [
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT
        ]
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                docstring = ast.get_docstring(node, clean=False)
                if docstring:
                    prose.append((node.body[0].lineno, docstring))
    elif Path(name).suffix == ".R":
        prose = list(r_comments(text))
    else:
        return issues
    for line, content in prose:
        if NON_ENGLISH.search(content):
            issues.append(
                {"file": name, "line": line, "reason": "Non-English comment/docstring"}
            )
    return issues


def verify(root=ROOT):
    root = Path(root)
    names = sorted(
        set(
            subprocess.check_output(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=root,
            )
            .decode()
            .strip("\0")
            .split("\0")
        )
    )
    failures = []
    counts = {".py": 0, ".R": 0}
    for name in names:
        path = root / name
        if not name or not path.is_file():
            continue
        issue = artifact_issue(name)
        if issue:
            failures.append({"file": name, "reason": issue})
        if path.suffix in counts:
            counts[path.suffix] += 1
            try:
                failures.extend(comment_issues(name, path.read_text(encoding="utf-8")))
            except (SyntaxError, tokenize.TokenError, ValueError) as error:
                failures.append({"file": name, "reason": str(error)})
    return {
        "status": "FAIL" if failures else "PASS",
        "scope": "current public tree; historical snapshots are not rewritten",
        "Python_files": counts[".py"],
        "R_files": counts[".R"],
        "failures": failures,
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(result["status"] != "PASS")
