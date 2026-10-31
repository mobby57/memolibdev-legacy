#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import re

p = Path("assistant_v2.py")
src = p.read_text(encoding="utf-8")

new_prompt = '''SYSTEM_PROMPT = """Tu es MemoLibDev, assistant de code local.

OUTILS : read_file(path), list_files(pattern), find_symbol(name).

REGLES :
- Reponds TOUJOURS en francais, directement.
- Pour lire un fichier, emets :
<tool_call>{"name": "read_file", "args": {"path": "..."}}</tool_call>
- Ne dis JAMAIS "je ne peux pas lire les fichiers".
- Reponds en 2-5 phrases concises."""'''

src2, n = re.subn(
    r'SYSTEM_PROMPT\s*=\s*""".*?"""',
    new_prompt,
    src,
    count=1,
    flags=re.DOTALL,
)

if n == 0:
    print("ECHEC : SYSTEM_PROMPT introuvable")
elif src2 == src:
    print("PAS CHANGE")
else:
    p.write_text(src2, encoding="utf-8")
    print("OK - prompt remplace")