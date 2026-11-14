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
    SCHEMA_BLOCK,
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
    format_nvidia_user_message,
    NIM_TIMEOUT,
    NIM_MODEL,
    NIM_FALLBACK_MODEL,
)
from scenarios import get_scenario
from voice import render_voice_note
from discom_dashboard import render_discom_dashboard
from share_card import render_share_tab
from tariff import estimate_next_with_trueup
from draft_features import trueup_explainer, jump_card_text, cliff_card_text
from demo_data import lakshmi_demo_bundle
from terms import t
from citizen_ui import (
    render_main_understand,
    render_comparison_section,
    render_estimate_section,
    render_calculation_section,
    render_suggestions_section,
)
from history_input import (
    MAX_PAST_BILLS, bill_to_history_row, parse_manual_rows,
    merge_history_rows, parse_history_table_payload,
)
from dashboard import build_dashboard_model, render_dashboard, CSS

# -----------------------------------------------------------------------------
# NVIDIA NIM vision
# -----------------------------------------------------------------------------
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MAX_SIDE = 1600

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
    """Short structured Telugu. Never include name, USC, address, or meter readings."""
    from share_card import short_share_text
    return short_share_text(b, include_link=False)


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
                    render_user_error("గత బిల్లు చదవడం కాలేదు.\nPrevious-bill extraction failed.", tech=str(e)[:200])
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


def render_user_error(msg: str, tech: Optional[str] = None) -> None:
    """Telugu first, then English; any leftover technical detail as small text."""
    parts = [p.strip() for p in (msg or "").splitlines() if p.strip()]
    main = "\n\n".join(parts[:2]) if parts else (msg or "")
    st.error(main)
    detail = tech or (" ".join(parts[2:]) if len(parts) > 2 else None)
    if detail:
        st.caption(detail)


def _missing_key_message() -> None:
    render_user_error(
        "NVIDIA_API_KEY లేదు. డెమో మోడ్ (?demo=1) కీ లేకుండా పనిచేస్తుంది. "
        "అసలు ఫోటో చదవడానికి Streamlit secrets లేదా envలో కీ పెట్టండి.\n"
        "API key is not configured. Demo mode works without a key."
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
                        if getattr(e, "kind", None) == "missing_key" or "NVIDIA_API_KEY missing" in str(e):
                            _missing_key_message()
                            break
                        errors.append(f"{f.name}: {format_nvidia_user_message(e)}")
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
                    if getattr(e, "kind", None) == "missing_key" or "NVIDIA_API_KEY missing" in str(e):
                        _missing_key_message()
                    else:
                        render_user_error(format_nvidia_user_message(e))

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



def _result_from_scenario(key: str, use_sarvam: bool = False) -> Dict[str, Any]:
    """Build a dashboard result from a tariff-computed sample scenario. No NVIDIA call."""
    sc = get_scenario(key)
    bill = sc["bill"]
    prev = sc.get("prev_bill")
    checks = run_all_checks(bill)
    telugu = sc["telugu"]
    est = estimate_next_bill_from_actual(bill)
    model = build_dashboard_model(bill, prev, checks)
    return {
        "bill": bill,
        "prev_bill": prev,
        "corrections": [],
        "guard": None,
        "checks": checks,
        "telugu": telugu,
        "src": "scenario",
        "est": est,
        "kept_attempt": None,
        "attempts_used": 0,
        "attempts": [],
        "from_cache": False,
        "demo": True,
        "scenario": sc["id"],
        "display_name": sc["title_te"],
        "label": sc["label"],
        "model": model,
        "english": sc.get("english"),
    }



def _ingest_uploaded_bill(uploaded, use_sarvam: bool):
    """Run the same extract → explain → estimate path as the red Read button."""
    if uploaded is None:
        st.warning("దయచేసి ముందు బిల్లు ఫోటో అప్‌లోడ్ చేయండి.")
        return None
    img = Image.open(uploaded)
    with st.spinner("బిల్లు చదువుతున్నాం..."):
        if not nvidia_key_configured():
            _missing_key_message()
            return None
        try:
            pipe = extract_bill_pipeline_cached(img, use_cache=True)
        except Exception as e:
            if getattr(e, "kind", None) == "missing_key" or "NVIDIA_API_KEY missing" in str(e):
                _missing_key_message()
            else:
                render_user_error(format_nvidia_user_message(e))
            st.session_state["result"] = None
            return None
    bill = pipe["bill"]
    guard = pipe.get("guard")
    telugu, src = (None, None)
    est = None
    model = None
    if not guard:
        telugu, src = explain_bill(bill, use_sarvam=bool(use_sarvam))
        est = estimate_next_bill_from_actual(bill)
        prev_bill = (st.session_state.get("prev_result") or {}).get("bill")
        model = build_dashboard_model(
            bill, prev_bill, pipe.get("checks"),
            extra_history=st.session_state.get("user_history_rows") or None,
        )
    result = {
        "bill": bill,
        "prev_bill": (st.session_state.get("prev_result") or {}).get("bill"),
        "corrections": pipe.get("corrections") or [],
        "guard": guard,
        "checks": pipe.get("checks"),
        "telugu": telugu,
        "src": src,
        "est": est,
        "kept_attempt": pipe.get("kept_attempt"),
        "kept_model": pipe.get("kept_model"),
        "attempts_used": pipe.get("attempts_used"),
        "attempts": pipe.get("attempts"),
        "from_cache": pipe.get("from_cache"),
        "demo": False,
        "model": model,
    }
    st.session_state["result"] = result
    return result


def render_citizen_tab(demo: bool, use_sarvam: bool) -> None:
    uploaded = None
    from share_card import render_inline_share, share_button_plan
    existing = st.session_state.get("result") or {}
    has_result = bool(existing.get("bill")) and not existing.get("guard")
    if not demo:
        uploaded = st.file_uploader(
            t("upload_label"),
            type=["jpg", "jpeg", "png"],
            key="bill_upload",
        )
        st.caption(t("upload_hint"))
        c1, c2 = st.columns(2)
        with c1:
            clicked = st.button(
                t("upload_button"),
                type="primary",
                icon="📄",
                disabled=uploaded is None,
                width="stretch",
                key="read_bill_btn",
            )
        with c2:
            wa_clicked = st.button(
                "WhatsApp కి పంపండి",
                icon="📲",
                disabled=(uploaded is None and not has_result),
                width="stretch",
                key="wa_send_top",
            )
        plan = share_button_plan(
            uploaded is not None,
            has_result,
            wa_clicked=bool(wa_clicked),
            read_clicked=bool(clicked),
        )
        if plan == "need_photo":
            st.warning("దయచేసి ముందు బిల్లు ఫోటో అప్‌లోడ్ చేయండి.")
        elif plan in ("read_only", "read_then_share"):
            result = _ingest_uploaded_bill(uploaded, use_sarvam)
            if result is not None and not result.get("guard") and plan == "read_then_share":
                st.session_state["share_now"] = True
            elif result is not None and result.get("guard"):
                st.session_state["share_now"] = False
        elif plan == "share_only":
            st.session_state["share_now"] = True
    else:
        st.caption("డెమో మోడ్ ఆన్ — అసలు బిల్లు ఫోటో అవసరం లేదు, NVIDIA కాల్ లేదు, PII లేదు.")
        c1, c2 = st.columns(2)
        with c1:
            st.button(
                t("upload_button"),
                type="primary",
                icon="📄",
                disabled=True,
                width="stretch",
                key="read_bill_demo",
            )
        with c2:
            wa_clicked = st.button(
                "WhatsApp కి పంపండి",
                icon="📲",
                width="stretch",
                key="wa_send_demo",
            )
        if wa_clicked:
            st.session_state["share_now"] = True

    result = st.session_state.get("result")
    if st.session_state.get("share_now") and result and not result.get("guard"):
        render_inline_share(result)
    if not result:
        with st.expander(t("try_sample"), expanded=False):
            st.caption("రూపాయలు tariff.py లెక్కిస్తుంది — హార్డ్‌కోడ్ కాదు. నమూనా డేటా, నిజమైన కన్స్యూమర్ కాదు.")
            c1, c2, c3 = st.columns(3)
            for col, key in ((c1, "A"), (c2, "B"), (c3, "C")):
                sc = get_scenario(key)
                if col.button(sc["title_te"], key=f"citizen_sc_{key}"):
                    st.session_state["result"] = _result_from_scenario(key, use_sarvam)
                    st.session_state["prev_result"] = None
                    st.rerun()
        if not demo and uploaded is None:
            st.info("స్పష్టమైన బిల్లు ఫోటో అప్‌లోడ్ చేయండి, ఒక నమూనా నొక్కండి, లేదా సైడ్‌బార్‌లో డెమో మోడ్ ఆన్ చేయండి.")
        return

    if result.get("scenario"):
        st.caption(result.get("label") or "SAMPLE / one-click scenario")
        st.caption(f"సీనారియో: {result.get('display_name')}")
    elif result.get("demo"):
        st.caption(f"డెమో: {result.get('display_name') or 'లక్ష్మి (డెమో)'} — USC / చిరునామా / ఫోన్ లేవు.")

    if result.get("guard"):
        render_user_error(str(result["guard"]))
        return

    model = result.get("model")
    if model is None:
        model = build_dashboard_model(result["bill"], result.get("prev_bill"), result.get("checks"))
        result["model"] = model

    tab_u, tab_c, tab_e, tab_h, tab_s = st.tabs([
        t("nav_understand"),
        t("nav_compare"),
        t("nav_estimate"),
        t("nav_calculated"),
        t("nav_suggestions"),
    ])
    with tab_u:
        render_main_understand(model, corrections=result.get("corrections"))
        st.markdown(
            '<div class="privacy" data-testid="privacy-note">'
            "గోప్యత: బిల్లు ఫోటోను మేము సేవ్ చేయం, USC/పేరు స్క్రీన్‌పై దాచబడతాయి. "
            "చదవడానికి ఫోటో NVIDIA Visionకి వెళ్తుంది.</div>",
            unsafe_allow_html=True,
        )
    with tab_c:
        render_comparison_section(model)
        if not result.get("demo"):
            render_history_collectors(result)
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
                with st.spinner("గత బిల్లు చదువుతున్నాం..."):
                    try:
                        pipe = extract_bill_pipeline_cached(img, use_cache=True)
                        st.session_state["prev_result"] = pipe
                        result["prev_bill"] = pipe.get("bill")
                        result["model"] = build_dashboard_model(
                            result["bill"], pipe.get("bill"), result.get("checks")
                        )
                        st.session_state["result"] = result
                        st.rerun()
                    except Exception as e:
                        if getattr(e, "kind", None) == "missing_key" or "NVIDIA_API_KEY missing" in str(e):
                            _missing_key_message()
                        else:
                            render_user_error(format_nvidia_user_message(e))
    with tab_e:
        render_estimate_section(model)
    with tab_h:
        render_calculation_section(
            model,
            corrections=result.get("corrections"),
            result=result,
            telugu=result.get("telugu") or "",
        )
    with tab_s:
        render_suggestions_section(model)

    # Keep photo preview and sample bills out of the way of the receipt.
    if uploaded is not None:
        with st.expander("ఫోటో ప్రివ్యూ దాచబడింది / preview hidden (PII)", expanded=False):
            st.caption("పేరు, ఫోన్, చిరునామా స్క్రీన్‌పై చూపించం.")
            st.write(f"File: {uploaded.name}")
    with st.expander(t("try_sample"), expanded=False):
        st.caption("రూపాయలు tariff.py లెక్కిస్తుంది — హార్డ్‌కోడ్ కాదు. నమూనా డేటా, నిజమైన కన్స్యూమర్ కాదు.")
        c1, c2, c3 = st.columns(3)
        for col, key in ((c1, "A"), (c2, "B"), (c3, "C")):
            sc = get_scenario(key)
            if col.button(sc["title_te"], key=f"citizen_sc_footer_{key}"):
                st.session_state["result"] = _result_from_scenario(key, use_sarvam)
                st.session_state["prev_result"] = None
                st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="మీ విద్యుత్ బిల్లు సహాయకుడు",
        page_icon="⚡",
        layout="wide",
    )

    # Query param demo=1 auto-loads PII-free Lakshmi data (for screenshots).
    # ?view=discom opens the pitch-only DISCOM dashboard.
    try:
        qp = st.query_params
        demo_q = str(qp.get("demo", "") or "").lower() in {"1", "true", "yes"}
        discom_q = str(qp.get("view", "") or "").lower() == "discom"
    except Exception:
        demo_q = False
        discom_q = False

    if "result" not in st.session_state:
        st.session_state["result"] = None
    if "prev_result" not in st.session_state:
        st.session_state["prev_result"] = None

    with st.sidebar:
        st.header(t("settings"))
        demo = st.checkbox(
            t("demo_mode"),
            value=demo_q,
            help="Ground-truth Lakshmi bills + synthetic 13-month history. No NVIDIA call.",
            key="demo_mode",
        )
        if "discom_officials_view" not in st.session_state:
            st.session_state["discom_officials_view"] = discom_q
        discom_mode = st.checkbox(
            "For DISCOM officials (pitch demo)",
            help="Concept dashboard for the TISC pitch — not shown as a consumer tab.",
            key="discom_officials_view",
        )
        use_sarvam = False
        with st.expander(t("technical"), expanded=False):
            use_sarvam = st.checkbox(
                "Use Sarvam for Telugu (optional, paid — leave OFF)",
                value=False,
                help="Falls back to template on error. Leave OFF unless Jay re-approves.",
                key="use_sarvam",
            )
            if not demo:
                st.caption("AI key: configured yes" if nvidia_key_configured() else "AI key: configured no")
            st.caption(
                f"Vision: `{NIM_MODEL}` · fallback `{NIM_FALLBACK_MODEL}` · "
                f"timeout {NIM_TIMEOUT}s · hash cache on"
            )
            result_side = st.session_state.get("result") or {}
            if result_side.get("from_cache"):
                st.caption("ఈ ఫోటో ఫలితం హాష్ కాష్ నుండి వచ్చింది (మళ్లీ NVIDIA కాల్ లేదు).")
            elif result_side.get("kept_attempt") and not result_side.get("demo"):
                kept_model = result_side.get("kept_model") or NIM_MODEL
                st.caption(
                    f"NVIDIA attempt kept: {result_side.get('kept_attempt')} of "
                    f"{result_side.get('attempts_used')} (model={kept_model})."
                )

    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="tisc-hero"><h1>⚡ {t("app_title")}</h1>'
        f"<p>{t('app_tagline')}</p></div>",
        unsafe_allow_html=True,
    )

    result = st.session_state.get("result")
    # Leaving demo clears the Lakshmi demo only; one-click scenarios stay.
    if not demo and result and result.get("demo") and not result.get("scenario"):
        st.session_state["result"] = None
        result = None
    if demo and (result is None or (not result.get("demo") and not result.get("scenario"))):
        st.session_state["result"] = _demo_result()
        st.session_state["prev_result"] = None

    if discom_mode:
        st.caption("For DISCOM officials (pitch demo) — Demo / Concept, not an official TGSPDCL service.")
        render_discom_dashboard()
        return

    tab_citizen, tab_share = st.tabs(
        [t("tab_citizen"), t("tab_whatsapp")]
    )
    with tab_citizen:
        render_citizen_tab(demo, use_sarvam)
    with tab_share:
        from share_card import render_share_tab as _render_share_tab
        def _try_demo():
            st.session_state["result"] = _demo_result()
            st.session_state["prev_result"] = None
            st.rerun()
        _render_share_tab(st.session_state.get("result"), on_try_demo=_try_demo)

    st.markdown(
        '<div class="tisc-footer">Demo / Concept – not an official TGSPDCL service</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
