"""Late-reading detector + days-from-dates + due-date safety tests. No API calls."""
from __future__ import annotations

import unittest

from demo_data import LAKSHMI_CURR, LAKSHMI_PREV
from late_reading import (
    days_from_reading_dates,
    resolve_billing_days,
    due_date_is_safe,
    apply_due_date_safety,
    late_reading_effect,
)
from post_ocr import apply_post_ocr_corrections
from tariff import energy_charges


class TestDaysFromDates(unittest.TestCase):
    def test_hwrq_33(self):
        self.assertEqual(days_from_reading_dates("01/10/26", "03/11/26"), 33)

    def test_lakshmi_feb_30(self):
        self.assertEqual(days_from_reading_dates("05/01/26", "04/02/26"), 30)

    def test_hwim_30(self):
        self.assertEqual(days_from_reading_dates("04/10/26", "03/11/26"), 30)

    def test_jay6_off_by_one_keeps_printed(self):
        r = resolve_billing_days({
            "prev_reading_date": "09/Sep/23",
            "present_reading_date": "09/Oct/23",
            "days": 29,
        })
        self.assertEqual(r["computed_days"], 30)
        self.assertEqual(r["days"], 29)
        self.assertEqual(r["source"], "printed")
        self.assertIn("off-by-one", r["note"])

    def test_fill_days_when_printed_missing(self):
        r = resolve_billing_days({
            "prev_reading_date": "05/01/26",
            "present_reading_date": "04/02/26",
        })
        self.assertEqual(r["days"], 30)
        self.assertEqual(r["source"], "reading_dates")

    def test_disagree_keeps_plausible_printed_days(self):
        # Printed 30 is a normal cycle (25–35); do not overwrite from dates.
        r = resolve_billing_days({
            "prev_reading_date": "01/10/26",
            "present_reading_date": "03/11/26",
            "days": 30,
        })
        self.assertEqual(r["days"], 30)
        self.assertEqual(r["source"], "printed")
        self.assertEqual(r["computed_days"], 33)

    def test_disagree_uses_dates_when_printed_implausible(self):
        r = resolve_billing_days({
            "prev_reading_date": "01/10/26",
            "present_reading_date": "03/11/26",
            "days": 92,
        })
        self.assertEqual(r["days"], 33)
        self.assertEqual(r["source"], "reading_dates")


class TestDueDateSafety(unittest.TestCase):
    def test_accepts_normal_due(self):
        ok, reason, d = due_date_is_safe("18-02-2026", "04/02/2026")
        self.assertTrue(ok)
        self.assertEqual(str(d), "2026-02-18")
        ok, _, _ = due_date_is_safe("17/11/2026", "03/11/2026")
        self.assertTrue(ok)

    def test_rejects_arrears_cutoff_lookalike(self):
        ok, reason, _ = due_date_is_safe("01-04-2026", "03/11/2026")
        self.assertFalse(ok)
        self.assertIn("before", reason)
        b, note = apply_due_date_safety({
            "due_date": "01-04-2026",
            "bill_date": "03/11/2026",
        })
        self.assertIsNone(b["due_date"])
        self.assertEqual(b["due_date_rejected"], "01-04-2026")
        self.assertIn("rejected", note)


class TestLateReadingExtra(unittest.TestCase):
    def test_lakshmi_31d_is_4_67(self):
        eff = late_reading_effect(LAKSHMI_CURR)
        self.assertEqual(eff["actual_energy"], 599.20)
        self.assertEqual(eff["fair_energy_prorated"], 594.53)
        self.assertEqual(eff["extra_rupees"], 4.67)
        self.assertTrue(eff["is_late"])
        self.assertEqual(
            energy_charges(154, "1B(i)", days=31, pro_rate=True),
            594.53,
        )
        # scaled-units view is a different (larger) gap — not the headline
        self.assertNotEqual(eff["units_scaled_energy"], eff["fair_energy_prorated"])
        self.assertEqual(eff["units_30d"], 149.03)

    def test_hwrq_33d(self):
        eff = late_reading_effect({
            "units": 127,
            "days": 33,
            "energy_charges": 461.20,
            "category": "1B(i)",
            "prev_reading_date": "01/10/26",
            "present_reading_date": "03/11/26",
        })
        self.assertEqual(eff["days"], 33)
        self.assertEqual(eff["days_source"], "printed")
        self.assertEqual(eff["computed_days"], 33)
        self.assertEqual(eff["extra_rupees"], 5.60)

    def test_exact_30_days_zero_extra(self):
        bill = dict(LAKSHMI_PREV)  # 82u / 30d
        # use tariff energy for a clean zero (printed Oct energy is 199 vs 196.70)
        bill["energy_charges"] = energy_charges(82, "1A", days=30, pro_rate=False)
        eff = late_reading_effect(bill)
        self.assertEqual(eff["extra_rupees"], 0.0)
        self.assertFalse(eff["is_late"])


class TestPostOcrHook(unittest.TestCase):
    def test_fills_days_and_rejects_due(self):
        raw = {
            "units": 127,
            "prev_reading": 14440,
            "present_reading": 14567,
            "prev_reading_date": "01/10/26",
            "present_reading_date": "03/11/26",
            "bill_date": "03/11/2026",
            "due_date": "01-04-2026",
            "energy_charges": 461.20,
            "is_electricity_bill": True,
        }
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["days"], 33)
        self.assertEqual(bill["days_source"], "reading_dates")
        self.assertIsNone(bill["due_date"])
        self.assertTrue(any("days" in n.lower() or "due-date" in n.lower() or "due date" in n.lower() or "reading" in n.lower() for n in notes))


if __name__ == "__main__":
    unittest.main()
