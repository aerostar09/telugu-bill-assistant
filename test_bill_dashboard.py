"""L6 bill-tab hero view: payable, due, match banner. No Streamlit, no PII."""
from __future__ import annotations

import unittest
from pathlib import Path

from citizen_ui import bill_dashboard_view, payable_size_class, dashboard_hero_html, RING_CAPTION
from gruha_jyothi import gruha_jyothi_view
from scenarios import scenario_b
from self_checks import run_all_checks
from terms import t, format_due_date_display
from test_gjs_subsidy import gj_bill
from test_lt_notice import lt_notice
from bill_lines import CHARGE_ROWS, CHARGE_LABELS_EN, GJS_ROW, AFTER_BILL_ROWS
from receipt_ui import receipt_card_html


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

    def test_gj_hero_has_scheme_pill_and_no_slash_200_in_ring(self):
        view = bill_dashboard_view(_model(scenario_b()["bill"]))
        self.assertEqual(view["theme"], "gj")
        self.assertTrue(view["show_scheme_pill"])
        self.assertEqual(view["scheme_pill_te"], "గృహ జ్యోతి వర్తించింది")
        self.assertEqual(view["scheme_pill_en"], "Gruha Jyothi applied")
        self.assertEqual(view["ring_caption"], RING_CAPTION)
        self.assertNotIn("200", view["ring_caption"])
        html = dashboard_hero_html(view)
        start = html.index('data-testid="units-ring"')
        end = html.index("</div></div></div></div>", start)
        ring = html[start:end]
        self.assertNotIn("/ 200", ring)
        self.assertNotIn("/200", ring)
        self.assertIn("180", ring)
        self.assertIn("యూనిట్లు / units", ring)
        self.assertIn('data-testid="scheme-pill"', html)
        self.assertIn("గృహ జ్యోతి వర్తించింది", html)
        self.assertIn("Gruha Jyothi applied", html)
        # Telugu before English in the pill
        self.assertLess(html.index("గృహ జ్యోతి వర్తించింది"), html.index("Gruha Jyothi applied"))
        self.assertFalse(view["show_due_highlight"])
        self.assertFalse(view["show_gj_tip"])
        self.assertTrue(view["show_units_bar"])

    def test_regular_hero_has_no_scheme_pill(self):
        view = bill_dashboard_view(_model(lt_notice()))
        self.assertEqual(view["theme"], "regular")
        self.assertFalse(view["show_scheme_pill"])
        self.assertEqual(view["scheme_pill_te"], "")
        self.assertTrue(view["show_due_highlight"])
        self.assertTrue(view["show_gj_tip"])
        self.assertFalse(view["show_units_bar"])
        html = dashboard_hero_html(view)
        self.assertNotIn("scheme-pill", html)
        self.assertNotIn("గృహ జ్యోతి వర్తించింది", html)
        self.assertNotIn("స్కీమ్ వర్తించలేదు", html)
        start = html.index('data-testid="units-ring"')
        end = html.index("</div></div></div></div>", start)
        ring = html[start:end]
        self.assertNotIn("/ 200", ring)
        self.assertNotIn("/200", ring)
        self.assertIn("due-hot", html)


    def test_units_bar_only_on_gj_bills(self):
        """N / 200 meter is for Gruha Jyothi bills only, same signal as the green hero."""
        gj = bill_dashboard_view(_model(scenario_b()["bill"]))
        regular = bill_dashboard_view(_model(lt_notice()))
        self.assertEqual(gj["theme"], "gj")
        self.assertTrue(gj["show_units_bar"])
        self.assertEqual(regular["theme"], "regular")
        self.assertFalse(regular["show_units_bar"])
        # Printed GJS zero bill uses the same hero detection.
        printed = bill_dashboard_view(_model(gj_bill()))
        self.assertEqual(printed["theme"], "gj")
        self.assertTrue(printed["show_units_bar"])
        src = Path(__file__).with_name("citizen_ui.py").read_text()
        self.assertIn('if view.get("show_units_bar"):', src)
        self.assertIn("render_units_bar(model[\"bill\"])", src)


class ReceiptBilingualTests(unittest.TestCase):
    def test_every_line_type_has_english_and_telugu_first(self):
        for key, te, _meaning in list(CHARGE_ROWS) + [GJS_ROW] + list(AFTER_BILL_ROWS):
            en = CHARGE_LABELS_EN[key]
            self.assertTrue(te.strip(), key)
            self.assertTrue(en.strip(), key)

        html = receipt_card_html(scenario_b()["bill"], gj_mode="gjs_printed", show_gj_tip=False)
        self.assertNotIn('data-testid="gj-tip"', html)
        # Energy row: Telugu name before English
        self.assertLess(html.index("కరెంటు వాడకం"), html.index(">Energy<"))
        self.assertLess(html.index("గృహ జ్యోతి సబ్సిడీ"), html.index("Gruha Jyothi subsidy"))
        self.assertLess(html.index("మొత్తం చెల్లింపు"), html.index(">Total<"))

        html_r = receipt_card_html(lt_notice(), gj_mode=None, show_gj_tip=True)
        self.assertIn('data-testid="gj-tip"', html_r)
        self.assertLess(
            html_r.index("అర్హత ఉన్న కుటుంబాలకు 200 యూనిట్ల లోపు గృహ జ్యోతి ఉచితం"),
            html_r.index("Eligible households: free up to 200 units (Gruha Jyothi)"),
        )
        # No scheme-applied pill text in a regular receipt
        self.assertNotIn("గృహ జ్యోతి వర్తించింది", html_r)


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

