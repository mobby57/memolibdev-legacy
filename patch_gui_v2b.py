#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_v2b.py - Fix affichage V2 + menu modeles."""
from __future__ import annotations
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


# ----------------------------------------------------------------------
# Blocs
# ----------------------------------------------------------------------
NEW_V2CHAT = '''    def v2_chat(self, text: str) -> bool:
        """Chat V2 avec streaming dans une bulle dediee."""
        if not getattr(self, "_v2_ready", False):
            return False

        # Bulle utilisateur
        self._user(text)

        # --- Bulle assistant vide qui va recevoir le streaming ---
        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=8)
        b = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14)
        b.pack(anchor="w", padx=(0, 20), fill="x")

        header = ctk.CTkFrame(b, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            header, text="MemoLibDev", text_color=ACCENT,
            font=ctk.CTkFont(size=10, weight="bold"), anchor="w",
        ).pack(side="left")

        content = ctk.CTkTextbox(
            b, height=120, wrap="word",
            fg_color=CARD, text_color=TEXT,
            border_width=0, font=ctk.CTkFont(size=12),
        )
        content.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        content.insert("1.0", "")
        content.configure(state="disabled")

        self._stream_box = content
        self._stream_buffer = []

        def on_token(chunk):
            self.after(0, lambda c=chunk: self._append_stream(c))

        try:
            response = self._v2_assistant.chat(text, on_token=on_token)
            self.messages.append(f"[MemoLibDev] {response}")
            return True
        except Exception as e:
            self._system(f"V2 erreur : {e}")
            return False

    def _append_stream(self, chunk: str):
        """Ajoute un token a la bulle de streaming."""
        box = getattr(self, "_stream_box", None)
        if box is None:
            return
        try:
            box.configure(state="normal")
            box.insert("end", chunk)
            box.see("end")
            box.configure(state="disabled")
            self.after(10, self._scroll)
        except Exception:
            pass
'''

LOAD_MODELS = '''
        # Charger la liste des modeles Ollama
        try:
            import json as _json
            _req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(_req, timeout=3) as _r:
                _data = _json.loads(_r.read().decode("utf-8"))
            self._available_models = [m["name"] for m in _data.get("models", [])]
            if not self._available_models:
                self._available_models = [DEFAULT_MODEL]
        except Exception:
            self._available_models = [DEFAULT_MODEL]
'''

MENU_BLOCK = '''        try:
            ctk.CTkOptionMenu(
                header,
                values=self._available_models or [DEFAULT_MODEL],
                variable=self.model_var,
                width=200,
            ).pack(side="right", padx=(8, 0))
        except Exception:
            pass
'''


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def find_method_range(lines, method_name):
    """Retourne (start, end) d'une methode (indentation 4)."""
    start = None
    indent = None
    for i, l in enumerate(lines):
        stripped = l.lstrip()
        if stripped.startswith(f"def {method_name}("):
            start = i
            indent = len(l) - len(stripped)
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        l = lines[i]
        if not l.strip():
            continue
        cur_indent = len(l) - len(l.lstrip())
        if cur_indent == indent and (l.lstrip().startswith("def ") or
                                      l.lstrip().startswith("@")):
            end = i
            break
    return (start, end)


def replace_method(lines, method_name, new_block):
    rng = find_method_range(lines, method_name)
    if rng is None:
        return None
    start, end = rng
    new_lines = new_block.splitlines(keepends=True)
    if not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    return lines[:start] + new_lines + lines[end:]


# ----------------------------------------------------------------------
# Patch
# ----------------------------------------------------------------------
def patch():
    log("=" * 72)
    log("PATCH GUI V2b - fix affichage + menu modeles")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # ---- [1] Remplacer v2_chat ----
    log("[1/4] Remplacement de v2_chat (streaming dans une bulle)...")
    new_lines = replace_method(lines, "v2_chat", NEW_V2CHAT)
    if new_lines is None:
        log("  ERREUR : v2_chat introuvable.")
        return 1
    lines = new_lines
    log("  -> v2_chat remplace")

    # ---- [2] Supprimer _append_stream (le nouveau bloc le contient) ----
    log("[2/4] Suppression de l'ancien _append_stream...")
    rng = find_method_range(lines, "_append_stream")
    if rng:
        # On a maintenant DEUX _append_stream. Supprimer le premier (ancien).
        # Le nouveau est dans NEW_V2CHAT, l'ancien est avant v2_chat.
        # On cherche le premier _append_stream et on le supprime.
        first = find_method_range(lines, "_append_stream")
        # S'il y a deux occurrences, supprimer la premiere
        start, end = first
        # Verifier qu'il y en a bien deux
        count = sum(1 for l in lines if l.lstrip().startswith("def _append_stream("))
        if count > 1:
            lines = lines[:start] + lines[end:]
            log(f"  -> ancien _append_stream supprime (total etait {count})")
        else:
            log("  -> un seul _append_stream, pas de suppression")
    else:
        log("  -> _append_stream absent (OK)")

    # ---- [3] Charger les modeles Ollama ----
    log("[3/4] Ajout du chargement des modeles...")
    src2 = "".join(lines)
    if "_available_models" in src2:
        log("  -> deja present, skip.")
    else:
        # Trouve la ligne "self.model_var = ctk.StringVar(...)"
        for i, l in enumerate(lines):
            if "self.model_var" in l and "StringVar" in l:
                lines.insert(i + 1, LOAD_MODELS)
                log(f"  -> insere apres la ligne {i + 1}")
                break
        else:
            log("  ERREUR : 'self.model_var' introuvable.")
            return 1

    # ---- [4] Ajouter le menu dans le header ----
    log("[4/4] Ajout du menu deroulant des modeles...")
    src3 = "".join(lines)
    if "CTkOptionMenu" in src3 and "_available_models" in src3.split("CTkOptionMenu")[0][-2000:]:
        log("  -> menu deja present, skip.")
    else:
        # Cherche "Sauver log" et insere le menu avant
        for i, l in enumerate(lines):
            if "Sauver log" in l and ("Button" in l or "CTkButton" in l or "text=" in l):
                # Insere avant cette ligne (le "with" est avant)
                # On cherche la ligne d'ouverture du bouton
                insert_at = i
                # Remonter pour trouver le debut du statement (with ctk.CTkButton...)
                while insert_at > 0:
                    prev = lines[insert_at - 1].strip()
                    if prev.endswith(":") or "CTkButton" in prev or prev == "":
                        break
                    insert_at -= 1
                lines.insert(insert_at, MENU_BLOCK)
                log(f"  -> menu insere avant la ligne {i + 1}")
                break
        else:
            log("  ATTENTION : 'Sauver log' introuvable, menu non ajoute.")

    # ---- Ecriture + verif ----
    src4 = "".join(lines)
    TARGET.write_text(src4, encoding="utf-8")

    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src4)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        log(f"  Restauration depuis backup...")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Fichier restaure.")
        return 1

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Relancez la GUI :")
    log("  python .\\memolibdev_gui_v4.py")
    log()
    log("Attendu :")
    log("  - Reponse en streaming dans une bulle grise")
    log("  - Menu deroulant des modeles en haut a droite")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(patch())