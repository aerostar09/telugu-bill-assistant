"""
Telugu Electricity Bill Assistant — NVIDIA NIM vision MVP (TISC #13)
----------------------------------------------------------------------
Flow: upload photo → NVIDIA extract → self-checks → Telugu explanation → anchana estimate.

Requires:
  pip install streamlit pillow requests
  env: NVIDIA_API_KEY
  optional: SARVAM_API_KEY (Telugu LLM; default OFF after test failures — toggle in sidebar)

Run:
  streamlit run app_nvidia.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests
import streamlit as st
from PIL import Image

from self_checks import (
    IMPROVED_VISION_PROMPT,
    run_self_checks,
    estimate_next_bill_from_actual,
    image_guard,
    check_jump_sum,
    run_all_checks,
)
from post_ocr import apply_post_ocr_corrections
from nvidia_pipeline import (
    extract_bill_pipeline,
    extract_bill_pipeline_cached,
    extract_history_table_pipeline,
    nvidia_key_configured,
)
from tariff import estimate_next_with_trueup
from draft_features import trueup_explainer, jump_card_text, cliff_card_text
from demo_data import lakshmi_demo_bundle
from history_input import (
    MAX_PAST_BILLS, bill_to_history_row, parse_manual_rows,
    merge_history_rows, parse_history_table_payload,
)
from dashboard import build_dashboard_model, render_dashboard, CSS

# -----------------------------------------------------------------------------
# NVIDIA NIM vision
# -----------------------------------------------------------------------------
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "meta/llama-3.2-90b-vision-instruct"
NIM_TIMEOUT = 45
MAX_SIDE = 1600

SCHEMA_BLOCK = """
Return ONLY a single JSON object (no markdown fences) with exactly these keys.
Use null for any field that is not clearly readable — do NOT guess or invent.
{
  "discom": string|null,
  "usc_no": string|null,
  "category": string|null,
  "contracted_load_kw": number|null,
  "phase": string|null,
  "bill_date": string|null,
  "prev_reading": number|null,
  "present_reading": number|null,
  "units": number|null,
  "days": number|null,
  "energy_charges": number|null,
  "fixed_charges": number|null,
  "customer_charges": number|null,
  "electricity_duty": number|null,
  "interest_on_ed": number|null,
  "surcharge": number|null,
  "trueup_charges": number|null,
  "trueup_units": number|null,
  "fsa_fca": number|null,
  "subsidy": number|null,
  "adjustment": number|null,
  "loss_gain": number|null,
  "bill_amount": number|null,
  "arrears": number|null,
  "total_due": number|null,
  "due_date": string|null,
  "present_reading_date": string|null,
  "prev_reading_date": string|null,
  "average_month_units": number|null,
  "acd_due": number|null,
  "acd_surcharge": number|null,
  "unit_history": [{"year": number, "month": number, "units": number, "estimated": boolean}]|null,
  "is_electricity_bill": boolean,
  "image_quality": "clear"|"cropped"|"crumpled"|"blurry"|"unknown"
}
Ignore handwritten notes scribbled on the form.
""".strip()

VISION_PROMPT = IMPROVED_VISION_PROMPT + "\n\n" + SCHEMA_BLOCK


def _downscale_jpeg(img: Image.Image, max_side: int = MAX_SIDE) -> bytes:
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def _parse_json_loose(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def extract_bill_nvidia(img: Image.Image) -> Dict[str, Any]:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY missing")
    jpeg = _downscale_jpeg(img)
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    payload = {
        "model": NIM_MODEL,
        "temperature": 0,
        "top_p": 0.1,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    last_err: Optional[str] = None
    for _attempt in (1, 2):
        try:
            resp = requests.post(NIM_URL, headers=headers, json=payload, timeout=NIM_TIMEOUT)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            content = body["choices"][0]["message"].get("content")
            if content is None:
                raise RuntimeError("empty model content")
            if isinstance(content, list):
                content = "".join(
                    (p.get("text") or "") if isinstance(p, dict) else str(p) for p in content
                )
            return _parse_json_loose(content)
        except Exception as e:
            last_err = str(e)
            time.sleep(1.0)
    raise RuntimeError(last_err or "NVIDIA extract failed")


# -----------------------------------------------------------------------------
# Template Telugu explanation (borrowed style from Grok Build describeBill)
# -----------------------------------------------------------------------------
def _inr(n: Optional[float]) -> str:
    if n is None:
        return "కనిపించలేదు"
    return "₹" + format(float(n), ",.2f")


def generate_telugu_explanation_template(b: Dict[str, Any]) -> str:
    units = b.get("units")
    days = b.get("days")
    prev_r = b.get("prev_reading")
    pres_r = b.get("present_reading")
    energy = b.get("energy_charges")
    fixed = b.get("fixed_charges")
    cust = b.get("customer_charges")
    duty = b.get("electricity_duty")
    trueup = b.get("trueup_charges")
    trueup_u = b.get("trueup_units")
    fsa = b.get("fsa_fca") or 0
    total = b.get("bill_amount")
    due = b.get("due_date") or "కనిపించలేదు"
    # Do not echo the consumer / USC number (PII) in the spoken explanation.
    usc = "దాచబడింది" if b.get("usc_no") else "కనిపించలేదు"

    lines = []
    if units is not None:
        day_bit = f" ({days} రోజులలో)" if days else ""
        meter_bit = ""
        if prev_r is not None and pres_r is not None:
            meter_bit = f" మీటర్ {int(prev_r)} నుండి {int(pres_r)}కు పెరిగింది."
        lines.append(f"ఈ నెల బిల్లులో{day_bit} {units:g} యూనిట్లు వాడారు.{meter_bit}")
    else:
        lines.append("యూనిట్ల సంఖ్య బిల్లు ఫోటోలో స్పష్టంగా కనిపించలేదు.")

    lines.append(
        f"కరెంట్ ఛార్జీ {_inr(energy)}. ఫిక్స్‌డ్ ఛార్జీ {_inr(fixed)}. "
        f"కస్టమర్ ఛార్జీ (నెలవారీ సర్వీస్ ఫీ) {_inr(cust)}. "
        f"ఎలక్ట్రిసిటీ డ్యూటీ (ప్రభుత్వానికి పన్ను) {_inr(duty)}."
    )
    if fsa and float(fsa) > 0:
        lines.append(f"ఇంధన ధర సర్దుబాటు (FSA/FCA) {_inr(float(fsa))}.")

    if trueup is not None and float(trueup) > 0:
        u_bit = f" ({trueup_u:g} యూనిట్లు)" if trueup_u is not None else ""
        lines.append(
            f"PP TRUEUP / True-up{u_bit}: {_inr(float(trueup))} — "
            "ఇది 2022-23 లో DISCOM కి ఎక్కువైన పవర్ కాస్ట్, ఇప్పుడు కొంచెం కొంచెం వసూలు చేస్తున్నారు."
        )

    lines.append(
        f"సర్వీస్ నంబర్ {usc}. చెల్లించవలసిన మొత్తం {_inr(total)}. చివరి తేదీ {due}."
    )

    if units is not None and float(units) > 200:
        lines.append(
            "చిన్న చిట్కా: గృహ జ్యోతి ఉచిత 200 యూనిట్లు కేవలం అర్హులైన లబ్ధిదారులకు. "
            "200 దాటితే అర్హులైనా మొత్తం బిల్లు వస్తుంది (మిగిలిన యూనిట్లు మాత్రమే కాదు). "
            "ఏసీని 24°C–26°C వద్ద ఉంచండి."
        )
    elif units is not None and float(units) > 100:
        lines.append(
            "చిన్న చిట్కా: గృహ జ్యోతి అర్హులైతే 200 యూనిట్లు దాటవద్దు — "
            "దాటితే మొత్తం బిల్లు వసూలు అవుతుంది. అర్హత లేనివారు 200 లోపు ఉన్నా సాధారణ టారిఫ్ చెల్లిస్తారు. "
            "టీవీ/సెట్-టాప్ మెయిన్ స్విచ్ ఆఫ్ చేయండి."
        )
    else:
        lines.append(
            "చిన్న చిట్కా: మీ వాడకం అదుపులో ఉంది. LED బల్బులు / BLDC ఫ్యాన్లు కొనసాగించండి."
        )
    return "\n\n".join(lines)


# -----------------------------------------------------------------------------
# OPTIONAL Sarvam hook — NOT called unless sidebar toggle is ON.
# Test on 2026-11-10: 4/4 calls returned unusable content (parser/API shape).
# Default remains OFF; template is the reliable path until Jay re-approves.
# -----------------------------------------------------------------------------
SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-105b"


def generate_telugu_explanation_sarvam(b: Dict[str, Any]) -> str:
    """Optional Sarvam LLM explanation. Raises on failure so caller can fall back."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY missing")
    slim_keys = [
        "discom", "usc_no", "category", "contracted_load_kw", "prev_reading", "present_reading",
        "units", "days", "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
        "interest_on_ed", "surcharge", "trueup_charges", "trueup_units", "fsa_fca", "subsidy",
        "adjustment", "loss_gain", "bill_amount", "due_date",
    ]
    slim = {k: b.get(k) for k in slim_keys}
    prompt = f"""You are a friendly Telangana electricity bill guide.
Explain this bill in 5–6 short simple Telugu-script sentences for a non-technical person.
Rules:
- Use ONLY numbers that appear in the JSON. Do not invent any number.
- true-up / PP TRUEUP = "2022-23 లో DISCOM కి ఎక్కువైన పవర్ కాస్ట్, ఇప్పుడు కొంచెం కొంచెం వసూలు చేస్తున్నారు"
- customer charges = "నెలవారీ సర్వీస్ ఫీ"
- electricity duty (ED) = "ప్రభుత్వానికి పన్ను"
- End with ONE practical tip in Telugu.
- Telugu script only (numbers and ₹ OK).

Bill JSON:
{json.dumps(slim, ensure_ascii=False, indent=2)}
"""
    payload = {
        "model": SARVAM_MODEL,
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"api-subscription-key": key, "Content-Type": "application/json"}
    resp = requests.post(SARVAM_URL, headers=headers, json=payload, timeout=90)
    if resp.status_code >= 400:
        raise RuntimeError(f"Sarvam HTTP {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    # Defensive: content may be null, str, or list depending on API version
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        # some gateways put text under 'text' or refusal
        content = msg.get("text") or body.get("text")
    if isinstance(content, list):
        content = "".join(
            (p.get("text") or "") if isinstance(p, dict) else str(p) for p in content
        )
    if not content or not str(content).strip():
        raise RuntimeError(f"Sarvam empty content; keys={list(body.keys())}")
    return str(content).strip()


def explain_bill(b: Dict[str, Any], use_sarvam: bool) -> Tuple[str, str]:
    """Returns (text, source) where source is 'sarvam' or 'template'."""
    if use_sarvam:
        try:
            return generate_telugu_explanation_sarvam(b), "sarvam"
        except Exception as e:
            st.warning(f"Sarvam unavailable ({e}); using template Telugu.")
    return generate_telugu_explanation_template(b), "template"



def render_draft_section(curr_bill: Dict[str, Any]) -> None:
    """Modular DRAFT block: jump card, true-up, cliff, 50p estimate, optional prev bill.

    Does not replace the existing Telugu + anchana flow.
    Previous-bill NVIDIA extract runs only when the user clicks Compare.
    """
    st.divider()
    st.subheader("DRAFT — మీ బిల్లు ఎందుకు పెరిగింది?")
    st.caption(
        "Experimental section (Jay may change later). "
        "Existing extract → Telugu → anchana flow is unchanged. "
        "Tariff math is code, not an LLM."
    )

    st.markdown("##### True-up ఎందుకు వచ్చింది?")
    st.write(trueup_explainer(curr_bill))

    cliff = cliff_card_text(curr_bill)
    if cliff:
        st.markdown("##### స్లాబ్ బండ హెచ్చరిక")
        st.warning(cliff)

    st.markdown("##### వచ్చే నెల అంచనా (50 పైసల True-upతో)")
    est2 = estimate_next_with_trueup(curr_bill)
    if est2:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("అంచనా యూనిట్లు (30 రోజులు)", est2["est_units_30d"])
        c2.metric("అంచనా ఎనర్జీ", f"₹{est2['est_energy']:,.2f}")
        c3.metric(f"True-up ({int(est2['est_trueup_rate']*100)} పైసలు)", f"₹{est2['est_trueup']:,.2f}")
        c4.metric("అంచనా మొత్తం", f"₹{est2['est_total']:,.2f}")
        st.caption(est2["note"])
    else:
        st.info("యూనిట్లు/రోజులు లేనందున 50పైసల True-up అంచనా లెక్కించలేం.")

    st.markdown("##### గత నెల బిల్లు ఫోటో (ఐచ్ఛికం)")
    prev_up = st.file_uploader(
        "పోలిక కోసం గత బిల్లు ఫోటో (JPG/PNG) — లేకపోయినా పై వివరణలు కనిపిస్తాయి",
        type=["jpg", "jpeg", "png"],
        key="prev_bill_upload",
    )
    if prev_up is not None:
        with st.expander("Previous bill photo (PII hidden by default)", expanded=False):
            st.caption("Preview hidden to protect names, phones and addresses on the bill.")
            st.write(f"File: {prev_up.name}")

    if "prev_result" not in st.session_state:
        st.session_state["prev_result"] = None

    prev_clicked = st.button(
        "గత బిల్లుతో పోల్చండి / Compare previous bill",
        disabled=prev_up is None,
        key="compare_prev_bill",
    )
    if prev_clicked:
        if prev_up is None:
            st.warning("Please upload a previous bill photo first.")
        else:
            img = Image.open(prev_up)
            with st.spinner("NVIDIA Vision తో గత బిల్లు చదువుతున్నాం..."):
                try:
                    pipe = extract_bill_pipeline(img)
                    st.session_state["prev_result"] = pipe
                except Exception as e:
                    st.error(f"Previous-bill extraction failed: {e}")
                    st.session_state["prev_result"] = None

    prev_pipe = st.session_state.get("prev_result")
    prev_bill = (prev_pipe or {}).get("bill") if prev_pipe else None

    st.markdown("##### మీ బిల్లు ఎందుకు పెరిగింది?")
    if not prev_bill:
        st.info(
            "గత నెల బిల్లు ఫోటో ఇస్తే, పెరుగుదలను రూపాయి వారీగా చూపిస్తాం "
            "(అదనపు యూనిట్లు, కేటగిరీ మార్పు, True-up, ఇతర ఛార్జీలు, residual). "
            "ఒక్క బిల్లు ఉన్నా True-up, స్లాబ్ హెచ్చరిక, వచ్చే నెల అంచనా పైన కనిపిస్తాయి."
        )
        return

    if prev_pipe and prev_pipe.get("corrections"):
        st.caption("గత బిల్లు auto-correct: " + " | ".join(prev_pipe["corrections"]))

    card = jump_card_text(prev_bill, curr_bill)
    if not card:
        st.info("పోలికకు సరిపడా సంఖ్యలు లేవు.")
        return
    for para in card["paragraphs"]:
        st.write(para)

    br = card["breakdown"]
    rows = [
        {"భాగం": "అదనపు యూనిట్లు (పాత రేటు)", "₹": f"{br['extra_units_old_rate']:,.2f}"},
        {"భాగం": "కేటగిరీ మార్పు", "₹": f"{br['category_change']:,.2f}"},
        {"భాగం": "True-up జోడింపు", "₹": f"{br['trueup_added']:,.2f}"},
        {"భాగం": "ఫిక్స్‌డ్ / కస్టమర్ / ED / ఇతరం", "₹": f"{br['other_changes']:,.2f}"},
        {"భాగం": "Residual", "₹": f"{br['residual']:,.2f}"},
        {"భాగం": "మొత్తం తేడా", "₹": f"{br['difference']:,.2f}"},
    ]
    st.table(rows)

    chk = check_jump_sum(prev_bill, curr_bill)
    if chk.get("ok"):
        st.success(
            f"Self-check: breakdown sum == difference "
            f"(₹{chk['parts_plus_residual']:,.2f} = ₹{chk['difference']:,.2f})."
        )
    else:
        st.warning(
            "Self-check failed: భాగాల మొత్తం బిల్లు తేడాకు సరిపోలలేదు. "
            f"{chk}"
        )


# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------

def _init_history_state() -> None:
    if "user_history_rows" not in st.session_state:
        st.session_state["user_history_rows"] = []
    if "extracted_past_bills" not in st.session_state:
        st.session_state["extracted_past_bills"] = []


def _rebuild_model_with_history(result: Dict[str, Any]) -> Dict[str, Any]:
    rows = list(st.session_state.get("user_history_rows") or [])
    bill = result["bill"]
    result["model"] = build_dashboard_model(
        bill,
        result.get("prev_bill"),
        result.get("checks"),
        extra_history=rows or None,
    )
    return result


def _missing_key_message() -> None:
    st.error(
        "NVIDIA_API_KEY లేదు. డెమో మోడ్ (?demo=1) కీ లేకుండా పనిచేస్తుంది. "
        "అసలు ఫోటో చదవడానికి Streamlit secrets లేదా envలో కీ పెట్టండి."
    )


def render_history_collectors(result: Dict[str, Any]) -> None:
    """Past-bill photos (≤6), DISCOM history-table screenshot, or manual month/units."""
    _init_history_state()
    st.markdown("### గత నెలల చరిత్ర (అంచనా / చార్ట్ కోసం)")
    st.caption(
        "6 బిల్లు ఫోటోల వరకు, లేదా DISCOM యాప్ Bill History స్క్రీన్‌షాట్, లేదా మాన్యువల్ టేబుల్. "
        "మూలం 'Your bills' అవుతుంది. ఫోటో ప్రివ్యూ దాచబడుతుంది (PII)."
    )
    tab_photos, tab_table, tab_manual = st.tabs(
        ["గత బిల్లు ఫోటోలు (6 వరకు)", "DISCOM Bill History స్క్రీన్‌షాట్", "మాన్యువల్ నమోదు"]
    )

    with tab_photos:
        past = st.file_uploader(
            "గత బిల్లు ఫోటోలు (గరిష్ఠం 6)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="past_bills_multi",
        )
        if past and len(past) > MAX_PAST_BILLS:
            st.warning(f"మొదటి {MAX_PAST_BILLS} ఫోటోలు మాత్రమే వాడతాం.")
            past = past[:MAX_PAST_BILLS]
        if past:
            with st.expander("ఫైల్ పేర్లు (ప్రివ్యూ దాచబడింది)", expanded=False):
                for f in past:
                    st.write(f.name)
        if st.button("ఫోటోల నుండి చరిత్ర చదవండి", disabled=not past, key="extract_past_bills"):
            if not nvidia_key_configured():
                _missing_key_message()
            else:
                new_rows = []
                errors = []
                for f in past:
                    try:
                        img = Image.open(f)
                        with st.spinner(f"చదువుతున్నాం: {f.name}"):
                            pipe = extract_bill_pipeline_cached(img, use_cache=True)
                        bill = pipe.get("bill") or {}
                        row = bill_to_history_row(bill, source="bill_photo")
                        if row:
                            new_rows.append(row)
                        else:
                            errors.append(f"{f.name}: units/date కనిపించలేదు")
                    except Exception as e:
                        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                            errors.append(f"{f.name}: సర్వర్ నెమ్మదిగా ఉంది")
                        elif "NVIDIA_API_KEY missing" in str(e):
                            _missing_key_message()
                            break
                        else:
                            errors.append(f"{f.name}: {e}")
                if new_rows:
                    merged = merge_history_rows(st.session_state["user_history_rows"], new_rows)
                    st.session_state["user_history_rows"] = merged
                    st.session_state["extracted_past_bills"] = new_rows
                    st.success(f"{len(new_rows)} నెల(లు) చేర్చాం.")
                    result = _rebuild_model_with_history(st.session_state["result"])
                    st.session_state["result"] = result
                    st.rerun()
                for e in errors:
                    st.warning(e)

    with tab_table:
        hist_shot = st.file_uploader(
            "DISCOM యాప్ 'Bill History' టేబుల్ స్క్రీన్‌షాట్",
            type=["jpg", "jpeg", "png"],
            key="history_table_shot",
        )
        if hist_shot is not None:
            with st.expander("స్క్రీన్‌షాట్ (PII hidden)", expanded=False):
                st.caption("Preview hidden.")
                st.write(hist_shot.name)
        if st.button("టేబుల్ చదవండి", disabled=hist_shot is None, key="extract_hist_table"):
            if not nvidia_key_configured():
                _missing_key_message()
            else:
                try:
                    img = Image.open(hist_shot)
                    with st.spinner("Bill History చదువుతున్నాం..."):
                        out = extract_history_table_pipeline(img, use_cache=True)
                    rows = out.get("rows") or []
                    if not rows:
                        st.warning("పంక్తులు కనిపించలేదు. మరింత స్పష్టమైన స్క్రీన్‌షాట్ ఇవ్వండి.")
                    else:
                        merged = merge_history_rows(st.session_state["user_history_rows"], rows)
                        st.session_state["user_history_rows"] = merged
                        st.success(f"{len(rows)} నెల(లు) చేర్చాం.")
                        result = _rebuild_model_with_history(st.session_state["result"])
                        st.session_state["result"] = result
                        st.rerun()
                except Exception as e:
                    if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                        st.error("సర్వర్ నెమ్మదిగా ఉంది. దయచేసి కొద్ది సేపు తర్వాత మళ్లీ ప్రయత్నించండి.")
                    elif "NVIDIA_API_KEY missing" in str(e):
                        _missing_key_message()
                    else:
                        st.error(f"History table extraction failed: {e}")

    with tab_manual:
        import pandas as pd
        existing = st.session_state.get("user_history_rows") or []
        start = [
            {
                "month": f"{r['year']}-{int(r['month']):02d}" if r.get("year") else "",
                "units": r.get("units"),
                "amount": r.get("amount"),
            }
            for r in existing
        ]
        while len(start) < 6:
            start.append({"month": "", "units": None, "amount": None})
        edited = st.data_editor(
            pd.DataFrame(start),
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "month": st.column_config.TextColumn("నెల (2026-10 లేదా Oct 2026)"),
                "units": st.column_config.NumberColumn("యూనిట్లు", min_value=0, step=1),
                "amount": st.column_config.NumberColumn("బిల్లు ₹ (ఐచ్ఛికం)", min_value=0, step=1),
            },
            key="manual_history_editor",
        )
        if st.button("మాన్యువల్ చరిత్ర సేవ్ చేయండి", key="save_manual_history"):
            rows = parse_manual_rows(edited.to_dict("records"))
            st.session_state["user_history_rows"] = rows
            st.success(f"{len(rows)} నెల(లు) సేవ్ అయ్యాయి.")
            result = _rebuild_model_with_history(st.session_state["result"])
            st.session_state["result"] = result
            st.rerun()

    rows = st.session_state.get("user_history_rows") or []
    if rows:
        st.caption("ప్రస్తుతం ఉన్న చరిత్ర: " + ", ".join(
            f"{r['year']}-{int(r['month']):02d}={r['units']:g}" for r in rows
        ))
        if st.button("చరిత్ర క్లియర్ చేయండి", key="clear_history"):
            st.session_state["user_history_rows"] = []
            result = _rebuild_model_with_history(st.session_state["result"])
            st.session_state["result"] = result
            st.rerun()


def _demo_result():
    bundle = lakshmi_demo_bundle()
    bill = bundle["bill"]
    prev = bundle["prev_bill"]
    checks = run_all_checks(bill)
    telugu, src = explain_bill(bill, use_sarvam=False)
    est = estimate_next_bill_from_actual(bill)
    model = build_dashboard_model(bill, prev, checks)
    return {
        "bill": bill,
        "prev_bill": prev,
        "corrections": [],
        "guard": None,
        "checks": checks,
        "telugu": telugu,
        "src": src,
        "est": est,
        "kept_attempt": None,
        "attempts_used": 0,
        "attempts": [],
        "from_cache": False,
        "demo": True,
        "display_name": bundle["display_name"],
        "model": model,
    }


def main() -> None:
    st.set_page_config(
        page_title="మీ విద్యుత్ బిల్లు సహాయకుడు",
        page_icon="⚡",
        layout="wide",
    )

    # Query param demo=1 auto-loads PII-free Lakshmi data (for screenshots).
    try:
        qp = st.query_params
        demo_q = str(qp.get("demo", "") or "").lower() in {"1", "true", "yes"}
    except Exception:
        demo_q = False

    with st.sidebar:
        st.header("సెట్టింగ్స్")
        demo = st.checkbox(
            "డెమో మోడ్ (లక్ష్మి, PII లేదు)",
            value=demo_q,
            help="Ground-truth Lakshmi bills + synthetic 13-month history. No NVIDIA call.",
            key="demo_mode",
        )
        use_sarvam = st.checkbox(
            "Use Sarvam for Telugu (optional, paid)",
            value=False,
            help="Falls back to template on error. Leave OFF unless Jay re-approves.",
            key="use_sarvam",
        )
        st.caption(f"Vision: `{NIM_MODEL}` · timeout {NIM_TIMEOUT}s · hash cache on")

    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    st.markdown(
        '<div class="tisc-hero"><h1>⚡ మీ విద్యుత్ బిల్లు సహాయకుడు</h1>'
        "<p>TGSPDCL బిల్లు ఫోటో → చార్జీల వివరణ, ఎందుకు పెరిగింది, వచ్చే నెల అంచనా</p></div>",
        unsafe_allow_html=True,
    )

    if "result" not in st.session_state:
        st.session_state["result"] = None
    if "prev_result" not in st.session_state:
        st.session_state["prev_result"] = None

    if not demo and st.session_state.get("result") and st.session_state["result"].get("demo"):
        st.session_state["result"] = None
    if demo and (st.session_state.get("result") is None or not st.session_state["result"].get("demo")):
        st.session_state["result"] = _demo_result()
        st.session_state["prev_result"] = None

    uploaded = None
    if not demo:
        uploaded = st.file_uploader(
            "బిల్లు ఫోటో అప్‌లోడ్ చేయండి (JPG/PNG)",
            type=["jpg", "jpeg", "png"],
        )
        if uploaded is not None:
            with st.expander("Bill photo (PII hidden by default / ఫోటోలో వ్యక్తిగత వివరాలు ఉన్నాయి)", expanded=False):
                st.caption("Preview hidden to protect names, phones and addresses on the bill.")
                st.write(f"File: {uploaded.name}")

        clicked = st.button("🔍 బిల్లు వివరించండి", type="primary", disabled=uploaded is None)
        if clicked:
            if uploaded is None:
                st.warning("దయచేసి ముందు బిల్లు ఫోటో అప్‌లోడ్ చేయండి.")
                return
            img = Image.open(uploaded)
            with st.spinner("NVIDIA Vision తో చదువుతున్నాం..."):
                if not nvidia_key_configured():
                    _missing_key_message()
                    return
                try:
                    pipe = extract_bill_pipeline_cached(img, use_cache=True)
                except Exception as e:
                    err = str(e)
                    low = err.lower()
                    if "timeout" in low or "timed out" in low:
                        st.error("సర్వర్ నెమ్మదిగా ఉంది. దయచేసి కొద్ది సేపు తర్వాత మళ్లీ ప్రయత్నించండి.")
                    elif "NVIDIA_API_KEY missing" in err:
                        _missing_key_message()
                    else:
                        st.error(f"Extraction failed: {e}")
                    st.session_state["result"] = None
                    return
            bill = pipe["bill"]
            guard = pipe.get("guard")
            telugu, src = (None, None)
            est = None
            model = None
            if not guard:
                telugu, src = explain_bill(bill, use_sarvam=bool(use_sarvam))
                est = estimate_next_bill_from_actual(bill)
                prev_bill = (st.session_state.get("prev_result") or {}).get("bill")
                model = build_dashboard_model(bill, prev_bill, pipe.get("checks"), extra_history=st.session_state.get("user_history_rows") or None)
            st.session_state["result"] = {
                "bill": bill,
                "prev_bill": (st.session_state.get("prev_result") or {}).get("bill"),
                "corrections": pipe.get("corrections") or [],
                "guard": guard,
                "checks": pipe.get("checks"),
                "telugu": telugu,
                "src": src,
                "est": est,
                "kept_attempt": pipe.get("kept_attempt"),
                "attempts_used": pipe.get("attempts_used"),
                "attempts": pipe.get("attempts"),
                "from_cache": pipe.get("from_cache"),
                "demo": False,
                "model": model,
            }
    else:
        st.caption("డెమో మోడ్ ఆన్ — అసలు బిల్లు ఫోటో అవసరం లేదు, NVIDIA కాల్ లేదు, PII లేదు.")

    result = st.session_state.get("result")
    if not result:
        if not demo and uploaded is None:
            st.info("స్పష్టమైన బిల్లు ఫోటో అప్‌లోడ్ చేయండి, లేదా సైడ్‌బార్‌లో డెమో మోడ్ ఆన్ చేయండి.")
        return

    if result.get("demo"):
        st.caption(f"డెమో: {result.get('display_name') or 'లక్ష్మి (డెమో)'} — USC / చిరునామా / ఫోన్ లేవు.")
    elif result.get("from_cache"):
        st.caption("ఈ ఫోటో ఫలితం హాష్ కాష్ నుండి వచ్చింది (మళ్లీ NVIDIA కాల్ లేదు).")
    elif result.get("kept_attempt"):
        st.caption(
            f"NVIDIA attempt kept: {result.get('kept_attempt')} of {result.get('attempts_used')} "
            f"(temperature=0, top_p=0.1, timeout={NIM_TIMEOUT}s)."
        )

    if result.get("corrections"):
        st.info(
            "auto-correct chesam:\n\n- " + "\n- ".join(result["corrections"]),
            icon="🔧",
        )

    if result.get("guard"):
        st.error(result["guard"])
        with st.expander("Extracted JSON"):
            st.json(result["bill"])
        return

    model = result.get("model")
    if model is None:
        model = build_dashboard_model(result["bill"], result.get("prev_bill"), result.get("checks"))
        result["model"] = model

    render_dashboard(model)

    if result.get("demo"):
        st.caption("డెమో మోడ్‌లో చార్ట్ మూలం 'Demo data'. అసలు బిల్లులు జోడించాలంటే డెమో ఆఫ్ చేసి ఫోటో అప్‌లోడ్ చేయండి.")
    else:
        render_history_collectors(result)

    # Optional previous bill (non-demo) — rebuild jump after compare
    if not result.get("demo"):
        st.markdown("##### గత నెల బిల్లు ఫోటో (ఐచ్ఛికం)")
        prev_up = st.file_uploader(
            "పోలిక కోసం గత బిల్లు ఫోటో",
            type=["jpg", "jpeg", "png"],
            key="prev_bill_upload",
        )
        if prev_up is not None:
            with st.expander("Previous bill photo (PII hidden by default)", expanded=False):
                st.caption("Preview hidden to protect names, phones and addresses on the bill.")
                st.write(f"File: {prev_up.name}")
        prev_clicked = st.button(
            "గత బిల్లుతో పోల్చండి",
            disabled=prev_up is None,
            key="compare_prev_bill",
        )
        if prev_clicked and prev_up is not None:
            img = Image.open(prev_up)
            with st.spinner("NVIDIA Vision తో గత బిల్లు చదువుతున్నాం..."):
                try:
                    pipe = extract_bill_pipeline_cached(img, use_cache=True)
                    st.session_state["prev_result"] = pipe
                    result["prev_bill"] = pipe.get("bill")
                    result["model"] = build_dashboard_model(result["bill"], pipe.get("bill"), result.get("checks"))
                    st.session_state["result"] = result
                    st.rerun()
                except Exception as e:
                    if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                        st.error("సర్వర్ నెమ్మదిగా ఉంది. దయచేసి కొద్ది సేపు తర్వాత మళ్లీ ప్రయత్నించండి.")
                    else:
                        st.error(f"Previous-bill extraction failed: {e}")

    # Existing Telugu + rough anchana kept, collapsed so the dashboard leads.
    if st.checkbox("పాత టెంప్లేట్ తెలుగు వివరణ / rough anchana చూపించు", key="show_old_template"):
        st.caption(f"source: {result.get('src')}")
        telugu = result.get("telugu") or ""
        st.markdown(
            f'<div data-testid="telugu-explanation" style="background:#f0fdfa;border:1px solid #99f6e4;border-radius:12px;'
            f'padding:1.1rem 1.3rem;line-height:1.8;font-size:1.05rem">{telugu.replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )
        est = result.get("est")
        if est:
            c1, c2, c3 = st.columns(3)
            c1.metric("అంచనా యూనిట్లు (30 రోజులు)", est["est_units_30d"])
            c2.metric("అంచనా ఎనర్జీ", f"₹{est['est_energy']:,.2f}")
            c3.metric("అంచనా మొత్తం (rough)", f"₹{est['est_total_rough']:,.2f}")
            st.caption(est["note"])

    st.subheader("Extracted fields")
    bill = result["bill"]
    display_keys = [
        "discom", "category", "contracted_load_kw", "phase", "bill_date",
        "prev_reading", "present_reading", "prev_reading_date", "present_reading_date",
        "units", "days", "days_source",
        "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
        "interest_on_ed", "surcharge", "trueup_charges", "trueup_units",
        "fsa_fca", "subsidy", "adjustment", "loss_gain", "acd_due", "acd_surcharge",
        "average_month_units",
        "bill_amount", "bill_amount_printed", "total_due", "due_date",
    ]
    rows = []
    for k in display_keys:
        if k in bill and bill[k] is not None:
            rows.append({"Field": k, "Value": "" if bill[k] is None else str(bill[k])})
    if rows:
        st.table(rows)
    with st.expander("Raw JSON (USC / consumer number redacted)"):
        redacted = dict(bill)
        if redacted.get("usc_no"):
            redacted["usc_no"] = "••••••••"
        redacted.pop("unit_history", None)
        st.json(redacted)


if __name__ == "__main__":
    main()
