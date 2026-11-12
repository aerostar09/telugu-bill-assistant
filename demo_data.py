"""PII-free Lakshmi demo bills + synthetic 13-month history.

The Feb and Nov 2026 line items match ground-truth amounts (no name, USC,
address, or phone). The 13-month unit series is SYNTHETIC — thermal TGSPDCL
slips in /workspace/tisc/xbills do not print a 12–13 month history table,
and ground_truth.json has no history fields. Chart/forecast demos must label
this as డెమో / synthetic.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Consecutive-looking demo "previous" is the known ₹314 / 82-unit bill
# (printed 04/02/2026; readings 05/01/26 → 04/02/26 = 30 days).
LAKSHMI_PREV: Dict[str, Any] = {
    "discom": "TGSPDCL",
    "category": "1A Domestic",
    "contracted_load_kw": 3.0,
    "phase": "1ph",
    "bill_date": "04/02/2026",
    "prev_reading": 14872,
    "present_reading": 14954,
    "prev_reading_date": "05/01/26",
    "present_reading_date": "04/02/26",
    "units": 82,
    "days": 30,
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
    "due_date": "18-02-2026",
    "acd_due": 0.0,
    "is_electricity_bill": True,
    "image_quality": "clear",
}

# Known Nov 2026 bill (154 units / 31 days / ₹757). Reading dates were not
# on disk (jay8 photo never arrived); days=31 is from the printed bill.
LAKSHMI_CURR: Dict[str, Any] = {
    "discom": "TGSPDCL",
    "category": "1B(1) domestic",
    "contracted_load_kw": 3.0,
    "phase": "1ph",
    "bill_date": "06/11/2026",
    "prev_reading": 16204,
    "present_reading": 16358,
    "prev_reading_date": None,
    "present_reading_date": None,
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
    "acd_due": 0.0,
    "average_month_units": None,
    "is_electricity_bill": True,
    "image_quality": "clear",
}

# Nov 2025 … Nov 2026 (13 points). Jan 2026 = 82 matches the known Feb-dated
# bill; Nov 2026 = 154 matches the known Nov bill. Other months are plausible
# seasonal fillers for demo / backtest only. Apr 2026 marked estimated.
DEMO_HISTORY: List[Dict[str, Any]] = [
    {"year": 2025, "month": 11, "units": 148, "estimated": False},
    {"year": 2025, "month": 12, "units": 100, "estimated": False},
    {"year": 2026, "month": 1, "units": 82, "estimated": False},
    {"year": 2026, "month": 2, "units": 88, "estimated": False},
    {"year": 2026, "month": 3, "units": 105, "estimated": False},
    {"year": 2026, "month": 4, "units": 130, "estimated": True},
    {"year": 2026, "month": 5, "units": 175, "estimated": False},
    {"year": 2026, "month": 6, "units": 198, "estimated": False},
    {"year": 2026, "month": 7, "units": 185, "estimated": False},
    {"year": 2026, "month": 8, "units": 160, "estimated": False},
    {"year": 2026, "month": 9, "units": 142, "estimated": False},
    {"year": 2026, "month": 10, "units": 138, "estimated": False},
    {"year": 2026, "month": 11, "units": 154, "estimated": False},
]

# Hand-calculated short series used by unit tests of the blend formula.
BLEND_FIXTURE: List[Dict[str, Any]] = [
    {"year": 2025, "month": 10, "units": 80, "estimated": False},
    {"year": 2025, "month": 11, "units": 90, "estimated": False},
    {"year": 2025, "month": 12, "units": 70, "estimated": False},
    {"year": 2026, "month": 10, "units": 88, "estimated": False},
    {"year": 2026, "month": 11, "units": 99, "estimated": False},
]


def lakshmi_demo_bundle() -> Dict[str, Any]:
    curr = dict(LAKSHMI_CURR)
    curr["unit_history"] = [dict(p) for p in DEMO_HISTORY]
    curr["history_is_demo"] = True
    prev = dict(LAKSHMI_PREV)
    return {
        "bill": curr,
        "prev_bill": prev,
        "display_name": "లక్ష్మి (డెమో)",
        "pii_redacted": True,
    }
