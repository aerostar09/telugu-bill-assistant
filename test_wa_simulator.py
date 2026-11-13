"""Share / WhatsApp tab helpers: PII-free summary, rounded forecast, no fake chat."""
from __future__ import annotations

import unittest

from demo_data import lakshmi_demo_bundle
from dashboard import build_dashboard_model
from forecast import consumer_forecast_range, format_rupee_range
from self_checks import run_all_checks
from share_card import compact_extracted_summary, short_share_text


CONCEPT_LINE = "కాన్సెప్ట్: TGSPDCL WhatsApp 87124 41912 లోకి ప్లగ్ చేయవచ్చు."


class ShareTabHelperTests(unittest.TestCase):
    def test_concept_note_mentions_official_whatsapp(self):
        self.assertIn("87124 41912", CONCEPT_LINE)
        self.assertIn("TGSPDCL WhatsApp", CONCEPT_LINE)

    def test_extracted_summary_has_no_identity_or_meter_readings(self):
        bill = dict(lakshmi_demo_bundle()["bill"])
        bill["usc_no"] = "SYN-SHOULD-NOT-APPEAR"
        bill["prev_reading"] = 11000
        bill["present_reading"] = 11154
        rows = compact_extracted_summary(bill)
        blob = " ".join(f"{a} {b}" for a, b in rows)
        self.assertIn("154", blob)
        self.assertIn("757", blob)
        for forbidden in ("SYN-SHOULD-NOT-APPEAR", "11000", "11154", "usc", "USC", "Jayaram", "Mamidi"):
            self.assertNotIn(forbidden, blob)
        keys = [a for a, _ in rows]
        self.assertNotIn("ప్రెజెంట్ రీడింగ్", keys)

    def test_share_text_uses_hero_forecast_band(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(
            bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"])
        )
        rng = consumer_forecast_range(forecast=model.get("forecast"))
        self.assertIsNotNone(rng)
        band = format_rupee_range(rng["low"], rng["high"])
        text = short_share_text(bundle["bill"], forecast_range=rng, totals_ok=True)
        self.assertIn(band, text)
        # No leftover paise from the precise quote.
        self.assertNotIn("655.91", text)
        self.assertNotIn(".", text.split("అంచనా", 1)[-1].split("\n")[0] if "అంచనా" in text else "")


if __name__ == "__main__":
    unittest.main()
