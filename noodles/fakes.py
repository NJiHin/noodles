"""Fake model clients for tests and NOODLES_FAKE=1 (no paid or local model calls)."""


class FakeOllama:
    def __init__(self):
        self.calls = 0

    def transcribe(self, png: bytes) -> str:
        self.calls += 1
        return f"[vlm] Transcribed page ({len(png)} bytes of image)."
