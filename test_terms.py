"""Terminology dict + rounded-rupee helpers. No API, no PII."""
import unittest

from terms import TERMS, t, rupees_spoken, rupees_display, word_count, TARIFF_VERSION


class TermsTests(unittest.TestCase):
    def test_required_nav_keys(self):
        for key in (
            "nav_understand", "nav_compare", "nav_estimate",
            "nav_calculated", "nav_suggestions", "this_month_bill",
            "voice", "simulation", "calc_matches", "upload_button",
        ):
            self.assertIn(key, TERMS)
            self.assertTrue(t(key).strip())

    def test_tariff_version(self):
        self.assertEqual(TARIFF_VERSION, "FY 2026-27 TGERC")
        self.assertEqual(t("tariff_version"), TARIFF_VERSION)

    def test_rupees_are_rounded(self):
        self.assertEqual(rupees_spoken(757.00), "757 రూపాయలు")
        self.assertEqual(rupees_spoken(756.80), "757 రూపాయలు")
        self.assertEqual(rupees_display(757.24), "₹757")
        self.assertEqual(rupees_display(None), "—")

    def test_word_count(self):
        self.assertEqual(word_count("ఈ నెల బిల్లు 757 రూపాయలు."), 5)
