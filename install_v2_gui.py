#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install_v2_gui.py - Installe V2 dans memolibdev_gui_v4.py."""
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


# 1. IMPORTS
IMPORTS_BLOCK = '''import customtkinter as ctk

# --- V2 : assistant conversationnel ---
try:
    from assistant_v2 import AssistantV2
    from codebase_index import CodebaseIndex
    _V2_AVAILABLE = True
except Exception as _v2_err:
    _V2_AVAILABLE = False
    _V2_IMPORT_ERR = str(_v2_err)
'''

# 2. INIT dans __init__
INIT_ANCHOR = "        self.busy = False\n"
INIT_BLOCK = '''        self.busy = False

        # --- V2 : initialisation de l'assistant conversationnel ---
        if _V2_AVAILABLE:
            try:
                self._v2_index = CodebaseIndex(Path(".").resolve())
                self._v2_index.build()
                self._v2_assistant = AssistantV2(
                    Path(".").resolve(),
                    index=self._v2_index,
                )
                self._v2_ready = True
                print("[V2] Assistant conversationnel pret.")
            except Exception as _e:
                self._v2_ready = False
                print(f"[V2] init echouee : {_e}")
        else:
            self._v2_ready = False
            print(f"[V2] modules indisponibles : {_V2_IMPORT_ERR}")
'''

# 3. METHODES (v2_chat + _append_stream)
METHODS_ANCHOR = "    def _on_send(self):\n"
METHODS_BLOCK = '''    def v2_chat(self, text: str) -> bool:
        """Chat V2 avec streaming dans une bulle dediee."""
        if not getattr(self, "_v2_ready", False):
            return False

        self._user(text)

        # Bulle assistant vide pour le streaming
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


def main():
    log("=" * 72)
    log("INSTALL V2 GUI - imports + init + v2_chat + _append_stream")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log(f"ERREUR : {TARGET.name} introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # [1] Imports
    log("[1/3] Ajout des imports V2...")
    if "_V2_AVAILABLE" in src:
        log("  -> deja present, skip")
    elif "import customtkinter as ctk\n" in src:
        src = src.replace(
            "import customtkinter as ctk\n",
            IMPORTS_BLOCK,
            1,
        )
        log("  -> imports ajoutes")
    else:
        log("  ERREUR : 'import customtkinter as ctk' introuvable.")
        return 1

    # [2] Init dans __init__
    log("[2/3] Ajout de l'init V2 dans __init__...")
    if "self._v2_assistant = AssistantV2" in src:
        log("  -> deja present, skip")
    elif INIT_ANCHOR in src:
        src = src.replace(INIT_ANCHOR, INIT_BLOCK, 1)
        log("  -> init ajoutee")
    else:
        log("  ERREUR : 'self.busy = False' introuvable.")
        return 1

    # [3] Methodes v2_chat + _append_stream
    log("[3/3] Ajout des methodes v2_chat + _append_stream...")
    if "def v2_chat" in src and "def _append_stream" in src:
        log("  -> deja presente, skip")
    elif METHODS_ANCHOR in src:
        src = src.replace(METHODS_ANCHOR, METHODS_BLOCK + METHODS_ANCHOR, 1)
        log("  -> methodes ajoutees")
    else:
        log("  ERREUR : 'def _on_send(self):' introuvable.")
        return 1

    # Verif syntaxe
    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Restaure depuis backup.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    # Verif finale
    log()
    log("Verifications finales :")
    checks = [
        ("_V2_AVAILABLE", "imports"),
        ("self._v2_assistant = AssistantV2", "init"),
        ("def v2_chat", "methode v2_chat"),
        ("def _append_stream", "methode _append_stream"),
        ("if self.v2_chat(text)", "routage _on_send"),
    ]
    all_ok = True
    for needle, label in checks:
        if needle in src:
            log(f"  [OK] {label}")
        else:
            log(f"  [MANQUE] {label}")
            all_ok = False

    log()
    if all_ok:
        log("=" * 72)
        log("INSTALLATION REUSSIE")
        log("=" * 72)
        log()
        log("Relancez :")
        log("  $env:PYTHONIOENCODING = 'utf-8'")
        log("  python .\\memolibdev_gui_v4.py")
        log()
        log("Dans le terminal, cherchez :")
        log("  [V2] Assistant conversationnel pret.")
        log()
        log("Puis dans la GUI, envoyez : 'bonjour'")
        log("La reponse doit arriver mot par mot dans une bulle.")
    else:
        log("PROBLEME : certaines verifications ont echoue.")
        log(f"Restaurez : git checkout -- {TARGET.name}")
        return 1

    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())