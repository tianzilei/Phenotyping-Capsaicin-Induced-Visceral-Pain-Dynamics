"""Normalize editable SVG resource names while preserving all references."""

import re


def normalize(text):
    names = re.findall(r'\bid="([^"]+)"', text)
    selected = [name for name in names if re.fullmatch(r"[a-z][0-9a-f]{8,}", name)]
    used = set(names)
    index = 0
    for name in dict.fromkeys(selected):
        index += 1
        while "resource_" + str(index) in used:
            index += 1
        replacement = "resource_" + str(index)
        used.add(replacement)
        text = text.replace('id="' + name + '"', 'id="' + replacement + '"')
        text = re.sub(r"#" + re.escape(name) + r"(?=[)\"'])", "#" + replacement, text)
    return text
