"""Mobile-first receipt card, units bar, and next-cliff helper."""
from __future__ import annotations

from typing import Any, Dict, Optional

from bill_lines import CHARGE_ROWS, REDUCTION_KEYS, effective_arrears, nonzero_rows, payable_amount
from dashboard import _inr, energy_formula
from tariff import delayed_payment_surcharge, trueup_rate_for_bill_date, infer_category


def formula_for(key: str, bill: Dict[str, Any]) -> str:
    units = bill.get("units")
    cat = bill.get("category")
    kw = bill.get("contracted_load_kw")
    if key == "energy_charges" and units is not None:
        return energy_formula(units, cat)
    if key == "fixed_charges":
        rate = 50 if (units is not None and float(units) > 800) else 10
        return f"{kw or 0:g} kW × ₹{rate} = {_inr(bill.get('fixed_charges'))}"
    if key == "customer_charges":
        return "బిల్లు నుండి (నెలవారీ సర్వీస్ ఫీ)"
    if key == "electricity_duty" and units is not None:
        return f"{int(round(float(units)))} × ₹0.06 = {_inr(round(float(units) * 0.06, 2))}"
    if key == "trueup_charges":
        tu_u = bill.get("trueup_units")
        from tariff import trueup_item_formulas
        formulas = trueup_item_formulas(bill, rupee="rs") if tu_u else []
        if formulas:
            return "; ".join(formulas)
        return "పాత సంవత్సరం పవర్ ఖర్చు సర్దుబాటు"
    if key == "surcharge":
        dps = delayed_payment_surcharge(bill.get("units"), bill.get("category"))
        return f"ఆలస్య చెల్లింపు రుసుము. Cat రేటు ₹{dps:.0f}."
    if key == "loss_gain":
        return "బిల్లు మొత్తానికి పైసల సర్దుబాటు (Loss/Gain)"
    if key == "subsidy":
        return "ప్రభుత్వం తగ్గించిన మొత్తం"
    if key == "gjs_subsidy":
        return "గృహ జ్యోతి స్కీమ్: బిల్లులో ముద్రించిన GJS సబ్సిడీ (Bill Amount − GJS = Net Bill Amount)"
    if key == "fsa_fca":
        return "ఇంధన ధర సర్దుబాటు (FSA/FCA)"
    if key == "interest_on_ed":
        return "ఎలక్ట్రిసిటీ డ్యూటీ మీద వడ్డీ"
    if key == "interest_on_cd":
        return "సెక్యూరిటీ డిపాజిట్ మీద వడ్డీ"
    return "బిల్లు నుండి"


def next_units_cliff(units: Optional[float]) -> Optional[Dict[str, Any]]:
    """Next official domestic threshold above current units (not hardcoded copy)."""
    if units is None:
        return None
    u = float(units)
    for thresh in (50, 100, 200, 300, 400, 800):
        if u < thresh:
            headroom = thresh - u
            # integer when whole units
            head_i = int(round(headroom)) if abs(headroom - round(headroom)) < 0.05 else headroom
            return {
                "threshold": thresh,
                "units": u,
                "headroom": head_i,
                "bar_max": thresh,
                "ratio": min(1.0, max(0.0, u / thresh)),
                "tone": "green" if thresh <= 100 and u <= 100 else ("yellow" if u <= 200 else "red"),
                "message_te": f"{head_i} యూనిట్లు దాటితే రేటు పెరుగుతుంది",
            }
    return {
        "threshold": int(u),
        "units": u,
        "headroom": 0,
        "bar_max": int(u),
        "ratio": 1.0,
        "tone": "red",
        "message_te": "ఈ వాడకం అత్యధిక స్లాబ్‌లో ఉంది",
    }


def render_units_bar(bill: Dict[str, Any]) -> None:
    import streamlit as st
    cliff = next_units_cliff(bill.get("units"))
    if not cliff:
        return
    u = int(round(cliff["units"])) if abs(cliff["units"] - round(cliff["units"])) < 0.05 else cliff["units"]
    pct = int(round(cliff["ratio"] * 100))
    st.markdown(
        f'<div class="units-bar" data-testid="units-bar">'
        f'<div class="units-bar-label">{u} / {cliff["threshold"]} యూనిట్లు</div>'
        f'<div class="track"><div class="fill fill-{cliff["tone"]}" style="width:{pct}%"></div></div>'
        f'<div class="units-bar-msg">{cliff["message_te"]}</div></div>',
        unsafe_allow_html=True,
    )


GJ_WITHOUT_SCHEME_LABEL_TE = "స్కీమ్ లేకపోతే చెల్లింపు"


def receipt_pay_label(bill: Dict[str, Any], gj_mode: Optional[str] = None) -> str:
    """Receipt total label. In the Gruha Jyothi ₹0 view (ticked, ≤200 units,
    no printed subsidy) the printed total means 'without the scheme'."""
    if gj_mode == "free":
        return GJ_WITHOUT_SCHEME_LABEL_TE
    if effective_arrears(bill) >= 1.0 and bill.get("total_due") is not None:
        return "మొత్తం చెల్లింపు (Total Due)"
    return "మొత్తం చెల్లింపు"


def render_receipt_card(
    bill: Dict[str, Any],
    formulas: Optional[Dict[str, str]] = None,
    gj_mode: Optional[str] = None,
) -> None:
    import streamlit as st
    rows = nonzero_rows(bill)
    parts = ['<div class="receipt" data-testid="receipt-card">']
    for r in rows:
        formula = (formulas or {}).get(r["key"]) or formula_for(r["key"], bill)
        if r["key"] == "trueup_charges":
            from draft_features import trueup_what_is_it_html
            formula = f"{formula}<br>{trueup_what_is_it_html()}"
        if r["key"] == "gjs_subsidy" and bill.get("bill_amount") is not None:
            # Printed Bill Amount before the scheme, then the GJS line.
            parts.append(
                f'<div class="rc-row rc-sub" data-testid="receipt-gj-without" '
                f'style="display:flex;justify-content:space-between;padding:.35rem 0;'
                f'border-top:1px dashed #cfd8dc;color:#455a64">'
                f'<span>{GJ_WITHOUT_SCHEME_LABEL_TE}</span>'
                f'<span>₹{float(bill["bill_amount"]):,.2f}</span></div>'
            )
        sign = "−" if r["amount"] < 0 or r["key"] in REDUCTION_KEYS else ""
        amt = f"{sign}₹{abs(r['amount']):,.2f}"
        parts.append(
            f'<details class="rc-row"><summary>'
            f'<span><b>{r["name_te"]}</b><br><small>{r["meaning_te"]}</small></span>'
            f'<span class="rc-amt">{amt}</span></summary>'
            f'<div class="rc-formula">{formula}</div></details>'
        )
    pay = payable_amount(bill)
    pay_label = receipt_pay_label(bill, gj_mode)
    if pay is not None:
        parts.append(
            f'<div class="rc-total" data-testid="receipt-total">'
            f'<span>{pay_label}</span><span>₹{pay:,.0f}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
