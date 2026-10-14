#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_v2.py - Integre AssistantV2 dans memolibdev_gui_v4.py (4 patches)."""
from __future__ import annotations
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


# ---- Blocs a inserer -------------------------------------------------

IMPORTS = """
# --- V2 : assistant conversationnel ---
try:
    from assistant_v2 import AssistantV2
    from codebase_index import CodebaseIndex
    _V2_AVAILABLE = True
except Exception as _v2_err:
    _V2_AVAILABLE = False
    _V2_IMPORT_ERR = str(_v2_err)
"""

INIT_BLOCK = '''
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

METHODS = '''    def _append_stream(self, chunk: str):
        """Ajoute un token au fil de discussion (streaming V2)."""
        try:
            self.chat.configure(state="normal")
            self.chat.insert("end", chunk)
            self.chat.see("end")
        except Exception:
            pass

    def _new_conversation(self):
        """Repart sur une nouvelle conversation V2."""
        if getattr(self, "_v2_ready", False):
            try:
                self._v2_assistant.new_conversation()
            except Exception as e:
                self._system(f"Reset V2 echoue : {e}")
        try:
            self.chat.delete("1.0", "end")
        except Exception:
            pass

    def v2_chat(self, text: str) -> bool:
        """Chat V2 avec streaming. Retourne True si V2 a traite le message."""
        if not getattr(self, "_v2_ready", False):
            return False
        self._user(text)
        self._system("V2 en cours...")

        def on_token(chunk):
            self.after(0, lambda c=chunk: self._append_stream(c))

        try:
            response = self._v2_assistant.chat(text, on_token=on_token)
            self._system(f"V2 termine ({len(response)} caracteres)")
            self.messages.append(f"[V2] {response}")
            return True
        except Exception as e:
            self._system(f"V2 erreur : {e}")
            return False

'''

ON_SEND_OLD = """    def _on_send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return

        if getattr(self, "_identity_check_pending", False):
            return
"""

ON_SEND_NEW = """    def _on_send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return

        if getattr(self, "_identity_check_pending", False):
            return

        # --- V2 : priorite si disponible ---
        if getattr(self, "_v2_ready", False):
            self.entry.delete("1.0", "end")
            if self.v2_chat(text):
                return
        # --- sinon, continuer avec la CLI existante ---
"""


# ---- Application -----------------------------------------------------

def patch():
    log("=" * 72)
    log("PATCH GUI V2")
    log("=" * 72)
    log(f"Cible : {TARGET.name}")
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    if "_V2_AVAILABLE" in src:
        log("Deja patche. Rien a faire.")
        return 0

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    lines = src.splitlines(keepends=True)

    # [1] Imports apres "import customtkinter as ctk"
    log("[1/4] Ajout des imports V2...")
    idx_imp = None
    for i, l in enumerate(lines[:60]):
        if l.strip() == "import customtkinter as ctk":
            idx_imp = i + 1
            break
    if idx_imp is None:
        log("  ERREUR : 'import customtkinter as ctk' introuvable.")
        return 1
    lines.insert(idx_imp, IMPORTS)
    log(f"  -> insere apres la ligne {idx_imp}")

    # [2] Init V2 dans __init__ apres "self.busy = False"
    log("[2/4] Ajout de l'init V2 dans __init__...")
    src2 = "".join(lines)
    lines = src2.splitlines(keepends=True)
    idx_busy = None
    for i, l in enumerate(lines):
        if l.strip() == "self.busy = False":
            idx_busy = i + 1
            break
    if idx_busy is None:
        log("  ERREUR : 'self.busy = False' introuvable.")
        return 1
    lines.insert(idx_busy, INIT_BLOCK)
    log(f"  -> insere apres la ligne {idx_busy}")

    # [3] Methodes V2 avant "def _on_send"
    log("[3/4] Ajout des methodes V2 avant _on_send...")
    src3 = "".join(lines)
    lines = src3.splitlines(keepends=True)
    idx_send = None
    for i, l in enumerate(lines):
        if l.strip() == "def _on_send(self):":
            idx_send = i
            break
    if idx_send is None:
        log("  ERREUR : 'def _on_send(self):' introuvable.")
        return 1
    lines.insert(idx_send, METHODS)
    log(f"  -> insere avant la ligne {idx_send + 1}")

    # [4] Priorite V2 dans _on_send
    log("[4/4] Activation V2 dans _on_send...")
    src4 = "".join(lines)
    if ON_SEND_OLD not in src4:
        log("  ERREUR : bloc _on_send initial introuvable.")
        log("  Restaurez : git checkout -- memolibdev_gui_v4.py")
        return 1
    src4 = src4.replace(ON_SEND_OLD, ON_SEND_NEW, 1)
    log("  -> priorite V2 ajoutee")

    # Ecriture + verif syntaxe
    TARGET.write_text(src4, encoding="utf-8")
    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src4)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  Restauration...")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Fichier restaure depuis backup.")
        return 1

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Test :")
    log("  python .\\memolibdev_gui_v4.py")
    log()
    log("Attendu au demarrage : [V2] Assistant conversationnel pret.")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(patch())