#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_ux_waiting.py - Spinner + etapes + streaming visible."""
from pathlib import Path
import ast
import re
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "_show_spinner" in src:
    print("Deja patche.")
    raise SystemExit(0)

# 1. Ajouter les methodes UX avant v2_chat
UX_METHODS = '''    def _show_spinner(self, message: str = "En cours"):
        """Affiche un indicateur anime dans le status."""
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
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
            self.after(100, self._tick_spinner)
        except Exception:
            pass

    def _stop_spinner(self, final_text: str = "Prêt."):
        self._spinner_active = False
        try:
            self.status.configure(text=final_text, text_color=MUTED)
        except Exception:
            pass

    def _update_spinner(self, message: str):
        self._spinner_msg = message

'''

anchor = "    def v2_chat(self, text: str) -> bool:"
if anchor not in src:
    print("ERREUR : 'def v2_chat' introuvable")
    raise SystemExit(1)

src = src.replace(anchor, UX_METHODS + anchor, 1)
print("-> methodes spinner ajoutees")

# 2. Remplacer v2_chat par une version avec etapes
OLD_CHAT_START = "    def v2_chat(self, text: str) -> bool:"
idx = src.index(OLD_CHAT_START)
after = src[idx + len(OLD_CHAT_START):]
next_def = after.find("\n    def ")
if next_def == -1:
    end_idx = len(src)
else:
    end_idx = idx + len(OLD_CHAT_START) + next_def + 1

NEW_V2CHAT = '''    def v2_chat(self, text: str) -> bool:
        """Chat V2 avec etapes visibles + streaming."""
        if not getattr(self, "_v2_ready", False):
            return False

        self._user(text)
        self.send_btn.configure(state="disabled")
        self._show_spinner("Preparation...")

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

        # Petit label "recherche en cours..."
        progress_lbl = ctk.CTkLabel(
            b, text="Recherche...", text_color=MUTED,
            font=ctk.CTkFont(size=10, slant="italic"), anchor="w",
        )
        progress_lbl.pack(fill="x", padx=14, pady=(0, 4))

        content = ctk.CTkTextbox(
            b, height=120, wrap="word",
            fg_color=CARD, text_color=TEXT,
            border_width=0, font=ctk.CTkFont(size=12),
        )
        content.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        content.insert("1.0", "")
        content.configure(state="disabled")

        self._stream_box = content
        self._stream_started = False

        def on_token(chunk):
            if not self._stream_started:
                self._stream_started = True
                self.after(0, lambda: progress_lbl.configure(text="Redaction..."))
                self.after(0, lambda: self._update_spinner("Redaction de la reponse..."))
            self.after(0, lambda c=chunk: self._append_stream(c))

        try:
            response = self._v2_assistant.chat(text, on_token=on_token)
            self.messages.append(f"[MemoLibDev] {response}")
            progress_lbl.destroy()
            self._stop_spinner("Pret.")
            self.send_btn.configure(state="normal")
            return True
        except Exception as e:
            self._system(f"V2 erreur : {e}")
            progress_lbl.destroy()
            self._stop_spinner("Erreur.")
            self.send_btn.configure(state="normal")
            return False

'''

src2 = src[:idx] + NEW_V2CHAT + src[end_idx:]

try:
    ast.parse(src2)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    print(f"  {e.text}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src2, encoding="utf-8")
print(f"OK - UX ameliorations ajoutees")
print()
print("Relancez : python .\\memolibdev_gui_v4.py")