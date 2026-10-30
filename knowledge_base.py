"""
knowledge_base.py — Base vectorielle locale ultra-légère (sans ChromaDB).
Utilise numpy + sqlite3 + Ollama pour les embeddings. 100% local, 0 dépendance lourde.
"""
from pathlib import Path
from typing import List
import json
import sqlite3
import numpy as np
import urllib.request as _urllib_req

DB_DIR = Path(r"C:\Users\moros\MemoLibDev_KnowledgeBase")
DOCS_DIR = DB_DIR / "documents"
DB_FILE = DB_DIR / "vectors.db"
EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

DB_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

def _embed(text: str) -> List[float]:
    """Calcule un embedding via Ollama (local)."""
    url = "http://127.0.0.1:11434/api/embeddings"
    data = {"model": EMBEDDING_MODEL, "prompt": text[:2000]}
    try:
        req = _urllib_req.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with _urllib_req.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8')).get("embedding", [])
    except Exception as e:
        print(f"[EMBED ERROR] {e}")
        return []

def _init_db():
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, source TEXT, content TEXT, embedding BLOB)")
    conn.commit()
    return conn

def _chunk_text(text: str) -> List[str]:
    """Découpe un texte en morceaux avec overlap."""
    chunks = []
    for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
        chunks.append(text[i:i + CHUNK_SIZE])
    return [c for c in chunks if c.strip()]

def build_or_update_index():
    """Indexe tous les documents du dossier DOCS_DIR."""
    conn = _init_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chunks")  # Reset simple pour cette version

    count = 0
    for ext in ("*.md", "*.txt", "*.py", "*.js", "*.ts", "*.dart", "*.html", "*.css", "*.json"):
        for f in DOCS_DIR.glob(ext):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                for chunk in _chunk_text(content):
                    vec = _embed(chunk)
                    if vec:
                        cursor.execute("INSERT INTO chunks (source, content, embedding) VALUES (?, ?, ?)",
                                       (f.name, chunk, np.array(vec, dtype=np.float32).tobytes()))
                        count += 1
            except Exception as e:
                print(f"[SKIP] {f.name}: {e}")
    conn.commit()
    conn.close()
    print(f"[OK] {count} chunks indexés depuis {DOCS_DIR}")
    return count

def search(query: str, k: int = 4) -> List[dict]:
    """Recherche par similarité cosinus."""
    query_vec = _embed(query)
    if not query_vec:
        return []
    query_np = np.array(query_vec, dtype=np.float32)
    query_norm = query_np / (np.linalg.norm(query_np) + 1e-9)

    conn = _init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT source, content, embedding FROM chunks")
    results = []
    for source, content, emb_blob in cursor.fetchall():
        emb = np.frombuffer(emb_blob, dtype=np.float32)
        score = float(np.dot(query_norm, emb / (np.linalg.norm(emb) + 1e-9)))
        results.append({"source": source, "content": content, "score": score})
    conn.close()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]

def get_context_for_prompt(query: str, k: int = 3) -> str:
    hits = search(query, k=k)
    if not hits:
        return ""
    lines = ["[CONNAISSANCES LOCALES PERTINENTES]"]
    for h in hits:
        lines.append(f"--- Source : {h['source']} (pertinence : {h['score']:.2f}) ---")
        lines.append(h["content"][:800])
        lines.append("")
    return "\n".join(lines)