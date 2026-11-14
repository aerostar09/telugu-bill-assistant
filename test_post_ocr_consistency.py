"""Post-OCR consistency repairs: units/readings, days/due dates, DPS snap,
true-up fill, category labels, arrears vs Total Due. No PII, no API calls.
"""
from __future__ import annotations

import unittest

from late_reading import apply_due_date_safety, resolve_billing_days
from post_ocr import apply_post_ocr_corrections, line_sum
from bill_lines import effective_arrears, nonzero_rows, payable_amount
from self_checks import run_all_checks
from tariff import energy_charges, infer_category, quote_bill, trueup_charges


def _domestic(**overrides):
    """Generic fictional domestic bill; amounts come from tariff.py."""
    units = int(overrides.pop("units", 95))
    days = int(overrides.get("days", 30))
    load = float(overrides.get("contracted_load_kw", 3.0))
    tu_u = overrides.get("trueup_units", 110)
    bill_date = overrides.get("bill_date", "07/11/2026")
    q = quote_bill(
        units, load_kw=load, days=days, trueup_units=tu_u, bill_date=bill_date
    )
    prev = int(overrides.pop("prev_reading", 10000))
    present = int(overrides.pop("present_reading", prev + units))
    energy = q["energy_charges"]
    fixed = q["fixed_charges"]
    cust = q["customer_charges"]
    ed = q["electricity_duty"]
    tu = q["trueup_charges"]
    surcharge = float(overrides.get("surcharge", 0.0))
    gross = round(energy + fixed + cust + ed + tu + surcharge, 2)
    bill_amount = float(overrides.get("bill_amount", round(gross)))
    loss = round(bill_amount - gross, 2)
    acd = float(overrides.get("acd_due", 0.0))
    arrears = float(overrides.get("arrears", 0.0))
    total = float(overrides.get("total_due", round(bill_amount + arrears + acd, 2)))
    b = {
        "discom": "TGSPDCL",
        "usc_no": None,
        "category": q["category"],
        "contracted_load_kw": load,
        "bill_date": bill_date,
        "prev_reading": prev,
        "present_reading": present,
        "units": units,
        "days": days,
        "energy_charges": energy,
        "fixed_charges": fixed,
        "customer_charges": cust,
        "electricity_duty": ed,
        "interest_on_ed": 0.0,
        "surcharge": surcharge,
        "trueup_charges": tu,
        "trueup_units": tu_u,
        "fsa_fca": 0.0,
        "subsidy": 0.0,
        "adjustment": 0.0,
        "loss_gain": loss,
        "bill_amount": bill_amount,
        "total_due": total,
        "arrears": arrears,
        "acd_due": acd,
        "due_date": "21-11-2026",
        "is_electricity_bill": True,
    }
    b.update(overrides)
    return b


class UnitsAndReadingsTests(unittest.TestCase):
    def test_single_digit_present_typo_repaired_from_energy(self):
        """Present reading off by one mid digit; units copied the bad delta.

        Energy still matches the true consumption, not the bad delta.
        """
        true_units = 95
        prev = 11993
        true_present = prev + true_units  # 12088
        bad_present = 12008  # 8 → 0 typo
        raw = _domestic(
            units=true_units,
            prev_reading=prev,
            present_reading=true_present,
            trueup_units=110,
            surcharge=10.0,
        )
        self.assertEqual(raw["energy_charges"], energy_charges(true_units, "1A"))
        raw["present_reading"] = bad_present
        raw["units"] = bad_present - prev  # 15, consistent with the typo
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], true_units)
        self.assertEqual(int(bill["present_reading"]), true_present)
        self.assertEqual(int(bill["prev_reading"]), prev)
        self.assertTrue(any("energy" in n.lower() or "digit" in n.lower() or "reading" in n.lower() for n in notes))

    def test_energy_consistent_units_win_over_plausible_but_wrong_delta(self):
        raw = _domestic(
            units=180,
            prev_reading=15260,
            present_reading=15440,  # delta 180 — already good; sanity
            trueup_units=88,
        )
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], 180)

    def test_keeps_energy_consistent_units_when_readings_disagree(self):
        # Units and energy agree at 180; a bad reading delta of 80 must not win.
        raw = _domestic(
            units=180,
            prev_reading=15260,
            present_reading=15440,
            trueup_units=88,
            days=31,
            bill_date="08/11/2026",
        )
        raw["present_reading"] = 15340  # typo, delta 80
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], 180)

    def test_does_not_flip_consistent_pair_for_small_energy_slip(self):
        """Readings and units already agree; energy is only a couple of rupees off.

        A 1-unit typo search must not rewrite 182→183 just because ₹199 is
        slightly closer to 83 units than to 82.
        """
        raw = _domestic(
            units=82,
            prev_reading=100,
            present_reading=182,
            trueup_units=0,
            surcharge=10.0,
            bill_date="04/02/2026",
        )
        raw["energy_charges"] = 199.0  # 82-unit energy is 196.70
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], 82)
        self.assertEqual(int(bill["present_reading"]), 182)
        self.assertEqual(int(bill["prev_reading"]), 100)

    def test_consistent_high_slab_pair_survives_one_unit_energy_slip(self):
        """At 1B(ii) rates one unit is ~₹9, so an ₹8 energy slip must not bump units."""
        raw = _domestic(
            units=360,
            prev_reading=44140,
            present_reading=44500,
            trueup_units=240,
            days=33,
            bill_date="11/11/2026",
        )
        true_e = energy_charges(360, "1B(ii)")
        raw["energy_charges"] = round(true_e + 8.0, 2)
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], 360)
        self.assertEqual(int(bill["present_reading"]), 44500)
        self.assertEqual(int(bill["prev_reading"]), 44140)


class ArrearsVsTotalDueTests(unittest.TestCase):
    def test_arrears_copied_from_total_due_is_replaced_by_gap(self):
        bill_amount = 386.0
        arrears = 420.0
        total = 806.0
        raw = _domestic(
            units=95, surcharge=10.0, bill_amount=bill_amount,
            total_due=total, arrears=total,  # copied from Total Due
        )
        raw["loss_gain"] = 0.30
        self.assertEqual(raw["arrears"], total)
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["arrears"], arrears, places=2)
        self.assertFalse(abs(bill["arrears"] - total) < 0.05)
        self.assertTrue(any("arrear" in n.lower() or "బకాయి" in n for n in notes))

    def test_as_on_copied_from_bill_amount_is_not_added_to_after(self):
        """Arrears-as-on sometimes repeats Bill Amount; don't add it to after."""
        raw = _domestic(
            units=95, surcharge=10.0, bill_amount=386.0,
            total_due=806.0, arrears=420.0,
            arrears_as_on=386.0, arrears_after=420.0,
        )
        raw["loss_gain"] = 0.30
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["arrears"], 420.0, places=2)

    def test_zero_bill_with_arrears_equal_to_total_is_kept(self):
        raw = _domestic(
            units=95, bill_amount=0.0, subsidy=386.0,
            total_due=500.0, arrears=500.0,
        )
        # Make the charge sum consistent with a zero current bill + arrears
        raw["loss_gain"] = 0.0
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["arrears"], 500.0, places=2)

    def test_stray_sub_rupee_as_on_is_zeroed_when_bill_equals_total(self):
        """₹0.60 in Arrears as-on when Bill = Total Due is not real arrears.

        The 0.60 is rounding-scale (often a Loss/Gain or paise field leak)
        and must be cleared on every arrears field, not just the combined one.
        """
        raw = _domestic(
            units=154,
            days=31,
            bill_date="07/11/2026",
            trueup_units=96,
            bill_amount=757.0,
            total_due=757.0,
            arrears=0.0,
        )
        raw["arrears_as_on"] = 0.60
        raw["arrears_after"] = 0.0
        raw["loss_gain"] = -0.24
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill.get("arrears") or 0.0, 0.0, places=2)
        self.assertAlmostEqual(bill.get("arrears_as_on") or 0.0, 0.0, places=2)
        self.assertAlmostEqual(bill.get("arrears_after") or 0.0, 0.0, places=2)
        self.assertEqual(effective_arrears(bill), 0.0)
        keys = [r["key"] for r in nonzero_rows(bill)]
        self.assertNotIn("arrears", keys)
        self.assertNotIn("arrears_as_on", keys)
        self.assertNotIn("arrears_after", keys)
        self.assertAlmostEqual(bill["loss_gain"], -0.24, places=2)
        self.assertAlmostEqual(payable_amount(bill), 757.0, places=2)
        self.assertTrue(any("arrear" in n.lower() or "బకాయి" in n for n in notes))

    def test_display_hides_stray_as_on_even_before_post_ocr(self):
        """Share/receipt must not show ₹0.60 as-on if Bill already equals Total Due."""
        raw = _domestic(
            units=154, days=31, bill_date="07/11/2026",
            trueup_units=96, bill_amount=757.0, total_due=757.0, arrears=0.0,
        )
        raw["arrears_as_on"] = 0.60
        raw["arrears_after"] = 0.0
        self.assertEqual(effective_arrears(raw), 0.0)
        keys = [r["key"] for r in nonzero_rows(raw)]
        self.assertNotIn("arrears_as_on", keys)
        self.assertNotIn("arrears", keys)
        self.assertAlmostEqual(payable_amount(raw), 757.0, places=2)


class DaysAndDueDateTests(unittest.TestCase):
    def test_keeps_plausible_printed_days_when_dates_disagree(self):
        r = resolve_billing_days({
            "prev_reading_date": "07/10/26",
            "present_reading_date": "07/01/27",  # 92 days if trusted
            "days": 31,
        })
        self.assertEqual(r["days"], 31)
        self.assertEqual(r["source"], "printed")
        self.assertEqual(r["computed_days"], 92)

    def test_uses_dates_when_printed_days_are_implausible(self):
        r = resolve_billing_days({
            "prev_reading_date": "07/10/26",
            "present_reading_date": "07/11/26",  # 31 days
            "days": 92,
        })
        self.assertEqual(r["days"], 31)
        self.assertEqual(r["source"], "reading_dates")

    def test_post_ocr_does_not_overwrite_plausible_days_or_drop_due(self):
        """Wrong bill_date (after the due date) must not drop a due date that
        is valid against the present reading date; printed 31 days stays."""
        raw = _domestic(
            units=180, days=31, trueup_units=88,
            bill_date="07-12-2026",  # misread, after the due date
            due_date="22-11-2026",
            prev_reading_date="07/08/26",
            present_reading_date="07/11/26",  # would compute 92 days
        )
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["days"], 31)
        self.assertEqual(bill["due_date"], "22-11-2026")
        self.assertIsNone(bill.get("due_date_rejected"))

    def test_still_rejects_arrears_cutoff_due_date(self):
        b, note = apply_due_date_safety({
            "due_date": "01-04-2026",
            "bill_date": "03/11/2026",
            "present_reading_date": "03/11/26",
        })
        self.assertIsNone(b["due_date"])
        self.assertIn("rejected", note)


class SurchargeSnapTests(unittest.TestCase):
    def test_snaps_dps_within_one_rupee_and_keeps_small_loss_gain(self):
        q = quote_bill(287, load_kw=3, days=30, trueup_units=164, bill_date="03/11/2026")
        energy, fixed, cust, ed, tu = (
            q["energy_charges"], q["fixed_charges"], q["customer_charges"],
            q["electricity_duty"], q["trueup_charges"],
        )
        surcharge = 25.00
        gross = round(energy + fixed + cust + ed + tu + surcharge, 2)
        bill_amount = round(gross)  # nearest rupee
        loss = round(bill_amount - gross, 2)
        self.assertLessEqual(abs(loss), 1.0)
        raw = {
            "discom": "TGSPDCL",
            "category": "1B(ii)",
            "contracted_load_kw": 3.0,
            "bill_date": "03/11/2026",
            "prev_reading": 29825,
            "present_reading": 30112,
            "units": 287,
            "days": 30,
            "energy_charges": energy,
            "fixed_charges": fixed,
            "customer_charges": cust,
            "electricity_duty": ed,
            "interest_on_ed": 100.22,  # hallucinated; should be zeroed
            "surcharge": 25.20,  # 20 paise OCR slip
            "trueup_charges": tu,
            "trueup_units": 164,
            "fsa_fca": 0.0,
            "subsidy": 0.0,
            "adjustment": 0.0,
            "loss_gain": loss,
            "bill_amount": bill_amount,
            "total_due": bill_amount,
            "is_electricity_bill": True,
        }
        # Without snapping, Loss/Gain would be asked to absorb the 0.20 slip
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["surcharge"], 25.00, places=2)
        self.assertAlmostEqual(bill["loss_gain"], loss, places=2)
        self.assertLessEqual(abs(bill["loss_gain"]), 1.0)
        self.assertAlmostEqual(bill["interest_on_ed"] or 0, 0.0, places=2)
        self.assertTrue(run_all_checks(bill).get("sum_eq_bill"))

    def test_does_not_snap_surcharge_far_from_typical_dps(self):
        raw = _domestic(units=95, surcharge=40.0, bill_amount=400.0, total_due=400.0)
        bill, _ = apply_post_ocr_corrections(raw)
        # 40 is more than ₹1 from 10 or 25; leave it (or zero it only if that
        # uniquely fixes a sum — this case should not silently become 25)
        self.assertNotAlmostEqual(bill.get("surcharge") or 0, 25.0, places=2)
        self.assertNotAlmostEqual(bill.get("surcharge") or 0, 10.0, places=2)


class TrueupFillTests(unittest.TestCase):
    def test_fills_missing_trueup_amount_from_units_at_nov_30p(self):
        raw = _domestic(units=360, days=33, load_kw=5.0, trueup_units=240,
                        bill_date="12/11/2026")
        expected = trueup_charges(240, bill_date="12/11/2026")
        self.assertAlmostEqual(expected, 72.0, places=2)
        raw["trueup_charges"] = 0.0
        # Break the sum the way a missing true-up would
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["trueup_charges"], expected, places=2)
        self.assertTrue(any("true-up" in n.lower() or "trueup" in n.lower() or "ట్రూ" in n for n in notes))

    def test_fills_december_trueup_at_50p(self):
        raw = _domestic(units=360, days=33, load_kw=5.0, trueup_units=240,
                        bill_date="12/12/2026")
        expected = trueup_charges(240, bill_date="12/12/2026")
        self.assertAlmostEqual(expected, 120.0, places=2)
        raw["trueup_charges"] = None
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill.get("trueup_charges") or 0.0, expected, places=2)

    def test_does_not_invent_trueup_when_sum_already_matches_at_zero(self):
        raw = _domestic(units=95, trueup_units=110, bill_date="07/11/2026")
        # Rebuild the printed total as if there really was no true-up.
        # Use a residual that is not itself a 30p multiple, so an existing
        # "find N×30p in another field" path cannot steal Loss/Gain.
        raw["trueup_charges"] = 0.0
        raw["trueup_units"] = 110
        without = line_sum({**raw, "trueup_charges": 0.0, "loss_gain": 0.0})
        raw["bill_amount"] = round(without) + 0.04  # force residual 0.04 vs rounded
        # Keep an exact-matching printed total with a non-30p residual
        residual = 0.04
        raw["loss_gain"] = residual
        raw["bill_amount"] = round(without + residual, 2)
        raw["total_due"] = raw["bill_amount"]
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertAlmostEqual(bill["trueup_charges"] or 0.0, 0.0, places=2)


class CategoryNormalizeTests(unittest.TestCase):
    def test_title_leak_falls_back_to_units_slab(self):
        raw = _domestic(units=142, days=31, trueup_units=130)
        raw["category"] = "LT-ELECTRICITY BILL-CUM NOTICE"
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["category"], "1B(i)")
        self.assertEqual(infer_category(142, bill["category"]), "1B(i)")

    def test_bare_domestic_uses_units(self):
        raw = _domestic(units=62, days=30, load_kw=2.0, trueup_units=45)
        raw["category"] = "DOMESTIC"
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["category"], "1A")

    def test_specific_label_is_normalized_not_replaced_by_units_only(self):
        raw = _domestic(units=154, days=31, trueup_units=96)
        raw["category"] = "1B(1) DOMESTIC"
        bill, _ = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["category"], "1B(i)")

    def test_clean_nov_style_bill_stays_untouched(self):
        """Regression: a consistent 154-unit bill must stay ₹757 / 154 / green."""
        raw = _domestic(
            units=154, days=31, load_kw=3.0, trueup_units=96,
            bill_date="06/11/2026",
            prev_reading=16204, present_reading=16358,
            due_date="20-11-2026",
        )
        self.assertAlmostEqual(raw["bill_amount"], 757.0, places=2)
        bill, notes = apply_post_ocr_corrections(raw)
        self.assertEqual(bill["units"], 154)
        self.assertAlmostEqual(bill["bill_amount"], 757.0, places=2)
        checks = run_all_checks(bill)
        self.assertTrue(checks.get("sum_eq_bill"))
        self.assertTrue(checks.get("consumer_ok"))


if __name__ == "__main__":
    unittest.main()
