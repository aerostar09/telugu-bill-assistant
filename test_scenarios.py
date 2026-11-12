"""Scenarios A/B/C: rupees from tariff.py, anomaly is a flag not a diagnosis."""
import unittest

from tariff import energy_charges, quote_bill
from scenarios import (
    get_scenario, is_usage_anomaly, SAMPLE_TRUEUP_UNITS, SAMPLE_BILL_DATE, SAMPLE_LOAD_KW, SAMPLE_DAYS,
)


class ScenarioATests(unittest.TestCase):
    def test_energy_is_computed_not_hardcoded_constant_in_isolation(self):
        sc = get_scenario("A")
        expected = energy_charges(215, "1B(ii)", days=SAMPLE_DAYS, pro_rate=False)
        self.assertEqual(expected, 200 * 5.10 + 15 * 7.70)
        self.assertEqual(expected, 1135.50)
        self.assertEqual(sc["energy_expected"], expected)
        self.assertEqual(sc["quote"]["energy_charges"], expected)
        self.assertEqual(sc["bill"]["energy_charges"], expected)

    def test_category_and_cliff_vs_200(self):
        sc = get_scenario("A")
        self.assertEqual(sc["quote"]["category"], "1B(ii)")
        self.assertEqual(sc["quote_at_200"]["category"], "1B(i)")
        q215 = quote_bill(215, load_kw=SAMPLE_LOAD_KW, days=SAMPLE_DAYS,
                          bill_date=SAMPLE_BILL_DATE, trueup_units=SAMPLE_TRUEUP_UNITS)
        q200 = quote_bill(200, load_kw=SAMPLE_LOAD_KW, days=SAMPLE_DAYS,
                          bill_date=SAMPLE_BILL_DATE, trueup_units=SAMPLE_TRUEUP_UNITS)
        self.assertEqual(sc["quote"]["total"], q215["total"])
        self.assertEqual(sc["quote_at_200"]["total"], q200["total"])
        self.assertEqual(sc["cliff_rupees"], round(q215["total"] - q200["total"], 2))
        self.assertGreater(sc["cliff_rupees"], 0)

    def test_sample_trueup_30p_on_labelled_fy22_units(self):
        sc = get_scenario("A")
        self.assertEqual(sc["sample_trueup_units"], 100)
        self.assertEqual(sc["quote"]["trueup_charges"], 30.0)  # 100 * 0.30
        self.assertIn("FY 2022-23", sc["telugu"])
        self.assertIn("నమూనా", sc["telugu"])

    def test_gruha_jyothi_loses_benefit_above_200(self):
        sc = get_scenario("A")
        self.assertIn("మొత్తం బిల్లు", sc["telugu"])
        self.assertIn("whole bill", sc["english"].lower())


class ScenarioBTests(unittest.TestCase):
    def test_energy_180_1bi(self):
        sc = get_scenario("B")
        expected = energy_charges(180, "1B(i)", days=SAMPLE_DAYS, pro_rate=False)
        self.assertEqual(expected, 100 * 3.40 + 80 * 4.80)
        self.assertEqual(expected, 724.00)
        self.assertEqual(sc["quote"]["energy_charges"], expected)
        self.assertEqual(sc["quote"]["category"], "1B(i)")

    def test_gj_zero_and_buffer(self):
        sc = get_scenario("B")
        self.assertEqual(sc["gruha_jyothi_amount"], 0.0)
        self.assertEqual(sc["buffer_units"], 20)
        self.assertIn("₹0", sc["telugu"])
        self.assertEqual(sc["daily_budget_units"], round(200 / 30, 2))


class ScenarioCTests(unittest.TestCase):
    def test_anomaly_flag_not_a_diagnosis(self):
        sc = get_scenario("C")
        flag = sc["anomaly"]
        self.assertTrue(flag["flagged"])
        self.assertEqual(flag["current_units"], 650)
        self.assertEqual(flag["recent_units"], [150])
        self.assertAlmostEqual(flag["ratio"], 650 / 150, places=2)
        self.assertGreater(flag["ratio"], 2.5)
        self.assertNotIn("మీటర్ లోపం అని నిర్ధారణ", sc["telugu"])
        self.assertIn("అని చెప్పడం లేదు", sc["telugu"])
        self.assertIn("not a claim that the meter is faulty", sc["english"].lower())
        self.assertIn("1912", sc["telugu"])
        self.assertIn("87124 41912", sc["telugu"])

    def test_helper_threshold(self):
        self.assertFalse(is_usage_anomaly(200, [100])["flagged"])  # 2.0x, not >2.5
        self.assertTrue(is_usage_anomaly(251, [100])["flagged"])
        self.assertFalse(is_usage_anomaly(100, [])["flagged"])


if __name__ == "__main__":
    unittest.main()
