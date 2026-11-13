"""Enterprise dashboard rendering for the Telugu bill assistant.

CSS + Telugu-first cards. Pure helpers are importable without Streamlit
(for unit tests of WhatsApp/complaint text). Streamlit is imported only
inside render_* functions.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from tariff import (
    infer_category,
    energy_charges,
    jump_breakdown,
    check_jump_breakdown,
    cliff_warning,
    parse_bill_date,
    trueup_rate_for_bill_date,
    trueup_rate_for_next_bill,
    CAT_1A_SLABS,
    CAT_1BI_SLABS,
    CAT_1BII_SLABS,
    _slabs_for,
    fixed_charges,
    delayed_payment_surcharge,
    customer_charges_for_units,
)
from history_input import merge_history_rows, history_display_meta, GRUHA_JYOTHI_NOTE_TE
from late_reading import late_reading_effect, resolve_billing_days
from forecast import forecast_bill, backtest, history_from_bill, forecast_display_range
from draft_features import trueup_explainer, jump_card_text, cliff_card_text
from self_checks import run_all_checks, check_jump_sum
from terms import t, rupees_display, TARIFF_VERSION

FEEDBACK_PATH = Path(__file__).resolve().parent / "data" / "feedback.json"
WA_MAX_CHARS = 700

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;500;600;700&family=Noto+Sans:wght@400;500;600;700&display=swap');

/* Noto for typography only. Do NOT force it on div/span — that overrides
   Material icon fonts and renders ligatures as literal text (e.g. _arrow_right). */
html, body, [data-testid="stAppViewContainer"], .stApp, .stMarkdown, p, h1, h2, h3, h4, h5, label {
  font-family: "Noto Sans Telugu", "Noto Sans", sans-serif !important;
}
span[data-testid="stIconMaterial"],
span[data-testid="stExpanderToggleIcon"],
i.material-icons,
.material-icons,
.material-symbols-rounded,
.material-symbols-outlined,
[data-testid="stIconMaterial"],
[class*="material-symbols"],
[class*="material-icons"] {
  font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons", sans-serif !important;
  font-style: normal;
  font-weight: 400;
  letter-spacing: normal;
  text-transform: none;
}
.block-container { max-width: 1120px; padding-top: 1.2rem; padding-bottom: 3rem; }
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent; display: none !important;}
div[data-testid="stToolbar"], div[data-testid="stAppDeployButton"], .stAppDeployButton {display: none !important;}
div[data-testid="stDecoration"] {display: none !important;}

.tisc-hero { margin: 0 0 1.1rem 0; }
.tisc-hero h1 { font-size: 1.7rem; font-weight: 700; color: #0f3d38; margin: 0 0 .2rem 0; }
.tisc-hero p { color: #4b635f; margin: 0; font-size: 0.95rem; }

.verdict { border-radius: 14px; padding: 0.9rem 1.15rem; font-weight: 600; font-size: 1.15rem; margin: 0 0 1rem 0; border: 1px solid transparent; }
.verdict-ok { background: #ecfdf3; color: #05603a; border-color: #abefc6; }
.verdict-bad { background: #fff6ed; color: #93370d; border-color: #fdc6a7; }

.card { background: #fff; border: 1px solid #e5eeec; border-radius: 14px; padding: 0.95rem 1.05rem; box-shadow: 0 1px 2px rgba(15,61,56,.04); height: 100%; }
.card h4 { margin: 0 0 .35rem 0; font-size: 0.82rem; font-weight: 600; color: #5b726e; letter-spacing: .01em; }
.card .amt { font-size: 1.45rem; font-weight: 700; color: #10221f; }
.card .formula { font-size: 0.82rem; color: #4b635f; margin-top: .35rem; line-height: 1.45; }

.badge { display: inline-block; border-radius: 999px; padding: 0.12rem 0.6rem; font-size: 0.75rem; font-weight: 700; margin-left: .3rem; }
.badge-green { background: #d1fadf; color: #05603a; }
.badge-yellow { background: #fef0c7; color: #93370d; }
.badge-red { background: #fecdca; color: #912018; }
.badge-muted { background: #eef2f1; color: #4b635f; }
.bill-hero { background: linear-gradient(180deg, #f0fdfa 0%, #ffffff 100%); border: 1px solid #c5ebe3; border-radius: 18px; padding: 1.15rem 1.2rem 1.25rem; text-align: center; margin: 0 0 1rem 0; }
.bill-hero-label { font-size: 0.95rem; color: #4b635f; font-weight: 600; }
.bill-hero-amt { font-size: 2.55rem; font-weight: 800; color: #0f3d38; line-height: 1.15; margin: .15rem 0 .35rem; }
.bill-hero-meta { display: flex; flex-wrap: wrap; gap: .45rem .8rem; justify-content: center; align-items: center; color: #4b635f; font-size: 0.95rem; }
.reason-card { background:#fff; border:1px solid #e5eeec; border-radius:14px; padding:.4rem 1rem .55rem; margin: 0 0 1rem 0; }
.reason-row { display:flex; justify-content:space-between; align-items:center; padding:.55rem 0; border-bottom:1px solid #eef2f1; gap: .75rem; }
.reason-row:last-child { border-bottom:0; }
.reason-row .why { font-weight: 600; color:#10221f; }
.reason-row .amt { font-weight: 700; white-space: nowrap; }
.upload-panel { background:#fff; border:2px dashed #9fd4c8; border-radius:16px; padding:1rem 1rem .6rem; margin: 0 0 1rem 0; }
.verdict-sm { font-size: 1rem; padding: .65rem 1rem; }
@media (max-width: 480px) {
  .bill-hero-amt { font-size: 2.15rem; }
  .tisc-hero h1 { font-size: 1.4rem; }
  .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
}


.jump-row { display: flex; justify-content: space-between; align-items: center; padding: .55rem 0; border-bottom: 1px solid #eef2f1; }
.jump-row:last-child { border-bottom: 0; font-weight: 700; }
.privacy { font-size: 0.8rem; color: #5b726e; background: #f4f7f6; border-radius: 10px; padding: .7rem .9rem; margin-top: 1rem; }


.receipt{border:1px solid #e5eeec;border-radius:14px;padding:4px 14px 6px;background:#fff;margin:0 0 1rem 0;}
.rc-row summary{display:flex;justify-content:space-between;align-items:flex-start;padding:10px 0;border-bottom:1px dashed #e5eeec;cursor:pointer;list-style:none;gap:12px;}
.rc-row summary::-webkit-details-marker{display:none;}
.rc-row small{color:#5b726e;font-weight:400;}
.rc-amt{font-weight:700;white-space:nowrap;color:#10221f;}
.rc-formula{font-size:13px;color:#4b635f;padding:6px 0 10px;line-height:1.45;}
.rc-total{display:flex;justify-content:space-between;align-items:baseline;font-size:1.25rem;font-weight:800;color:#0f3d38;padding:12px 0 8px;}
.units-bar{margin:0 0 1rem 0;}
.units-bar-label{font-weight:600;color:#10221f;margin-bottom:6px;}
.units-bar .track{height:10px;background:#eef2f1;border-radius:999px;overflow:hidden;}
.units-bar .fill{height:100%;border-radius:999px;}
.units-bar .fill-green{background:#12b76a;}
.units-bar .fill-yellow{background:#f79009;}
.units-bar .fill-red{background:#d92d20;}
.units-bar-msg{font-size:0.9rem;color:#4b635f;margin-top:6px;}
.forecast-one{font-size:1rem;color:#0f3d38;background:#f0fdfa;border:1px solid #c5ebe3;border-radius:12px;padding:.7rem 1rem;margin:0 0 1rem;}
div[data-testid="stMetricValue"] { font-family: "Noto Sans", "Noto Sans Telugu", sans-serif !important; }
"""


def _inr(n: Optional[float], signed: bool = False) -> str:
    if n is None:
        return "—"
    if signed:
        sign = "+" if n > 0.005 else ("−" if n < -0.005 else "")
        return f"{sign}₹{abs(n):,.2f}"
    return f"₹{n:,.2f}"


def energy_formula(units: float, category: Optional[str] = None) -> str:
    cat = infer_category(units, category)
    slabs = _slabs_for(cat)
    remaining = max(0.0, float(units))
    parts = []
    last_rate = slabs[-1][1]
    for width, rate in slabs:
        last_rate = rate
        if remaining <= 0:
            break
        cap = width if width is not None else remaining
        used = min(remaining, cap)
        parts.append(f"{_u(used)} × ₹{rate:.2f}")
        remaining -= used
    if remaining > 0:
        parts.append(f"{_u(remaining)} × ₹{last_rate:.2f}")
    total = energy_charges(units, cat, pro_rate=False)
    return f"{' + '.join(parts)} = {_inr(total)}  ({cat})"


def _u(n: float) -> str:
    return str(int(n)) if abs(n - int(n)) < 0.005 else f"{n:.2f}"


def charge_cards_data(bill: Dict[str, Any]) -> List[Dict[str, str]]:
    units = bill.get("units")
    cat = bill.get("category")
    kw = bill.get("contracted_load_kw")
    energy = bill.get("energy_charges")
    cards = []
    if energy is not None and units is not None:
        cards.append({
            "title": "ఎనర్జీ ఛార్జీలు",
            "amount": _inr(energy),
            "formula": energy_formula(units, cat),
        })
    if bill.get("fixed_charges") is not None:
        cards.append({
            "title": "ఫిక్స్‌డ్ ఛార్జీ",
            "amount": _inr(bill.get("fixed_charges")),
            "formula": (
                f"{_u(float(kw or 0))} kW × ₹"
                f"{'50' if (units is not None and float(units) > 800) else '10'}"
                f" = {_inr(bill.get('fixed_charges'))}"
                + (" (800 యూనిట్లు దాటితే ₹50/kW)" if (units is not None and float(units) > 800) else "")
            ),
        })
    if bill.get("customer_charges") is not None:
        cards.append({
            "title": "కస్టమర్ ఛార్జీ",
            "amount": _inr(bill.get("customer_charges")),
            "formula": "బిల్లు నుండి (నెలవారీ సర్వీస్ ఫీ)",
        })
    if bill.get("electricity_duty") is not None and units is not None:
        cards.append({
            "title": "ఎలక్ట్రిసిటీ డ్యూటీ",
            "amount": _inr(bill.get("electricity_duty")),
            "formula": f"{_u(float(units))} × ₹0.06 = {_inr(round(float(units) * 0.06, 2))}",
        })
    tu = bill.get("trueup_charges")
    tu_u = bill.get("trueup_units")
    if tu or tu_u:
        rate = trueup_rate_for_bill_date(bill.get("bill_date"))
        cards.append({
            "title": "PP TRUEUP",
            "amount": _inr(tu or 0),
            "formula": (
                f"FY 2022-23 యూనిట్లు {_u(float(tu_u or 0))} × ₹{rate:.2f} = {_inr(tu or 0)}"
                if tu_u else "బిల్లు నుండి"
            ),
        })
    sur = bill.get("surcharge")
    if sur is not None and float(sur) != 0:
        dps = delayed_payment_surcharge(bill.get("units"), bill.get("category"))
        cards.append({
            "title": "సర్‌ఛార్జ్ (DPS)",
            "amount": _inr(sur),
            "formula": (
                "ఆలస్య చెల్లింపు రుసుము (Delayed Payment Surcharge) — "
                "డ్యూ డేట్ తర్వాత చెల్లిస్తే. "
                f"అధికారిక రేటు: Cat 1Aకి ₹10, Cat 1Bకి ₹25 (ఈ బిల్లుకు ₹{dps:.0f})."
            ),
        })
    if bill.get("bill_amount") is not None:
        cards.append({
            "title": "మొత్తం బిల్లు",
            "amount": _inr(bill.get("bill_amount")),
            "formula": f"చెల్లించాల్సింది · గడువు {bill.get('due_date') or 'కనిపించలేదు'}",
        })
    return cards


def daily_budget(bill: Dict[str, Any], forecast: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Units-per-day to stay at or under the 100 and 200 cliffs next cycle."""
    out: Dict[str, Any] = {
        "budget_100": round(100 / 30.0, 2),
        "budget_200": round(200 / 30.0, 2),
        "cliff": cliff_warning(bill),
        "forecast_cliff": None,
    }
    if forecast and forecast.get("likely") is not None:
        # treat forecast as a 30-day next bill
        fake = {"units": forecast["likely"], "contracted_load_kw": bill.get("contracted_load_kw"),
                "customer_charges": bill.get("customer_charges"), "days": 30}
        out["forecast_cliff"] = cliff_warning(fake)
    return out


def whatsapp_summary(
    bill: Dict[str, Any],
    checks: Optional[Dict[str, Any]] = None,
    jump: Optional[Dict[str, Any]] = None,
    late: Optional[Dict[str, Any]] = None,
    forecast: Optional[Dict[str, Any]] = None,
) -> str:
    units = bill.get("units")
    total = bill.get("bill_amount")
    days = bill.get("days")
    ok = (checks or {}).get("ok")
    lines = ["మీ విద్యుత్ బిల్లు సారాంశం"]
    bits = []
    if units is not None:
        bits.append(f"{_u(float(units))} యూనిట్లు")
    if total is not None:
        bits.append(_inr(total))
    if days is not None:
        bits.append(f"{_u(float(days))} రోజులు")
    if bits:
        lines.append("ఈ నెల: " + ", ".join(bits) + ".")
    if ok is True:
        lines.append("లెక్క సరిగా ఉంది.")
    elif ok is False:
        lines.append("లెక్కల్లో తేడా ఉంది — CSC/1912 కి చూపించండి.")
    if jump and jump.get("difference") is not None:
        br = jump
        lines.append(
            "ఎందుకు పెరిగింది: "
            f"యూనిట్లు {_inr(br.get('extra_units_old_rate'), True)}, "
            f"కేటగిరీ {_inr(br.get('category_change'), True)}, "
            f"True-up {_inr(br.get('trueup_added'), True)}."
        )
    tu = bill.get("trueup_charges")
    tu_u = bill.get("trueup_units")
    if tu and tu_u:
        rate = trueup_rate_for_bill_date(bill.get("bill_date"))
        nxt = trueup_rate_for_next_bill(bill.get("bill_date"))
        lines.append(
            f"True-up FY 2022-23 {_u(float(tu_u))} × ₹{rate:.2f} = {_inr(tu)} "
            f"(ఈ నెల వాడకం కాదు). వచ్చే నెల ₹{nxt:.2f}/యూనిట్."
        )
    if late and late.get("is_late"):
        lines.append(
            f"{late['days']} రోజుల స్లాబ్ పుష్ ≈ {_inr(late['extra_rupees'])}."
        )
    if forecast and forecast.get("likely") is not None:
        q = (forecast.get("quotes") or {}).get("likely") or {}
        lo = (forecast.get("quotes") or {}).get("low") or {}
        hi = (forecast.get("quotes") or {}).get("high") or {}
        lines.append(
            f"వచ్చే నెల అంచనా: ~{forecast['likely']:g} యూనిట్లు, "
            f"{_inr(q.get('total'))} ({_inr(lo.get('total'))}–{_inr(hi.get('total'))})."
        )
    text = "\n".join(lines)
    if len(text) > WA_MAX_CHARS:
        text = text[: WA_MAX_CHARS - 1].rstrip() + "…"
    return text


def whatsapp_link(text: str) -> str:
    return "https://wa.me/?text=" + quote(text, safe="")


def complaint_draft(bill: Dict[str, Any], late: Optional[Dict[str, Any]] = None) -> str:
    parts = [
        "1912 / CSC కి ఫిర్యాదు డ్రాఫ్ట్:",
        f"బిల్లు తేదీ {bill.get('bill_date') or '—'}, "
        f"యూనిట్లు {bill.get('units') if bill.get('units') is not None else '—'}, "
        f"రోజులు {bill.get('days') if bill.get('days') is not None else '—'}, "
        f"మొత్తం {_inr(bill.get('bill_amount')) if bill.get('bill_amount') is not None else '—'}.",
    ]
    if late and late.get("is_late"):
        parts.append(
            f"మీటర్ రీడింగ్ {late['days']} రోజులకు జరిగింది (30 కాదు). "
            f"అన్‌ప్రోరేటెడ్ స్లాబ్‌ల వల్ల ఎనర్జీపై అంచనా అదనం {_inr(late['extra_rupees'])}."
        )
    parts.append(
        "దయచేసి బిల్లు సరిచూసి, అవసరమైతే స్లాబ్/రీడింగ్‌పై స్పష్టత ఇవ్వండి. "
        "(USC / పేరు ఇక్కడ మీరు జోడించండి — ఈ యాప్ వాటిని సేవ్ చేయదు.)"
    )
    return " ".join(parts)


def load_feedback() -> Dict[str, int]:
    try:
        if FEEDBACK_PATH.is_file():
            data = json.loads(FEEDBACK_PATH.read_text())
            return {"yes": int(data.get("yes") or 0), "no": int(data.get("no") or 0)}
    except Exception:
        pass
    return {"yes": 0, "no": 0}


def save_feedback(yes: int, no: int) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps({"yes": yes, "no": no}, indent=2))


def acd_explainer(bill: Dict[str, Any]) -> Optional[str]:
    amt = bill.get("acd_due")
    if amt is None and bill.get("acd_surcharge") is None:
        return None
    acd = amt if amt is not None else bill.get("acd_surcharge")
    try:
        acd_f = float(acd or 0)
    except (TypeError, ValueError):
        acd_f = 0.0
    if acd_f == 0:
        return (
            "ఈ బిల్లులో ACD Due ₹0.00. ACD (Additional Consumption Deposit) అంటే "
            "వార్షిక వాడకం బట్టి DISCOM తీసుకునే సెక్యూరిటీ డిపాజిట్ — ఈ నెల ఎనర్జీ ఛార్జీ కాదు."
        )
    return (
        f"ఈ బిల్లులో ACD Due {_inr(acd_f)}. ఇది అదనపు సెక్యూరిటీ డిపాజిట్ "
        "(Additional Consumption Deposit) — సాధారణంగా వార్షిక సగటు వాడకం పెరిగితే వస్తుంది, "
        "ఈ నెల యూనిట్ల ఛార్జీ కాదు. ఇల్లు అద్దెకు ఉంటే ఎవరు చెల్లించాలో అద్దె ఒప్పందం / "
        "కనెక్షన్ యజమాని బట్టి నిర్ణయించుకోండి."
    )


def build_dashboard_model(
    bill: Dict[str, Any],
    prev_bill: Optional[Dict[str, Any]] = None,
    checks: Optional[Dict[str, Any]] = None,
    extra_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    checks = checks or run_all_checks(bill)
    jump = jump_breakdown(prev_bill, bill) if prev_bill else None
    jump_chk = check_jump_breakdown(jump) if jump else None
    late = late_reading_effect(bill)
    existing = history_from_bill(bill)
    user_rows = list(extra_history or [])
    if user_rows:
        hist = merge_history_rows(existing, user_rows, current_bill=bill)
        is_demo = False
    else:
        hist = existing
        is_demo = bool(bill.get("history_is_demo"))
    meta = history_display_meta(hist, is_demo)
    bill_for_fc = dict(bill)
    bill_for_fc["unit_history"] = hist
    bill_for_fc["history_is_demo"] = is_demo
    fc = forecast_bill(bill_for_fc)
    bt = backtest(hist, bill) if meta.get("show_backtest") else None
    return {
        "bill": bill,
        "prev_bill": prev_bill,
        "checks": checks,
        "jump": jump,
        "jump_check": jump_chk,
        "late": late,
        "forecast": fc,
        "backtest": bt,
        "charges": charge_cards_data(bill),
        "budget": daily_budget(bill, fc),
        "trueup_text": trueup_explainer(bill),
        "cliff_text": cliff_card_text(bill),
        "acd_text": acd_explainer(bill),
        "wa_text": whatsapp_summary(bill, checks, jump, late, fc),
        "complaint": complaint_draft(bill, late),
        "history": hist,
        "history_is_demo": is_demo,
        "history_meta": meta,
    }


def render_dashboard(model: Dict[str, Any]) -> None:
    import streamlit as st
    import pandas as pd
    import altair as alt

    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

    bill = model["bill"]
    checks = model["checks"] or {}
    ok = checks.get("ok")
    if ok:
        st.markdown(
            '<div class="verdict verdict-ok" data-testid="trust-verdict">లెక్క సరిగా ఉంది ✅</div>',
            unsafe_allow_html=True,
        )
    else:
        msg = checks.get("message_te") or "లెక్కల్లో తేడా ఉంది"
        st.markdown(
            f'<div class="verdict verdict-bad" data-testid="trust-verdict">లెక్క సరిపోలలేదు ⚠️ — {msg}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Self-check వివరాలు"):
            st.json(checks)

    # Charge cards
    st.markdown("### ఛార్జీలు")
    cards = model["charges"]
    if cards:
        idx = 0
        for i in range(0, len(cards), 3):
            chunk = cards[i:i+3]
            cols = st.columns(len(chunk))
            for j, c in enumerate(chunk):
                with cols[j]:
                    st.markdown(
                        f'<div class="card" data-testid="charge-card-{idx}"><h4>{c["title"]}</h4>'
                        f'<div class="amt">{c["amount"]}</div>'
                        f'<div class="formula">{c["formula"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                idx += 1

    # Enduku perigindi
    st.markdown("### మీ బిల్లు ఎందుకు పెరిగింది?")
    jump = model.get("jump")
    if not jump or jump.get("difference") is None:
        st.info("గత బిల్లు ఉంటే, పెరుగుదలను రూపాయి వారీగా చూపిస్తాం.")
    else:
        br = jump
        rows = [
            ("అదనపు యూనిట్లు (పాత రేటుతో)", br.get("extra_units_old_rate"), "green", "మీ వాడకం"),
            ("కేటగిరీ / స్లాబ్ మార్పు", br.get("category_change"), "yellow", "స్లాబ్ మారింది"),
            ("True-up జోడింపు", br.get("trueup_added"), "red", "True-up"),
            ("ఫిక్స్‌డ్ / కస్టమర్ / ED / ఇతరం", br.get("other_changes"), "muted", "ఇతరం"),
            ("Residual", br.get("residual"), "muted", "మిగిలిన తేడా"),
        ]
        html = [f'<div class="card" data-testid="jump-card">']
        html.append(
            f'<div class="jump-row"><span>గత బిల్లు {_inr(br.get("prev_total"))} → ఈ నెల {_inr(br.get("curr_total"))}'
            f' ({_u(br.get("prev_units") or 0)} → {_u(br.get("curr_units") or 0)} యూనిట్లు, '
            f'{br.get("prev_category")} → {br.get("curr_category")})</span></div>'
        )
        for label, amt, badge, badge_te in rows:
            html.append(
                f'<div class="jump-row"><span>{label} '
                f'<span class="badge badge-{badge}">{badge_te}</span></span>'
                f'<span>{_inr(amt, signed=True)}</span></div>'
            )
        html.append(
            f'<div class="jump-row"><span>మొత్తం తేడా</span><span>{_inr(br.get("difference"), signed=True)}</span></div>'
        )
        html.append("</div>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        chk = model.get("jump_check") or {}
        if chk.get("ok"):
            st.success(
                f"Self-check: భాగాలు + residual = తేడా "
                f"({_inr(chk.get('parts_plus_residual'))} = {_inr(chk.get('difference'))})."
            )
        elif chk:
            st.warning("Self-check: భాగాల మొత్తం బిల్లు తేడాకు సరిపోలలేదు.")

    # Late reading
    st.markdown("### ఆలస్య రీడింగ్ / బిల్లింగ్ రోజులు")
    late = model.get("late")
    if not late:
        st.info("రోజులు లేదా యూనిట్లు కనిపించలేదు.")
    else:
        if late["is_late"]:
            st.markdown(
                f'<div class="card" data-testid="late-card">'
                f'<h4>రీడింగ్ {late["days"]} రోజులకు జరిగింది (30 కాదు)</h4>'
                f'<div class="amt">{_inr(late["extra_rupees"], signed=True)}</div>'
                f'<div class="formula">అన్‌ప్రోరేటెడ్ స్లాబ్‌లు {_inr(late["actual_energy"])} '
                f'− రోజులు/30 ప్రోరేటెడ్ స్లాబ్‌లు {_inr(late["fair_energy_prorated"])} '
                f'= {_inr(late["extra_rupees"])}. '
                f'30 రోజుల సమాన యూనిట్లు {_u(late["units_30d"])} '
                f'(ఇది వేరే లెక్క, హెడ్‌లైన్ తేడా కాదు). '
                f'మూలం: {late["days_source"]}.</div></div>',
                unsafe_allow_html=True,
            )
        elif late["is_early"]:
            st.markdown(
                f'<div class="card" data-testid="late-card">'
                f'<h4>రీడింగ్ {late["days"]} రోజులకే జరిగింది (30 కంటే తక్కువ)</h4>'
                f'<div class="formula">ప్రోరేటెడ్ స్లాబ్‌తో పోలిస్తే తేడా {_inr(late["extra_rupees"], signed=True)}.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="card" data-testid="late-card">'
                f'<h4>{late["days"]} రోజుల చక్రం — స్లాబ్ పుష్ లేదు</h4>'
                f'<div class="formula">extra = {_inr(late["extra_rupees"])}.</div></div>',
                unsafe_allow_html=True,
            )

    # History + forecast chart
    st.markdown("### 13 నెలల వాడకం + వచ్చే నెల అంచనా")
    meta = model.get("history_meta") or {}
    src = meta.get("source_label") or ("Demo data" if (model.get("history_is_demo") or bill.get("history_is_demo")) else "Your bills")
    src_te = meta.get("source_label_te") or src
    st.markdown(
        f'<div data-testid="history-source" class="badge {"badge-muted" if meta.get("is_demo") else "badge-green"}">'
        f"Source / మూలం: {src} · {src_te}</div>",
        unsafe_allow_html=True,
    )
    if meta.get("is_demo") or model.get("history_is_demo"):
        st.caption(
            "Demo data: ఈ చార్ట్‌లోని చాలా నెలలు సింథటిక్. థర్మల్ TGSPDCL స్లిప్‌లపై 12–13 నెలల టేబుల్ "
            "కనిపించలేదు; జనవరి 82, నవంబర్ 154 మాత్రం అసలు బిల్లు సంఖ్యలు. "
            "మీ అసలు బిల్లులు/మాన్యువల్ టేబుల్ ఇస్తే మూలం 'Your bills' అవుతుంది."
        )
    else:
        st.caption("Your bills: మీరు అప్‌లోడ్ / నమోదు చేసిన నెలలు (ప్రస్తుత బిల్లు సహా).")
    hist = model.get("history") or []
    fc = model.get("forecast")
    if hist:
        rows = []
        for p in hist:
            rows.append({
                "label": f"{p['year']}-{p['month']:02d}",
                "units": p["units"],
                "kind": "అంచనా నెల" if p.get("estimated") else "అసలు",
                "series": "చరిత్ర",
            })
        if fc:
            rows.append({
                "label": f"{fc['target_year']}-{fc['target_month']:02d}",
                "units": fc["likely"],
                "kind": "అంచనా",
                "series": "అంచనా",
                "low": fc["low"],
                "high": fc["high"],
            })
        df = pd.DataFrame(rows)
        color = alt.Color(
            "kind:N",
            scale=alt.Scale(
                domain=["అసలు", "అంచనా నెల", "అంచనా"],
                range=["#0e7c66", "#dc6803", "#155eef"],
            ),
            legend=alt.Legend(title=None),
        )
        bars = alt.Chart(df[df["series"] == "చరిత్ర"]).mark_bar(size=18, cornerRadiusEnd=3).encode(
            x=alt.X("label:N", title=None, sort=None),
            y=alt.Y("units:Q", title="యూనిట్లు"),
            color=color,
            tooltip=["label", "units", "kind"],
        )
        charts = [bars]
        fc_df = df[df["series"] == "అంచనా"]
        if not fc_df.empty:
            pts = alt.Chart(fc_df).mark_point(filled=True, size=90).encode(
                x=alt.X("label:N", sort=None),
                y="units:Q",
                color=color,
                tooltip=["label", "units", "low", "high"],
            )
            err = alt.Chart(fc_df).mark_errorbar().encode(
                x=alt.X("label:N", sort=None),
                y=alt.Y("low:Q"),
                y2="high:Q",
            )
            charts.extend([err, pts])
        # 100 / 200 guide lines
        rules = alt.Chart(pd.DataFrame({"y": [100, 200], "t": ["100", "200"]})).mark_rule(
            strokeDash=[4, 4], color="#98a2b3"
        ).encode(y="y:Q")
        chart = alt.layer(*charts, rules).properties(height=280).configure_view(stroke=None)
        st.altair_chart(chart, use_container_width=True)

    if fc:
        c1, c2, c3, c4 = st.columns(4)
        q = fc["quotes"]
        c1.metric("తక్కువ", f"{fc['low']:g} u")
        c1.caption(_inr(q["low"]["total"]))
        c2.metric("అవకాశం", f"{fc['likely']:g} u")
        c2.caption(_inr(q["likely"]["total"]))
        c3.metric("ఎక్కువ", f"{fc['high']:g} u")
        c3.caption(_inr(q["high"]["total"]))
        c4.metric("వచ్చే True-up", _inr(q["likely"]["trueup_charges"]))
        c4.caption(f"{int(fc['trueup_rate']*100)} పైసలు")
        st.caption(
            f"పద్ధతి: {fc['method']} · సీజనల్ {fc.get('seasonal')} + ట్రెండ్ {fc.get('trend')} "
            f"· True-up {fc['trueup_rate']} × FY 2022-23 ({fc.get('trueup_units') or '—'} యూనిట్లు, ఈ నెల వాడకం కాదు)."
        )
    bt = model.get("backtest") or {}
    if (model.get("history_meta") or {}).get("show_backtest") and bt.get("n"):
        st.caption(
            f"బ్యాక్‌టెస్ట్ (rolling one-step, n={bt['n']}): "
            f"MAE {bt['mae_units']:g} యూనిట్లు / {_inr(bt['mae_rupees'])}, "
            f"రేంజ్‌లో {bt['pct_within_range']:g}%."
            + (
                " సీజనల్ డేటా ఉన్న నెలలు: MAE "
                f"{bt['by_method']['blend_seasonal_trend']['mae_units']:g} యూనిట్లు, "
                f"రేంజ్‌లో {bt['by_method']['blend_seasonal_trend']['pct_within_range']:g}%."
                if (bt.get("by_method") or {}).get("blend_seasonal_trend")
                else ""
            )
        )

    # Cliff + daily budget
    st.markdown("### 100 / 200 యూనిట్ల బండ · రోజువారీ బడ్జెట్")
    bud = model["budget"]
    cliff_html = (
        f'<div class="card" data-testid="cliff-card">'
        f'<div class="formula">వచ్చే 30 రోజుల్లో 100 యూనిట్ల లోపు ఉండాలంటే రోజుకు '
        f'<b>{bud["budget_100"]:.2f}</b> యూనిట్లు; 200 లోపు ఉండాలంటే రోజుకు '
        f'<b>{bud["budget_200"]:.2f}</b> యూనిట్లు.</div>'
        f'<div class="formula" style="margin-top:.5rem">{GRUHA_JYOTHI_NOTE_TE}</div>'
    )
    if model.get("cliff_text"):
        cliff_html += f'<div class="formula" style="margin-top:.5rem">{model["cliff_text"]}</div>'
    elif fc and fc["likely"] >= 85:
        if fc["high"] >= 200:
            cliff_html += (
                f'<div class="formula" style="margin-top:.5rem">అంచనా పై హద్దు {fc["high"]:g} — '
                f"200 బండ దాటే అవకాశం ఉంది.</div>"
            )
        elif fc["low"] <= 100 < fc["high"]:
            cliff_html += (
                f'<div class="formula" style="margin-top:.5rem">అంచనా 100 బండ దగ్గరగా ఉంది '
                f"({fc['low']:g}–{fc['high']:g}).</div>"
            )
        else:
            cliff_html += '<div class="formula" style="margin-top:.5rem">ఈ బిల్లు 15 యూనిట్ల బండ లోపు లేదు.</div>'
    cliff_html += "</div>"
    st.markdown(cliff_html, unsafe_allow_html=True)

    # DPS / due-date tip
    st.markdown("### డ్యూ డేట్ · ఆలస్య చెల్లింపు సర్‌ఛార్జ్ (DPS)")
    dps = delayed_payment_surcharge(bill.get("units"), bill.get("category"))
    sur = bill.get("surcharge")
    dps_html = (
        f'<div class="card" data-testid="dps-card">'
        f'<div class="formula">డ్యూ డేట్ లోపల కడితే DPS ఆదా అవుతుంది: '
        f"Cat 1A (100 యూనిట్లు లోపు)కి నెలకు <b>₹10</b>, "
        f"Cat 1Bకి నెలకు <b>₹25</b>. "
        f"మీ కేటగిరీకి ఇప్పుడు ₹{dps:.0f}. "
        "ఇది ఆలస్య చెల్లింపు రుసుము, ఈ నెల వాడకం కాదు. "
        "వచ్చే నెల అంచనాలో DPS లేదు — సమయానికి చెల్లిస్తారని అనుకున్నాం.</div>"
    )
    if sur is not None and float(sur) != 0:
        dps_html += (
            f'<div class="formula" style="margin-top:.5rem">'
            f"ఈ బిల్లులో సర్‌ఛార్జ్ {_inr(float(sur))} కనిపిస్తోంది — "
            "అది DPS (డ్యూ డేట్ తర్వాత చెల్లింపు).</div>"
        )
    dps_html += "</div>"
    st.markdown(dps_html, unsafe_allow_html=True)

    # True-up
    st.markdown("### True-up / PP TRUEUP")
    st.markdown(
        f'<div class="card" data-testid="trueup-card"><div class="formula">'
        + model["trueup_text"].replace("\n\n", "<br><br>")
        + "</div></div>",
        unsafe_allow_html=True,
    )

    # ACD
    if model.get("acd_text"):
        st.markdown("### ACD (సెక్యూరిటీ డిపాజిట్)")
        st.markdown(
            f'<div class="card" data-testid="acd-card"><div class="formula">{model["acd_text"]}</div></div>',
            unsafe_allow_html=True,
        )

    # Action bar
    st.markdown("### తర్వాత ఏం చేయొచ్చు")
    wa = whatsapp_link(model["wa_text"])
    # Guard encoded length moderately
    a1, a2 = st.columns([2, 1])
    with a1:
        st.markdown(
            f'<a href="{wa}" target="_blank" rel="noopener" data-testid="whatsapp-link" '
            f'style="display:inline-block;background:#128C7E;color:#fff;padding:.55rem 1rem;'
            f'border-radius:10px;text-decoration:none;font-weight:600;">WhatsApp కి పంపండి</a>',
            unsafe_allow_html=True,
        )
        st.caption("మీరే కాంటాక్ట్ ఎంచుకుని Send నొక్కాలి. టెక్స్ట్ మాత్రమే.")
    with a2:
        st.markdown("**ఇది ఉపయోగపడిందా?**")
        fb = load_feedback()
        b1, b2 = st.columns(2)
        if b1.button("అవును", key="fb_yes"):
            fb["yes"] += 1
            save_feedback(fb["yes"], fb["no"])
            st.rerun()
        if b2.button("కాదు", key="fb_no"):
            fb["no"] += 1
            save_feedback(fb["yes"], fb["no"])
            st.rerun()
        st.caption(f"అవును {fb['yes']} · కాదు {fb['no']} (ఈ పరికరం మీద మాత్రమే)")

    if st.checkbox("1912 / CSC ఫిర్యాదు డ్రాఫ్ట్ చూపించు", key="show_complaint"):
        st.text_area("కాపీ చేసుకోండి", model["complaint"], height=120, key="complaint_box")
        st.markdown("[1912 కి కాల్ చేయండి](tel:1912)")

    st.markdown(
        '<div class="privacy" data-testid="privacy-note">'
        "గోప్యత: బిల్లు ఫోటోను మేము సేవ్ చేయం, USC/పేరు స్క్రీన్‌పై దాచబడతాయి. "
        "చదవడానికి ఫోటో NVIDIA Visionకి వెళ్తుంది. ఈ పరికరంపై హాష్ కాష్ వేగం కోసం మాత్రమే; "
        "మీ ఫీడ్‌బ్యాక్ కౌంటర్ స్థానిక ఫైలులో ఉంటుంది. క్లౌడ్‌లో బిల్లు నిల్వ ఉండదు.</div>",
        unsafe_allow_html=True,
    )
