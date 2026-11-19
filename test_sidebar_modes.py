"""Hidden demo/officials URL flags, and citizen sidebar no longer exposes internals."""
import unittest
from pathlib import Path

from app_nvidia import parse_hidden_modes


class ParseHiddenModesTests(unittest.TestCase):
    def test_default_off(self):
        self.assertEqual(parse_hidden_modes({}), (False, False))
        self.assertEqual(parse_hidden_modes({"demo": "", "officials": "", "view": ""}), (False, False))
        self.assertEqual(parse_hidden_modes({"demo": "0", "officials": "no"}), (False, False))

    def test_demo_query(self):
        for val in ("1", "true", "YES", "True"):
            self.assertEqual(parse_hidden_modes({"demo": val}), (True, False), val)

    def test_officials_query(self):
        self.assertEqual(parse_hidden_modes({"officials": "1"}), (False, True))
        self.assertEqual(parse_hidden_modes({"officials": "yes"}), (False, True))

    def test_view_discom_alias(self):
        self.assertEqual(parse_hidden_modes({"view": "discom"}), (False, True))
        self.assertEqual(parse_hidden_modes({"view": "DISCOM"}), (False, True))
        self.assertEqual(parse_hidden_modes({"view": "citizen"}), (False, False))

    def test_demo_and_officials_together(self):
        self.assertEqual(parse_hidden_modes({"demo": "1", "officials": "1"}), (True, True))
        self.assertEqual(parse_hidden_modes({"demo": "1", "view": "discom"}), (True, True))

    def test_list_values(self):
        self.assertEqual(parse_hidden_modes({"demo": ["1"]}), (True, False))
        self.assertEqual(parse_hidden_modes({"officials": ["true"]}), (False, True))


class CitizenSidebarSourceTests(unittest.TestCase):
    """The settings widgets must not come back as visible citizen UI."""

    @classmethod
    def setUpClass(cls):
        cls.src = (Path(__file__).resolve().parent / "app_nvidia.py").read_text()

    def test_no_citizen_settings_widgets(self):
        self.assertNotIn("Use Sarvam for Telugu", self.src)
        self.assertNotIn("AI key: configured", self.src)
        self.assertNotIn('key="demo_mode"', self.src)
        self.assertNotIn('key="use_sarvam"', self.src)
        self.assertNotIn('key="discom_officials_view"', self.src)
        self.assertNotIn("For DISCOM officials (pitch demo)", self.src.split("def parse_hidden_modes")[0])

    def test_concept_label_stays_on_main_page(self):
        self.assertIn("Demo / Concept – not an official TGSPDCL service", self.src)

    def test_use_sarvam_stays_off(self):
        self.assertIn("use_sarvam = False", self.src)
