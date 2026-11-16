"""Date-aware true-up (TGERC order 05.10.2026, para 12(c)-(j)).

Nov 2026 bills → Rs 0.30/unit; Dec 2026+ → Rs 0.50/unit; unknown date → either.
Quantum = units PRINTED on the true-up line (1/12 of the FY consumption),
never this month's units. One item per FY. Synthetic data only, no PII.
"""
from __future__ import annotations

import unittest

from post_ocr import apply_post_ocr_corrections
from self_checks import run_all_checks
from tariff import (
    estimate_next_with_trueup, infer_trueup_rate, normalize_trueup_items, quote_bill,
    trueup_allowed_rates, trueup_charges, trueup_item_formulas, trueup_rate_for_bill_date,
    trueup_units_for_bill,
)
from forecast import forecast_bill
from test_lt_notice import lt_notice


def dec_bill(**over):
    """Synthetic Dec 2026 1B(i) slip: 154 units, true-up 96 × 50p = 48.00."""
    q = quote_bill(154, load_kw=3.0, days=31, customer_charges=90.0,
                   trueup_units=96, bill_date="06/12/2026")
    self_total = q["total"]
    b = lt_notice(
        bill_date="06/12/2026", prev_reading_date="06/11/2026", present_reading_date="06/12/2026",
        due_date="20-12-26", disc_date="05-01-27",
        trueup_charges=48.00, trueup_units=96,
        loss_gain=round(round(self_total) - self_total, 2),
        bill_amount=float(round(self_total)), total_due=float(round(self_total)),
    )
    b.update(over)
    return b


class RateByDateTests(unittest.TestCase):
    def test_rates(self):
        self.assertEqual(trueup_allowed_rates("06/11/2026"), (0.30,))
        self.assertEqual(trueup_allowed_rates("06/12/2026"), (0.50,))
        self.assertEqual(trueup_allowed_rates("05/03/2027"), (0.50,))
        self.assertEqual(trueup_allowed_rates("06/10/2026"), ())
        self.assertEqual(trueup_allowed_rates(None), (0.30, 0.50))
        self.assertEqual(trueup_allowed_rates("garbled"), (0.30, 0.50))
        self.assertEqual(trueup_rate_for_bill_date("06/10/2026"), 0.0)

    def test_unknown_date_accepts_either_rate(self):
        self.assertEqual(infer_trueup_rate(96, 28.80, None), 0.30)
        self.assertEqual(infer_trueup_rate(96, 48.00, None), 0.50)
        self.assertIsNone(infer_trueup_rate(96, 40.00, None))
        # A dated bill only accepts its own rate
        self.assertIsNone(infer_trueup_rate(96, 48.00, "06/11/2026"))
        self.assertIsNone(infer_trueup_rate(96, 28.80, "06/12/2026"))


class SelfCheckTests(unittest.TestCase):
    def test_nov_30p_passes(self):
        c = run_all_checks(lt_notice())
        self.assertTrue(c["trueup_eq_rate"])
        self.assertNotIn("trueup_eq_rate", c["fail_keys"])

    def test_dec_50p_passes_and_30p_fails(self):
        self.assertTrue(run_all_checks(dec_bill())["trueup_eq_rate"])
        bad = dec_bill(trueup_charges=28.80)
        self.assertFalse(run_all_checks(bad)["trueup_eq_rate"])

    def test_unknown_date_either_rate_passes(self):
        self.assertTrue(run_all_checks(lt_notice(bill_date=None))["trueup_eq_rate"])
        self.assertTrue(run_all_checks(dec_bill(bill_date=None))["trueup_eq_rate"])


class PostOcrDecemberTests(unittest.TestCase):
    def test_clean_dec_bill_unchanged(self):
        raw = dec_bill()
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["trueup_charges"], 48.00)
        self.assertEqual(bill["trueup_units"], 96)
        self.assertTrue(run_all_checks(bill)["sum_eq_bill"])
        self.assertFalse(any("true-up" in n.lower() for n in notes), notes)

    def test_dec_paise_slip_snaps_to_50p(self):
        bill, _ = apply_post_ocr_corrections(dec_bill(trueup_charges=48.08))
        self.assertEqual(bill["trueup_charges"], 48.00)

    def test_dec_trueup_misfiled_in_surcharge_moves_back(self):
        bill, _ = apply_post_ocr_corrections(dec_bill(surcharge=48.00, trueup_charges=0))
        self.assertEqual(bill["trueup_charges"], 48.00)
        self.assertEqual(bill["surcharge"], 0)

    def test_unknown_date_does_not_invent_amount(self):
        # Two possible rates → never fill a missing amount.
        bill, _ = apply_post_ocr_corrections(lt_notice(bill_date=None, trueup_charges=None))
        self.assertIn(bill.get("trueup_charges"), (None, 0, 0.0))


class NoInventedQuantumTests(unittest.TestCase):
    def test_missing_line_shows_nothing(self):
        # No true-up line read: a 30p multiple elsewhere must NOT become a
        # true-up with an invented quantum.
        raw = lt_notice(trueup_charges=None, trueup_units=None, adjustment=28.80,
                        bill_amount=757.0, total_due=757.0)
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertIsNone(bill.get("trueup_units"))
        self.assertIn(bill.get("trueup_charges"), (None, 0, 0.0))
        self.assertEqual(normalize_trueup_items(bill), [])
        self.assertEqual(trueup_item_formulas(bill), [])

    def test_quantum_never_from_this_months_units(self):
        b = lt_notice(trueup_units=None, trueup_charges=None)
        self.assertIsNone(trueup_units_for_bill(b))
        est = estimate_next_with_trueup(b)
        self.assertEqual(est["est_trueup"], 0.0)
        fb = forecast_bill(b)
        self.assertEqual(fb["quotes"]["likely"]["trueup_charges"], 0.0)

    def test_quantum_independent_of_consumption(self):
        a = quote_bill(120, trueup_units=96, bill_date="06/12/2026")
        b = quote_bill(480, trueup_units=96, bill_date="06/12/2026")
        self.assertEqual(a["trueup_charges"], b["trueup_charges"])
        self.assertEqual(a["trueup_charges"], 48.00)


class MultiFyItemTests(unittest.TestCase):
    def test_single_legacy_line_is_one_fy22_item(self):
        items = normalize_trueup_items(lt_notice())
        self.assertEqual(items, [{"fy": "2022-23", "units": 96.0, "rate": 0.30,
                                  "amount": 28.80, "valid": True}])

    def test_both_fys_validated_and_summed(self):
        raw = dec_bill(trueup_items=[
            {"fy": "FY-2022-23", "units": 20, "rate_paise": 50, "amount": 10.00},
            {"fy": "FY-2023-24", "units": 76, "rate_paise": 50, "amount": 38.00},
        ], trueup_units=None, trueup_charges=None)
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["trueup_units"], 96)
        self.assertEqual(bill["trueup_charges"], 48.00)
        self.assertEqual([i["fy"] for i in bill["trueup_items"]], ["2022-23", "2023-24"])
        self.assertTrue(all(i["valid"] for i in bill["trueup_items"]))
        self.assertTrue(run_all_checks(bill)["trueup_eq_rate"])
        self.assertTrue(run_all_checks(bill)["sum_eq_bill"])
        f = trueup_item_formulas(bill)
        self.assertEqual(len(f), 2)
        self.assertIn("FY 2023-24 76", f[1])
        self.assertIn("50 పైసలు", f[1])

    def test_one_fy_item(self):
        raw = lt_notice(trueup_items=[{"fy": "2022-23", "units": 96, "rate_paise": 30, "amount": 28.80}])
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(len(bill["trueup_items"]), 1)
        self.assertEqual(bill["trueup_charges"], 28.80)

    def test_wrong_printed_rate_item_is_invalid(self):
        b = lt_notice(trueup_items=[{"fy": "2022-23", "units": 96, "rate_paise": 50, "amount": 48.00}])
        items = normalize_trueup_items(b)  # Nov bill cannot carry 50p
        self.assertFalse(items[0]["valid"])
        self.assertFalse(run_all_checks({**b, "trueup_units": 96, "trueup_charges": 48.0})["trueup_eq_rate"])

    def test_unreadable_item(self):
        b = lt_notice(trueup_items=[{"fy": "2022-23", "units": None, "amount": None},
                                    {"fy": "2023-24", "units": 40, "amount": None}])
        items = normalize_trueup_items(b)
        self.assertEqual(len(items), 1)  # fully-unreadable line dropped
        self.assertFalse(items[0]["valid"])
        self.assertIsNone(run_all_checks({**b, "trueup_units": None, "trueup_charges": None})["trueup_eq_rate"])


class ForecastShareTests(unittest.TestCase):
    def test_dec_forecast_stays_50p(self):
        fb = forecast_bill(dec_bill())
        self.assertEqual(fb["trueup_rate"], 0.50)
        self.assertEqual(fb["quotes"]["likely"]["trueup_charges"], 48.00)

    def test_dec_share_text_says_50_paise(self):
        from share_card import short_share_text
        bill = dec_bill()
        txt = short_share_text(bill, checks=run_all_checks(bill), totals_ok=True)
        self.assertIn("96 యూనిట్లు × 50 పైసలు = ₹48.00", txt)
        self.assertNotIn("× 30 పైసలు", txt)

    def test_trueup_charges_helper_dec(self):
        self.assertEqual(trueup_charges(96, bill_date="06/12/2026"), 48.00)
        self.assertEqual(trueup_charges(96, bill_date="06/11/2026"), 28.80)


class NoServiceNumberInPromptTests(unittest.TestCase):
    def test_prompt_has_no_usc_no(self):
        from self_checks import IMPROVED_VISION_PROMPT, SCHEMA_BLOCK, BILL_SCHEMA_KEYS
        from nvidia_pipeline import VISION_PROMPT
        from bill_lines import SCHEMA_KEYS
        for text in (IMPROVED_VISION_PROMPT, SCHEMA_BLOCK, VISION_PROMPT):
            self.assertNotIn("usc_no", text)
            self.assertNotIn("service_no", text.lower())
        self.assertNotIn("usc_no", BILL_SCHEMA_KEYS)
        self.assertNotIn("usc_no", SCHEMA_KEYS)


if __name__ == "__main__":
    unittest.main()
