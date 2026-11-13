---
title: Mee Vidyut Billu Sahayakudu
emoji: ⚡
colorFrom: teal
colorTo: green
sdk: streamlit
sdk_version: 1.67.0
app_file: app.py
pinned: false
license: mit
short_description: Telugu electricity bill explainer for Telangana (TISC #13)
---

# మీ విద్యుత్ బిల్లు సహాయకుడు

Telugu-first assistant for TGSPDCL / TGNPDCL domestic bills (TISC problem statement #13).  
Upload a bill photo → structured extract → Telugu explanation of every charge, why the bill jumped, late-reading slab push, 100/200-unit cliff, true-up (30p → 50p), and a next-month forecast.

**Demo (no API key):** open the app with `?demo=1` or turn on **డెమో మోడ్** in the sidebar. Uses PII-free Lakshmi ground-truth numbers plus clearly labelled synthetic history.

Three top-level tabs: **పౌరుడు / Citizen** (upload or one-click scenarios A/B/C, rupees from `tariff.py`), a **WhatsApp డెమో** tab (a simulation of a proposed 'Explain my bill' option on the official TGSPDCL chatbot 87124 41912: sample bill thumbnail, short Telugu summary, and voice note — labelled Demo / Concept, not the official bot), and a **DISCOM dashboard** (real counts from an anonymised public set, n=71, plus clearly labelled sample map / anomaly table / queries-avoided concept).

Photo extract uses NVIDIA NIM vision (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, thinking disabled, first attempt timeout 60s, image downscaled to max 1600px JPEG quality 85). On timeout it falls back to `minimaxai/minimax-m3.1-flash` (thinking also disabled, 90s). Successful extracts are hash-cached so a repeat upload of the same image returns immediately. After extract, post-OCR reconciles line items with the printed total: if Surcharge was copied from the separate PP TRUEUP line, or setting exactly one optional line to 0 makes the sum match within ₹1, the app auto-corrects and shows an auto-correct note instead of the 1912 mismatch warning. A Loss/Gain rounding residual of at most ₹1 is also applied. The 1912 warning is kept only for unexplained mismatches. The Citizen page is mobile-first: a short main view (this-month total, units, due date, confidence pill, up to 3 data-supported reasons, a 15–25s Telugu voice note, and a calculation-matches banner) plus sub-tabs for past-month comparison, the next-month range (rounded rupees, e.g. ₹500–₹800), a labelled units what-if simulation, the full FY 2026-27 TGERC breakdown, and data-driven suggestions. Voice uses gTTS with slow=False and is sped up ~1.30× with ffmpeg (listed in packages.txt; falls back if ffmpeg is missing). Technical NVIDIA diagnostics live in the sidebar Technical details expander. The older `meta/llama-3.2-90b-vision-instruct` endpoint is deprecated 15 Nov / unsupported after 16 Nov 2026 and is no longer used. Auth failures (HTTP 401/403) show an API-key problem message (Telugu + English); other HTTP errors show the status code; timeouts keep the slow-server message. Streamlit logs record status and elapsed time — never the key. In non-demo mode the sidebar shows `AI key: configured yes/no` (never the value).

## Rollout concepts (demo only)

The `assets/` folder holds pitch / Demo Day mockups for later channels. Every file is labelled **Demo / Concept – not an official TGSPDCL service**. No official DISCOM or government logos are used.

- `qr_app.png` / `qr_app_caption.png` — high-res QR to the live app (`https://telugu-electricitybill-assistant.streamlit.app/`). Anyone with the link can open it in a browser for free; no install or login. The Community Cloud app may sleep when idle, so wake it before a demo.
- `mock_discom_portal.html` plus mobile / desktop screenshots — a generic “Your DISCOM portal (concept)” page with an **Explain my bill / బిల్లు వివరణ** button that links to the app.
- `bill_with_qr.png` — fictional sample bill (name “Sample Customer”, units 154, total ₹757) with a QR and the line “ఈ బిల్లు అర్థం కాలేదా? స్కాన్ చేయండి”.
- `sms_sample.txt` — a short Telugu + English SMS with the same link.
- `demo_bill_thumb.png` — PII-free sample thumbnail used in the WhatsApp డెమో tab.

Regenerate with `python scripts/make_rollout_assets.py` (needs `qrcode` and the Telugu fonts on the machine; not required at app runtime).

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional, only needed to extract real bill photos:
export NVIDIA_API_KEY="your-key"
# or: cp .streamlit/secrets.toml.example .streamlit/secrets.toml  and edit it
streamlit run app.py
```

Then visit http://localhost:8501/?demo=1 — this works **without** an API key.

The key is read from `NVIDIA_API_KEY` in the environment or from Streamlit secrets (`st.secrets["NVIDIA_API_KEY"]`). The value is never printed or logged.

## Deploy — Streamlit Community Cloud

1. Create a GitHub repository and push **this folder** (the files next to this README) as the repo root. Do **not** commit `.streamlit/secrets.toml`, `.env`, bill photos, or `.extract_cache/`.
2. Go to [https://share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → pick the repo, branch, and main file `app.py`.
4. **Settings → Secrets** and add:

   ```toml
   NVIDIA_API_KEY = "your-nvidia-api-key"
   ```

5. Deploy. Confirm `https://<your-app>.streamlit.app/?demo=1` loads without depending on the key.

## Deploy — Hugging Face Spaces

1. Create a new Space: **SDK = Streamlit**, `app_file` is `app.py` (already set in the YAML header above).
2. Push this folder to the Space git remote, or create the Space from the same GitHub repo.
3. **Settings → Secrets** (or Repository secrets) and add `NVIDIA_API_KEY`. Hugging Face injects Space secrets as environment variables, which this app also reads.
4. Confirm `?demo=1` works with the secret unset.

## What the app does not do

- It does **not** call Sarvam (paid Telugu LLM) unless a developer turns the sidebar toggle on; default is OFF.
- Bill photos are not kept on our side. An on-device hash cache avoids repeat NVIDIA calls; it is gitignored.
- Gruha Jyothi free-200-unit relief applies only to **eligible beneficiaries**. If they go above 200 units, the **entire** bill is charged, not only the excess.

## Tariff sources

Energy slabs, fixed charge (₹10/kW, **₹50/kW above 800 units**), customer charges, and Delayed Payment Surcharge (LT-I(A) ₹10/month, LT-I(B) ₹25/month) follow the TGERC Retail Supply Tariff Order / Schedule FY 2026-27, Appendix A (pages 289, 294–295). Forecasts assume **on-time payment** and therefore exclude DPS.

## Tests

```bash
python -m unittest discover -s . -p 'test_*.py' -q
```
