"""L6 bill-tab hero view: payable, due, match banner. No Streamlit, no PII."""
from __future__ import annotations

import unittest
from pathlib import Path

from citizen_ui import bill_dashboard_view, payable_size_class
from gruha_jyothi import gruha_jyothi_view
from scenarios import scenario_b
from self_checks import run_all_checks
from terms import t, format_due_date_display
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

    def test_payable_size_class_keeps_long_amounts_on_one_line(self):
        self.assertEqual(payable_size_class("₹0"), "")
        self.assertEqual(payable_size_class("₹757"), "")
        self.assertEqual(payable_size_class("₹12346"), "pay-mid")
        self.assertEqual(payable_size_class("₹12,345.60"), "pay-long")
        bill = lt_notice(bill_amount=12345.60)
        view = bill_dashboard_view(_model(bill))
        self.assertEqual(view["payable_display"], "₹12346")
        self.assertEqual(view["pay_size"], "pay-mid")


    def test_iso_due_date_displays_as_ddmmyyyy(self):
        self.assertEqual(format_due_date_display("2026-11-20"), "20/11/2026")
        self.assertEqual(format_due_date_display("20/11/2026"), "20/11/2026")
        self.assertEqual(format_due_date_display("20-11-2026"), "20-11-2026")
        self.assertEqual(format_due_date_display("20-11-26"), "20-11-26")
        self.assertEqual(format_due_date_display("not-a-date"), "not-a-date")
        self.assertEqual(format_due_date_display("2026-13-40"), "2026-13-40")
        self.assertEqual(format_due_date_display(None), "")
        self.assertEqual(format_due_date_display("  "), "")
        view = bill_dashboard_view(_model(lt_notice(due_date="2026-11-20")))
        self.assertEqual(view["due"], "20/11/2026")

class SingleWhatsAppButtonTests(unittest.TestCase):
    def test_only_hero_row_whatsapp_button_key_remains(self):
        app = Path(__file__).with_name("app_nvidia.py").read_text()
        ui = Path(__file__).with_name("citizen_ui.py").read_text()
        self.assertNotIn('key="wa_send_top"', app)
        self.assertNotIn('key="wa_send_demo"', app)
        self.assertNotIn('key="wa_send_top"', ui)
        self.assertNotIn('key="wa_send_demo"', ui)
        self.assertIn('key="wa_send_bill"', ui)
        self.assertEqual(app.count("WhatsApp కి పంపండి"), 0)
        self.assertEqual(ui.count("WhatsApp కి పంపండి"), 1)

