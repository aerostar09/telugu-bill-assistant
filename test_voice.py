"""gTTS helper: cache by hash, silent fallback, never raises into the UI."""
import unittest
from pathlib import Path
from unittest.mock import patch

import voice
from citizen_summary import build_voice_summary, top_reasons, VOICE_MAX_WORDS
from demo_data import lakshmi_demo_bundle
from dashboard import build_dashboard_model
from forecast import forecast_display_range
from self_checks import run_all_checks
from terms import word_count


class VoiceTests(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(voice.synthesize_te(""))
        self.assertIsNone(voice.synthesize_te("   "))

    def test_gtts_failure_is_silent(self):
        with patch("voice.gTTS", create=True):
            # Force import path: synthesize imports gTTS inside the try
            pass
        def boom(*a, **k):
            raise RuntimeError("network down")
        with patch.dict("sys.modules"):
            with patch("gtts.gTTS", side_effect=boom):
                self.assertIsNone(voice.synthesize_te("పరీక్ష వాక్యం"))

    def test_cache_hit_skips_network(self):
        text = "cached-voice-unit-test-unique"
        path = voice.cached_voice_path(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ID3FAKE")
        try:
            with patch("gtts.gTTS") as g:
                out = voice.synthesize_te(text)
                self.assertEqual(out, path)
                g.assert_not_called()
        finally:
            if path.exists():
                path.unlink()



class VoiceSummaryLengthTests(unittest.TestCase):
    def test_lakshmi_demo_is_short(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"]))
        reasons = top_reasons(model["jump"], model["late"], model["bill"], max_n=3)
        self.assertLessEqual(len(reasons), 3)
        rng = forecast_display_range(model["forecast"])
        text = build_voice_summary(model["bill"], reasons=reasons, forecast_range=rng)
        n = word_count(text)
        self.assertLessEqual(n, VOICE_MAX_WORDS)
        self.assertLessEqual(n, 60)
        self.assertIn("757", text)
        self.assertIn("154", text)
        self.assertIn("రూపాయలు", text)
        # no paise precision, no long template dump
        self.assertNotIn("599.20", text)
        self.assertNotIn("కస్టమర్ ఛార్జీ", text)

    def test_tempo_default_and_ffmpeg_helper(self):
        self.assertGreaterEqual(voice.VOICE_TEMPO, 1.25)
        self.assertLessEqual(voice.VOICE_TEMPO, 1.35)
        # cache path depends on tempo
        a = voice.cached_voice_path("abc", tempo=1.30)
        b = voice.cached_voice_path("abc", tempo=1.00)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
