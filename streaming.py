"""streaming.py - Streaming Ollama."""
from __future__ import annotations
import json
from typing import Callable, Iterator
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def stream_ollama(
    prompt: str,
    model: str = "qwen2.5-coder",
    host: str = "http://127.0.0.1:11434",
    system: str | None = None,
    timeout: int = 120,
    temperature: float = 0.2,
) -> Iterator[str]:
    """Genere des tokens un par un depuis Ollama."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature},
    }
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


def chat_once(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = "qwen2.5-coder",
    host: str = "http://127.0.0.1:11434",
    timeout: int = 180,
    temperature: float = 0.2,
    num_predict: int | None = None,
) -> dict:
    """Appel /api/chat (non-streaming) avec tools natifs Ollama."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if tools:
        payload["tools"] = tools
    if num_predict is not None:
        payload["options"]["num_predict"] = int(num_predict)

    req = Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _dbg = Path(__file__).parent / "_debug_last_payload.json"
        _dbg.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("message", {})
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "(corps illisible)"
        return {
            "role": "assistant",
            "content": f"[ERREUR /api/chat HTTP {e.code}] {body}",
        }
    except (URLError, TimeoutError, ConnectionError) as e:
        return {"role": "assistant", "content": f"[ERREUR /api/chat : {e}]"}


def model_capabilities(
    model: str,
    host: str = "http://127.0.0.1:11434",
    timeout: int = 5,
) -> set[str] | None:
    """Interroge /api/show et renvoie l'ensemble des capacites du modele.

    Renvoie None si Ollama est injoignable, si le modele n'existe pas,
    ou si la reponse ne contient pas de champ 'capabilities' exploitable.
    """
    payload = {"name": model}
    req = Request(
        f"{host}/api/show",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError, OSError):
        return None
    caps = result.get("capabilities", [])
    if not isinstance(caps, list):
        return None
    return set(str(c) for c in caps)
