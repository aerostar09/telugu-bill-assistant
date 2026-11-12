from __future__ import annotations
import unittest
from urllib.parse import urlparse, parse_qs, unquote

from demo_data import lakshmi_demo_bundle
from dashboard import build_dashboard_model, whatsapp_summary, whatsapp_link, WA_MAX_CHARS, energy_formula
from self_checks import run_all_checks


class TestDashboardCopy(unittest.TestCase):
    def test_whatsapp_under_limit_and_roundtrip(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"]))
        text = model["wa_text"]
        self.assertLessEqual(len(text), WA_MAX_CHARS)
        self.assertIn("757", text)
        self.assertIn("154", text)
        link = whatsapp_link(text)
        self.assertTrue(link.startswith("https://wa.me/?text="))
        decoded = unquote(link.split("text=", 1)[1])
        self.assertEqual(decoded, text)

    def test_energy_formula_nov(self):
        s = energy_formula(154, "1B(1)")
        self.assertIn("100 × ₹3.40", s)
        self.assertIn("54 × ₹4.80", s)
        self.assertIn("₹599.20", s)

    def test_demo_checks_and_late(self):
        bundle = lakshmi_demo_bundle()
        checks = run_all_checks(bundle["bill"])
        self.assertTrue(checks["ok"], checks)
        model = build_dashboard_model(bundle["bill"], bundle["prev_bill"], checks)
        self.assertEqual(model["late"]["extra_rupees"], 4.67)
        self.assertTrue(model["jump_check"]["ok"])
        self.assertEqual(model["jump"]["difference"], 443.0)
        self.assertTrue(model["acd_text"])  # ACD Due 0 present
        self.assertIn("50", model["trueup_text"])


if __name__ == "__main__":
    unittest.main()
