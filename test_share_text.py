"""WhatsApp / Web Share text format — classic bill list plus short extras."""
from __future__ import annotations

import unittest

from demo_data import lakshmi_demo_bundle
from draft_features import TRUEUP_OFFICIAL_URL, TRUEUP_LINK_LABEL_TE, TRUEUP_ONE_LINER_TE
from forecast import consumer_forecast_range, format_rupee_range
from self_checks import run_all_checks
from share_card import share_button_plan, short_share_text
from dashboard import WA_MAX_CHARS, build_dashboard_model, whatsapp_summary
from test_lt_notice import lt_notice
from bill_lines import nonzero_rows, payable_amount
from post_ocr import apply_post_ocr_corrections


class ShareTextFormatTests(unittest.TestCase):
    def _text(self, **kwargs):
        bill = lt_notice()
        checks = run_all_checks(bill)
        model = build_dashboard_model(bill, None, checks)
        rng = consumer_forecast_range(forecast=model.get("forecast"))
        return short_share_text(
            bill,
            forecast_range=rng,
            forecast=model.get("forecast"),
            totals_ok=True,
            late=model.get("late"),
            checks=checks,
            **kwargs,
        )

    def test_classic_bullets_then_short_extras(self):
        text = self._text()
        self.assertTrue(text.startswith("⚡ TGSPDCL కరెంట్ బిల్లు వివరాలు"), text[:80])
        self.assertNotIn("\ufffd", text)
        self.assertNotIn("�", text)
        lines = text.splitlines()
        self.assertEqual(lines[1], "(Bill Summary)")
        self.assertIn("• వినియోగించిన యూనిట్లు (Units): 154 kWh", text)
        self.assertIn("• విద్యుత్ ఛార్జీ (Energy): ₹599.20", text)
        self.assertIn("• ఫిక్స్‌డ్ + కస్టమర్ ఛార్జీ: ₹120.00", text)
        self.assertIn("• ఎలక్ట్రిసిటీ డ్యూటీ (ED): ₹9.24", text)
        self.assertIn("• ట్రూ-అప్ ఛార్జీ (True-Up): ₹28.80", text)
        self.assertIn("⚡ మొత్తం చెల్లించాల్సిన బిల్లు (Total Due): ₹757.00", text)
        self.assertIn("✅ లెక్క సరిగా ఉంది", text)
        self.assertIn("FY 2022-23 96 యూనిట్లు × 30 పైసలు = ₹28.80", text)
        self.assertIn("ఈ నెల వాడకం కాదు", text)
        self.assertIn("వచ్చే నెల 50 పైసలు/యూనిట్", text)
        self.assertIn("31 రోజుల స్లాబ్", text)
        self.assertIn("₹4.67", text)
        self.assertIn("గడువు 20-11-26", text)
        self.assertIn("Disc Date 05-12-26", text)
        self.assertIn("వచ్చే నెల అంచనా ₹600–₹900", text)
        self.assertIn("🔗 https://telugu-electricitybill-assistant.streamlit.app/", text)
        # Official TGERC true-up order (not a news link)
        self.assertIn(TRUEUP_LINK_LABEL_TE, text)
        self.assertIn(TRUEUP_OFFICIAL_URL, text)
        self.assertTrue(TRUEUP_OFFICIAL_URL.startswith("https://tgerc.telangana.gov.in/"))
        self.assertIn("ఈ నెల వాడకం కాదు", TRUEUP_ONE_LINER_TE)
        # Charge list comes before the extras
        self.assertLess(text.find("(Bill Summary)"), text.find("✅ లెక్క సరిగా ఉంది"))
        self.assertLess(text.find("Total Due"), text.find("✅ లెక్క సరిగా ఉంది"))
        self.assertLess(text.find("✅ లెక్క సరిగా ఉంది"), text.find(TRUEUP_OFFICIAL_URL))
        self.assertLessEqual(len(text), WA_MAX_CHARS)
        # Rejected paragraph form must not return
        self.assertNotIn("మీ విద్యుత్ బిల్లు సారాంశం", text)

    def test_whatsapp_summary_is_the_same_text(self):
        bill = lt_notice()
        checks = run_all_checks(bill)
        model = build_dashboard_model(bill, None, checks)
        share = short_share_text(
            bill,
            forecast=model.get("forecast"),
            totals_ok=None,
            late=model.get("late"),
            checks=checks,
        )
        wa = whatsapp_summary(
            bill,
            checks=checks,
            late=model.get("late"),
            forecast=model.get("forecast"),
        )
        self.assertEqual(share, wa)
        self.assertEqual(model["wa_text"], wa)
        self.assertIn("₹600–₹900", share)
        self.assertIn("₹600–₹900", wa)

    def test_surcharge_line_appears_when_nonzero(self):
        bill = lt_notice()
        bill = dict(bill)
        bill["surcharge"] = 50.0
        text = short_share_text(bill, totals_ok=True, include_link=False)
        self.assertIn("ఆలస్య రుసుము (DPS): ₹50.00", text)
        # still after energy/true-up, before Total Due
        self.assertLess(text.find("True-Up"), text.find("DPS"))
        self.assertLess(text.find("DPS"), text.find("Total Due"))

    def test_mismatch_uses_1912_line(self):
        bill = lt_notice()
        text = short_share_text(bill, totals_ok=False, include_link=False)
        self.assertIn("లెక్కల్లో తేడా ఉంది — CSC/1912 కి చూపించండి", text)
        self.assertNotIn("✅ లెక్క సరిగా ఉంది", text)


class ShareButtonPlanTests(unittest.TestCase):
    def test_plans(self):
        self.assertEqual(
            share_button_plan(False, False, wa_clicked=True, read_clicked=False),
            "need_photo",
        )
        self.assertEqual(
            share_button_plan(True, False, wa_clicked=False, read_clicked=True),
            "read_only",
        )
        self.assertEqual(
            share_button_plan(True, False, wa_clicked=True, read_clicked=False),
            "read_then_share",
        )
        self.assertEqual(
            share_button_plan(True, True, wa_clicked=True, read_clicked=False),
            "share_only",
        )
        self.assertEqual(
            share_button_plan(False, True, wa_clicked=True, read_clicked=False),
            "share_only",
        )
        self.assertEqual(
            share_button_plan(True, True, wa_clicked=False, read_clicked=False),
            "idle",
        )


class DemoShareBandTests(unittest.TestCase):
    def test_demo_bundle_uses_rounded_band(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(
            bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"])
        )
        rng = consumer_forecast_range(forecast=model.get("forecast"))
        band = format_rupee_range(rng["low"], rng["high"])
        text = short_share_text(
            bundle["bill"], forecast_range=rng, totals_ok=True, late=model.get("late")
        )
        self.assertIn(band, text)
        self.assertNotIn("655.91", text)


class StrayArrearsShareTests(unittest.TestCase):
    def test_nov_style_bill_share_has_no_arrears_line_for_stray_60_paise(self):
        """Jay's Nov bill shape: Bill = Total Due = ₹757, as-on leaked ₹0.60."""
        raw = lt_notice(arrears_as_on=0.60, arrears_after=0.0, arrears=0.0)
        bill, _ = apply_post_ocr_corrections(raw)
        text = short_share_text(bill, totals_ok=True, include_link=False)
        self.assertNotIn("బకాయిలు", text)
        self.assertNotIn("0.60", text)
        self.assertIn("⚡ మొత్తం చెల్లించాల్సిన బిల్లు (Total Due): ₹757.00", text)
        self.assertAlmostEqual(payable_amount(bill), 757.0, places=2)
        keys = [r["key"] for r in nonzero_rows(bill)]
        self.assertNotIn("arrears_as_on", keys)
        self.assertNotIn("arrears", keys)
        # Loss/Gain stays the printed rounding, not the stray 0.60
        self.assertAlmostEqual(bill["loss_gain"], -0.24, places=2)

    def test_share_still_lists_consistent_arrears(self):
        bill = lt_notice(arrears=200, arrears_as_on=200, arrears_after=0, total_due=957.00)
        text = short_share_text(bill, totals_ok=True, include_link=False)
        self.assertIn("బకాయిలు", text)
        self.assertIn("₹200.00", text)
        self.assertIn("Total Due): ₹957.00", text)


if __name__ == "__main__":
    unittest.main()
