"""Post-OCR sum reconciliation: duplicate true-up/surcharge, rounding — no PII."""
import unittest

from post_ocr import apply_post_ocr_corrections, line_sum, reconcile_line_sum
from self_checks import run_all_checks


def nov_bill(**overrides):
    """Anonymised line items matching a printed 154-unit 1B(i) bill (no identity fields)."""
    b = {
        "discom": "TGSPDCL",
        "usc_no": None,
        "category": "1B(i)",
        "contracted_load_kw": 3.0,
        "bill_date": "06/11/2026",
        "prev_reading": 16204,
        "present_reading": 16358,
        "units": 154,
        "days": 31,
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
        "loss_gain": -0.24,
        "bill_amount": 757.00,
        "total_due": 757.00,
        "due_date": "20-11-26",
    }
    b.update(overrides)
    return b


def oct_bill_82u(**overrides):
    """Anonymised 82-unit 1A bill with a real ₹10 DPS."""
    b = {
        "discom": "TGSPDCL",
        "usc_no": None,
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
        "interest_on_ed": 0.00,
        "surcharge": 10.00,
        "trueup_charges": 0,
        "trueup_units": None,
        "fsa_fca": 0,
        "subsidy": 0,
        "adjustment": 0,
        "loss_gain": 0.08,
        "bill_amount": 314.00,
        "total_due": 314.00,
        "due_date": "18-02-2026",
    }
    b.update(overrides)
    return b


class DuplicateTrueupAsSurchargeTests(unittest.TestCase):
    def test_surcharge_copied_from_trueup_is_zeroed(self):
        raw = nov_bill(surcharge=28.80)
        self.assertEqual(line_sum(raw), 785.80)
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["surcharge"], 0)
        self.assertEqual(bill["trueup_charges"], 28.80)
        self.assertEqual(bill["trueup_units"], 96)
        self.assertEqual(bill["loss_gain"], -0.24)
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertTrue(any("surcharge" in n and "duplicate" in n.lower() for n in notes))
        checks = run_all_checks(bill)
        self.assertTrue(checks["ok"], checks)
        self.assertTrue(checks["sum_eq_bill"])
        self.assertIsNone(checks["message_te"])
        self.assertNotIn("1912", checks.get("message_te") or "")

    def test_1912_warning_only_for_unexplained_mismatch(self):
        # Energy off by a lot, no single-zero or duplicate fix — keep 1912.
        raw = nov_bill(energy_charges=699.20)
        bill, notes = apply_post_ocr_corrections(raw)
        checks = run_all_checks(bill)
        self.assertFalse(checks["ok"])
        self.assertFalse(checks["sum_eq_bill"])
        self.assertIn("1912", checks["message_te"] or "")
        # Did not wipe the real true-up or the printed 0 surcharge in a bad way
        self.assertEqual(bill["trueup_charges"], 28.80)

    def test_real_dps_on_82_unit_bill_is_kept(self):
        raw = oct_bill_82u()
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["surcharge"], 10)
        self.assertAlmostEqual(line_sum(bill), 314.00, places=2)
        checks = run_all_checks(bill)
        self.assertTrue(checks["ok"], checks)
        self.assertIsNone(checks["message_te"])


class LossGainRoundingTests(unittest.TestCase):
    def test_missing_loss_gain_is_snapped_to_residual(self):
        raw = nov_bill(loss_gain=None)
        # 757.24 vs 757 without the -0.24 rounding line
        self.assertAlmostEqual(line_sum(raw), 757.24, places=2)
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["loss_gain"], -0.24, places=2)
        self.assertAlmostEqual(line_sum(bill), 757.00, places=2)
        self.assertTrue(any("Loss/Gain" in n or "loss" in n.lower() for n in notes))
        self.assertTrue(run_all_checks(bill)["ok"])

    def test_correct_loss_gain_is_left_alone(self):
        raw = nov_bill()
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["loss_gain"], -0.24, places=2)
        self.assertTrue(run_all_checks(bill)["ok"])
        self.assertFalse(any("Loss/Gain set" in n for n in notes))


class LineSumHelpersTests(unittest.TestCase):
    def test_negative_loss_gain_is_not_dropped(self):
        self.assertAlmostEqual(line_sum(nov_bill()), 757.00, places=2)
        self.assertAlmostEqual(line_sum(nov_bill(surcharge=28.80)), 785.80, places=2)


if __name__ == "__main__":
    unittest.main()
