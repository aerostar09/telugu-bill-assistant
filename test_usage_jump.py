"""Unusual usage-jump alert + simple match-banner wording. Synthetic data only."""
import unittest

from usage_jump import usage_jump_alert
from terms import t
from test_lt_notice import lt_notice


def hist(*units, year=2026, start_month=8):
    return [{"year": year, "month": start_month + i, "units": u, "estimated": False}
            for i, u in enumerate(units)]


class UsageJumpTests(unittest.TestCase):
    def test_no_history_no_alert(self):
        self.assertIsNone(usage_jump_alert(lt_notice(units=400)))

    def test_jump_from_history_alerts(self):
        a = usage_jump_alert(lt_notice(units=300), hist(150, 160, 140))  # Aug–Oct, bill Nov
        self.assertIsNotNone(a)
        self.assertEqual(a["past_average"], 150.0)
        self.assertIn("1912", a["text_te"])
        self.assertIn("87124 41912", a["text_te"])
        self.assertIn("మీటర్", a["text_te"])
        self.assertIn("Present", a["text_te"])

    def test_normal_usage_no_alert(self):
        self.assertIsNone(usage_jump_alert(lt_notice(units=154), hist(150, 160, 140)))

    def test_under_50_percent_no_alert(self):
        self.assertIsNone(usage_jump_alert(lt_notice(units=220), hist(150, 150, 150)))  # +47%

    def test_small_absolute_jump_no_alert(self):
        # +100% but only +40 units
        self.assertIsNone(usage_jump_alert(lt_notice(units=80), hist(40, 40, 40)))

    def test_uses_only_recent_three_past_months(self):
        h = hist(400, 400, 400, 400, start_month=3) + hist(100, 100, 100, start_month=8)
        self.assertIsNotNone(usage_jump_alert(lt_notice(units=200), h))

    def test_ignores_current_and_future_rows(self):
        h = hist(150, 150, 150) + [{"year": 2026, "month": 11, "units": 300, "label": "current"}]
        a = usage_jump_alert(lt_notice(units=300), h)
        self.assertEqual(a["past_average"], 150.0)

    def test_prev_bill_used_when_no_history(self):
        self.assertIsNotNone(usage_jump_alert(lt_notice(units=650), None, {"units": 150}))

    def test_printed_average_used_last(self):
        self.assertIsNotNone(usage_jump_alert(lt_notice(units=300, average_month_units=150)))
        self.assertIsNone(usage_jump_alert(lt_notice(units=180, average_month_units=150)))

    def test_demo_bill_does_not_alert(self):
        from demo_data import lakshmi_demo_bundle
        from dashboard import build_dashboard_model
        b = lakshmi_demo_bundle()
        m = build_dashboard_model(b["bill"], b.get("prev_bill"), None)
        self.assertIsNone(m["usage_jump"])

    def test_scenario_c_alerts_in_model(self):
        from scenarios import get_scenario
        from dashboard import build_dashboard_model
        s = get_scenario("C")
        self.assertIsNotNone(build_dashboard_model(s["bill"], s["prev_bill"], None)["usage_jump"])

    def test_57_day_132_units_vs_avg_72_is_not_a_jump(self):
        # 132 units / 57 days ≈ 69.5 per 30 days, at or below the printed average.
        self.assertIsNone(usage_jump_alert(
            lt_notice(units=132, days=57, average_month_units=72)
        ))

    def test_30_day_154_units_vs_avg_72_still_alerts(self):
        a = usage_jump_alert(lt_notice(units=154, days=30, average_month_units=72))
        self.assertIsNotNone(a)
        self.assertFalse(a["normalised"])
        self.assertIn("ఈ నెల 154 యూనిట్లు", a["text_te"])
        self.assertNotIn("నెలకు సుమారు", a["text_te"])

    def test_60_day_300_units_vs_avg_72_still_alerts(self):
        # 300 / 60 * 30 = 150 per month: still a jump vs 72.
        a = usage_jump_alert(lt_notice(units=300, days=60, average_month_units=72))
        self.assertIsNotNone(a)
        self.assertTrue(a["normalised"])
        self.assertEqual(a["monthly_units"], 150.0)
        self.assertIn("60 రోజులకు 300 యూనిట్లు", a["text_te"])
        self.assertIn("నెలకు సుమారు 150 యూనిట్లు", a["text_te"])

    def test_missing_days_keeps_raw_units(self):
        # Same 132 vs 72, but no period to normalise — current behaviour stands.
        self.assertIsNotNone(usage_jump_alert(
            lt_notice(units=132, days=None, average_month_units=72)
        ))

    def test_long_prev_bill_is_normalised_in_average(self):
        # Prev 144 units over 60 days is ~72/month; 154 in 30 days is still a jump.
        a = usage_jump_alert(
            lt_notice(units=154, days=30),
            None,
            {"units": 144, "days": 60},
        )
        self.assertIsNotNone(a)
        self.assertEqual(a["past_average"], 72.0)

    def test_long_history_row_is_normalised_in_average(self):
        h = [{"year": 2026, "month": 8, "units": 144, "days": 60, "estimated": False}]
        a = usage_jump_alert(lt_notice(units=154, days=30), h)
        self.assertIsNotNone(a)
        self.assertEqual(a["past_average"], 72.0)


class BannerWordingTests(unittest.TestCase):
    def test_banner_is_short_and_has_no_rupee_tolerance(self):
        self.assertEqual(t("calc_matches"), "బిల్లులోని లెక్కలు మొత్తానికి సరిపోయాయి ✅")
        self.assertNotIn("₹1", t("calc_matches"))
        self.assertNotIn("లోపు", t("calc_matches"))


if __name__ == "__main__":
    unittest.main()
