"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import sys
from types import FunctionType

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def portable(function):
    """Imported CLI modules are not installed on workers; send standalone code."""
    return FunctionType(
        function.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        function.__name__,
        function.__defaults__,
    )
