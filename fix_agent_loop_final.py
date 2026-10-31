#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_agent_loop_final.py - Boucle agentique + UX dans la GUI."""
from __future__ import annotations
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V2 = ROOT / "assistant_v2.py"
GUI = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


# =====================================================================
# PATCH V2 : ajouter _run_agent_loop + chat_with_tools
# =====================================================================
V2_METHODS = '''    def _run_agent_loop(self, prompt: str, max_iters: int = 3):
        """Execute les <tool_call> du modele jusqu'a reponse finale."""
        from tool_use import parse_tool_calls
        for _ in range(max_iters):
            response = ""
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                response += chunk

            calls = parse_tool_calls(response)
            if not calls:
                return response, []

            results = []
            for name, args in calls:
                res = self.registry.execute(name, args)
                results.append(f"[{name}] {res[:1500]}")

            prompt = (
                prompt
                + "\\n\\n--- Reponse precedente ---\\n"
                + response
                + "\\n\\n--- Resultats outils ---\\n"
                + "\\n".join(results)
                + "\\n\\n--- Ta reponse finale en francais, sans tool_call ---\\n"
            )
        return response, results

    def chat_with_tools(
        self,
        user_text: str,
        on_token=None,
    ) -> str:
        """Chat avec boucle agentique : execute les outils automatiquement."""
        self.conversation.add("user", user_text)
        prompt = self.build_prompt(user_text)
        response, _ = self._run_agent_loop(prompt)
        if on_token and response:
            on_token(response)
        self.conversation.add("assistant", response)
        return response

'''


def patch_v2():
    log("[1/3] Patch assistant_v2.py (boucle agentique)...")
    if not V2.exists():
        log(f"  ERREUR : {V2.name} introuvable.")
        return False

    src = V2.read_text(encoding="utf-8")

    if "def chat_with_tools" in src and "def _run_agent_loop" in src:
        log("  -> deja patche, skip")
        return True

    # Chercher l'ancre : la fin de la classe, ou avant "def chat("
    anchor = "    def chat(\n"
    if anchor not in src:
        log(f"  ERREUR : 'def chat(' introuvable.")
        return False

    src = src.replace(anchor, V2_METHODS + anchor, 1)

    try:
        ast.parse(src)
    except SyntaxError as e:
        log(f"  ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        return False

    shutil.copy2(V2, BK / V2.name)
    V2.write_text(src, encoding="utf-8")
    log("  -> _run_agent_loop + chat_with_tools ajoutes")
    return True


# =====================================================================
# PATCH GUI : spinner + chat_with_tools + etapes
# =====================================================================
GUI_UX_METHODS = '''    def _show_spinner(self, message: str = "En cours"):
        self._spinner_frames = ["|", "/", "-", "\\\\"]
        self._spinner_idx = 0
        self._spinner_msg = message
        self._spinner_active = True
        self._tick_spinner()

    def _tick_spinner(self):
        if not getattr(self, "_spinner_active", False):
            return
        try:
            frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
            self._spinner_idx += 1
            self.status.configure(
                text=f"{frame}  {self._spinner_msg}",
                text_color=ACCENT,
            )
            self.after(120, self._tick_spinner)
        except Exception:
            pass

    def _stop_spinner(self, final_text: str = "Pret."):
        self._spinner_active = False
        try:
            self.status.configure(text=final_text, text_color=MUTED)
        except Exception:
            pass

    def _update_spinner(self, message: str):
        self._spinner_msg = message

'''


def patch_gui():
    log("[2/3] Patch memolibdev_gui_v4.py (spinner + chat_with_tools)...")
    if not GUI.exists():
        log(f"  ERREUR : {GUI.name} introuvable.")
        return False

    src = GUI.read_text(encoding="utf-8")
    changes = []

    # 1. Ajouter les methodes spinner avant v2_chat
    if "_show_spinner" not in src:
        anchor = "    def v2_chat(self, text: str) -> bool:"
        if anchor in src:
            src = src.replace(anchor, GUI_UX_METHODS + anchor, 1)
            changes.append("spinner ajoute")
        else:
            changes.append("ANCRE v2_chat introuvable")
            return False

    # 2. Remplacer chat() par chat_with_tools() dans v2_chat
    old_call = "response = self._v2_assistant.chat(text, on_token=on_token)"
    new_call = "response = self._v2_assistant.chat_with_tools(text, on_token=on_token)"
    if old_call in src:
        src = src.replace(old_call, new_call, 1)
        changes.append("chat_with_tools active")
    elif new_call in src:
        changes.append("chat_with_tools deja actif")
    else:
        changes.append("ANCRE chat() introuvable")

    # 3. Ajouter spinner au debut de v2_chat
    old_start = '''        self._user(text)

        # Bulle assistant vide pour le streaming'''
    new_start = '''        self._user(text)
        self.send_btn.configure(state="disabled")
        self._show_spinner("Analyse en cours...")

        # Bulle assistant vide pour le streaming'''
    if "_show_spinner(\"Analyse" in src:
        changes.append("spinner deja cable")
    elif old_start in src:
        src = src.replace(old_start, new_start, 1)
        changes.append("spinner cable")
    else:
        # Fallback : chercher self._user(text)
        if "        self._user(text)\n" in src and "_show_spinner" not in src.split("def v2_chat")[1][:500]:
            src = src.replace(
                "        self._user(text)\n",
                '        self._user(text)\n        self.send_btn.configure(state="disabled")\n        self._show_spinner("Analyse en cours...")\n',
                1,
            )
            changes.append("spinner cable (fallback)")

    # 4. Stop spinner a la fin de v2_chat (avant return True/False)
    if "_stop_spinner(\"Pret.\")" not in src:
        # Chercher les deux return de v2_chat
        src = src.replace(
            "            return True\n        except Exception as e:\n            self._system(f\"V2 erreur : {e}\")\n            return False",
            "            self._stop_spinner(\"Pret.\")\n            self.send_btn.configure(state=\"normal\")\n            return True\n        except Exception as e:\n            self._system(f\"V2 erreur : {e}\")\n            self._stop_spinner(\"Erreur.\")\n            self.send_btn.configure(state=\"normal\")\n            return False",
            1,
        )
        changes.append("stop spinner cable")

    for c in changes:
        log(f"  -> {c}")

    if "ANCRE" in " ".join(changes):
        log("  ERREUR : ancre manquante, rollback.")
        return False

    try:
        ast.parse(src)
    except SyntaxError as e:
        log(f"  ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        return False

    shutil.copy2(GUI, BK / GUI.name)
    GUI.write_text(src, encoding="utf-8")
    log("  -> GUI patchee")
    return True


# =====================================================================
# VERIF
# =====================================================================
def verify():
    log("[3/3] Verification finale...")
    checks = [
        (V2, "def _run_agent_loop", "V2 : _run_agent_loop"),
        (V2, "def chat_with_tools", "V2 : chat_with_tools"),
        (GUI, "def _show_spinner", "GUI : spinner"),
        (GUI, "chat_with_tools", "GUI : utilise chat_with_tools"),
        (GUI, "_stop_spinner", "GUI : arret spinner"),
    ]
    all_ok = True
    for path, needle, label in checks:
        if not path.exists():
            log(f"  [MANQUE] {label} (fichier absent)")
            all_ok = False
            continue
        if needle in path.read_text(encoding="utf-8"):
            log(f"  [OK] {label}")
        else:
            log(f"  [MANQUE] {label}")
            all_ok = False
    return all_ok


def main():
    log("=" * 72)
    log("FIX AGENT LOOP + UX")
    log("=" * 72)
    log()

    BK.mkdir(exist_ok=True)
    log(f"Backups : {BK.name}/")
    log()

    if not patch_v2():
        log("ECHEC : patch V2")
        return 1
    log()

    if not patch_gui():
        log("ECHEC : patch GUI")
        return 1
    log()

    if not verify():
        log("ECHEC : verification")
        return 1

    log()
    log("=" * 72)
    log("SUCCES")
    log("=" * 72)
    log()
    log("Relancez :")
    log("  $env:PYTHONIOENCODING = 'utf-8'")
    log("  python .\\memolibdev_gui_v4.py")
    log()
    log("Test GUI : 'Cherche la fonction handleSubmit dans le projet'")
    log("Attendu : le modele utilise find_symbol et donne le fichier")
    log()
    log("Rollback :")
    log(f"  Copy-Item {BK.name}\\* . -Force")
    return 0


if __name__ == "__main__":
    sys.exit(main())