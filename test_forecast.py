"""Forecast + backtest unit tests. Ground-truth / demo dicts only — no API calls."""
from __future__ import annotations

import unittest

from demo_data import BLEND_FIXTURE, DEMO_HISTORY, LAKSHMI_CURR, lakshmi_demo_bundle
from forecast import (
    forecast_units,
    forecast_bill,
    backtest,
    history_from_bill,
    normalize_history,
    SEASONAL_WEIGHT,
    TREND_WEIGHT,
)


class TestNormalize(unittest.TestCase):
    def test_list_and_month_names(self):
        rows = normalize_history([
            {"year": 2026, "month": "Nov", "units": 154},
            {"label": "Oct 2026", "units": 138, "estimated": True},
        ])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["month"], 10)
        self.assertTrue(rows[0]["estimated"])
        self.assertEqual(rows[1]["units"], 154)

    def test_does_not_invent(self):
        self.assertEqual(normalize_history(None), [])
        self.assertEqual(normalize_history([]), [])
        self.assertEqual(normalize_history([{"month": 5}]), [])


class TestBlendFormula(unittest.TestCase):
    def test_hand_calculated_dec_2026(self):
        # smly=70; YoY window Oct-Nov 93.5/85=1.1 → seasonal=77
        # trend: 99 + (99-88)=110
        # likely=0.55*77+0.45*110=91.85 → 91.8
        # half=max(8, 0.12*91.85, 16.5)=16.5 → low 75.3 high 108.3
        fc = forecast_units(BLEND_FIXTURE, 2026, 12)
        self.assertEqual(fc["method"], "blend_seasonal_trend")
        self.assertEqual(fc["seasonal"], 77.0)
        self.assertEqual(fc["trend"], 110.0)
        self.assertAlmostEqual(SEASONAL_WEIGHT * 77 + TREND_WEIGHT * 110, 91.85, places=2)
        self.assertEqual(fc["likely"], 91.8)
        self.assertEqual(fc["low"], 75.3)
        self.assertEqual(fc["high"], 108.3)
        self.assertLessEqual(fc["low"], fc["likely"])
        self.assertLessEqual(fc["likely"], fc["high"])

    def test_short_history_fallback(self):
        fc = forecast_units([{"year": 2026, "month": 11, "units": 154}], 2026, 12)
        self.assertIsNotNone(fc)
        self.assertEqual(fc["method"], "last_month")
        self.assertEqual(fc["likely"], 154.0)
        self.assertEqual(fc["low"], 123.2)  # 154-max(8, 0.20*154)=154-30.8
        self.assertEqual(fc["high"], 184.8)

    def test_empty_history(self):
        self.assertIsNone(forecast_units([]))


class TestLakshmiDemoForecast(unittest.TestCase):
    def test_dec_2026_uses_50p_trueup(self):
        bill = lakshmi_demo_bundle()["bill"]
        fb = forecast_bill(bill)
        self.assertEqual(fb["target_year"], 2026)
        self.assertEqual(fb["target_month"], 12)
        self.assertEqual(fb["trueup_rate"], 0.50)
        self.assertEqual(fb["quotes"]["likely"]["trueup_charges"], 48.00)  # 96×0.50
        self.assertEqual(fb["quotes"]["low"]["trueup_charges"], 48.00)
        self.assertEqual(fb["quotes"]["high"]["trueup_charges"], 48.00)
        # category from units; all three stay in 1B(i) on this series
        self.assertEqual(fb["quotes"]["likely"]["category"], "1B(i)")
        self.assertEqual(fb["likely"], 129.2)
        self.assertEqual(fb["quotes"]["likely"]["total"], 655.91)
        self.assertTrue(fb["history_is_demo"])

    def test_backtest_demo_history(self):
        bt = backtest(DEMO_HISTORY, LAKSHMI_CURR)
        self.assertEqual(bt["n"], 12)
        self.assertEqual(bt["mae_units"], 25.03)
        # Rupee MAE uses official customer-charge bands (0–50 = ₹40).
        self.assertEqual(bt["mae_rupees"], 174.81)
        self.assertEqual(bt["pct_within_range"], 33.3)
        # Only Nov 2026 has same-month-last-year available on this 13-month series
        blend = bt["by_method"]["blend_seasonal_trend"]
        self.assertEqual(blend["n"], 1)
        self.assertEqual(blend["mae_units"], 15.4)
        self.assertEqual(blend["pct_within_range"], 100.0)
        # components sum / range invariant
        for row in bt["rows"]:
            self.assertLessEqual(row["low"], row["likely"])
            self.assertLessEqual(row["likely"], row["high"])


if __name__ == "__main__":
    unittest.main()
