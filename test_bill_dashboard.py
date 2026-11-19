"""L6 bill-tab hero view: payable, due, match banner. No Streamlit, no PII."""
from __future__ import annotations

import unittest

from citizen_ui import bill_dashboard_view
from gruha_jyothi import gruha_jyothi_view
from scenarios import scenario_b
from self_checks import run_all_checks
from terms import t
from test_gjs_subsidy import gj_bill
from test_lt_notice import lt_notice


def _model(bill, gj_ticked=False, checks=None):
    if checks is None:
        checks = run_all_checks(bill)
    return {
        "bill": bill,
        "checks": checks,
        "gruha_jyothi": gruha_jyothi_view(bill, gj_ticked),
    }


class BillDashboardViewTests(unittest.TestCase):
    def test_normal_757_bill(self):
        view = bill_dashboard_view(_model(lt_notice()))
        self.assertEqual(view["units_label"], "154")
        self.assertEqual(view["payable"], 757)
        self.assertEqual(view["payable_display"], "₹757")
        self.assertNotEqual(view["due"], "—")
        self.assertTrue(view["match_ok"])
        self.assertEqual(view["banner_kind"], "ok")
        self.assertEqual(view["banner_te"], t("calc_matches"))
        self.assertEqual(view["conf"]["css"], "badge-green")

    def test_printed_gj_zero_bill(self):
        view = bill_dashboard_view(_model(gj_bill()))
        self.assertEqual(view["units_label"], "132")
        self.assertEqual(view["payable"], 0)
        self.assertEqual(view["payable_display"], "₹0")
        self.assertEqual(view["due"], "17/09/2026")
        self.assertTrue(view["match_ok"])
        self.assertEqual(view["banner_kind"], "ok")

    def test_sample_b_gj_zero(self):
        view = bill_dashboard_view(_model(scenario_b()["bill"]))
        self.assertEqual(view["units_label"], "180")
        self.assertEqual(view["payable"], 0)
        self.assertEqual(view["payable_display"], "₹0")
        self.assertEqual(view["due"], "20/11/2026")
        self.assertTrue(view["match_ok"])

    def test_missing_due_date_is_dash(self):
        view = bill_dashboard_view(_model(lt_notice(due_date=None)))
        self.assertEqual(view["due"], "—")
        self.assertEqual(view["payable_display"], "₹757")
        self.assertTrue(view["match_ok"])

    def test_blank_due_date_is_dash(self):
        view = bill_dashboard_view(_model(lt_notice(due_date="  ")))
        self.assertEqual(view["due"], "—")

    def test_mismatch_yellow_banner(self):
        bill = lt_notice(bill_amount=900)
        view = bill_dashboard_view(_model(bill))
        self.assertFalse(view["match_ok"])
        self.assertEqual(view["banner_kind"], "bad")
        self.assertTrue(view["banner_te"])
        self.assertNotEqual(view["banner_te"], t("calc_matches"))
        self.assertEqual(view["conf"]["css"], "badge-red")
        # Payable still follows the printed/net amount helper, not the check result.
        self.assertEqual(view["payable_display"], "₹900")
