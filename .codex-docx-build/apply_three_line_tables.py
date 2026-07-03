from __future__ import annotations

import argparse
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)


def w_tag(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def set_attr(element: ET.Element, name: str, value: str) -> None:
    element.set(w_tag(name), value)


def first_child(parent: ET.Element, name: str) -> ET.Element | None:
    return parent.find(w_tag(name))


def ensure_child(parent: ET.Element, name: str, index: int | None = None) -> ET.Element:
    child = first_child(parent, name)
    if child is not None:
        return child
    child = ET.Element(w_tag(name))
    if index is None:
        parent.append(child)
    else:
        parent.insert(index, child)
    return child


def replace_borders(parent: ET.Element, borders_name: str, specs: dict[str, dict[str, str]]) -> None:
    for existing in list(parent.findall(w_tag(borders_name))):
        parent.remove(existing)
    borders = ET.SubElement(parent, w_tag(borders_name))
    for side, attrs in specs.items():
        side_element = ET.SubElement(borders, w_tag(side))
        for key, value in attrs.items():
            set_attr(side_element, key, value)


def no_border() -> dict[str, str]:
    return {"val": "nil"}


def line(size: str) -> dict[str, str]:
    return {"val": "single", "sz": size, "space": "0", "color": "000000"}


def clear_cell_borders(cell: ET.Element) -> None:
    tc_pr = ensure_child(cell, "tcPr", 0)
    replace_borders(
        tc_pr,
        "tcBorders",
        {
            "top": no_border(),
            "left": no_border(),
            "bottom": no_border(),
            "right": no_border(),
            "insideH": no_border(),
            "insideV": no_border(),
        },
    )


def set_header_bottom_border(row: ET.Element) -> None:
    for cell in row.findall(w_tag("tc")):
        tc_pr = ensure_child(cell, "tcPr", 0)
        replace_borders(
            tc_pr,
            "tcBorders",
            {
                "top": no_border(),
                "left": no_border(),
                "bottom": line("8"),
                "right": no_border(),
                "insideH": no_border(),
                "insideV": no_border(),
            },
        )


def apply_three_line_tables(document_xml: bytes) -> tuple[bytes, int]:
    root = ET.fromstring(document_xml)
    tables = root.findall(f".//{w_tag('tbl')}")

    for table in tables:
        tbl_pr = ensure_child(table, "tblPr", 0)
        replace_borders(
            tbl_pr,
            "tblBorders",
            {
                "top": line("12"),
                "left": no_border(),
                "bottom": line("12"),
                "right": no_border(),
                "insideH": no_border(),
                "insideV": no_border(),
            },
        )

        rows = table.findall(w_tag("tr"))
        for row in rows:
            for cell in row.findall(w_tag("tc")):
                clear_cell_borders(cell)
        if rows:
            set_header_bottom_border(rows[0])

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), len(tables)


def write_docx_with_updated_document(input_path: Path, output_path: Path) -> int:
    with ZipFile(input_path, "r") as source:
        document_xml, table_count = apply_three_line_tables(source.read("word/document.xml"))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp_path = Path(tmp.name)

        try:
            with ZipFile(tmp_path, "w", ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                    target.writestr(item, data)
            shutil.move(str(tmp_path), output_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    return table_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    table_count = write_docx_with_updated_document(args.input, args.output)
    print(f"Updated {table_count} tables")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
