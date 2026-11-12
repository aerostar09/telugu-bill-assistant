"""gTTS helper: cache by hash, silent fallback, never raises into the UI."""
import unittest
from pathlib import Path
from unittest.mock import patch

import voice


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


if __name__ == "__main__":
    unittest.main()
