"""streaming.py - Streaming Ollama."""
from __future__ import annotations
import json
from typing import Callable, Iterator
from urllib.request import Request, urlopen
from urllib.error import URLError


def stream_ollama(
    prompt: str,
    model: str = "qwen2.5-coder",
    host: str = "http://127.0.0.1:11434",
    system: str | None = None,
    timeout: int = 120,
) -> Iterator[str]:
    """Genere des tokens un par un depuis Ollama."""
    payload = {"model": model, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system

    req = Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("response", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
    except URLError as e:
        yield f"[ERREUR streaming : {e}]"


def stream_to_callback(
    prompt: str,
    on_token: Callable[[str], None],
    **kwargs,
) -> str:
    """Envoie chaque token a un callback. Retourne le texte complet."""
    full = []
    for chunk in stream_ollama(prompt, **kwargs):
        full.append(chunk)
        on_token(chunk)
    return "".join(full)
