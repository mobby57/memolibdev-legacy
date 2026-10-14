#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_parser.py - Detecte les tool_calls dans plusieurs formats."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "tool_use.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "_extract_json_objects" in src:
    print("Deja patche.")
    raise SystemExit(0)

NEW_FUNC = '''def _extract_json_objects(text: str) -> list[dict]:
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
            if ch == "\\\\":
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


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Detecte les appels d'outils dans plusieurs formats.

    Formats supportes :
    1. <tool_call>{"name": ..., "args": ...}</tool_call>
    2. JSON brut {"name": ..., "args": ...} (sans balises)
    """
    import json
    import re
    calls = []

    # Format 1 : balises <tool_call>
    for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
            name = obj.get("name")
            args = obj.get("args", {})
            if name:
                calls.append((name, args))
        except json.JSONDecodeError:
            continue

    # Format 2 : JSON brut (si aucun tool_call trouve)
    if not calls:
        for obj in _extract_json_objects(text):
            name = obj.get("name")
            args = obj.get("args", {})
            if name and name in (
                "read_file", "list_files", "find_symbol",
                "write_file", "edit_file", "delete_file", "run_command"
            ):
                calls.append((name, args))

    return calls
'''

# Trouver la fonction existante parse_tool_calls
import re as _re
pattern = _re.compile(
    r"def parse_tool_calls\(text: str\) -> list\[tuple\[str, dict\]\]:.*?(?=\n\ndef |\n\nclass |\Z)",
    _re.DOTALL,
)
m = pattern.search(src)

if m:
    src2 = src[:m.start()] + NEW_FUNC + src[m.end():]
else:
    print("ERREUR : parse_tool_calls introuvable")
    raise SystemExit(1)

try:
    ast.parse(src2)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src2, encoding="utf-8")
print("OK - parse_tool_calls ameliore (balises + JSON brut)")
print(f"Backup : {BK.name}/")