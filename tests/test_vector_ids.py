"""Editable vector references must continue to identify the same geometry."""

import unittest
from xml.etree import ElementTree as ET
from capsaicin.vector_ids import normalize


class VectorReferenceTests(unittest.TestCase):
    def test_links_geometry_and_preexisting_names(self):
        text = '<svg><defs><path id="resource_1" d="M1 2"/><path id="mabcdef1234" d="M3 4"/><clipPath id="p0123456789"><use href="#mabcdef1234"/></clipPath></defs><use href="#mabcdef1234" clip-path="url(#p0123456789)"/></svg>'
        root = ET.fromstring(normalize(text))
        paths = {node.attrib["id"]: node.attrib["d"] for node in root.iter("path")}
        self.assertEqual(paths["resource_1"], "M1 2")
        use = root.find("use")
        self.assertEqual(paths[use.attrib["href"][1:]], "M3 4")
        clip = use.attrib["clip-path"][5:-1]
        self.assertIsNotNone(root.find(f".//clipPath[@id='{clip}']"))
        self.assertEqual(normalize(normalize(text)), normalize(text))
