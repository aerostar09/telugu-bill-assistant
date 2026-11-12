"""History merge / table / manual-entry tests. No NVIDIA calls."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from history_input import (
    bill_to_history_row,
    parse_history_table_payload,
    parse_manual_rows,
    merge_history_rows,
    history_display_meta,
    BACKTEST_MIN_REAL_MONTHS,
    LABEL_DEMO,
    LABEL_USER,
)
from demo_data import LAKSHMI_CURR, DEMO_HISTORY, lakshmi_demo_bundle
from dashboard import build_dashboard_model
from self_checks import run_all_checks


class TestBillToRow(unittest.TestCase):
    def test_nov_bill(self):
        row = bill_to_history_row(LAKSHMI_CURR)
        self.assertEqual(row["year"], 2026)
        self.assertEqual(row["month"], 11)
        self.assertEqual(row["units"], 154)
        self.assertEqual(row["amount"], 757.0)

    def test_skips_unreadable(self):
        self.assertIsNone(bill_to_history_row({"units": 100}))
        self.assertIsNone(bill_to_history_row({"bill_date": "06/11/2026"}))


class TestTableAndManual(unittest.TestCase):
    def test_history_table_payload(self):
        raw = {"rows": [
            {"month": "Oct 2026", "units": 138, "amount": 700},
            {"month": "2026-09", "units": 142},
            {"month": "bad", "units": 10},  # dropped
        ]}
        rows = parse_history_table_payload(raw)
        self.assertEqual([(r["year"], r["month"], r["units"]) for r in rows], [
            (2026, 9, 142.0),
            (2026, 10, 138.0),
        ])
        self.assertEqual(rows[1]["amount"], 700)

    def test_manual_rows(self):
        rows = parse_manual_rows([
            {"month": "2026-08", "units": 160, "amount": 800},
            {"month": "Jul 2026", "units": 185},
            {"month": "2026-08", "units": ""},  # ignored empty
            {"year": 2026, "month": 6, "units": 198},
        ])
        self.assertEqual([r["month"] for r in rows], [6, 7, 8])
        self.assertEqual(rows[-1]["units"], 160)


class TestMergeAndMeta(unittest.TestCase):
    def test_merge_overrides_and_current_wins(self):
        photos = [
            bill_to_history_row({"bill_date": "05/10/2026", "units": 130, "bill_amount": 600}),
        ]
        manual = parse_manual_rows([{"month": "2026-10", "units": 138}])
        hist = merge_history_rows(photos, manual, current_bill=LAKSHMI_CURR)
        by = {(r["year"], r["month"]): r for r in hist}
        self.assertEqual(by[(2026, 10)]["units"], 138)  # manual later
        self.assertEqual(by[(2026, 11)]["units"], 154)
        self.assertEqual(by[(2026, 11)]["source"], "current_bill")

    def test_demo_label_hides_backtest(self):
        meta = history_display_meta(DEMO_HISTORY, is_demo=True)
        self.assertEqual(meta["source_label"], LABEL_DEMO)
        self.assertFalse(meta["show_backtest"])
        self.assertEqual(meta["n_real"], 0)

    def test_user_label_backtest_threshold(self):
        five = DEMO_HISTORY[:5]
        self.assertFalse(history_display_meta(five, is_demo=False)["show_backtest"])
        six = DEMO_HISTORY[:BACKTEST_MIN_REAL_MONTHS]
        meta = history_display_meta(six, is_demo=False)
        self.assertTrue(meta["show_backtest"])
        self.assertEqual(meta["source_label"], LABEL_USER)
        self.assertEqual(meta["n_real"], 6)


class TestDashboardRespectsSource(unittest.TestCase):
    def test_demo_model_hides_backtest(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"]))
        self.assertTrue(model["history_meta"]["is_demo"])
        self.assertEqual(model["history_meta"]["source_label"], LABEL_DEMO)
        self.assertFalse(model["history_meta"]["show_backtest"])
        self.assertIsNone(model["backtest"])

    def test_user_history_shows_backtest_at_6(self):
        bill = dict(LAKSHMI_CURR)
        bill["history_is_demo"] = False
        bill["unit_history"] = DEMO_HISTORY  # 13 real-looking months supplied by the user
        model = build_dashboard_model(bill, None, run_all_checks(bill))
        self.assertEqual(model["history_meta"]["source_label"], LABEL_USER)
        self.assertTrue(model["history_meta"]["show_backtest"])
        self.assertIsNotNone(model["backtest"])
        self.assertGreaterEqual(model["backtest"]["n"], 6)


class TestHistoryTableExtractMocked(unittest.TestCase):
    def test_mocked_nvidia_no_live_call(self):
        # Prefer mocks; do not hit NVIDIA.
        from nvidia_pipeline import extract_history_table_pipeline

        fake = {"rows": [{"month": "Sep 2026", "units": 142, "amount": 680}]}
        img = Image.new("RGB", (200, 100), "white")
        with patch("nvidia_pipeline.call_nvidia_once", return_value=(fake, 0.01, "{}")) as mocked:
            out = extract_history_table_pipeline(img, use_cache=False)
        mocked.assert_called_once()
        self.assertEqual(len(out["rows"]), 1)
        self.assertEqual(out["rows"][0]["units"], 142)
        self.assertFalse(out.get("from_cache"))


if __name__ == "__main__":
    unittest.main()
