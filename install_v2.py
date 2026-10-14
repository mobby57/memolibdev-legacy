#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_v2.py
-------------
Cree les 4 modules V2 de MemoLibDev :
  - conversation.py      : multi-tour persistant (SQLite)
  - streaming.py         : streaming Ollama
  - codebase_index.py    : indexation AST du codebase
  - tool_use.py          : function calling Ollama
  - assistant_v2.py      : orchestrateur qui assemble le tout
  - test_integration_v2.py : tests

N'ecrase JAMAIS un fichier existant (backup + skip).
Affiche les instructions d'integration GUI a la fin.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ======================================================================
# MODULES A CREER
# ======================================================================

CONVERSATION_PY = '''"""conversation.py - Multi-tour persistant (SQLite)."""
from __future__ import annotations
import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Turn:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    mission_id: str | None = None
    proposal_id: str | None = None


class Conversation:
    """Conversation multi-tour persistee en SQLite."""

    def __init__(self, db_path: Path, conversation_id: str | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        if conversation_id is None:
            self.conversation_id = self._create()
        else:
            self.conversation_id = conversation_id
        self.turns: list[Turn] = self._load()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                mission_id TEXT,
                proposal_id TEXT)""")

    def _create(self) -> str:
        cid = secrets.token_urlsafe(12)
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO conversations (id, created_at) VALUES (?, ?)",
                      (cid, datetime.now().isoformat()))
        return cid

    def _load(self) -> list[Turn]:
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute(
                "SELECT role, content, timestamp, mission_id, proposal_id "
                "FROM turns WHERE conversation_id = ? ORDER BY id",
                (self.conversation_id,)).fetchall()
        return [Turn(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    def add(self, role: str, content: str, mission_id: str | None = None,
            proposal_id: str | None = None) -> Turn:
        t = Turn(role, content, mission_id=mission_id, proposal_id=proposal_id)
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT INTO turns (conversation_id, role, content, timestamp, "
                "mission_id, proposal_id) VALUES (?, ?, ?, ?, ?, ?)",
                (self.conversation_id, t.role, t.content, t.timestamp,
                 t.mission_id, t.proposal_id))
        self.turns.append(t)
        return t

    def to_messages(self, max_turns: int = 20) -> list[dict]:
        recent = self.turns[-max_turns:]
        return [{"role": t.role, "content": t.content} for t in recent]

    def summary_for_context(self, max_chars: int = 2000) -> str:
        lines = []
        for t in self.turns[-10:]:
            role = "Utilisateur" if t.role == "user" else "Assistant"
            snippet = t.content[:200].replace("\\n", " ")
            lines.append(f"{role}: {snippet}")
        return "\\n".join(lines)[-max_chars:]

    def clear(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM turns WHERE conversation_id = ?",
                      (self.conversation_id,))
        self.turns = []
'''


STREAMING_PY = '''"""streaming.py - Streaming Ollama."""
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
'''


CODEBASE_INDEX_PY = '''"""codebase_index.py - Indexation AST du codebase."""
from __future__ import annotations
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Symbol:
    kind: str          # "function" | "class" | "method"
    name: str
    file: str
    line: int
    docstring: str = ""
    signature: str = ""


@dataclass
class FileIndex:
    path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    error: str | None = None


class CodebaseIndex:
    """Indexe les symboles Python d'un codebase."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.files: dict[str, FileIndex] = {}

    def build(self, max_files: int = 500) -> int:
        count = 0
        for py in sorted(self.root.rglob("*.py")):
            if any(p in py.parts for p in
                   (".git", "__pycache__", ".venv", "venv",
                    ".patch_backups", "_legacy_document_engine")):
                continue
            if count >= max_files:
                break
            self._index_file(py)
            count += 1
        return count

    def _index_file(self, path: Path):
        rel = str(path.relative_to(self.root)).replace("\\\\", "/")
        try:
            src = path.read_text(encoding="utf-8")
        except Exception as e:
            self.files[rel] = FileIndex(rel, error=str(e))
            return
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            self.files[rel] = FileIndex(rel, error=f"SyntaxError L{e.lineno}")
            return

        fi = FileIndex(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    fi.imports.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for n in node.names:
                    fi.imports.append(f"{mod}.{n.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = f"def {node.name}("
                try:
                    args = [a.arg for a in node.args.args]
                    sig += ", ".join(args) + ")"
                except Exception:
                    sig += "...)"
                fi.symbols.append(Symbol(
                    kind="function", name=node.name, file=rel,
                    line=node.lineno,
                    docstring=(ast.get_docstring(node) or "")[:200],
                    signature=sig))
            elif isinstance(node, ast.ClassDef):
                fi.symbols.append(Symbol(
                    kind="class", name=node.name, file=rel,
                    line=node.lineno,
                    docstring=(ast.get_docstring(node) or "")[:200],
                    signature=f"class {node.name}"))
        self.files[rel] = fi

    def find_symbol(self, name: str) -> list[Symbol]:
        results = []
        for fi in self.files.values():
            for s in fi.symbols:
                if name.lower() in s.name.lower():
                    results.append(s)
        return results

    def find_in_file(self, rel_path: str) -> FileIndex | None:
        return self.files.get(rel_path)

    def search(self, term: str, limit: int = 20) -> list[dict]:
        results = []
        term_lower = term.lower()
        for rel, fi in self.files.items():
            if term_lower in rel.lower():
                results.append({"file": rel, "match": "path"})
            for s in fi.symbols:
                if term_lower in s.name.lower():
                    results.append({
                        "file": rel, "line": s.line,
                        "kind": s.kind, "name": s.name,
                        "signature": s.signature,
                        "match": "symbol",
                    })
            if len(results) >= limit:
                break
        return results[:limit]

    def stats(self) -> dict:
        total_symbols = sum(len(fi.symbols) for fi in self.files.values())
        errors = [f for f, fi in self.files.items() if fi.error]
        return {
            "files": len(self.files),
            "symbols": total_symbols,
            "errors": len(errors),
        }

    def save(self, path: Path):
        data = {
            "root": str(self.root),
            "files": {
                rel: {
                    "imports": fi.imports,
                    "symbols": [
                        {"kind": s.kind, "name": s.name, "line": s.line,
                         "signature": s.signature, "docstring": s.docstring}
                        for s in fi.symbols
                    ],
                    "error": fi.error,
                }
                for rel, fi in self.files.items()
            },
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CodebaseIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        idx = cls(Path(data["root"]))
        for rel, fd in data["files"].items():
            fi = FileIndex(rel, imports=fd["imports"], error=fd.get("error"))
            for s in fd["symbols"]:
                fi.symbols.append(Symbol(
                    kind=s["kind"], name=s["name"], file=rel,
                    line=s["line"], docstring=s.get("docstring", ""),
                    signature=s.get("signature", "")))
            idx.files[rel] = fi
        return idx
'''


TOOL_USE_PY = '''"""tool_use.py - Function calling Ollama."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    func: Callable


class ToolRegistry:
    """Registre d'outils avec parsing JSON."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def schemas(self) -> list[dict]:
        return [
            {"type": "function",
             "function": {"name": t.name,
                          "description": t.description,
                          "parameters": t.schema}}
            for t in self.tools.values()
        ]

    def execute(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERREUR: outil inconnu {name}"
        try:
            result = tool.func(**args)
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)
        except Exception as e:
            return f"ERREUR {type(e).__name__}: {e}"


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Cherche des appels type <tool_call>{"name": "...", "args": {...}}</tool_call>."""
    calls = []
    pattern = r"<tool_call>(.*?)</tool_call>"
    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
            name = obj.get("name")
            args = obj.get("args", {})
            if name:
                calls.append((name, args))
        except json.JSONDecodeError:
            continue
    return calls


def make_standard_tools(root: Path, registry: ToolRegistry,
                        index=None):
    """Enregistre les outils standards."""
    root = Path(root).resolve()

    def read_file(path: str) -> str:
        p = (root / path).resolve()
        if not str(p).startswith(str(root)):
            return "ERREUR: chemin hors perimetre"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        return p.read_text(encoding="utf-8")[:8000]

    def list_files(pattern: str = "*.py", limit: int = 50) -> list[str]:
        results = []
        for f in sorted(root.rglob(pattern)):
            if any(p in f.parts for p in (".git", "__pycache__",
                                          ".venv", ".patch_backups")):
                continue
            results.append(str(f.relative_to(root)).replace("\\\\", "/"))
            if len(results) >= limit:
                break
        return results

    def find_symbol(name: str) -> list[dict]:
        if index is None:
            return []
        return [
            {"file": s.file, "line": s.line, "kind": s.kind,
             "name": s.name, "signature": s.signature}
            for s in index.find_symbol(name)
        ]

    registry.register(Tool(
        "read_file", "Lire un fichier du projet",
        {"type": "object",
         "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        read_file))

    registry.register(Tool(
        "list_files", "Lister les fichiers correspondant a un pattern",
        {"type": "object",
         "properties": {"pattern": {"type": "string"},
                        "limit": {"type": "integer"}}},
        list_files))

    registry.register(Tool(
        "find_symbol", "Chercher un symbole (fonction/classe) par nom",
        {"type": "object",
         "properties": {"name": {"type": "string"}},
         "required": ["name"]},
        find_symbol))
'''


ASSISTANT_V2_PY = '''"""assistant_v2.py - Orchestrateur V2 (conversation + streaming + tools)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable, Iterator

from conversation import Conversation
from streaming import stream_ollama
from codebase_index import CodebaseIndex
from tool_use import ToolRegistry, parse_tool_calls, make_standard_tools


SYSTEM_PROMPT = """Tu es MemoLibDev, un assistant de code local et securise.
Tu reponds en francais. Tu ne modifies JAMAIS un fichier sans validation explicite.
Quand tu veux utiliser un outil, emets :
<tool_call>{"name": "read_file", "args": {"path": "..."}}</tool_call>"""


class AssistantV2:
    """Assistant conversationnel avec memoire, streaming et outils."""

    def __init__(
        self,
        project_root: Path,
        model: str = "qwen2.5-coder",
        db_path: Path | None = None,
        index: CodebaseIndex | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.model = model
        self.db_path = db_path or (self.project_root / "data" / "conv.db")
        self.conversation = Conversation(self.db_path)
        self.index = index
        self.registry = ToolRegistry()
        make_standard_tools(self.project_root, self.registry, index)

    def build_prompt(self, user_text: str, max_turns: int = 15) -> str:
        parts = []
        if self.index:
            st = self.index.stats()
            parts.append(
                f"Projet: {self.project_root} | "
                f"{st['files']} fichiers, {st['symbols']} symboles indexes."
            )
        tools_desc = "\\n".join(
            f"- {t.name}: {t.description}"
            for t in self.registry.tools.values()
        )
        if tools_desc:
            parts.append(f"Outils disponibles:\\n{tools_desc}")

        history = self.conversation.summary_for_context()
        if history:
            parts.append(f"Historique recent:\\n{history}")

        parts.append(f"Demande actuelle: {user_text}")
        return "\\n\\n".join(parts)

    def chat(
        self,
        user_text: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        self.conversation.add("user", user_text)
        prompt = self.build_prompt(user_text)

        full = []
        if on_token:
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                full.append(chunk)
                on_token(chunk)
        else:
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                full.append(chunk)

        response = "".join(full)

        # Executer les tool calls si presents
        calls = parse_tool_calls(response)
        if calls:
            tool_results = []
            for name, args in calls:
                result = self.registry.execute(name, args)
                tool_results.append(f"[{name}] {result[:1000]}")
            response += "\\n\\n--- Resultats outils ---\\n" + "\\n".join(tool_results)

        self.conversation.add("assistant", response)
        return response

    def new_conversation(self):
        self.conversation = Conversation(self.db_path)

    def history(self) -> list[dict]:
        return [
            {"role": t.role, "content": t.content, "time": t.timestamp}
            for t in self.conversation.turns
        ]
'''


TEST_INTEGRATION_V2_PY = '''"""test_integration_v2.py - Tests des modules V2."""
from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conversation import Conversation
from codebase_index import CodebaseIndex
from tool_use import Tool, ToolRegistry, parse_tool_calls, make_standard_tools

PASS, FAIL = [], []

def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" +
          (f" :: {detail}" if detail else ""))


def main() -> int:
    print("=" * 72)
    print("INTEGRATION V2 - conversation + index + tools")
    print("=" * 72)
    tmp = Path(tempfile.mkdtemp(prefix="memolib-v2-"))
    try:
        print("\\n[C] conversation")
        db = tmp / "conv.db"
        c = Conversation(db)
        c.add("user", "bonjour")
        c.add("assistant", "salut")
        ok("C1 tour ajoute", len(c.turns) == 2)
        c2 = Conversation(db, conversation_id=c.conversation_id)
        ok("C2 persistance", len(c2.turns) == 2)
        ok("C3 to_messages", len(c2.to_messages()) == 2)
        ok("C4 summary", "bonjour" in c2.summary_for_context())

        print("\\n[I] codebase_index")
        src_dir = tmp / "proj"
        src_dir.mkdir()
        (src_dir / "a.py").write_text(
            "import os\\nclass Foo:\\n    pass\\n"
            "def bar():\\n    pass\\n", encoding="utf-8")
        (src_dir / "b.py").write_text(
            "from a import Foo\\ndef baz():\\n    pass\\n", encoding="utf-8")
        idx = CodebaseIndex(src_dir)
        n = idx.build()
        ok("I1 fichiers indexes", n == 2, f"n={n}")
        ok("I2 find_symbol Foo", len(idx.find_symbol("Foo")) == 1)
        ok("I3 find_symbol bar", len(idx.find_symbol("bar")) == 1)
        ok("I4 search baz", any(r["name"] == "baz" for r in idx.search("baz")))
        st = idx.stats()
        ok("I5 stats", st["files"] == 2 and st["symbols"] >= 3, str(st))

        print("\\n[P] persistence index")
        out = tmp / "index.json"
        idx.save(out)
        idx2 = CodebaseIndex.load(out)
        ok("P1 reload", idx2.stats()["files"] == 2)

        print("\\n[T] tool_use")
        reg = ToolRegistry()
        reg.register(Tool("echo", "echo", {"type": "object"}, lambda msg: msg))
        ok("T1 execute", reg.execute("echo", {"msg": "hi"}) == "hi")
        ok("T2 unknown", "inconnu" in reg.execute("nope", {}))
        ok("T3 schemas", len(reg.schemas()) == 1)

        print("\\n[TC] parse_tool_calls")
        text = 'bla <tool_call>{"name": "read_file", "args": {"path": "a.py"}}</tool_call>'
        calls = parse_tool_calls(text)
        ok("TC1 parsed", len(calls) == 1 and calls[0][0] == "read_file")

        print("\\n[ST] standard tools")
        reg2 = ToolRegistry()
        make_standard_tools(src_dir, reg2, idx)
        ok("ST1 read_file", "class Foo" in reg2.execute("read_file", {"path": "a.py"}))
        ok("ST2 list_files", len(reg2.execute("list_files", {})) >= 2)
        ok("ST3 find_symbol", len(reg2.execute("find_symbol", {"name": "Foo"})) == 1)

        print("\\n" + "=" * 72)
        print(f"RESULTAT V2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ECHECS :", ", ".join(FAIL))
        print("=" * 72)
        return 0 if not FAIL else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
'''


# ======================================================================
# INSTALLATION
# ======================================================================
FILES = {
    "conversation.py": CONVERSATION_PY,
    "streaming.py": STREAMING_PY,
    "codebase_index.py": CODEBASE_INDEX_PY,
    "tool_use.py": TOOL_USE_PY,
    "assistant_v2.py": ASSISTANT_V2_PY,
    "test_integration_v2.py": TEST_INTEGRATION_V2_PY,
}


def install():
    print("=" * 72)
    print("INSTALL V2 - 4 modules + tests")
    print("=" * 72)
    print(f"Dossier : {ROOT}")
    print()

    bk = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    created, skipped = [], []
    for name, content in FILES.items():
        p = ROOT / name
        if p.exists():
            skipped.append(name)
            print(f"[SKIP] {name} existe deja")
            continue
        p.write_text(content, encoding="utf-8")
        created.append(name)
        print(f"[OK]   {name} cree")

    print()
    print(f"Crees : {len(created)}  Skippes : {len(skipped)}")
    print()
    print("Test de la nouvelle chaine :")
    print("  python test_integration_v2.py")
    print()
    print("Integration GUI (optionnel) :")
    print("  1. Dans memolibdev_gui_v4.py, ajouter en haut :")
    print("       from assistant_v2 import AssistantV2")
    print("       from codebase_index import CodebaseIndex")
    print("  2. Dans __init__ de MemoLibDevApp :")
    print("       self.index = CodebaseIndex(Path('.'))")
    print("       self.index.build()")
    print("       self.assistant = AssistantV2(Path('.'), index=self.index)")
    print("  3. Dans _on_send, remplacer l'appel CLI par :")
    print("       def on_token(chunk):")
    print("           self.after(0, lambda: self._append_stream(chunk))")
    print("       self.assistant.chat(text, on_token=on_token)")
    return 0


if __name__ == "__main__":
    sys.exit(install())