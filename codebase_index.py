"""codebase_index.py - Indexation AST du codebase."""
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
        rel = str(path.relative_to(self.root)).replace("\\", "/")
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
