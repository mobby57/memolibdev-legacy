"""tool_use.py - Function calling Ollama."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

READ_ONLY_TOOL_NAMES = frozenset({
    "read_file", "list_files", "find_symbol",
    "grep_file", "extract_lines",
})
WRITE_TOOL_NAMES = frozenset({
    "write_file", "edit_file", "delete_file",
})
CODER_EXTRA_TOOL_NAMES = frozenset({"verify_file", "run_command"})
# Allowlist par défaut (rétro-compat). NE PLUS MUTER depuis d'autres modules :
# passer `allowed=` au constructeur de ToolRegistry.
ALLOWED_TOOL_NAMES = READ_ONLY_TOOL_NAMES


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    func: Callable


class ToolRegistry:
    """Registre d'outils avec parsing JSON."""

    def __init__(self, allowed: frozenset[str] | None = None):
        self.tools: dict[str, Tool] = {}
        self.allowed = allowed if allowed is not None else ALLOWED_TOOL_NAMES

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
            if t.name in self.allowed
            and t.name not in WRITE_TOOL_NAMES
        ]

    def execute(self, name: str, args: dict) -> str:
        # Garde inconditionnelle : les effets de bord ne passent JAMAIS
        # par execute(). Les écritures passent par agent_loop -> D5.9.
        # coder_mode élargit self.allowed mais ne lève pas ce blocage.
        if name in WRITE_TOOL_NAMES or name == "run_command":
            return (
                f"BLOQUE: écriture directe interdite pour {name}. "
                "Utilisez le circuit d'approbation supervisée de la CLI."
            )
        if name not in self.allowed:
            return f"BLOQUE: outil {name} interdit dans le registre direct."
        if not isinstance(args, dict):
            return "ERREUR: arguments invalides"
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

def _extract_json_objects(text: str) -> list[dict]:
    """Extrait tous les objets JSON equilibres du texte."""
    import json
    results = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        start = i
        in_string = False
        escape = False
        for j in range(i, n):
            ch = text[j]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start:j+1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict) and "name" in obj:
                            results.append(obj)
                    except json.JSONDecodeError:
                        pass
                    i = j
                    break
        i += 1
    return results



def _normalize_args(obj: dict) -> dict:
    """Accepte 'args', 'arguments', 'params' ou 'parameters'.
    Le modele Qwen produit 'arguments' ; le code initial n'acceptait que 'args'."""
    if not isinstance(obj, dict):
        return {}
    for key in ("args", "arguments", "params", "parameters"):
        value = obj.get(key)
        if isinstance(value, dict):
            return value
    return {}


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Accepte les appels JSON structures vers les outils de lecture.
    Cherche d'abord les balises <tool_call>, puis tout objet JSON
    contenant une cle 'name' reconnue."""
    calls = []
    allowed = ALLOWED_TOOL_NAMES
    for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
        try:
            obj = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        name = obj.get("name") if isinstance(obj, dict) else None
        args = _normalize_args(obj) if isinstance(obj, dict) else {}
        if name in allowed:
            calls.append((name, args))
    if not calls:
        for obj in _extract_json_objects(text):
            name = obj.get("name")
            args = _normalize_args(obj)
            if name in allowed:
                calls.append((name, args))
    return calls

def make_standard_tools(root: Path, registry: ToolRegistry,
                        index=None):
    """Enregistre les outils standards."""
    root = Path(root).resolve()

    def read_file(path: str) -> str:
        import re as _re
        try:
            if not isinstance(path, str) or not path.strip():
                return 'ERREUR: chemin invalide'
            candidate = Path(path)
            if candidate.is_absolute():
                return 'ERREUR: chemin absolu interdit'
            p = (root / candidate).resolve(strict=True)
            p.relative_to(root)
        except (ValueError, OSError, RuntimeError):
            return 'ERREUR: chemin hors perimetre ou inaccessible'
        except Exception:
            return 'ERREUR: chemin invalide'
        parts = p.relative_to(root).parts
        if any(part.startswith('.patch_backups') for part in parts):
            return 'BLOQUE: fichier de sauvegarde prive'
        sensitive_dirs = {
            '.git', '.ssh', '.aws', '.azure', 'secrets', 'credentials',
            '.vscode', '.idea', '.cursor', '.claude', '.aider', '.continue',
        }
        if any(part.lower() in sensitive_dirs for part in parts):
            return 'BLOQUE: repertoire sensible'
        name = p.name.lower()
        blocked_names = {
            '.env', '.env.local', '.env.production', '.env.development',
            'credentials', 'credentials.json', 'secrets.json',
            'id_rsa', 'id_ed25519', 'known_hosts', 'authorized_keys',
            '.netrc', '.npmrc', '.pypirc', '.htpasswd', 'shadow',
            'secret', 'secrets', 'secret.txt', 'passwords.txt',
            'motdepasse', 'mot_de_passe', 'identifiants', 'confidentiel',
        }
        if name in blocked_names or name.startswith('.env.'):
            return 'BLOQUE: fichier sensible'
        if name.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore',
                          '.jks', '.asc', '.gpg')):
            return 'BLOQUE: fichier sensible'
        # Marqueurs multilingues dans le nom
        name_markers = (
            'password', 'passwd', 'credential', 'access_token',
            'refresh_token', 'private_key', 'api_key', 'apikey',
            'auth_token', 'bearer', 'secret', 'motdepasse',
            'mot_de_passe', 'jeton', 'cle_privee', 'cle_prive',
            'identifiant', 'identifiants', 'confidentiel',
        )
        if any(m in name for m in name_markers):
            return 'BLOQUE: fichier potentiellement sensible'
        # Mots courts verifies par segment (evite oracle/vehicle/muscle)
        segments = _re.split(r'[-_.]', name)
        short_risky = {'cle', 'key', 'keys', 'pwd', 'mdp', 'pass',
                       'token', 'tokens', 'auth', 'cred'}
        if any(seg in short_risky for seg in segments):
            return 'BLOQUE: fichier potentiellement sensible (segment sensible)'
        if not p.is_file():
            return 'ERREUR: cible non fichier'
        # --- Lecture limitee ---
        try:
            with p.open('rb') as stream:
                data = stream.read(8001)
            truncated = len(data) > 8000
            text = data[:8000].decode('utf-8', errors='replace')
        except OSError as exc:
            return f'ERREUR lecture {type(exc).__name__}'
        # --- Detection de motifs de secrets dans le CONTENU ---
        secret_patterns = [
            (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'cle privee PEM'),
            (r'-----BEGIN OPENSSH PRIVATE KEY-----', 'cle privee OpenSSH'),
            (r'AKIA[0-9A-Z]{16}', 'cle AWS Access Key'),
            (r'ASIA[0-9A-Z]{16}', 'cle AWS Session'),
            (r'ghp_[A-Za-z0-9]{36}', 'token GitHub'),
            (r'gho_[A-Za-z0-9]{36}', 'token GitHub OAuth'),
            (r'sk-[A-Za-z0-9]{20,}', 'cle OpenAI-like'),
            (r'sk-ant-[A-Za-z0-9_-]{20,}', 'cle Anthropic'),
            (r'xox[baprs]-[A-Za-z0-9-]{10,}', 'token Slack'),
            (r'AIza[0-9A-Za-z_-]{35}', 'cle Google API'),
            (r'ya29\.[0-9A-Za-z_-]{20,}', 'token OAuth Google'),
            (r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
             'JWT'),
        ]
        for pattern, label in secret_patterns:
            if _re.search(pattern, text):
                return (
                    f'BLOQUE: contenu sensible detecte ({label}). '
                    f'Fichier non transmis au modele.'
                )
        lines = text.split('\n')
        if truncated:
            lines[-1] = lines[-1] + ' [LECTURE TRONQUEE : limite de 8000 octets]'
        return '\n'.join(f"{i:4d}: {l}" for i, l in enumerate(lines, start=1))
    def list_files(pattern: str = "*.py", limit: int = 50) -> list[str]:
        import fnmatch
        import os as _os
        if not isinstance(pattern, str) or not pattern or len(pattern) > 100:
            return []
        if any(token in pattern for token in ('..', '/', '\\')):
            return []
        try:
            limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError, OverflowError):
            limit = 50
        excluded_dirs = {
            '.git', '.hg', '.svn',
            '__pycache__', '.venv', 'venv', 'env',
            'node_modules',
            '.next', 'dist', 'build', 'out', 'coverage', '.turbo',
            '.ssh', '.aws', '.azure', 'secrets', 'credentials',
            '.claude', '.cursor', '.aider', '.vscode', '.idea',
            '_safety_backup',
        }
        blocked_names = {
            '.env', '.env.local', '.env.production', 'credentials',
            'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519',
        }
        blocked_suffixes = ('.pem', '.key', '.p12', '.pfx', '.keystore')
        results: list[str] = []
        root_str = str(root)

        def onerror(_err):
            return

        for dirpath, dirnames, filenames in _os.walk(root_str, onerror=onerror):
            try:
                relative_dir = Path(dirpath).relative_to(root)
                parts = relative_dir.parts
                if any(
                    part in excluded_dirs
                    or part.startswith('.patch_backups')
                    for part in parts
                ):
                    dirnames[:] = []
                    continue
                dirnames[:] = [
                    d for d in dirnames
                    if d not in excluded_dirs
                    and not d.startswith('.patch_backups')
                ]
                for name in filenames:
                    try:
                        if not fnmatch.fnmatch(name, pattern):
                            continue
                        lower = name.lower()
                        if lower in blocked_names:
                            continue
                        if lower.endswith(blocked_suffixes):
                            continue
                        if any(marker in lower for marker in (
                            'password', 'credential', 'access_token',
                            'refresh_token', 'private_key',
                        )):
                            continue
                        full = Path(dirpath) / name
                        if full.is_symlink() or not full.is_file():
                            continue
                        rel = full.relative_to(root).as_posix()
                        results.append(rel)
                        if len(results) >= limit:
                            return results
                    except (OSError, ValueError, RuntimeError):
                        continue
            except (OSError, ValueError, RuntimeError):
                continue
        return results

    def find_symbol(name: str) -> list[dict]:
        if index is None:
            return []
        return [
            {"file": s.file, "line": s.line, "kind": s.kind,
             "name": s.name, "signature": s.signature}
            for s in index.find_symbol(name)
        ]

    def grep_file(pattern: str, max_results: int = 100) -> list[dict]:
        import re as _re
        import os as _os
        if not isinstance(pattern, str) or not pattern or len(pattern) > 200:
            return []
        try:
            max_results = max(1, min(int(max_results), 500))
        except (TypeError, ValueError, OverflowError):
            max_results = 100
        try:
            rx = _re.compile(pattern)
        except _re.error:
            return []
        excluded_dirs = {
            '.git', '.hg', '.svn',
            '__pycache__', '.venv', 'venv', 'env',
            'node_modules',
            '.next', 'dist', 'build', 'out', 'coverage', '.turbo',
            '.ssh', '.aws', '.azure', 'secrets', 'credentials',
            '.claude', '.cursor', '.aider', '.vscode', '.idea',
            '_safety_backup',
        }
        blocked_names = {
            '.env', '.env.local', '.env.production', 'credentials',
            'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519',
        }
        blocked_suffixes = ('.pem', '.key', '.p12', '.pfx', '.keystore')
        results: list[dict] = []
        root_str = str(root)

        def onerror(_err):
            return

        for dirpath, dirnames, filenames in _os.walk(root_str, onerror=onerror):
            try:
                relative_dir = Path(dirpath).relative_to(root)
                parts = relative_dir.parts
                if any(
                    part in excluded_dirs
                    or part.startswith('.patch_backups')
                    for part in parts
                ):
                    dirnames[:] = []
                    continue
                dirnames[:] = [
                    d for d in dirnames
                    if d not in excluded_dirs
                    and not d.startswith('.patch_backups')
                ]
                for name in filenames:
                    try:
                        lower = name.lower()
                        if lower in blocked_names:
                            continue
                        if lower.endswith(blocked_suffixes):
                            continue
                        if any(marker in lower for marker in (
                            'password', 'credential', 'access_token',
                            'refresh_token', 'private_key',
                        )):
                            continue
                        full = Path(dirpath) / name
                        if full.is_symlink() or not full.is_file():
                            continue
                        try:
                            if full.stat().st_size > 2_000_000:
                                continue
                        except OSError:
                            continue
                        try:
                            content = full.read_text(
                                encoding='utf-8', errors='replace'
                            )
                        except (OSError, UnicodeError):
                            continue
                        rel = full.relative_to(root).as_posix()
                        for i, line in enumerate(content.split('\n'), start=1):
                            if rx.search(line):
                                results.append({
                                    "file": rel,
                                    "line": i,
                                    "text": line[:500],
                                })
                                if len(results) >= max_results:
                                    return results
                    except (OSError, ValueError, RuntimeError):
                        continue
            except (OSError, ValueError, RuntimeError):
                continue
        return results

    def extract_lines(path: str, start: int, end: int) -> str:
        try:
            if not isinstance(path, str) or not path.strip():
                return 'ERREUR: chemin invalide'
            candidate = Path(path)
            if candidate.is_absolute():
                return 'ERREUR: chemin absolu interdit'
            p = (root / candidate).resolve(strict=True)
            p.relative_to(root)
        except (ValueError, OSError, RuntimeError):
            return 'ERREUR: chemin hors perimetre ou inaccessible'
        except Exception:
            return 'ERREUR: chemin invalide'
        parts = p.relative_to(root).parts
        if any(part.startswith('.patch_backups') for part in parts):
            return 'BLOQUE: fichier de sauvegarde prive'
        if any(part.lower() in {
    '.git', '.hg', '.svn',
    '__pycache__', '.venv', 'venv', 'env',
    'node_modules',
    '.next', 'dist', 'build', 'out', 'coverage', '.turbo',
    '.ssh', '.aws', '.azure', 'secrets', 'credentials',
} for part in parts):
            return 'BLOQUE: repertoire sensible'
        name = p.name.lower()
        blocked_names = {
            '.env', '.env.local', '.env.production', 'credentials',
            'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519',
            'known_hosts', 'authorized_keys',
        }
        if (name in blocked_names
                or name.startswith('.env.')
                or name.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore'))):
            return 'BLOQUE: fichier sensible'
        if any(marker in name for marker in (
            'password', 'credential', 'access_token',
            'refresh_token', 'private_key',
        )):
            return 'BLOQUE: fichier potentiellement sensible'
        if not p.is_file():
            return 'ERREUR: cible non fichier'
        try:
            start = max(1, int(start))
            end = max(start, int(end))
        except (TypeError, ValueError, OverflowError):
            return 'ERREUR: bornes invalides'
        if end - start > 500:
            return 'ERREUR: plage trop large (max 500 lignes)'
        try:
            with p.open('rb') as stream:
                data = stream.read(2_000_000)
            text = data.decode('utf-8', errors='replace')
            all_lines = text.split('\n')
            total = len(all_lines)
            if start > total:
                return f'ERREUR: start {start} > total {total}'
            end = min(end, total)
            selected = all_lines[start - 1:end]
            return '\n'.join(
                f"{i:4d}: {l}" for i, l in enumerate(selected, start=start)
            )
        except OSError as exc:
            return f'ERREUR lecture {type(exc).__name__}'

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

    registry.register(Tool(
        "grep_file",
        "Cherche une expression reguliere dans tous les fichiers texte du projet. "
        "Retourne fichier, numero de ligne et contenu. Deterministique.",
        {"type": "object",
         "properties": {"pattern": {"type": "string"},
                        "max_results": {"type": "integer"}},
         "required": ["pattern"]},
        grep_file))

    registry.register(Tool(
        "extract_lines",
        "Extrait un bloc de lignes numerote d'un fichier. "
        "start et end sont des numeros de ligne (1-indexed, inclus). Deterministique.",
        {"type": "object",
         "properties": {"path": {"type": "string"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"}},
         "required": ["path", "start", "end"]},
        extract_lines))
