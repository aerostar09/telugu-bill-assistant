"""Hidden demo/officials URL flags, and citizen sidebar no longer exposes internals."""
import unittest
from pathlib import Path

from app_nvidia import parse_hidden_modes, citizen_inner_tab_labels


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


class CitizenSamplePickerTests(unittest.TestCase):
    """Main citizen screen offers only the Gruha Jyothi sample (B)."""

    @classmethod
    def setUpClass(cls):
        cls.src = (Path(__file__).resolve().parent / "app_nvidia.py").read_text()

    def test_no_developer_tariff_caption(self):
        self.assertNotIn("tariff.py లెక్కిస్తుంది", self.src)
        self.assertNotIn("upload-panel", self.src)

    def test_default_picker_is_scenario_b_only(self):
        from terms import t
        self.assertIn("try_sample_gj", self.src)
        self.assertIn('t("try_sample_gj")', self.src)
        self.assertEqual(t("try_sample_gj"), "నమూనా బిల్లు చూడండి (గృహ జ్యోతి)")
        self.assertEqual(t("sample_note"), "నమూనా డేటా, నిజమైన కస్టమర్ కాదు")

    def test_a_and_c_only_inside_demo_branch(self):
        # The default path loads only B; A/C buttons exist only in the demo branch.
        self.assertIn('for col, key in zip(cols, ("A", "B", "C")):', self.src)
        helper = self.src.split("def _render_sample_picker", 1)[1].split("def render_citizen_tab", 1)[0]
        default = helper.split("if demo:", 1)[1].split("return", 1)[1]
        self.assertIn('_result_from_scenario("B"', default)
        self.assertNotIn('"A"', default)
        self.assertNotIn('"C"', default)


class CalculatedTabVisibilityTests(unittest.TestCase):
    """లెక్క is hidden from citizens; visible only on demo/officials URL flags."""

    def test_citizen_default_has_four_tabs_without_lekkha(self):
        labels = citizen_inner_tab_labels(False)
        self.assertEqual(labels, ["బిల్లు", "పోలిక", "అంచనా", "సూచనలు"])
        self.assertNotIn("లెక్క", labels)
        self.assertEqual(len(labels), 4)

    def test_demo_or_officials_include_lekkha(self):
        labels = citizen_inner_tab_labels(True)
        self.assertEqual(labels, ["బిల్లు", "పోలిక", "అంచనా", "లెక్క", "సూచనలు"])
        self.assertEqual(labels[3], "లెక్క")
        self.assertEqual(len(labels), 5)

    def test_flag_follows_hidden_modes(self):
        self.assertFalse(parse_hidden_modes({})[0] or parse_hidden_modes({})[1])
        demo, officials = parse_hidden_modes({"demo": "1"})
        self.assertTrue(demo or officials)
        demo, officials = parse_hidden_modes({"officials": "1"})
        self.assertTrue(demo or officials)
        demo, officials = parse_hidden_modes({"view": "discom"})
        self.assertTrue(demo or officials)
