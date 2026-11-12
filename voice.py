"""Telugu voice notes via gTTS. Cache by text hash. Fail silent — never crash the app."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent / ".voice_cache"
# Keep clips reasonably short for WhatsApp-style notes
MAX_CHARS = 900


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cached_voice_path(text: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_hash_text(text)}.mp3"


def synthesize_te(text: str, *, lang: str = "te") -> Optional[Path]:
    """Return a cached MP3 path, or None if gTTS/network fails."""
    clean = (text or "").strip()
    if not clean:
        return None
    if len(clean) > MAX_CHARS:
        clean = clean[:MAX_CHARS].rsplit(" ", 1)[0] + "…"
    path = cached_voice_path(clean)
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        from gtts import gTTS
    except Exception:
        return None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.mp3")
        gTTS(text=clean, lang=lang).save(str(tmp))
        tmp.replace(path)
        if path.exists() and path.stat().st_size > 0:
            return path
    except Exception:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return None
    return None


def render_voice_note(text: str, *, label: str = "తెలుగు వాయిస్ నోట్ / Telugu voice note") -> None:
    """Show st.audio when synthesis works; hide the player otherwise (no error banner)."""
    try:
        import streamlit as st
    except Exception:
        return
    path = synthesize_te(text)
    if not path:
        return
    try:
        st.caption(label)
        st.audio(str(path), format="audio/mp3")
    except Exception:
        return
