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

Three top-level tabs: **పౌరుడు / Citizen** (upload or one-click scenarios A/B/C, rupees from `tariff.py`), a **WhatsApp simulator** of a proposed integration with the official TGSPDCL chatbot 87124 41912 (this is a simulation, not the official bot), and a **DISCOM dashboard** (real counts from an anonymised public set, n=71, plus clearly labelled sample map / anomaly table / queries-avoided concept).

Photo extract uses NVIDIA NIM vision (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, thinking disabled, first attempt timeout 60s, image downscaled to max 1600px JPEG quality 85). On timeout it falls back to `minimaxai/minimax-m3.1-flash` (thinking also disabled, 90s). Successful extracts are hash-cached so a repeat upload of the same image returns immediately. The older `meta/llama-3.2-90b-vision-instruct` endpoint is deprecated 15 Nov / unsupported after 16 Nov 2026 and is no longer used. Auth failures (HTTP 401/403) show an API-key problem message (Telugu + English); other HTTP errors show the status code; timeouts keep the slow-server message. Streamlit logs record status and elapsed time — never the key. In non-demo mode the sidebar shows `AI key: configured yes/no` (never the value).

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
