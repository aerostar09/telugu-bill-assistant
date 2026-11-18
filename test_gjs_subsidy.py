"""Gruha Jyothi '0' Bill: printed GJS Subsidy / Net Bill Amount lines.

Synthetic numbers modelled on the printed layout (Bill Amount 602 /
GJS Subsidy -602 / Net Bill Amount 0). No consumer identity fields.
"""
from __future__ import annotations

import unittest

from bill_lines import (
    SCHEMA_KEYS, current_net_amount, gjs_subsidy_amount, nonzero_rows, payable_amount,
)
from citizen_summary import build_voice_summary
from gruha_jyothi import (
    gj_forecast_note_te, gruha_jyothi_forecast_warning, gruha_jyothi_view,
)
from post_ocr import apply_post_ocr_corrections
from receipt_ui import receipt_pay_label
from self_checks import BILL_SCHEMA_KEYS, IMPROVED_VISION_PROMPT, SCHEMA_BLOCK, run_all_checks
from share_card import short_share_text
from test_lt_notice import lt_notice


def gj_raw(**over):
    """Model-style output for a 132-unit Gruha Jyothi zero bill (GJS printed negative)."""
    b = {
        "discom": "TGSPDCL", "category": "1B(i)", "contracted_load_kw": 1.0,
        "bill_date": "03/09/2026", "prev_reading": 1000, "present_reading": 1132,
        "units": 132, "days": 30,
        "energy_charges": 493.60, "fixed_charges": 10.0, "customer_charges": 90.0,
        "electricity_duty": 7.92, "interest_on_ed": 0.0, "surcharge": 0.0,
        "trueup_charges": None, "trueup_units": None, "trueup_items": None,
        "fsa_fca": 0.0, "subsidy": 0.0, "adjustment": 0.0, "interest_on_cd": 0.0,
        "loss_gain": 0.48, "bill_amount": 602.0,
        "gjs_subsidy": -602.0, "net_bill_amount": 0.0, "gj_zero_bill_header": True,
        "arrears_as_on": 0.0, "arrears_after": 0.0, "arrears": 0.0,
        "acd_due": 0.0, "total_due": 0.0, "due_date": "17/09/2026",
        "is_electricity_bill": True, "image_quality": "clear",
    }
    b.update(over)
    return b


def gj_bill(**over):
    bill, _notes = apply_post_ocr_corrections(gj_raw(**over))
    return bill


class SchemaPromptTests(unittest.TestCase):
    def test_schema_has_gjs_fields(self):
        for k in ("gjs_subsidy", "net_bill_amount", "gj_zero_bill_header"):
            self.assertIn(k, SCHEMA_KEYS)
            self.assertIn(f'"{k}"', SCHEMA_BLOCK)
        self.assertEqual(BILL_SCHEMA_KEYS, SCHEMA_KEYS)

    def test_prompt_separates_gjs_from_plain_subsidy(self):
        self.assertIn("GJS Subsidy", IMPROVED_VISION_PROMPT)
        self.assertIn("Net Bill Amount", IMPROVED_VISION_PROMPT)
        self.assertIn("Gruha Jyothi '0' Bill", IMPROVED_VISION_PROMPT)
        self.assertIn("DIFFERENT", IMPROVED_VISION_PROMPT)


class NormaliseTests(unittest.TestCase):
    def test_gjs_stored_positive_and_header_bool(self):
        b = gj_bill()
        self.assertEqual(b["gjs_subsidy"], 602.0)
        self.assertIs(b["gj_zero_bill_header"], True)
        self.assertEqual(b["bill_amount"], 602.0)  # gross kept, not replaced by net
        self.assertEqual(gjs_subsidy_amount(b), 602.0)
        self.assertEqual(current_net_amount(b), 0.0)

    def test_gjs_copied_into_plain_subsidy_is_moved(self):
        b, notes = apply_post_ocr_corrections(gj_raw(gjs_subsidy=None, subsidy=602.0))
        self.assertEqual(b["gjs_subsidy"], 602.0)
        self.assertEqual(b["subsidy"], 0.0)
        self.assertTrue(any("GJS" in n for n in notes))

    def test_header_with_zero_net_but_unread_gjs_line(self):
        b = gj_bill(gjs_subsidy=None)
        self.assertEqual(gjs_subsidy_amount(b), 602.0)
        self.assertEqual(payable_amount(b), 0.0)


class ChecksTests(unittest.TestCase):
    def test_line_sum_still_compares_to_gross_bill_amount(self):
        c = run_all_checks(gj_bill())
        self.assertTrue(c["sum_eq_bill"])
        self.assertAlmostEqual(c["sum_calc"], 602.0, places=2)
        self.assertTrue(c["gjs_net_ok"])
        self.assertTrue(c["consumer_ok"])

    def test_net_mismatch_detected(self):
        c = run_all_checks(gj_bill(net_bill_amount=50.0))
        self.assertIs(c["gjs_net_ok"], False)
        self.assertIn("gjs_net_ok", c["fail_keys"])
        self.assertFalse(c["consumer_ok"])
        self.assertIsNotNone(c["message_te"])

    def test_non_gjs_bill_has_no_gjs_check(self):
        c = run_all_checks(lt_notice())
        self.assertIsNone(c["gjs_net_ok"])


class PayableTests(unittest.TestCase):
    def test_printed_gjs_is_zero_without_checkbox(self):
        b = gj_bill()
        self.assertEqual(payable_amount(b), 0.0)
        v = gruha_jyothi_view(b, False)
        self.assertEqual(v["mode"], "gjs_printed")
        self.assertEqual(v["payable"], 0.0)
        self.assertEqual(v["normal_amount"], 602.0)
        self.assertIn("స్కీమ్ లేకపోతే చెల్లింపు ₹602", v["note_te"])
        self.assertIn("₹0", v["note_te"])

    def test_printed_gjs_wins_over_ticked_checkbox(self):
        self.assertEqual(gruha_jyothi_view(gj_bill(), True)["mode"], "gjs_printed")

    def test_receipt_rows_and_label(self):
        b = gj_bill()
        keys = [r["key"] for r in nonzero_rows(b)]
        self.assertIn("gjs_subsidy", keys)
        self.assertEqual(receipt_pay_label(b, "gjs_printed"), "మొత్తం చెల్లింపు")

    def test_gjs_bill_with_arrears_keeps_arrears_payable(self):
        b = gj_bill(arrears=150.0, total_due=150.0)
        self.assertEqual(payable_amount(b), 150.0)
        v = gruha_jyothi_view(b, False)
        self.assertEqual(v["payable"], 150.0)
        self.assertIn("బకాయిలు/ACD ₹150", v["note_te"])

    def test_gjs_bill_with_arrears_split_and_acd(self):
        b = gj_bill(arrears_as_on=100.0, arrears=None, acd_due=40.0, total_due=140.0)
        self.assertEqual(payable_amount(b), 140.0)

    def test_total_due_misread_as_gross_is_not_payable(self):
        b = gj_bill(total_due=602.0)
        self.assertEqual(payable_amount(b), 0.0)

    def test_bill_without_gjs_unchanged(self):
        b = lt_notice()
        self.assertIsNone(gjs_subsidy_amount(b))
        self.assertEqual(payable_amount(b), 757.0)
        self.assertIsNone(gruha_jyothi_view(b, False))
        self.assertEqual(gruha_jyothi_view(b, True)["mode"], "free")
        self.assertNotIn("gjs_subsidy", [r["key"] for r in nonzero_rows(b)])
        b2, _ = apply_post_ocr_corrections(dict(lt_notice()))
        self.assertIsNone(b2["gjs_subsidy"])
        self.assertEqual(payable_amount(b2), 757.0)


class SurfacesTests(unittest.TestCase):
    def test_share_text_does_not_ask_for_gross(self):
        text = short_share_text(gj_bill(), include_link=False)
        self.assertIn("(Total Due): ₹0", text)
        self.assertIn("గృహ జ్యోతి సబ్సిడీ (GJS): −₹602", text)
        self.assertIn("స్కీమ్ లేకపోతే చెల్లింపు", text)
        self.assertNotIn("(Total Due): ₹602", text)

    def test_voice_says_zero(self):
        b = gj_bill()
        text = build_voice_summary(b, gj=gruha_jyothi_view(b, False))
        self.assertIn("చెల్లించాల్సింది 0 రూపాయలు", text)
        self.assertIn("స్కీమ్ లేకపోతే 602 రూపాయలు", text)
        self.assertNotIn("ఈ నెల బిల్లు 602", text)

    def test_voice_non_gjs_unchanged(self):
        self.assertIn("ఈ నెల బిల్లు 757 రూపాయలు", build_voice_summary(lt_notice()))

    def test_forecast_warning_196_200_without_checkbox(self):
        b = gj_bill()
        self.assertIsNotNone(gruha_jyothi_forecast_warning(b, {"likely": 198}, False))
        self.assertIsNone(gruha_jyothi_forecast_warning(b, {"likely": 150}, False))
        # non-GJS, unticked: unchanged (no warning)
        self.assertIsNone(gruha_jyothi_forecast_warning(lt_notice(), {"likely": 198}, False))

    def test_forecast_note_marks_range_as_without_scheme(self):
        b = gj_bill()
        note = gj_forecast_note_te(gruha_jyothi_view(b, False), {"likely": 140})
        self.assertIn("₹0", note)
        self.assertIsNone(gj_forecast_note_te(gruha_jyothi_view(b, False), {"likely": 230}))
        self.assertIsNone(gj_forecast_note_te(None, {"likely": 140}))


if __name__ == "__main__":
    unittest.main()
