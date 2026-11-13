"""Deterministic what-if slider math. No API, no PII."""
import unittest

from demo_data import lakshmi_demo_bundle
from whatif import whatif_for_units, same_units_delta_note
from terms import TARIFF_VERSION


class WhatIfTests(unittest.TestCase):
    def test_labelled_simulation_and_difference(self):
        bill = lakshmi_demo_bundle()["bill"]
        # 154 units current bill is 757; same units is still a simulation
        # at the *next* true-up rate (50p), so total is not 757.
        w = whatif_for_units(bill, 154)
        self.assertEqual(w["label"], "simulation / estimate")
        self.assertEqual(w["tariff_version"], TARIFF_VERSION)
        self.assertIn("సిమ్యులేషన్", w["label_te"])
        self.assertEqual(w["current_bill"], 757.0)
        self.assertIsNotNone(w["difference"])
        # Next-bill true-up is 96 * 0.50 = 48 vs current 28.80, so ~+19
        self.assertAlmostEqual(w["quote"]["trueup_charges"], 48.00, places=2)
        self.assertAlmostEqual(w["total"], w["current_bill"] + w["difference"], places=2)

    def test_fewer_units_is_cheaper(self):
        bill = lakshmi_demo_bundle()["bill"]
        high = whatif_for_units(bill, 180)
        mid = whatif_for_units(bill, 120)
        self.assertGreater(high["total"], mid["total"])
        self.assertEqual(high["quote"]["trueup_charges"], mid["quote"]["trueup_charges"])


class SameUnitsDeltaNoteTests(unittest.TestCase):
    def test_next_trueup_note_when_units_match(self):
        bill = lakshmi_demo_bundle()["bill"]
        w = whatif_for_units(bill, 154)
        note = same_units_delta_note(bill, w)
        self.assertIsNotNone(note)
        self.assertIn("వచ్చే నెల ట్రూ-అప్ 50 పైసలు", note)
        self.assertIn("ఎక్కువ", note)

    def test_no_note_when_units_differ(self):
        bill = lakshmi_demo_bundle()["bill"]
        w = whatif_for_units(bill, 100)
        self.assertIsNone(same_units_delta_note(bill, w))


if __name__ == "__main__":
    unittest.main()
