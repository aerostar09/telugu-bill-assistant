"""DRAFT feature copy + payloads for the jump / true-up / cliff section.

Keep this modular: the main extract → explain → estimate flow does not depend
on it. Streamlit rendering stays in app_nvidia.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from tariff import (
    jump_breakdown,
    check_jump_breakdown,
    cliff_warning,
    estimate_next_with_trueup,
    trueup_rate_for_bill_date,
    trueup_rate_for_next_bill,
    infer_category,
)


def _inr(n: Optional[float]) -> str:
    if n is None:
        return "—"
    sign = "+" if n > 0.005 else ""
    return f"{sign}₹{n:,.2f}"


def trueup_explainer(bill: Dict[str, Any]) -> str:
    tu = bill.get("trueup_charges")
    tu_u = bill.get("trueup_units")
    rate = trueup_rate_for_bill_date(bill.get("bill_date"))
    next_rate = trueup_rate_for_next_bill(bill.get("bill_date"))
    lines = [
        "ఈ True-up / PP TRUEUP ఈ నెల వాడిన యూనిట్లపై కాదు. "
        "2022-23 లో DISCOM కి ఎక్కువైన పవర్ కాస్ట్‌ను ఇప్పుడు కొంచెం కొంచెం వసూలు చేస్తున్నారు.",
    ]
    if tu_u and tu is not None and float(tu) > 0:
        lines.append(
            f"మీ బిల్లులో FY 2022-23 యూనిట్లు {float(tu_u):g}. "
            f"ఈ నెల రేటు యూనిట్‌కు {int(rate*100)} పైసలు → ₹{float(tu):.2f}."
        )
    elif not tu or float(tu or 0) == 0:
        lines.append("ఈ బిల్లులో True-up లైన్ లేదు (లేదా ₹0).")
    lines.append(
        f"వచ్చే నెల నుండి రేటు యూనిట్‌కు {int(next_rate*100)} పైసలు అవుతుంది"
        + (f" ({float(tu_u):g} × ₹{next_rate:.2f} = ₹{float(tu_u)*next_rate:.2f})." if tu_u else ".")
    )
    lines.append(
        "ఇల్లు అద్దెకు ఉంటే: ఈ ఛార్జీ కనెక్షన్ / సర్వీస్ నంబర్‌కు వస్తుంది. "
        "యజమాని–అద్దెదారు మధ్య ఎవరు చెల్లించాలో మీ అద్దె ఒప్పందం బట్టి నిర్ణయించుకోండి."
    )
    return "\n\n".join(lines)


def jump_card_text(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not curr.get("bill_amount") and not curr.get("units"):
        return None
    if not prev or prev.get("units") is None and prev.get("bill_amount") is None:
        return None
    br = jump_breakdown(prev, curr)
    chk = check_jump_breakdown(br)
    if br.get("difference") is None:
        return {"breakdown": br, "check": chk, "paragraphs": []}
    d = br["difference"]
    direction = "పెరిగింది" if d >= 0 else "తగ్గింది"
    paras = [
        f"గత బిల్లు ₹{br['prev_total']:,.2f} నుండి ఈ నెల ₹{br['curr_total']:,.2f} "
        f"— {direction} {_inr(d).replace('+','')} "
        f"({br['prev_units']:g} → {br['curr_units']:g} యూనిట్లు, "
        f"{br['prev_category']} → {br['curr_category']}).",
        f"అదనపు యూనిట్లు పాత కేటగిరీ రేటుతో: {_inr(br['extra_units_old_rate'])}.",
    ]
    if abs(br["category_change"]) > 0.005:
        paras.append(
            f"కేటగిరీ మార్పు (అన్ని యూనిట్లు కొత్త స్లాబ్‌లోకి): {_inr(br['category_change'])}."
        )
    if abs(br["trueup_added"]) > 0.005:
        paras.append(f"True-up జోడింపు: {_inr(br['trueup_added'])}.")
    if abs(br["other_changes"]) > 0.005:
        parts = ", ".join(f"{k} {_inr(v)}" for k, v in (br.get("other_parts") or {}).items() if abs(v) > 0.005)
        paras.append(f"ఫిక్స్‌డ్ / కస్టమర్ / డ్యూటీ / ఇతర మార్పులు: {_inr(br['other_changes'])} ({parts}).")
    if br["residual"] is not None and abs(br["residual"]) > 0.005:
        why = "గత బిల్లు లైన్‌లు టారిఫ్ నుండి లెక్కించినవి" if br.get("prev_computed_from_tariff") else "రౌండింగ్ / మిగిలిన తేడా"
        paras.append(f"మిగిలిన తేడా (residual, {why}): {_inr(br['residual'])}.")
    if not chk.get("ok"):
        paras.append("హెచ్చరిక: భాగాల మొత్తం బిల్లు తేడాకు సరిపోలలేదు.")
    return {"breakdown": br, "check": chk, "paragraphs": paras}


def cliff_card_text(bill: Dict[str, Any]) -> Optional[str]:
    w = cliff_warning(bill)
    if not w:
        return None
    if w.get("approaching"):
        return (
            f"మీ వాడకం {w['threshold']} యూనిట్ల బండకు దగ్గరగా ఉంది "
            f"(ఇంకా {w.get('units_headroom'):g} యూనిట్లు మిగిలాయి). "
            f"దాటితే {w['from_category']} నుండి {w['to_category']} స్లాబ్‌కు వెళ్తారు, బిల్లు ఒక్కసారిగా పెరగవచ్చు."
        )
    return (
        f"{w['units_to_cut']:g} యూనిట్లు తగ్గిస్తే ( {w['threshold']} లోపు ఉంచితే ) "
        f"సుమారు ₹{w['save_inr']:,.2f} ఆదా కావచ్చు "
        f"({w['from_category']} → {w['to_category']}). ఇది అంచనా మాత్రమే."
    )
