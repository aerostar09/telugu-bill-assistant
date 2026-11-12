"""One-click demo scenarios. Rupees come from tariff.py — never hardcoded totals."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from tariff import quote_bill, infer_category, energy_charges

# Sample FY 2022-23 units used only to illustrate the Nov 2026 30p true-up.
# Labelled sample — not a real consumer.
SAMPLE_TRUEUP_UNITS = 100
SAMPLE_BILL_DATE = "06/11/2026"  # 30 paise true-up month
SAMPLE_LOAD_KW = 3.0
SAMPLE_DAYS = 30
ANOMALY_FACTOR = 2.5

OFFICIAL_WA_DISPLAY = "87124 41912"
OFFICIAL_WA_DIGITS = "8712441912"
COMPLAINT_1912 = "1912"


def is_usage_anomaly(
    current_units: float,
    recent_units: Sequence[float],
    factor: float = ANOMALY_FACTOR,
) -> Dict[str, Any]:
    """Flag if current units exceed *factor* times the recent average.

    This is a screening flag only — never a diagnosis of meter fault.
    """
    recent = [float(u) for u in recent_units if u is not None]
    avg = (sum(recent) / len(recent)) if recent else None
    ratio = (float(current_units) / avg) if avg and avg > 0 else None
    flagged = bool(ratio is not None and ratio > factor)
    return {
        "flagged": flagged,
        "current_units": float(current_units),
        "recent_units": recent,
        "recent_average": None if avg is None else round(avg, 2),
        "ratio": None if ratio is None else round(ratio, 2),
        "factor": factor,
    }


def _bill_from_quote(q: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    bill = {
        "discom": "TGSPDCL",
        "usc_no": None,
        "category": q["category"],
        "contracted_load_kw": SAMPLE_LOAD_KW,
        "phase": "1",
        "bill_date": SAMPLE_BILL_DATE,
        "prev_reading": None,
        "present_reading": None,
        "units": q["units"],
        "days": q["days"],
        "energy_charges": q["energy_charges"],
        "fixed_charges": q["fixed_charges"],
        "customer_charges": q["customer_charges"],
        "electricity_duty": q["electricity_duty"],
        "interest_on_ed": 0,
        "surcharge": 0,
        "trueup_charges": q["trueup_charges"],
        "trueup_units": extra.pop("trueup_units", SAMPLE_TRUEUP_UNITS),
        "fsa_fca": 0,
        "subsidy": 0,
        "adjustment": 0,
        "loss_gain": 0,
        "bill_amount": q["total"],
        "bill_amount_printed": q["total"],
        "total_due": q["total"],
        "due_date": "20/11/2026",
    }
    bill.update(extra)
    return bill


def scenario_a() -> Dict[str, Any]:
    """215 units LT-I(B)(ii): first 200 @ ₹5.10 + 15 @ ₹7.70, cliff vs 200, sample true-up, GJ loss."""
    units = 215.0
    q = quote_bill(
        units,
        load_kw=SAMPLE_LOAD_KW,
        days=SAMPLE_DAYS,
        bill_date=SAMPLE_BILL_DATE,
        trueup_units=SAMPLE_TRUEUP_UNITS,
        pro_rate=False,
    )
    q200 = quote_bill(
        200.0,
        load_kw=SAMPLE_LOAD_KW,
        days=SAMPLE_DAYS,
        bill_date=SAMPLE_BILL_DATE,
        trueup_units=SAMPLE_TRUEUP_UNITS,
        pro_rate=False,
    )
    # Explicit slab math (must match energy_charges, used in copy + tests)
    energy_200_part = 200.0 * 5.10
    energy_excess = 15.0 * 7.70
    energy_expected = round(energy_200_part + energy_excess, 2)
    cliff = round(q["total"] - q200["total"], 2)
    bill = _bill_from_quote(q, trueup_units=SAMPLE_TRUEUP_UNITS)
    te = (
        f"సీనారియో A (నమూనా, నిజమైన కన్స్యూమర్ కాదు): {int(units)} యూనిట్లు, కేటగిరీ {q['category']}.\n"
        f"ఎనర్జీ: మొదటి 200 యూనిట్లు × ₹5.10 = ₹{energy_200_part:.2f}, "
        f"మిగిలిన 15 యూనిట్లు × ₹7.70 = ₹{energy_excess:.2f}. మొత్తం ఎనర్జీ ₹{energy_expected:.2f}.\n"
        f"ఫిక్స్‌డ్ ₹{q['fixed_charges']:.2f}, కస్టమర్ ₹{q['customer_charges']:.2f}, "
        f"ED ₹{q['electricity_duty']:.2f}.\n"
        f"True-up: నమూనా FY 2022-23 యూనిట్లు {SAMPLE_TRUEUP_UNITS} × 30 పైసలు (నవంబర్ 2026) = ₹{q['trueup_charges']:.2f}. "
        f"ఇది ప్రస్తుత యూనిట్లపై కాదు — బిల్లులో ఉన్న FY22-23 యూనిట్లపై.\n"
        f"మొత్తం బిల్లు ₹{q['total']:.2f}.\n"
        f"200 యూనిట్ల వద్ద (కేటగిరీ {q200['category']}) మొత్తం ₹{q200['total']:.2f} — "
        f"15 యూనిట్లు ఎక్కువైతే బిల్లు ₹{cliff:.2f} పెరుగుతుంది (స్లాబ్/కేటగిరీ క్లిఫ్).\n"
        "గృహ జ్యోతి లబ్ధిదారు అయితే: 200 యూనిట్లు దాటిన తర్వాత ఉచిత ప్రయోజనం పోతుంది, "
        "మొత్తం బిల్లు చెల్లించాలి (అదనపు యూనిట్లు మాత్రమే కాదు)."
    )
    en = (
        f"Scenario A (sample, not a real consumer): {int(units)} units, category {q['category']}. "
        f"Energy = 200×₹5.10 + 15×₹7.70 = ₹{energy_expected:.2f}. "
        f"Total ₹{q['total']:.2f}. At 200 units (category {q200['category']}) the bill would be "
        f"₹{q200['total']:.2f}; the 15-unit cliff is ₹{cliff:.2f}. "
        "A Gruha Jyothi beneficiary who crosses 200 loses the free benefit and pays the whole bill."
    )
    return {
        "id": "A",
        "title_te": "సీనారియో A — 215 యూనిట్లు, క్లిఫ్ + True-up",
        "title_en": "Scenario A — 215 units, cliff + true-up",
        "bill": bill,
        "prev_bill": None,
        "quote": q,
        "quote_at_200": q200,
        "energy_expected": energy_expected,
        "cliff_rupees": cliff,
        "sample_trueup_units": SAMPLE_TRUEUP_UNITS,
        "telugu": te,
        "english": en,
        "label": "SAMPLE / one-click scenario — rupees from tariff.py",
    }


def scenario_b() -> Dict[str, Any]:
    """180 units at normal tariff; GJ would be ₹0; 20-unit buffer before 200."""
    units = 180.0
    q = quote_bill(
        units,
        load_kw=SAMPLE_LOAD_KW,
        days=SAMPLE_DAYS,
        bill_date=SAMPLE_BILL_DATE,
        trueup_units=SAMPLE_TRUEUP_UNITS,
        pro_rate=False,
    )
    buffer = 200.0 - units
    daily_30 = round(200.0 / SAMPLE_DAYS, 2)
    bill = _bill_from_quote(q, trueup_units=SAMPLE_TRUEUP_UNITS)
    te = (
        f"సీనారియో B (నమూనా): {int(units)} యూనిట్లు, కేటగిరీ {q['category']}. "
        f"సాధారణ టారిఫ్ ప్రకారం ఎనర్జీ ₹{q['energy_charges']:.2f}, మొత్తం బిల్లు ₹{q['total']:.2f}.\n"
        "మీరు గృహ జ్యోతి లబ్ధిదారు అయితే ఈ బిల్లు ₹0 — 180 యూనిట్లు 200 లోపు ఉన్నాయి.\n"
        f"200 యూనిట్ల బండకు ఇంకా {int(buffer)} యూనిట్లు మిగిలాయి. "
        f"30 రోజుల సైకిల్‌లో 200 లోపు ఉండాలంటే రోజుకు సుమారు {daily_30} యూనిట్ల లోపు వాడండి. "
        "200 దాటితే ఉచిత ప్రయోజనం పోయి మొత్తం బిల్లు వస్తుంది."
    )
    en = (
        f"Scenario B (sample): {int(units)} units, category {q['category']}, "
        f"normal-tariff total ₹{q['total']:.2f}. If you are a Gruha Jyothi beneficiary this bill would be ₹0. "
        f"Buffer before 200: {int(buffer)} units. Daily budget tip: stay under about {daily_30} units/day "
        "over a 30-day cycle to remain at or below 200."
    )
    return {
        "id": "B",
        "title_te": "సీనారియో B — 180 యూనిట్లు, గృహ జ్యోతి బఫర్",
        "title_en": "Scenario B — 180 units, Gruha Jyothi buffer",
        "bill": bill,
        "prev_bill": None,
        "quote": q,
        "buffer_units": buffer,
        "daily_budget_units": daily_30,
        "gruha_jyothi_amount": 0.0,
        "sample_trueup_units": SAMPLE_TRUEUP_UNITS,
        "telugu": te,
        "english": en,
        "label": "SAMPLE / one-click scenario — rupees from tariff.py",
    }


def scenario_c() -> Dict[str, Any]:
    """Meter-fault-style anomaly: 150 → 650 units. Flag only, do not claim it IS a fault."""
    prev_u, curr_u = 150.0, 650.0
    q_prev = quote_bill(
        prev_u,
        load_kw=SAMPLE_LOAD_KW,
        days=SAMPLE_DAYS,
        bill_date="06/10/2026",
        trueup_units=SAMPLE_TRUEUP_UNITS,
        trueup_rate=0.0,  # before Nov 2026 true-up window
        pro_rate=False,
    )
    q = quote_bill(
        curr_u,
        load_kw=SAMPLE_LOAD_KW,
        days=SAMPLE_DAYS,
        bill_date=SAMPLE_BILL_DATE,
        trueup_units=SAMPLE_TRUEUP_UNITS,
        pro_rate=False,
    )
    flag = is_usage_anomaly(curr_u, [prev_u])
    bill = _bill_from_quote(q, trueup_units=SAMPLE_TRUEUP_UNITS)
    prev_bill = _bill_from_quote(q_prev, trueup_units=SAMPLE_TRUEUP_UNITS, bill_date="06/10/2026", due_date="20/10/2026")
    # October bill should not carry Nov 30p if we set rate 0
    prev_bill["trueup_charges"] = q_prev["trueup_charges"]
    te = (
        f"సీనారియో C (నమూనా): గత నెల {int(prev_u)} యూనిట్లు → ఈ నెల {int(curr_u)} యూనిట్లు "
        f"(సుమారు {flag['ratio']} రెట్లు, సగటు {flag['recent_average']}). "
        f"{flag['factor']} రెట్లు కంటే ఎక్కువైనందున ఇది ఒక అసాధారణ వినియోగ ఫ్లాగ్.\n"
        "ఇది మీటర్ లోపం అని చెప్పడం లేదు. సాధ్యమైన కారణాలు: మీటర్ లోపం, అంచనా రీడింగ్, "
        "రీడింగ్ పొరపాటు, లేదా నిజమైన వాడకం పెరగడం.\n"
        f"సాధారణ టారిఫ్ ప్రకారం ఈ నెల మొత్తం ₹{q['total']:.2f} (గత నెల ₹{q_prev['total']:.2f}).\n"
        f"ఫిర్యాదు/స్పష్టత కోసం 1912 కి కాల్ చేయండి లేదా TGSPDCL అధికారిక WhatsApp {OFFICIAL_WA_DISPLAY} కి రాయండి."
    )
    en = (
        f"Scenario C (sample): {int(prev_u)} → {int(curr_u)} units "
        f"({flag['ratio']}× recent average). Flagged because it exceeds {flag['factor']}×. "
        "This is not a claim that the meter is faulty. Possible causes include a meter fault, "
        "an estimated reading, a reading error, or a real usage increase. "
        f"Contact 1912 or the official TGSPDCL WhatsApp {OFFICIAL_WA_DISPLAY}."
    )
    return {
        "id": "C",
        "title_te": "సీనారియో C — 150→650 యూనిట్ల అసాధారణత",
        "title_en": "Scenario C — 150→650 unit anomaly flag",
        "bill": bill,
        "prev_bill": prev_bill,
        "quote": q,
        "quote_prev": q_prev,
        "anomaly": flag,
        "sample_trueup_units": SAMPLE_TRUEUP_UNITS,
        "telugu": te,
        "english": en,
        "complaint_hint": f"{COMPLAINT_1912} / official WhatsApp {OFFICIAL_WA_DISPLAY}",
        "label": "SAMPLE / one-click scenario — rupees from tariff.py; anomaly is a flag, not a diagnosis",
    }


SCENARIOS = {
    "A": scenario_a,
    "B": scenario_b,
    "C": scenario_c,
}


def get_scenario(key: str) -> Dict[str, Any]:
    fn = SCENARIOS[str(key).upper()]
    return fn()
