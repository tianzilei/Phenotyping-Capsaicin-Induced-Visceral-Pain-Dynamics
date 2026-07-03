from __future__ import annotations

import argparse
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def tag(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()


def image_description(paragraph: ET.Element) -> str:
    doc_pr = paragraph.find(".//wp:docPr", NS)
    if doc_pr is None:
        return ""
    return (doc_pr.attrib.get("descr") or "").strip()


def remove_duplicates(document_xml: bytes) -> tuple[bytes, int]:
    root = ET.fromstring(document_xml)
    body = root.find(".//w:body", NS)
    if body is None:
        return document_xml, 0

    removed = 0
    children = list(body)
    index = 0
    while index < len(children) - 1:
        current = children[index]
        if current.tag != tag("w", "p"):
            index += 1
            continue

        descr = image_description(current)
        if not descr:
            index += 1
            continue

        next_child = children[index + 1]
        if next_child.tag == tag("w", "p") and paragraph_text(next_child) == descr:
            body.remove(next_child)
            children.pop(index + 1)
            removed += 1
            continue

        index += 1

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), removed


def update_docx(path: Path) -> int:
    with ZipFile(path, "r") as source:
        document_xml, removed = remove_duplicates(source.read("word/document.xml"))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp_path = Path(tmp.name)

        try:
            with ZipFile(tmp_path, "w", ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                    target.writestr(item, data)
            shutil.move(str(tmp_path), path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    args = parser.parse_args()
    print(f"Removed {update_docx(args.docx)} duplicate image caption paragraphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
