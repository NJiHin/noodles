"""Page transcription with Qwen3-VL via a local Ollama server (sys-design Stage 0, step 5)."""
import base64

import httpx

MODEL = "qwen3-vl:2b"
PROMPT = (
    "Transcribe this page as markdown. Tables as markdown tables, equations as LaTeX, and describe each "
    "diagram in words. Cover only what is visible on the page; add nothing else."
)


class OllamaError(Exception):
    pass


class Ollama:
    def __init__(self, url: str = "http://127.0.0.1:11434"):
        self.url = url

    def transcribe(self, png: bytes) -> str:
        try:
            r = httpx.post(f"{self.url}/api/generate", timeout=600, json={
                "model": MODEL, "prompt": PROMPT, "images": [base64.b64encode(png).decode()],
                "stream": False, "options": {"temperature": 0},
            })
            r.raise_for_status()
            return r.json()["response"].strip()
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise OllamaError(f"Ollama is unreachable at {self.url} or failed ({e}). "
                              f"Start Ollama and run `ollama pull {MODEL}`, then confirm again.") from e
