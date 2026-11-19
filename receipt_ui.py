"""Mobile-first receipt card, units bar, and next-cliff helper."""
from __future__ import annotations

from typing import Any, Dict, Optional

from bill_lines import CHARGE_ROWS, REDUCTION_KEYS, effective_arrears, nonzero_rows, payable_amount
from dashboard import _inr, energy_formula
from tariff import delayed_payment_surcharge, trueup_rate_for_bill_date, infer_category
from terms import t


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



def _circle_icon(bg: str, svg: str) -> str:
    return (
        f'<span class="rc-ico" style="background:{bg}">{svg}</span>'
    )


_ICO_SVGS = {
    "energy_charges": ("#fff4d4", '<svg viewBox="0 0 20 20" width="14" height="14"><path fill="#d97706" d="M11.2 2.2L4.8 11h4.2L7.4 17.8 16 8.6h-4.3L11.2 2.2z"/></svg>'),
    "fixed_charges": ("#dbeafe", '<svg viewBox="0 0 20 20" width="14" height="14"><path fill="#2563eb" d="M10 3.2 3.5 8.2V16h5v-4h3v4h5V8.2L10 3.2z"/></svg>'),
    "customer_charges": ("#f3e8ff", '<svg viewBox="0 0 20 20" width="14" height="14"><circle cx="10" cy="7" r="3" fill="#7c3aed"/><path d="M4.5 16c.6-3 2.6-4.4 5.5-4.4S15 13 15.5 16" fill="#7c3aed"/></svg>'),
    "electricity_duty": ("#dcfce7", '<svg viewBox="0 0 20 20" width="14" height="14"><rect x="5" y="3" width="10" height="14" rx="1.5" fill="#0f9f6e"/><path d="M7.5 7h5M7.5 10h5M7.5 13h3" stroke="#fff" stroke-width="1.2"/></svg>'),
    "gjs_subsidy": ("#dcfce7", '<svg viewBox="0 0 20 20" width="14" height="14"><path fill="#16a34a" d="M4 16c6-1 10-5 12-12-6 1-11 5-12 12z"/></svg>'),
    "subsidy": ("#dcfce7", '<svg viewBox="0 0 20 20" width="14" height="14"><path fill="#16a34a" d="M4 16c6-1 10-5 12-12-6 1-11 5-12 12z"/></svg>'),
    "trueup_charges": ("#ffedd5", '<svg viewBox="0 0 20 20" width="14" height="14"><path fill="none" stroke="#c2410c" stroke-width="1.6" d="M5 10a5 5 0 1 1 1.5 3.5"/><path d="M5 13.5V10h3.2" fill="none" stroke="#c2410c" stroke-width="1.6"/></svg>'),
    "loss_gain": ("#f1f5f9", '<svg viewBox="0 0 20 20" width="14" height="14"><path d="M4 13h3l2-5 2 8 2-3h3" fill="none" stroke="#475569" stroke-width="1.6" stroke-linecap="round"/></svg>'),
    "surcharge": ("#fee2e2", '<svg viewBox="0 0 20 20" width="14" height="14"><path d="M10 3.5 17 16H3L10 3.5z" fill="#dc2626"/><path d="M10 8v4.2" stroke="#fff" stroke-width="1.5"/><circle cx="10" cy="14.2" r="0.8" fill="#fff"/></svg>'),
    "fsa_fca": ("#ffedd5", '<svg viewBox="0 0 20 20" width="14" height="14"><circle cx="10" cy="10" r="6" fill="none" stroke="#c2410c" stroke-width="1.5"/><path d="M10 6.5v3.5l2.2 1.4" stroke="#c2410c" stroke-width="1.5" fill="none"/></svg>'),
    "adjustment": ("#f1f5f9", '<svg viewBox="0 0 20 20" width="14" height="14"><path d="M6 10h8M10 6v8" stroke="#475569" stroke-width="1.6" stroke-linecap="round"/></svg>'),
    "interest_on_ed": ("#dcfce7", '<svg viewBox="0 0 20 20" width="14" height="14"><path d="M7 14V6h3.2a2.6 2.6 0 0 1 0 5.2H7" fill="none" stroke="#0f9f6e" stroke-width="1.6"/></svg>'),
    "interest_on_cd": ("#dbeafe", '<svg viewBox="0 0 20 20" width="14" height="14"><path d="M7 14V6h3.2a2.6 2.6 0 0 1 0 5.2H7" fill="none" stroke="#2563eb" stroke-width="1.6"/></svg>'),
    "arrears": ("#fee2e2", '<svg viewBox="0 0 20 20" width="14" height="14"><rect x="4" y="5" width="12" height="10" rx="1.5" fill="#dc2626"/></svg>'),
    "arrears_as_on": ("#fee2e2", '<svg viewBox="0 0 20 20" width="14" height="14"><rect x="4" y="5" width="12" height="10" rx="1.5" fill="#dc2626"/></svg>'),
    "arrears_after": ("#fee2e2", '<svg viewBox="0 0 20 20" width="14" height="14"><rect x="4" y="5" width="12" height="10" rx="1.5" fill="#dc2626"/></svg>'),
    "acd_due": ("#ffedd5", '<svg viewBox="0 0 20 20" width="14" height="14"><rect x="4" y="5" width="12" height="10" rx="1.5" fill="#c2410c"/></svg>'),
}
_DEFAULT_ICO = ("#eef2f1", '<svg viewBox="0 0 20 20" width="14" height="14"><circle cx="10" cy="10" r="5" fill="#64748b"/></svg>')


def row_icon(key: str) -> str:
    bg, svg = _ICO_SVGS.get(key, _DEFAULT_ICO)
    return _circle_icon(bg, svg)


def total_label_pair(pay_label: str) -> tuple[str, str]:
    if pay_label == GJ_WITHOUT_SCHEME_LABEL_TE:
        return pay_label, t("scheme_off_en")
    if "Total Due" in pay_label or "మొత్తం చెల్లింపు (Total Due)" == pay_label:
        return "మొత్తం చెల్లింపు", t("total_due_en")
    return "మొత్తం చెల్లింపు", t("total_en")


GJ_WITHOUT_SCHEME_LABEL_TE = "స్కీమ్ లేకపోతే చెల్లింపు"


def receipt_pay_label(bill: Dict[str, Any], gj_mode: Optional[str] = None) -> str:
    """Receipt total label. In the Gruha Jyothi ₹0 view (ticked, ≤200 units,
    no printed subsidy) the printed total means 'without the scheme'."""
    if gj_mode == "free":
        return GJ_WITHOUT_SCHEME_LABEL_TE
    if effective_arrears(bill) >= 1.0 and bill.get("total_due") is not None:
        return "మొత్తం చెల్లింపు (Total Due)"
    return "మొత్తం చెల్లింపు"


def receipt_card_html(
    bill: Dict[str, Any],
    formulas: Optional[Dict[str, str]] = None,
    gj_mode: Optional[str] = None,
    show_gj_tip: bool = False,
) -> str:
    """Charge list: Telugu name, English under it, icon, amount. Testable HTML."""
    rows = nonzero_rows(bill)
    parts = ['<div class="receipt" data-testid="receipt-card">']
    for r in rows:
        formula = (formulas or {}).get(r["key"]) or formula_for(r["key"], bill)
        if r["key"] == "trueup_charges":
            from draft_features import trueup_what_is_it_html
            formula = f"{formula}<br>{trueup_what_is_it_html()}"
        if r["key"] == "gjs_subsidy" and bill.get("bill_amount") is not None:
            parts.append(
                f'<div class="rc-row rc-sub" data-testid="receipt-gj-without">'
                f'<span class="rc-lab"><b>{GJ_WITHOUT_SCHEME_LABEL_TE}</b>'
                f'<small>{t("scheme_off_en")}</small></span>'
                f'<span class="rc-amt">₹{float(bill["bill_amount"]):,.2f}</span></div>'
            )
        sign = "−" if r["amount"] < 0 or r["key"] in REDUCTION_KEYS else ""
        amt = f"{sign}₹{abs(r['amount']):,.2f}"
        en = r.get("name_en") or ""
        amt_cls = "rc-amt subsidy" if (r["key"] in REDUCTION_KEYS or r["amount"] < 0) else "rc-amt"
        parts.append(
            f'<details class="rc-row"><summary>'
            f'{row_icon(r["key"])}'
            f'<span class="rc-lab"><b>{r["name_te"]}</b><small>{en}</small></span>'
            f'<span class="{amt_cls}">{amt}</span></summary>'
            f'<div class="rc-formula">{formula}</div></details>'
        )
    pay = payable_amount(bill)
    pay_label = receipt_pay_label(bill, gj_mode)
    te, en = total_label_pair(pay_label)
    if pay is not None:
        parts.append(
            f'<div class="rc-total" data-testid="receipt-total">'
            f'<span class="rc-lab"><b>{te}</b><small>{en}</small></span>'
            f'<span>₹{pay:,.0f}</span></div>'
        )
    if show_gj_tip:
        parts.append(
            f'<div class="gj-tip" data-testid="gj-tip">'
            f'<b>{t("gj_tip_te")}</b>'
            f'<small>{t("gj_tip_en")}</small></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_receipt_card(
    bill: Dict[str, Any],
    formulas: Optional[Dict[str, str]] = None,
    gj_mode: Optional[str] = None,
    show_gj_tip: bool = False,
) -> None:
    import streamlit as st
    st.markdown(
        receipt_card_html(bill, formulas, gj_mode, show_gj_tip=show_gj_tip),
        unsafe_allow_html=True,
    )
