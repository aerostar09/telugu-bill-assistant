"""Official TGSPDCL LT-ELECTRICITY BILL-CUM NOTICE mapping — synthetic IDs only."""
from __future__ import annotations

import unittest

from bill_lines import (
    AFTER_BILL_ROWS,
    CHARGE_ROWS,
    HEADER_KEYS,
    SCHEMA_KEYS,
    nonzero_rows,
    payable_amount,
)
from citizen_summary import confidence_level, top_reasons
from post_ocr import apply_post_ocr_corrections, line_sum
from receipt_ui import next_units_cliff
from self_checks import (
    BILL_SCHEMA_KEYS,
    IMPROVED_VISION_PROMPT,
    SCHEMA_BLOCK,
    run_all_checks,
)
from share_card import short_share_text
from thermal_repair import looks_like_trueup


# Synthetic identifiers only. Readings are a clean 154-unit delta and do not
# copy a real consumer meter. Amounts match the official Nov 2026 1B(i) slip.
LT_NOTICE_NOV = {
    "discom": "TGSPDCL",
    "usc_no": "SYN-0000-1547",
    "category": "1B(i)",
    "contracted_load_kw": 3.0,
    "phase": "1",
    "bill_date": "06/11/2026",
    "prev_reading": 11000,
    "present_reading": 11154,
    "prev_reading_date": "06/10/2026",
    "present_reading_date": "06/11/2026",
    "units": 154,
    "days": 31,
    "recorded_md": 0,
    "energy_charges": 599.20,
    "fixed_charges": 30.00,
    "customer_charges": 90.00,
    "electricity_duty": 9.24,
    "interest_on_ed": 0.00,
    "surcharge": 0.00,
    "trueup_charges": 28.80,
    "trueup_units": 96,
    "fsa_fca": 0.00,
    "subsidy": 0.00,
    "adjustment": 0.00,
    "interest_on_cd": 0.00,
    "loss_gain": -0.24,
    "bill_amount": 757.00,
    "arrears_as_on": 0.00,
    "arrears_after": 0.00,
    "arrears": 0.00,
    "acd_due": 0.00,
    "total_due": 757.00,
    "due_date": "20-11-26",
    "disc_date": "05-12-26",
    "last_paid_date": "08/10/2026",
    "is_electricity_bill": True,
    "image_quality": "clear",
}


def lt_notice(**overrides):
    b = dict(LT_NOTICE_NOV)
    b.update(overrides)
    return b


# WhatsApp-compressed thermal extract: column shift + typoed readings + 8p slip.
# Ground-truth amounts are recovered by post-OCR; typoed readings are left as-is.
LT_NOTICE_NOV_COMPRESSED_EXTRACT = lt_notice(
    prev_reading=11090,
    present_reading=11324,  # delta 234, typoed mid-digits
    units=234,
    days=154,  # units landed in Days
    energy_charges=599.28,
    fixed_charges=90.00,
    customer_charges=9.24,
    electricity_duty=0.00,
    trueup_charges=28.88,
    interest_on_cd=0.00,
    arrears=None,
    arrears_as_on=None,
    arrears_after=None,
)


OFFICIAL_CHARGE_ORDER = [
    "energy_charges",
    "fixed_charges",
    "customer_charges",
    "electricity_duty",
    "interest_on_ed",
    "surcharge",
    "trueup_charges",
    "fsa_fca",
    "subsidy",
    "adjustment",
    "interest_on_cd",
    "loss_gain",
]


class OfficialLineOrderTests(unittest.TestCase):
    def test_charge_rows_follow_thermal_order(self):
        self.assertEqual([k for k, _, _ in CHARGE_ROWS], OFFICIAL_CHARGE_ORDER)
        after = [k for k, _, _ in AFTER_BILL_ROWS]
        self.assertEqual(after[:3], ["arrears_as_on", "arrears_after", "arrears"])
        self.assertIn("acd_due", after)

    def test_schema_and_prompt_cover_every_official_field(self):
        self.assertEqual(BILL_SCHEMA_KEYS, SCHEMA_KEYS)
        prompt = IMPROVED_VISION_PROMPT + "\n" + SCHEMA_BLOCK
        for label in (
            "Energy Charges",
            "Fixed Charges",
            "Customer Charges",
            "Electricity Duty",
            "Interest on ED",
            "Surcharge",
            "PP TRUEUP",
            "FSA/FCA",
            "Subsidy",
            "Adjustment",
            "Interest on CD",
            "Loss/Gain",
            "Bill Amount",
            "Arrears as on",
            "Arrears after",
            "ACD Due",
            "Total Due",
            "Due Date",
            "Disc Date",
            "Last Paid",
            "Contracted Load",
            "Recorded MD",
        ):
            self.assertIn(label, prompt, msg=f"missing {label}")
        for key in (
            "recorded_md", "interest_on_cd", "arrears_as_on", "arrears_after",
            "acd_due", "total_due", "disc_date", "last_paid_date",
            "contracted_load_kw", "prev_reading", "present_reading",
        ):
            self.assertIn(f'"{key}"', SCHEMA_BLOCK)

    def test_header_keys_include_cat_load_readings_units_days_md(self):
        for key in (
            "category", "contracted_load_kw", "prev_reading", "present_reading",
            "units", "days", "recorded_md", "due_date", "disc_date", "last_paid_date",
        ):
            self.assertIn(key, HEADER_KEYS)


class GroundTruthFixtureTests(unittest.TestCase):
    def test_printed_total_is_757_and_checks_pass(self):
        bill, notes = apply_post_ocr_corrections(lt_notice())
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertEqual(bill["units"], 154)
        self.assertEqual(bill["days"], 31)
        self.assertEqual(bill["energy_charges"], 599.20)
        self.assertEqual(bill["fixed_charges"], 30.00)
        self.assertEqual(bill["customer_charges"], 90.00)
        self.assertEqual(bill["electricity_duty"], 9.24)
        self.assertEqual(bill["trueup_charges"], 28.80)
        self.assertEqual(bill["loss_gain"], -0.24)
        self.assertEqual(bill["bill_amount"], 757.00)
        self.assertEqual(bill["total_due"], 757.00)
        self.assertEqual(bill["due_date"], "20-11-26")
        self.assertEqual(bill["disc_date"], "05-12-26")
        self.assertEqual(bill["recorded_md"], 0)
        checks = run_all_checks(bill)
        self.assertTrue(checks["sum_eq_bill"], checks)
        self.assertTrue(checks["consumer_ok"], checks)
        self.assertTrue(checks["ok"], checks)
        self.assertIsNone(checks["message_te"])
        self.assertNotIn("1912", checks.get("message_te") or "")

    def test_receipt_shows_nonzero_lines_only_in_official_order(self):
        rows = nonzero_rows(lt_notice())
        keys = [r["key"] for r in rows]
        self.assertEqual(
            keys,
            [
                "energy_charges",
                "fixed_charges",
                "customer_charges",
                "electricity_duty",
                "trueup_charges",
                "loss_gain",
            ],
        )
        amounts = {r["key"]: r["amount"] for r in rows}
        self.assertEqual(amounts["energy_charges"], 599.20)
        self.assertEqual(amounts["trueup_charges"], 28.80)
        self.assertEqual(amounts["loss_gain"], -0.24)
        self.assertNotIn("surcharge", keys)
        self.assertNotIn("arrears", keys)
        self.assertNotIn("interest_on_ed", keys)
        self.assertNotIn("interest_on_cd", keys)
        self.assertNotIn("fsa_fca", keys)

    def test_units_bar_is_computed_from_tariff_thresholds(self):
        cliff = next_units_cliff(154)
        self.assertIsNotNone(cliff)
        self.assertEqual(cliff["threshold"], 200)
        self.assertEqual(cliff["headroom"], 46)
        self.assertEqual(cliff["tone"], "yellow")
        self.assertEqual(cliff["message_te"], "46 యూనిట్లు దాటితే రేటు పెరుగుతుంది")
        self.assertIn("46", next_units_cliff(154)["message_te"])
        # 199 units still has 1 unit of headroom to 200; 50 sits at the next cliff (100)
        self.assertEqual(next_units_cliff(199)["headroom"], 1)
        self.assertEqual(next_units_cliff(50)["threshold"], 100)


class PayableAmountTests(unittest.TestCase):
    def test_bill_amount_when_no_arrears(self):
        self.assertEqual(payable_amount(lt_notice()), 757.00)

    def test_total_due_when_arrears_positive(self):
        bill = lt_notice(arrears=200, arrears_as_on=200, arrears_after=0, total_due=957.00)
        self.assertEqual(payable_amount(bill), 957.00)
        # Combined arrears row is skipped when as-on / after are present
        keys = [r["key"] for r in nonzero_rows(bill)]
        self.assertIn("arrears_as_on", keys)
        self.assertNotIn("arrears", keys)

    def test_total_due_when_only_combined_arrears_set(self):
        bill = lt_notice(arrears=150, arrears_as_on=None, arrears_after=None, total_due=907)
        self.assertEqual(payable_amount(bill), 907)


class TrueupNotDpsTests(unittest.TestCase):
    def test_surcharge_only_2880_moves_to_trueup(self):
        raw = lt_notice(surcharge=28.80, trueup_charges=0)
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["surcharge"], 0)
        self.assertEqual(bill["trueup_charges"], 28.80)
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertTrue(any("PP TRUEUP" in n or "true-up" in n.lower() for n in notes))
        checks = run_all_checks(bill)
        self.assertTrue(checks["consumer_ok"], checks)
        self.assertIsNone(checks["message_te"])

    def test_duplicate_2880_surcharge_is_zeroed(self):
        raw = lt_notice(surcharge=28.80, trueup_charges=28.80)
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["surcharge"], 0)
        self.assertEqual(bill["trueup_charges"], 28.80)
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertTrue(run_all_checks(bill)["consumer_ok"])

    def test_top_reasons_labels_trueup_not_dps(self):
        bill, _ = apply_post_ocr_corrections(lt_notice(surcharge=28.80, trueup_charges=28.80))
        reasons = top_reasons(jump=None, late=None, bill=bill)
        titles = [r["title_te"] for r in reasons]
        self.assertTrue(any("ట్రూ-అప్" in t for t in titles), reasons)
        self.assertFalse(any("ఆలస్య రుసుము" == t or t.startswith("ఆలస్య రుసుము") for t in titles), reasons)
        self.assertFalse(any(r["key"] == "surcharge" for r in reasons))

    def test_unsanitized_surcharge_2880_is_not_called_dps(self):
        # Defense in depth if a stale extract still holds 28.80 in surcharge.
        raw = lt_notice(surcharge=28.80, trueup_charges=0)
        self.assertTrue(looks_like_trueup(28.80))
        reasons = top_reasons(jump=None, late=None, bill=raw)
        self.assertFalse(any(r["key"] == "surcharge" for r in reasons), reasons)

    def test_genuine_ten_rupee_dps_is_kept_and_labelled(self):
        raw = {
            "discom": "TGSPDCL",
            "usc_no": "SYN-0000-0082",
            "category": "1A",
            "contracted_load_kw": 3.0,
            "bill_date": "04/02/2026",
            "prev_reading": 100,
            "present_reading": 182,
            "units": 82,
            "days": 30,
            "energy_charges": 199.00,
            "fixed_charges": 30.00,
            "customer_charges": 70.00,
            "electricity_duty": 4.92,
            "surcharge": 10.00,
            "trueup_charges": 0,
            "trueup_units": None,
            "loss_gain": 0.08,
            "bill_amount": 314.00,
            "total_due": 314.00,
        }
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["surcharge"], 10)
        reasons = top_reasons(jump=None, late=None, bill=bill)
        self.assertTrue(any(r["key"] == "surcharge" for r in reasons), reasons)


class CompressedThermalExtractTests(unittest.TestCase):
    def test_label_shift_and_days_as_units_reconcile_to_757(self):
        bill, notes = apply_post_ocr_corrections(dict(LT_NOTICE_NOV_COMPRESSED_EXTRACT))
        self.assertEqual(bill["units"], 154)
        self.assertEqual(bill["days"], 31)
        self.assertEqual(bill["fixed_charges"], 30.00)
        self.assertEqual(bill["customer_charges"], 90.00)
        self.assertEqual(bill["electricity_duty"], 9.24)
        self.assertEqual(bill["trueup_charges"], 28.80)
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertTrue(any("line shift" in n.lower() or "జారి" in n for n in notes), notes)
        checks = run_all_checks(bill)
        self.assertTrue(checks["sum_eq_bill"], checks)
        self.assertTrue(checks["consumer_ok"], checks)
        self.assertIsNone(checks["message_te"])
        self.assertNotIn("1912", checks.get("message_te") or "")
        # Typoed mid-digit readings may still fail a diagnostic check.
        # The consumer banner must not go red when the printed total matches.
        conf = confidence_level(checks, notes)
        self.assertEqual(conf["level"], "green")
        self.assertTrue(conf["show_on_hero"])
        self.assertEqual(conf["label_te"], "స్పష్టంగా చదివాం")
        self.assertNotEqual(conf["label_te"], "కొన్ని అంకెలు సరిచేశాం")
        self.assertNotIn("1912", conf["label_te"])


class ShareTextPrivacyTests(unittest.TestCase):
    def test_share_text_has_no_identity_or_meter_readings(self):
        text = short_share_text(lt_notice(), totals_ok=True, include_link=True)
        self.assertIn("₹757", text)
        self.assertIn("154", text)
        self.assertIn("20-11-26", text)
        self.assertIn("ట్రూ-అప్", text)
        self.assertNotIn("ఆలస్య రుసుము", text)
        for forbidden in (
            "SYN-0000-1547",
            "11000",
            "11154",
            "usc",
            "USC",
            "meter",
            "16204",
            "16358",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("కరెంట్ బిల్లు వివరాలు", text)
        self.assertIn("(Bill Summary)", text)



class HeroPillAndReasonCopyTests(unittest.TestCase):
    def test_hero_pill_is_green_even_when_repairs_ran(self):
        conf = confidence_level(
            {"consumer_ok": True, "ok": False, "sum_eq_bill": True},
            corrections=["auto-correct chesam: thermal line shift"],
            image_quality="blurry",
        )
        self.assertEqual(conf["level"], "green")
        self.assertTrue(conf["show_on_hero"])
        self.assertEqual(conf["label_te"], "స్పష్టంగా చదివాం")
        self.assertNotIn("కొన్ని అంకెలు", conf["label_te"])

    def test_hero_pill_is_red_only_for_a_genuine_mismatch(self):
        conf = confidence_level({"consumer_ok": False, "sum_eq_bill": False})
        self.assertEqual(conf["level"], "red")
        self.assertTrue(conf["show_on_hero"])
        self.assertIn("తేడా", conf["label_te"])

    def test_unchecked_bill_hides_the_hero_pill(self):
        conf = confidence_level({})
        self.assertFalse(conf["show_on_hero"])
        self.assertEqual(conf["level"], "hidden")

    def test_trueup_reason_has_distinct_explanation(self):
        from citizen_summary import trueup_explain_te
        bill = lt_notice()
        detail = trueup_explain_te(bill)
        self.assertEqual(detail, "2022-23 బాకీ, 96 యూనిట్లు × 30 పైసలు")
        reasons = top_reasons(jump=None, late=None, bill=bill)
        tu = next(r for r in reasons if r["key"] == "trueup_charges")
        self.assertEqual(tu["title_te"], "ట్రూ-అప్ (పాత సంవత్సరం సర్దుబాటు)")
        self.assertEqual(tu["voice_te"], detail)
        self.assertNotEqual(tu["voice_te"], tu["title_te"])
        self.assertNotIn(tu["title_te"], tu["voice_te"])


if __name__ == "__main__":
    unittest.main()
