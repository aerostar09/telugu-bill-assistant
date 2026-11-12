"""Short Telugu voice notes via gTTS, optionally sped up with ffmpeg atempo.

Cache by hash of (text + tempo). Fail silent — never crash the app.
ffmpeg is listed in packages.txt for Streamlit Cloud; if it is missing the
unspeeded clip is still returned.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent / ".voice_cache"
# Short spoken summaries only (the long template lives on the calculation tab).
MAX_CHARS = 400
VOICE_TEMPO = 1.30  # 1.25–1.35x as requested


def _hash_key(text: str, tempo: float) -> str:
    raw = f"{text}|te|{tempo:.2f}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cached_voice_path(text: str, tempo: float = VOICE_TEMPO) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_hash_key(text, tempo)}.mp3"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _speed_up(src: Path, dest: Path, tempo: float) -> bool:
    """Return True if dest was written. atempo must be in 0.5–2.0."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    try:
        tmp = dest.with_suffix(".tmp.mp3")
        proc = subprocess.run(
            [
                exe, "-y", "-i", str(src),
                "-filter:a", f"atempo={tempo}",
                "-vn", str(tmp),
            ],
            capture_output=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 0:
            try:
                tmp.unlink()
            except Exception:
                pass
            return False
        tmp.replace(dest)
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def synthesize_te(
    text: str,
    *,
    lang: str = "te",
    tempo: float = VOICE_TEMPO,
) -> Optional[Path]:
    """Return a cached MP3 path, or None if gTTS/network fails.

    gTTS is called with slow=False. When ffmpeg is present the clip is
    sped up by `tempo` (default 1.30x). The cache key includes the tempo
    so a slower clip is never reused as a faster one.
    """
    clean = (text or "").strip()
    if not clean:
        return None
    if len(clean) > MAX_CHARS:
        clean = clean[:MAX_CHARS].rsplit(" ", 1)[0] + "…"
    path = cached_voice_path(clean, tempo)
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        from gtts import gTTS
    except Exception:
        return None
    raw = path.with_suffix(".raw.mp3")
    tmp = path.with_suffix(".tmp.mp3")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        gTTS(text=clean, lang=lang, slow=False).save(str(tmp))
        if not tmp.exists() or tmp.stat().st_size <= 0:
            return None
        if tempo and abs(tempo - 1.0) > 0.01 and ffmpeg_available():
            tmp.replace(raw)
            if _speed_up(raw, path, tempo):
                try:
                    raw.unlink()
                except Exception:
                    pass
                return path
            # ffmpeg failed — fall back to the unspeeded clip
            try:
                raw.replace(path)
            except Exception:
                if tmp.exists():
                    tmp.replace(path)
        else:
            tmp.replace(path)
        if path.exists() and path.stat().st_size > 0:
            return path
    except Exception:
        for p in (path, tmp, raw):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        return None
    return None


def clip_duration_s(path: Path) -> Optional[float]:
    """Best-effort duration via ffprobe; None if unavailable."""
    exe = shutil.which("ffprobe") or shutil.which("ffmpeg")
    if not exe or not path or not Path(path).exists():
        return None
    try:
        # ffprobe if present; otherwise skip
        probe = shutil.which("ffprobe")
        if not probe:
            return None
        proc = subprocess.run(
            [
                probe, "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True,
            timeout=15,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return float((proc.stdout or "").strip())
    except Exception:
        return None


def render_voice_note(text: str, *, label: str = "తెలుగులో వినండి / Listen in Telugu") -> None:
    """Show st.audio when synthesis works; hide the player otherwise."""
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
