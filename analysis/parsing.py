"""
Code parsing utilities for symptom and region codes.
Extracts individual codes from compact multi-character strings.
"""

import re
from typing import Dict, List, Optional, Set

from analysis.constants import COMPOSITE_REGION_CODES


def parse_compact_codes(cell: str, valid_codes: Optional[Set[str]] = None) -> List[str]:
    """
    Parse compact multi-character codes from a string.

    Handles formats like "ACE", "A,C,E", "A;C;E", "A C E", etc.
    Strips separators, filters against valid codes if provided.

    Parameters
    ----------
    cell : str
        Input string containing codes (e.g. "ACE", "A,C,E").
    valid_codes : set, optional
        If provided, only keep codes that are in this set.

    Returns
    -------
    list of str
        Deduplicated list of individual codes in original order.

    Examples
    --------
    >>> parse_compact_codes("ACE")
    ['A', 'C', 'E']
    >>> parse_compact_codes("A,C,E")
    ['A', 'C', 'E']
    >>> parse_compact_codes("ACE", valid_codes={"A", "B"})
    ['A']
    """
    if not isinstance(cell, str) or not cell.strip():
        return []

    # Remove separators and whitespace
    cleaned = re.sub(r"[;,|/\s]+", "", cell.strip())

    # Extract individual characters
    codes = [c for c in cleaned if c.isalnum()]

    # Filter against valid codes if provided
    if valid_codes is not None:
        codes = [c for c in codes if c in valid_codes]

    # Deduplicate while preserving order
    return unique_keep_order(codes)


def parse_symptom_codes(cell: str) -> List[str]:
    """
    Parse symptom codes (alphabetic only) from a string.

    Parameters
    ----------
    cell : str
        Input string containing symptom codes.

    Returns
    -------
    list of str
        Deduplicated list of alphabetic codes.
    """
    if not isinstance(cell, str) or not cell.strip():
        return []

    cleaned = re.sub(r"[;,|/\s]+", "", cell.strip())
    codes = [c for c in cleaned if c.isalpha()]
    return unique_keep_order(codes)


def parse_region_codes(
    cell: str,
    valid_codes: Optional[Set[str]] = None,
    composite_codes: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """
    Parse region codes from a string, correctly handling multi-digit codes.

    Region codes may be stored as numeric strings (e.g. "25.0" from a float
    column). Multi-digit codes like "25" (whole abdomen = regions 2+5) are
    composite codes that decompose into their constituent base regions.
    Concatenated single-digit codes like "2356" (regions 2,3,5,6) are split
    into individual digits.

    Parameters
    ----------
    cell : str
        Input string containing region codes.
    valid_codes : set, optional
        If provided, the function first checks whether the cleaned entire
        string is a valid multi-digit code before falling back to character-
        by-character splitting.
    composite_codes : dict, optional
        Mapping of composite codes to their constituent base region codes
        (e.g. {"25": ["2", "5"]}). Uses COMPOSITE_REGION_CODES if None.

    Returns
    -------
    list of str
        Deduplicated list of base region codes.
    """
    if composite_codes is None:
        composite_codes = COMPOSITE_REGION_CODES

    if not isinstance(cell, str) or not cell.strip():
        return []

    # Remove separators, whitespace, and trailing decimal zeros
    cleaned = re.sub(r"[;,|/\s]+", "", cell.strip())
    cleaned = re.sub(r"\.0+$", "", cleaned)

    # Check if the entire cleaned string is a composite code (e.g. "25")
    if cleaned in composite_codes:
        codes = composite_codes[cleaned]
        if valid_codes is not None:
            codes = [c for c in codes if c in valid_codes]
        return unique_keep_order(codes)

    # If the entire cleaned string is a valid base code, use it whole
    if valid_codes is not None and cleaned in valid_codes:
        return [cleaned]

    # Otherwise fall back to character-by-character splitting
    codes = [c for c in cleaned if c.isdigit()]

    if valid_codes is not None:
        codes = [c for c in codes if c in valid_codes]

    return unique_keep_order(codes)


def map_codes(
    code_list: List[str],
    mapping: dict,
    unknown_prefix: str = "UNKNOWN_",
) -> List[str]:
    """
    Map code list to human-readable labels via a dictionary.

    Parameters
    ----------
    code_list : list of str
        List of codes to map.
    mapping : dict
        Dictionary mapping codes to labels.
    unknown_prefix : str
        Prefix for unrecognized codes.

    Returns
    -------
    list of str
        Mapped labels.
    """
    return [mapping.get(code, f"{unknown_prefix}{code}") for code in code_list]


def unique_keep_order(seq: list) -> list:
    """
    Return deduplicated list preserving insertion order.

    Parameters
    ----------
    seq : list
        Input list.

    Returns
    -------
    list
        Deduplicated list.
    """
    seen = set()
    result = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
