"""Citizen-page section renderers. Tariff math stays in tariff/forecast/dashboard."""
from __future__ import annotations

import html as _html
from typing import Any, Dict, List, Optional

from dashboard import _inr, _u, whatsapp_link, load_feedback, save_feedback
from history_input import GRUHA_JYOTHI_NOTE_TE
from tariff import delayed_payment_surcharge
from citizen_summary import (
    top_reasons,
    confidence_level,
    printed_vs_calculated,
    build_voice_summary,
)
from forecast import forecast_display_range, consumer_forecast_range, format_rupee_range
from terms import t, rupees_display, format_due_date_display, TARIFF_VERSION
from bill_lines import payable_amount
from gruha_jyothi import gj_zero_bill_active
from receipt_ui import render_receipt_card, render_units_bar, next_units_cliff

_CHECK_ICON = (
    '<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">'
    '<circle cx="14" cy="14" r="14" fill="#12B76A"/>'
    '<path d="M8.2 14.3l3.3 3.3 8-8" fill="none" stroke="#fff" stroke-width="2.4" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_WARN_ICON = (
    '<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">'
    '<circle cx="14" cy="14" r="14" fill="#DC6803"/>'
    '<path d="M14 8v7" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'
    '<circle cx="14" cy="19.2" r="1.3" fill="#fff"/></svg>'
)



_LEAF_ICON = (
    '<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">'
    '<path fill="#16a34a" d="M4 16c6-1 10-5 12-12-6 1-11 5-12 12z"/>'
    '<path fill="none" stroke="#0b5c3a" stroke-width="1.2" d="M5 15c3-3 6-6 10-10"/>'
    '</svg>'
)
_BOLT_ICON = (
    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">'
    '<path fill="#16a34a" d="M11.2 2.2L4.8 11h4.2L7.4 17.8 16 8.6h-4.3L11.2 2.2z"/></svg>'
)
_CAL_ICON = (
    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">'
    '<rect x="3" y="5" width="14" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/>'
    '<path d="M3 8.5h14" stroke="currentColor" stroke-width="1.5"/>'
    '<path d="M7 3.5v3M13 3.5v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    '</svg>'
)

RING_CAPTION = "యూనిట్లు / units"


def payable_size_class(display: str) -> str:
    """Keep the ₹ amount on one line at a 420px-wide bill tab."""
    n = len(display or "")
    if n >= 8:
        return "pay-long"
    if n >= 6:
        return "pay-mid"
    return ""


def bill_dashboard_view(
    model: Dict[str, Any],
    corrections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Layout-A / L6 numbers for the bill-tab hero. Pure, testable."""
    bill = model["bill"]
    conf = confidence_level(model.get("checks"), corrections, bill.get("image_quality"))
    units = bill.get("units")
    if units is None:
        units_label = "—"
    else:
        try:
            units_f = float(units)
            units_label = str(int(units_f)) if units_f.is_integer() else str(units_f)
        except (TypeError, ValueError):
            units_label = "—"
    due = format_due_date_display(bill.get("due_date"))
    if not due:
        due = "—"
    payable = payable_amount(bill)
    gj = model.get("gruha_jyothi") or {}
    if gj.get("mode") == "free" and gj.get("payable") is not None:
        payable = gj.get("payable")
    checks = model.get("checks") or {}
    ok = checks.get("consumer_ok")
    if ok is None:
        ok = checks.get("ok")
    if ok:
        banner_kind = "ok"
        banner_te = t("calc_matches")
    else:
        banner_kind = "bad"
        banner_te = checks.get("message_te") or t("calc_mismatch")
    payable_display = rupees_display(payable) if payable is not None else "—"
    theme = "gj" if gj_zero_bill_active(gj) else "regular"
    return {
        "units_label": units_label,
        "due": due,
        "payable": payable,
        "payable_display": payable_display,
        "pay_size": payable_size_class(payable_display),
        "conf": conf,
        "match_ok": bool(ok),
        "banner_kind": banner_kind,
        "banner_te": banner_te or "",
        "theme": theme,
        "show_scheme_pill": theme == "gj",
        "scheme_pill_te": t("scheme_applied_te") if theme == "gj" else "",
        "scheme_pill_en": t("scheme_applied_en") if theme == "gj" else "",
        "ring_caption": RING_CAPTION,
        "show_due_highlight": theme == "regular",
        "show_gj_tip": theme == "regular",
        "show_units_bar": theme == "gj",
    }


def dashboard_hero_html(view: Dict[str, Any]) -> str:
    """Design-1 bill-tab hero + tiles. Pure HTML, testable. No '/ 200' in the ring."""
    theme = view.get("theme") or "regular"
    pay_cls = "pay"
    if view.get("pay_size"):
        pay_cls += " " + view["pay_size"]
    pill = ""
    if view.get("show_scheme_pill"):
        pill = (
            f'<div class="scheme-pill" data-testid="scheme-pill">'
            f'<span class="scheme-ico">{_LEAF_ICON}</span>'
            f'<span class="scheme-copy"><b>{_html.escape(view.get("scheme_pill_te") or "")}</b>'
            f'<small>{_html.escape(view.get("scheme_pill_en") or "")}</small></span>'
            f"</div>"
        )
    conf = view.get("conf") or {}
    trust_bits = []
    if conf.get("show_on_hero") and conf.get("label_te"):
        css = _html.escape(conf.get("css") or "")
        trust_bits.append(
            f'<span class="trust-pill {css}" data-testid="confidence-pill">'
            f'{_html.escape(conf["label_te"])}</span>'
        )
    if view.get("banner_te"):
        kind = "ok" if view.get("banner_kind") == "ok" else "bad"
        trust_bits.append(
            f'<span class="trust-msg trust-{kind}" data-testid="trust-verdict">'
            f'{_html.escape(view["banner_te"])}</span>'
        )
    trust = ""
    if trust_bits:
        trust = f'<div class="d1-trust">{" · ".join(trust_bits)}</div>'
    due_cls = "d1-tile due due-hot" if view.get("show_due_highlight") else "d1-tile due"
    cap = view.get("ring_caption") or RING_CAPTION
    html = (
        f'<div class="d1-stack" data-testid="bill-hero">'
        f'<div class="d1-hero d1-hero-{_html.escape(theme)}">'
        f'<div class="d1-hero-main">'
        f'<div class="d1-hero-pay">'
        f'<div class="k-te">{_html.escape(t("you_pay"))}</div>'
        f'<div class="k-en">{_html.escape(t("you_pay_en"))}</div>'
        f'<div class="{pay_cls}">{_html.escape(view["payable_display"])}</div>'
        f"{pill}"
        f"</div>"
        f'<div class="d1-ring" data-testid="units-ring">'
        f'<div class="ring-circle">'
        f'<div class="ring-num">{_html.escape(view["units_label"])}</div>'
        f'<div class="ring-cap">{_html.escape(cap)}</div>'
        f'<div class="ring-leaf" aria-hidden="true">{_LEAF_ICON}</div>'
        f"</div></div></div></div>"
        f"{trust}"
        f'<div class="d1-tiles">'
        f'<div class="d1-tile units"><span class="tile-ico">{_BOLT_ICON}</span>'
        f'<div class="tile-copy"><div class="k-te">{_html.escape(t("units"))}</div>'
        f'<div class="k-en">{_html.escape(t("units_en"))}</div>'
        f'<div class="v">{_html.escape(view["units_label"])}</div></div></div>'
        f'<div class="{due_cls}"><span class="tile-ico">{_CAL_ICON}</span>'
        f'<div class="tile-copy"><div class="k-te">{_html.escape(t("last_date"))}</div>'
        f'<div class="k-en">{_html.escape(t("last_date_en"))}</div>'
        f'<div class="v date">{_html.escape(view["due"])}</div></div></div>'
        f"</div></div>"
    )
    return html


def render_dashboard_hero(model: Dict[str, Any], corrections: Optional[List[str]] = None) -> None:
    import streamlit as st
    view = bill_dashboard_view(model, corrections)
    st.markdown(dashboard_hero_html(view), unsafe_allow_html=True)


def render_hero_card(model: Dict[str, Any], corrections: Optional[List[str]] = None) -> None:
    render_dashboard_hero(model, corrections)


def render_match_banner(model: Dict[str, Any]) -> None:
    import streamlit as st
    checks = model.get("checks") or {}
    if checks.get("consumer_ok") if checks.get("consumer_ok") is not None else checks.get("ok"):
        st.markdown(
            f'<div class="verdict verdict-ok verdict-sm" data-testid="trust-verdict">{t("calc_matches")}</div>',
            unsafe_allow_html=True,
        )
    else:
        msg = checks.get("message_te") or t("calc_mismatch")
        st.markdown(
            f'<div class="verdict verdict-bad verdict-sm" data-testid="trust-verdict">{msg}</div>',
            unsafe_allow_html=True,
        )


def render_gruha_jyothi_note(model: Dict[str, Any]) -> None:
    """Gruha Jyothi checkbox outcome (printed subsidy wins; see gruha_jyothi.py)."""
    import streamlit as st
    gj = model.get("gruha_jyothi")
    if not gj:
        return
    parts = [gj.get("note_te") or ""]
    if gj.get("trueup_note_te"):
        parts.append(gj["trueup_note_te"])
    if gj.get("check_te"):
        parts.append(gj["check_te"])
    text = " ".join(p for p in parts if p)
    if gj.get("mode") == "over":
        st.warning(text)
        return
    st.markdown(
        f'<div class="gj-note">{_html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def render_top_reasons(model: Dict[str, Any], max_n: int = 3) -> List[Dict[str, Any]]:
    import streamlit as st
    reasons = top_reasons(model.get("jump"), model.get("late"), model.get("bill"), max_n=max_n)
    jump = model.get("jump") or {}
    diff = jump.get("difference")
    title = t("why_up")
    if diff is not None and float(diff) < 0:
        title = t("why_down")
    st.markdown(f"### {title}")
    if not reasons:
        st.info(t("no_prev"))
        return []
    parts = ['<div class="reason-card" data-testid="reasons-card">']
    for r in reasons:
        parts.append(
            f'<div class="reason-row"><span class="why"><b>{r["title_te"]}</b>'
            f'<small>{r["voice_te"]}</small></span>'
            f'<span class="amt">{_inr(r["amount"], signed=True)}</span></div>'
        )
    parts.append("</div>")
    st.markdown("\n".join(parts), unsafe_allow_html=True)
    return reasons


def render_main_understand(
    model: Dict[str, Any],
    *,
    corrections: Optional[List[str]] = None,
    voice_text: Optional[str] = None,
) -> None:
    """L6 bill-tab dashboard: units | payable | due, actions, charges, estimate."""
    import streamlit as st
    from voice import render_voice_note
    from forecast import consumer_forecast_range, format_rupee_range

    render_dashboard_hero(model, corrections)
    if model.get("usage_jump"):
        st.warning(model["usage_jump"]["text_te"])

    rng = consumer_forecast_range(forecast=model.get("forecast"))
    spoken = voice_text or build_voice_summary(
        model["bill"], forecast_range=rng, gj=model.get("gruha_jyothi")
    )
    # Sticky dock is unreliable in Streamlit iframes; actions sit under the hero.
    c_voice, c_wa = st.columns([1.4, 1])
    with c_voice:
        if spoken:
            render_voice_note(spoken, label="తెలుగులో వినండి / Listen in Telugu")
    with c_wa:
        if st.button("WhatsApp కి పంపండి", width="stretch", key="wa_send_bill"):
            st.session_state["share_now"] = True
            st.rerun()

    view = bill_dashboard_view(model, corrections)
    render_gruha_jyothi_note(model)
    render_receipt_card(
        model["bill"],
        gj_mode=(model.get("gruha_jyothi") or {}).get("mode"),
        show_gj_tip=bool(view.get("show_gj_tip")),
    )
    tu = (model.get("bill") or {}).get("trueup_charges")
    try:
        tu_n = float(tu) if tu is not None else 0.0
    except (TypeError, ValueError):
        tu_n = 0.0
    if abs(tu_n) >= 0.005:
        from draft_features import render_trueup_what_is_it
        render_trueup_what_is_it()
    if view.get("show_units_bar"):
        render_units_bar(model["bill"])
    if rng:
        band = format_rupee_range(rng["low"], rng["high"])
        from gruha_jyothi import gj_forecast_note_te
        gj_fc = gj_forecast_note_te(model.get("gruha_jyothi"), model.get("forecast"))
        gj_bit = f'<br><small>{gj_fc}</small>' if gj_fc else ""
        st.markdown(
            f'<div class="forecast-one" data-testid="forecast-one">'
            f'వచ్చే నెల అంచనా <b>{band}</b>'
            f' (ఇదే వాడకం ఉంటే){gj_bit}</div>',
            unsafe_allow_html=True,
        )
    if model.get("gj_forecast_warn"):
        st.warning(model["gj_forecast_warn"])
    render_top_reasons(model, max_n=3)


def render_jump_card(model: Dict[str, Any]) -> None:
    import streamlit as st
    st.markdown(f"### {t('why_up')}")
    jump = model.get("jump")
    if not jump or jump.get("difference") is None:
        st.info(t("no_prev"))
        return
    br = jump
    rows = [
        ("అదనపు యూనిట్లు (పాత రేటుతో)", br.get("extra_units_old_rate"), "green", "మీ వాడకం"),
        ("కేటగిరీ / స్లాబ్ మార్పు", br.get("category_change"), "yellow", "స్లాబ్ మారింది"),
        ("True-up జోడింపు", br.get("trueup_added"), "red", "True-up"),
        ("ఫిక్స్‌డ్ / కస్టమర్ / ED / ఇతరం", br.get("other_changes"), "muted", "ఇతరం"),
        ("Residual", br.get("residual"), "muted", "మిగిలిన తేడా"),
    ]
    html = ['<div class="card" data-testid="jump-card">']
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
            f"భాగాలు + residual = తేడా "
            f"({_inr(chk.get('parts_plus_residual'))} = {_inr(chk.get('difference'))})."
        )
    elif chk:
        st.warning("భాగాల మొత్తం బిల్లు తేడాకు సరిపోలలేదు.")


def render_history_chart(model: Dict[str, Any]) -> None:
    import streamlit as st
    import pandas as pd
    import altair as alt
    bill = model["bill"]
    st.markdown("### గత నెలల వాడకం")
    meta = model.get("history_meta") or {}
    src = meta.get("source_label") or (
        "Demo data" if (model.get("history_is_demo") or bill.get("history_is_demo")) else "Your bills"
    )
    src_te = meta.get("source_label_te") or src
    muted = "badge-muted" if meta.get("is_demo") else "badge-green"
    st.markdown(
        f'<div data-testid="history-source" class="badge {muted}">'
        f"మూలం: {src} · {src_te}</div>",
        unsafe_allow_html=True,
    )
    if meta.get("is_demo") or model.get("history_is_demo"):
        st.caption(
            "నమూనా డేటా: ఈ చార్ట్‌లోని చాలా నెలలు సింథటిక్. థర్మల్ స్లిప్‌పై 12–13 నెలల టేబుల్ "
            "కనిపించలేదు. మీ అసలు బిల్లులు ఇస్తే మూలం 'Your bills' అవుతుంది."
        )
    else:
        st.caption("Your bills: మీరు అప్‌లోడ్ / నమోదు చేసిన నెలలు (ప్రస్తుత బిల్లు సహా).")
    hist = model.get("history") or []
    fc = model.get("forecast")
    if not hist:
        st.info("ఇంకా చరిత్ర లేదు.")
        return
    if sum(1 for p in hist if not p.get("estimated")) <= 1:
        st.caption("📌 ఇప్పుడు ఈ ఒక్క బిల్లు మాత్రమే ఉంది. కింద గత బిల్లుల ఫోటోలు పెడితే నెల నెలా ట్రెండ్ కనిపిస్తుంది.")
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
    rules = alt.Chart(pd.DataFrame({"y": [100, 200], "t": ["100", "200"]})).mark_rule(
        strokeDash=[4, 4], color="#98a2b3"
    ).encode(y="y:Q")
    chart = alt.layer(*charts, rules).properties(height=280).configure_view(stroke=None)
    st.altair_chart(chart, use_container_width=True)


def render_comparison_section(model: Dict[str, Any]) -> None:
    render_jump_card(model)
    render_history_chart(model)


def render_whatif_slider(bill: Dict[str, Any], *, key: str = "whatif_units") -> None:
    import streamlit as st
    from whatif import whatif_for_units, same_units_delta_note
    st.markdown("##### యూనిట్లు మారిస్తే బిల్లు ఎంతవుతుంది?")
    st.caption(t("simulation_note"))
    current = bill.get("units")
    try:
        current_i = int(round(float(current))) if current is not None else 100
    except (TypeError, ValueError):
        current_i = 100
    lo = max(0, current_i - 150)
    hi = max(current_i + 200, 400)
    u = st.slider(
        "యూనిట్లు (సిమ్యులేషన్)",
        min_value=int(lo),
        max_value=int(hi),
        value=int(current_i),
        step=1,
        key=key,
    )
    w = whatif_for_units(bill, u)
    c1, c2 = st.columns(2)
    c1.metric("అంచనా మొత్తం", f"₹{w['total']:,.0f}")
    if w["difference"] is not None:
        c2.metric("ఈ నెలతో తేడా", f"₹{w['difference']:+,.0f}")
    note = same_units_delta_note(bill, w)
    if note:
        st.caption(note)
    st.caption(f"{w['label_te']} · టారిఫ్ {w['tariff_version']} · కేటగిరీ {w['category']}")


def render_estimate_section(model: Dict[str, Any]) -> None:
    import streamlit as st
    fc = model.get("forecast")
    rng = forecast_display_range(fc)
    st.markdown(f"### {t('nav_estimate')}")
    if rng:
        st.markdown(
            f'<div class="bill-hero" data-testid="forecast-range">'
            f'<div class="bill-hero-label">{t("estimate")}</div>'
            f'<div class="bill-hero-amt">{format_rupee_range(rng["low"], rng["high"])}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.caption(rng["basis"])
        from gruha_jyothi import gj_forecast_note_te
        gj_fc = gj_forecast_note_te(model.get("gruha_jyothi"), fc)
        if gj_fc:
            st.info(gj_fc)
    elif not fc:
        st.info("అంచనాకు ఇంకా చాలిన డేటా లేదు.")
    if fc:
        c1, c2, c3 = st.columns(3)
        c1.metric("తక్కువ యూనిట్లు", f"{int(round(fc['low']))}")
        c2.metric("అవకాశం", f"{int(round(fc['likely']))}")
        c3.metric("ఎక్కువ యూనిట్లు", f"{int(round(fc['high']))}")
        bt = model.get("backtest") or {}
        if (model.get("history_meta") or {}).get("show_backtest") and bt.get("n"):
            st.caption(
                f"బ్యాక్‌టెస్ట్ (n={bt['n']}): MAE {bt['mae_units']:g} యూనిట్లు / "
                f"{_inr(bt['mae_rupees'])}."
            )
    render_whatif_slider(model["bill"], key="whatif_units_estimate")


def render_calculation_section(
    model: Dict[str, Any],
    *,
    corrections: Optional[List[str]] = None,
    result: Optional[Dict[str, Any]] = None,
    telugu: str = "",
) -> None:
    import streamlit as st
    bill = model["bill"]
    st.markdown(f"### {t('nav_calculated')}")
    st.caption(f"టారిఫ్ వెర్షన్: {TARIFF_VERSION}")
    pvc = printed_vs_calculated(bill)
    c1, c2, c3 = st.columns(3)
    c1.metric(t("printed"), _inr(pvc["printed"]) if pvc["printed"] is not None else "—")
    c2.metric(t("calculated"), _inr(pvc["calculated"]))
    c3.metric("తేడా", _inr(pvc["delta"], signed=True) if pvc["delta"] is not None else "—")
    if corrections:
        st.caption("ℹ️ ఫోటోలో చిన్న అంకె తప్పులు కనిపించాయి — మీటర్ రీడింగ్‌లతో పోల్చి సరిచేశాం.")
        with st.expander("సాంకేతిక వివరాలు / technical notes"):
            st.markdown("- " + "\n- ".join(corrections))
    st.markdown("##### ఛార్జీల వివరాలు")
    cards = model.get("charges") or []
    if cards:
        idx = 0
        for i in range(0, len(cards), 3):
            chunk = cards[i : i + 3]
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
    late = model.get("late")
    if late:
        st.markdown("##### బిల్లింగ్ రోజులు")
        if late["is_late"]:
            st.markdown(
                f'<div class="card" data-testid="late-card">'
                f'<h4>రీడింగ్ {late["days"]} రోజులకు జరిగింది (30 కాదు)</h4>'
                f'<div class="amt">{_inr(late["extra_rupees"], signed=True)}</div>'
                f'<div class="formula">అన్‌ప్రోరేటెడ్ స్లాబ్‌లు {_inr(late["actual_energy"])} '
                f'− రోజులు/30 ప్రోరేటెడ్ స్లాబ్‌లు {_inr(late["fair_energy_prorated"])} '
                f'= {_inr(late["extra_rupees"])}. మూలం: {late["days_source"]}.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"{late['days']} రోజుల చక్రం. extra = {_inr(late['extra_rupees'])}.")
    if model.get("trueup_text"):
        st.markdown("##### ట్రూ-అప్")
        st.write(model["trueup_text"])
        from draft_features import render_trueup_what_is_it
        render_trueup_what_is_it()
    with st.expander("సెల్ఫ్-చెక్ JSON / extracted fields", expanded=False):
        st.json(model.get("checks") or {})
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
                rows.append({"Field": k, "Value": str(bill[k])})
        if rows:
            st.table(rows)
        # Identity fields are never extracted; drop any that a model adds anyway.
        _pii = ("usc", "service", "name", "addr", "mobile", "phone", "email", "meter_no")
        redacted = {k: v for k, v in bill.items() if not any(p in str(k).lower() for p in _pii)}
        redacted.pop("unit_history", None)
        st.caption("Raw JSON (no identity fields)")
        st.json(redacted)
        if result:
            attempts = result.get("attempts") or []
            if attempts or result.get("kept_attempt"):
                st.caption(
                    f"NVIDIA attempt kept: {result.get('kept_attempt')} of "
                    f"{result.get('attempts_used')} (model={result.get('kept_model')})."
                )
                st.json({"attempts": attempts, "from_cache": result.get("from_cache")})
        if telugu:
            st.markdown("##### పాత టెంప్లేట్ వివరణ")
            st.write(telugu)


def render_suggestions_section(model: Dict[str, Any]) -> None:
    import streamlit as st
    bill = model["bill"]
    bud = model.get("budget") or {}
    st.markdown(f"### {t('nav_suggestions')}")
    cliff_html = (
        f'<div class="card" data-testid="cliff-card">'
        f'<div class="formula">వచ్చే 30 రోజుల్లో 100 యూనిట్ల లోపు ఉండాలంటే రోజుకు '
        f'<b>{bud.get("budget_100", 0):.2f}</b> యూనిట్లు; 200 లోపు ఉండాలంటే రోజుకు '
        f'<b>{bud.get("budget_200", 0):.2f}</b> యూనిట్లు.</div>'
        f'<div class="formula" style="margin-top:.5rem">{GRUHA_JYOTHI_NOTE_TE}</div>'
    )
    if model.get("cliff_text"):
        cliff_html += f'<div class="formula" style="margin-top:.5rem">{model["cliff_text"]}</div>'
    cliff_html += "</div>"
    st.markdown(cliff_html, unsafe_allow_html=True)

    dps = delayed_payment_surcharge(bill.get("units"), bill.get("category"))
    sur = bill.get("surcharge")
    dps_html = (
        f'<div class="card" data-testid="dps-card">'
        f'<div class="formula">డ్యూ డేట్ లోపల కడితే ఆలస్య రుసుము ఆదా: '
        f"Cat 1Aకి నెలకు <b>₹10</b>, Cat 1Bకి <b>₹25</b>. "
        f"మీ కేటగిరీకి ఇప్పుడు ₹{dps:.0f}. "
        "వచ్చే నెల అంచనాలో DPS లేదు — సమయానికి చెల్లిస్తారని అనుకున్నాం.</div>"
    )
    if sur is not None and float(sur) != 0:
        dps_html += (
            f'<div class="formula" style="margin-top:.5rem">'
            f"ఈ బిల్లులో సర్‌ఛార్జ్ {_inr(float(sur))} — ఆలస్య చెల్లింపు రుసుము.</div>"
        )
    dps_html += "</div>"
    st.markdown(dps_html, unsafe_allow_html=True)
    if model.get("acd_text"):
        st.markdown(
            f'<div class="card" data-testid="acd-card"><div class="formula">{model["acd_text"]}</div></div>',
            unsafe_allow_html=True,
        )
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
