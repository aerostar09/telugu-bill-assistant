"""Unit tests for tariff.py using Lakshmi Oct/Nov 2026 ground-truth dicts. No API calls."""
from __future__ import annotations

import unittest

from self_checks import check_jump_sum
from draft_features import jump_card_text, trueup_explainer, cliff_card_text
from tariff import (
    fixed_charges,
    customer_charges_for_units,
    delayed_payment_surcharge,
    DPS_LT_IA,
    DPS_LT_IB,

    energy_charges,
    quote_bill,
    trueup_charges,
    trueup_rate_for_bill_date,
    trueup_rate_for_next_bill,
    infer_category,
    jump_breakdown,
    check_jump_breakdown,
    cliff_warning,
    estimate_next_with_trueup,
)

# Ground truth (no PII)
LAKSHMI_OCT = {
    "discom": "TGSPDCL",
    "category": "1A Domestic",
    "contracted_load_kw": 3.0,
    "bill_date": "04/02/2026",  # printed date on the 82-unit / ₹314 Cat 1A bill
    "prev_reading": 14872,
    "present_reading": 14954,
    "units": 82,
    "days": None,
    "energy_charges": 199.00,
    "fixed_charges": 30.00,
    "customer_charges": 70.00,
    "electricity_duty": 4.92,
    "interest_on_ed": 0.01,
    "surcharge": 10.00,
    "trueup_charges": None,
    "trueup_units": None,
    "fsa_fca": 0.0,
    "subsidy": 0.0,
    "adjustment": 0.0,
    "loss_gain": 0.07,
    "bill_amount": 314.00,
}

LAKSHMI_NOV = {
    "discom": "TGSPDCL",
    "category": "1B(1) domestic",
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
    "interest_on_ed": 0.0,
    "surcharge": 0.0,
    "trueup_charges": 28.80,
    "trueup_units": 96,
    "fsa_fca": 0.0,
    "subsidy": 0.0,
    "adjustment": 0.0,
    "loss_gain": -0.24,
    "bill_amount": 757.00,
    "arrears": 0.0,
    "total_due": 757.00,
    "due_date": "20-11-2026",
}


class TestEnergySlabs(unittest.TestCase):
    def test_nov_energy_unprorated_matches_bill(self):
        e = energy_charges(154, "1B(1)", days=31, pro_rate=False)
        self.assertEqual(e, 599.20)
        self.assertEqual(round(100 * 3.40 + 54 * 4.80, 2), 599.20)

    def test_prorating_does_not_match_nov_bill(self):
        e = energy_charges(154, "1B(1)", days=31, pro_rate=True)
        self.assertNotEqual(e, 599.20)

    def test_cat_1a_82_units(self):
        e = energy_charges(82, "1A")
        self.assertEqual(e, round(50 * 1.95 + 32 * 3.10, 2))  # 196.70
        # Real Oct bill printed 199.00 — documented gap
        self.assertEqual(e, 196.70)
        self.assertNotEqual(e, LAKSHMI_OCT["energy_charges"])

    def test_infer_1b1_as_1bi(self):
        self.assertEqual(infer_category(154, "1B(1) domestic"), "1B(i)")
        self.assertEqual(infer_category(82, "1A Domestic"), "1A")
        self.assertEqual(infer_category(250, "1B(2)"), "1B(ii)")

    def test_ed_and_fixed_and_trueup(self):
        q = quote_bill(
            154, load_kw=3, days=31, category="1B(1)",
            customer_charges=90, trueup_units=96, bill_date="06/11/2026",
            pro_rate=False,
        )
        self.assertEqual(q["energy_charges"], 599.20)
        self.assertEqual(q["fixed_charges"], 30.00)
        self.assertEqual(q["electricity_duty"], 9.24)
        self.assertEqual(q["trueup_charges"], 28.80)
        self.assertEqual(q["trueup_rate"], 0.30)
        self.assertEqual(trueup_rate_for_next_bill("06/11/2026"), 0.50)
        self.assertEqual(trueup_charges(96, rate=0.50), 48.00)


class TestJumpBreakdown(unittest.TestCase):
    def test_oct_to_nov_known_line_items(self):
        br = jump_breakdown(LAKSHMI_OCT, LAKSHMI_NOV, pro_rate=False)
        chk = check_jump_breakdown(br)
        self.assertTrue(chk["ok"], chk)
        self.assertEqual(br["difference"], 443.00)  # 757-314
        # (a)+(b) = nov energy - oct energy = 599.20-199.00 = 400.20
        self.assertAlmostEqual(
            br["extra_units_old_rate"] + br["category_change"], 400.20, places=2
        )
        self.assertEqual(br["trueup_added"], 28.80)
        # other: customer +20, ED +4.32, intED -0.01, surcharge -10, loss -0.31 = 14.00
        self.assertAlmostEqual(br["other_changes"], 14.00, places=2)
        self.assertAlmostEqual(br["residual"], 0.0, places=2)
        self.assertEqual(br["prev_category"], "1A")
        self.assertEqual(br["curr_category"], "1B(i)")

    def test_oct_computed_from_tariff_puts_gap_in_residual(self):
        prev = {
            "units": 82,
            "category": "1A",
            "contracted_load_kw": 3.0,
            "customer_charges": 70.0,
            "bill_amount": 314.00,
        }
        br = jump_breakdown(prev, LAKSHMI_NOV, pro_rate=False)
        chk = check_jump_breakdown(br)
        self.assertTrue(chk["ok"], chk)
        self.assertEqual(br["difference"], 443.00)
        self.assertTrue(br["prev_computed_from_tariff"])
        # Tariff Oct energy 196.70 vs printed 199.00 → residual captures the gap
        # (and missing surcharge 10, intED 0.01, loss 0.07, energy +2.30, etc.)
        self.assertIsNotNone(br["residual"])
        self.assertNotEqual(round(br["residual"], 2), 0.0)

    def test_components_sum_to_difference(self):
        br = jump_breakdown(LAKSHMI_OCT, LAKSHMI_NOV)
        s = (
            br["extra_units_old_rate"]
            + br["category_change"]
            + br["trueup_added"]
            + br["other_changes"]
            + br["residual"]
        )
        self.assertAlmostEqual(s, br["difference"], places=2)


class TestCliffAndEstimate(unittest.TestCase):
    def test_nov_154_not_within_cliff_window(self):
        self.assertIsNone(cliff_warning(LAKSHMI_NOV))

    def test_cliff_just_over_100(self):
        w = cliff_warning({"units": 108, "contracted_load_kw": 3, "customer_charges": 90, "days": 30})
        self.assertIsNotNone(w)
        self.assertEqual(w["threshold"], 100)
        self.assertEqual(w["units_to_cut"], 8)
        self.assertGreater(w["save_inr"], 0)

    def test_next_estimate_uses_50p_after_nov(self):
        est = estimate_next_with_trueup(LAKSHMI_NOV)
        self.assertIsNotNone(est)
        # 154/31*30 = 149.032..., energy scaled, true-up 96*0.50=48
        self.assertEqual(est["est_trueup_rate"], 0.50)
        self.assertEqual(est["est_trueup"], 48.00)
        self.assertAlmostEqual(est["est_units_30d"], round((154 / 31) * 30, 1), places=1)



class TestSelfCheckAndCopy(unittest.TestCase):
    def test_self_checks_hook(self):
        chk = check_jump_sum(LAKSHMI_OCT, LAKSHMI_NOV)
        self.assertTrue(chk["ok"])
        self.assertEqual(chk["difference"], 443.0)
        self.assertEqual(chk["parts_plus_residual"], 443.0)

    def test_telugu_cards_render(self):
        card = jump_card_text(LAKSHMI_OCT, LAKSHMI_NOV)
        self.assertTrue(card["check"]["ok"])
        self.assertTrue(any("పెరిగింది" in p for p in card["paragraphs"]))
        self.assertIn("FY 2022-23", trueup_explainer(LAKSHMI_NOV))
        self.assertIsNone(cliff_card_text(LAKSHMI_NOV))
        self.assertIn("తగ్గిస్తే", cliff_card_text({"units": 108, "contracted_load_kw": 3, "customer_charges": 90, "days": 30}))



class TestFixedChargeAbove800(unittest.TestCase):
    def test_fixed_above_800_is_50_per_kw(self):
        # Official TGERC RST FY2026-27: LT-I(B)(ii) last row is ₹50/kW when units > 800
        self.assertEqual(fixed_charges(3.0, units=801), 150.00)
        self.assertEqual(fixed_charges(1.0, units=801), 50.00)
        q = quote_bill(801, load_kw=3.0, days=30, customer_charges=160)
        self.assertEqual(q["fixed_charges"], 150.00)
        self.assertEqual(q["category"], "1B(ii)")

    def test_fixed_at_or_below_800_stays_10_per_kw(self):
        self.assertEqual(fixed_charges(3.0, units=800), 30.00)
        self.assertEqual(fixed_charges(3.0, units=154), 30.00)
        self.assertEqual(fixed_charges(3.0, units=None), 30.00)
        self.assertEqual(quote_bill(154, load_kw=3.0, customer_charges=90)["fixed_charges"], 30.00)



class TestOfficialCustomerAndDps(unittest.TestCase):
    """TGERC RST Order FY 2026-27 Appendix A items 7–8 (pp. 294–295 / sched-6, sched-7)."""

    def test_customer_charge_table(self):
        self.assertEqual(customer_charges_for_units(0), 40)
        self.assertEqual(customer_charges_for_units(50), 40)
        self.assertEqual(customer_charges_for_units(51), 70)
        self.assertEqual(customer_charges_for_units(82), 70)   # Lakshmi Feb/Oct 1A printed ₹70
        self.assertEqual(customer_charges_for_units(100), 70)
        self.assertEqual(customer_charges_for_units(101), 90)
        self.assertEqual(customer_charges_for_units(154), 90)  # Lakshmi Nov printed ₹90
        self.assertEqual(customer_charges_for_units(200), 90)
        self.assertEqual(customer_charges_for_units(201), 100)
        self.assertEqual(customer_charges_for_units(300), 100)
        self.assertEqual(customer_charges_for_units(301), 120)
        self.assertEqual(customer_charges_for_units(400), 120)
        self.assertEqual(customer_charges_for_units(401), 140)
        self.assertEqual(customer_charges_for_units(800), 140)
        self.assertEqual(customer_charges_for_units(801), 160)

    def test_quote_uses_official_unless_bill_value_given(self):
        q = quote_bill(82, load_kw=3.0)  # no customer_charges
        self.assertEqual(q["customer_charges"], 70)
        q_bill = quote_bill(82, load_kw=3.0, customer_charges=70)
        self.assertEqual(q_bill["customer_charges"], 70)
        # extracted value still wins even if it differs from the table
        q_override = quote_bill(82, load_kw=3.0, customer_charges=55)
        self.assertEqual(q_override["customer_charges"], 55)

    def test_dps_lt_i(self):
        self.assertEqual(delayed_payment_surcharge(units=82, category="1A"), DPS_LT_IA)
        self.assertEqual(delayed_payment_surcharge(units=82), 10.0)
        self.assertEqual(delayed_payment_surcharge(units=154, category="1B(1)"), DPS_LT_IB)
        self.assertEqual(delayed_payment_surcharge(units=154), 25.0)
        # Lakshmi Oct printed surcharge ₹10 is the 1A DPS
        self.assertEqual(LAKSHMI_OCT["surcharge"], delayed_payment_surcharge(units=82, category="1A Domestic"))

    def test_forecast_quote_excludes_dps(self):
        q = quote_bill(154, load_kw=3.0, customer_charges=90, trueup_units=96, bill_date="01/12/2026")
        self.assertNotIn("surcharge", q)
        # total is energy+fixed+ed+customer+trueup only
        self.assertEqual(
            q["total"],
            round(q["energy_charges"] + q["fixed_charges"] + q["electricity_duty"]
                  + q["customer_charges"] + q["trueup_charges"], 2),
        )


if __name__ == "__main__":
    unittest.main()
