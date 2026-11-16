"""Gruha Jyothi checkbox logic (TGERC O.P.No.6 of 2024 / G.O.Ms.No.7). Synthetic data only."""
from __future__ import annotations

import unittest

from gruha_jyothi import (
    GJ_CHECKBOX_LABEL_TE, GJ_CHECKBOX_HINT_EN, gruha_jyothi_view, gruha_jyothi_forecast_warning,
)
from test_lt_notice import lt_notice


def small_bill(**over):
    """154-unit Nov slip, Bill ₹757, no printed subsidy."""
    return lt_notice(**over)


class CheckboxCopyTests(unittest.TestCase):
    def test_label_and_hint(self):
        self.assertIn("గృహ జ్యోతి", GJ_CHECKBOX_LABEL_TE)
        self.assertIn("200", GJ_CHECKBOX_LABEL_TE)
        self.assertIn("unticked", GJ_CHECKBOX_HINT_EN)
        self.assertIn("not sure", GJ_CHECKBOX_HINT_EN)


class ViewTests(unittest.TestCase):
    def test_unticked_no_subsidy_shows_nothing(self):
        self.assertIsNone(gruha_jyothi_view(small_bill(), False))

    def test_ticked_under_200_is_zero_bill(self):
        v = gruha_jyothi_view(small_bill(), True)
        self.assertEqual(v["mode"], "free")
        self.assertEqual(v["payable"], 0.0)
        self.assertEqual(v["normal_amount"], 757.0)
        self.assertIn("₹0", v["note_te"])
        # True-up wording is cautious: DISCOM statement, not the GO
        self.assertIn("DISCOM", v["trueup_note_te"])
        self.assertIn("GO లో లేదు", v["trueup_note_te"])

    def test_exactly_200_still_free(self):
        v = gruha_jyothi_view(small_bill(units=200), True)
        self.assertEqual(v["mode"], "free")

    def test_ticked_over_200_whole_bill(self):
        b = small_bill(units=201, bill_amount=1100.0, total_due=1100.0)
        v = gruha_jyothi_view(b, True)
        self.assertEqual(v["mode"], "over")
        self.assertEqual(v["payable"], 1100.0)
        self.assertIn("మొత్తం బిల్లు", v["note_te"])

    def test_arrears_and_acd_remain_payable(self):
        b = small_bill(arrears=120.0, acd_due=80.0, total_due=957.0)
        v = gruha_jyothi_view(b, True)
        self.assertEqual(v["mode"], "free")
        self.assertEqual(v["payable"], 200.0)
        self.assertIn("బకాయిలు/ACD ₹200", v["note_te"])

    def test_printed_subsidy_wins_over_checkbox(self):
        b = small_bill(subsidy=757.0, bill_amount=0.0, total_due=0.0)
        v = gruha_jyothi_view(b, True)
        self.assertEqual(v["mode"], "printed")
        self.assertEqual(v["payable"], 0.0)
        # Printed subsidy + units > 200 still trusts the bill, not the checkbox rule
        b2 = small_bill(units=210, subsidy=500.0, bill_amount=600.0, total_due=600.0)
        self.assertEqual(gruha_jyothi_view(b2, True)["mode"], "printed")
        self.assertEqual(gruha_jyothi_view(b2, True)["payable"], 600.0)

    def test_zero_subsidy_line_is_not_a_printed_subsidy(self):
        v = gruha_jyothi_view(small_bill(subsidy=0.0), True)
        self.assertEqual(v["mode"], "free")

    def test_unknown_units(self):
        v = gruha_jyothi_view(small_bill(units=None), True)
        self.assertEqual(v["mode"], "unknown")


class ForecastWarningTests(unittest.TestCase):
    def test_warns_196_to_200(self):
        for u in (196, 198.4, 200):
            self.assertIsNotNone(gruha_jyothi_forecast_warning(small_bill(), {"likely": u}, True))

    def test_no_warning_below_196_or_unticked(self):
        self.assertIsNone(gruha_jyothi_forecast_warning(small_bill(), {"likely": 195}, True))
        self.assertIsNone(gruha_jyothi_forecast_warning(small_bill(), {"likely": 198}, False))

    def test_warns_when_crossing_200(self):
        w = gruha_jyothi_forecast_warning(small_bill(units=190), {"likely": 212}, True)
        self.assertIn("200 దాటే", w)


if __name__ == "__main__":
    unittest.main()
