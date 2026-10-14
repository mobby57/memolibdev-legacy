#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_sidebar.py - Etape 1 : sidebar gauche (items visuels inertes)."""
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


# --- Bloc sidebar a inserer avant "header = ctk.CTkFrame" ---
SIDEBAR_BLOCK = '''        # --- Sidebar gauche (navigation) ---
        sidebar = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=0, width=200
        )
        sidebar.grid(row=0, column=0, rowspan=5, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        # En-tete sidebar
        sb_head = ctk.CTkFrame(sidebar, fg_color="transparent")
        sb_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 4))
        ctk.CTkLabel(
            sb_head, text="MemoLibDev",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=ACCENT, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            sb_head, text="AI Workspace",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=MUTED, anchor="w",
        ).pack(fill="x")

        # Separateur
        ctk.CTkFrame(
            sidebar, fg_color=BORDER, height=1,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(12, 8))

        # Items de navigation (visuels uniquement pour l'instant)
        nav_items = [
            ("Dialogue IA", True),
            ("Missions", False),
            ("Fichiers", False),
            ("Propositions", False),
            ("Controles", False),
        ]
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="ew", padx=8)
        for idx, (label, actif) in enumerate(nav_items):
            fg = ACCENT if actif else "transparent"
            tc = "#ffffff" if actif else TEXT
            ctk.CTkLabel(
                nav_frame, text=f"  {label}",
                font=ctk.CTkFont(size=12),
                text_color=tc, fg_color=fg,
                anchor="w", height=32,
            ).pack(fill="x", pady=1, padx=4)

        # Pied : projet actif
        sidebar.grid_rowconfigure(3, weight=1)
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 16))
        ctk.CTkFrame(
            footer, fg_color=BORDER, height=1,
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            footer, text="Projet actif",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=MUTED, anchor="w",
        ).pack(fill="x")
        self._sidebar_project_label = ctk.CTkLabel(
            footer, text="(aucun)",
            font=ctk.CTkFont(size=11),
            text_color=TEXT, anchor="w",
        )
        self._sidebar_project_label.pack(fill="x")

'''


def patch():
    log("=" * 72)
    log("ADD SIDEBAR - etape 1")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log(f"ERREUR : {TARGET.name} introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    if "_sidebar_project_label" in src:
        log("Deja patche. Rien a faire.")
        return 0

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # [1] Configuration grid : 2 colonnes
    log("[1/5] Configuration grid (2 colonnes)...")
    old_grid = "        self.grid_columnconfigure(0, weight=1)\n        self.grid_rowconfigure(1, weight=1)\n"
    new_grid = "        self.grid_columnconfigure(0, weight=0)\n        self.grid_columnconfigure(1, weight=1)\n        self.grid_rowconfigure(1, weight=1)\n"
    if old_grid in src:
        src = src.replace(old_grid, new_grid, 1)
        log("  -> 2 colonnes configurees")
    else:
        log("  ERREUR : ligne grid_columnconfigure introuvable.")
        return 1

    # [2] Insertion de la sidebar avant header
    log("[2/5] Insertion de la sidebar...")
    anchor = "        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=64)"
    if anchor not in src:
        log("  ERREUR : 'header = ctk.CTkFrame' introuvable.")
        return 1
    src = src.replace(anchor, SIDEBAR_BLOCK + anchor, 1)
    log("  -> sidebar inseree")

    # [3] Decaler header.grid column=0 -> column=1
    log("[3/5] Decalage du header...")
    old_h = 'header.grid(row=0, column=0, sticky="ew")'
    new_h = 'header.grid(row=0, column=1, sticky="ew")'
    if old_h in src:
        src = src.replace(old_h, new_h, 1)
        log("  -> header -> column=1")

    # [4] Decaler chat, sug, inp, status
    log("[4/5] Decalage du contenu principal...")
    replacements = [
        (
            'self.chat.grid(row=1, column=0, sticky="nsew")',
            'self.chat.grid(row=1, column=1, sticky="nsew")',
        ),
        (
            'sug.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 4))',
            'sug.grid(row=2, column=1, sticky="ew", padx=16, pady=(8, 4))',
        ),
        (
            'inp.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 6))',
            'inp.grid(row=3, column=1, sticky="ew", padx=16, pady=(4, 6))',
        ),
        (
            'self.status.grid(row=4, column=0, sticky="w", padx=20, pady=(0, 8))',
            'self.status.grid(row=4, column=1, sticky="w", padx=20, pady=(0, 8))',
        ),
    ]
    n_shifted = 0
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
            n_shifted += 1
    log(f"  -> {n_shifted}/4 widgets deplaces")

    # [5] Cable : mettre a jour le label projet sidebar
    log("[5/5] Cable du label projet sidebar...")
    # On modifie la methode _choose_project pour mettre a jour le label sidebar
    old_choose = '''        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")'''
    new_choose = '''        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
            try:
                self._sidebar_project_label.configure(text=Path(d).name)
            except Exception:
                pass'''
    if old_choose in src:
        src = src.replace(old_choose, new_choose, 1)
        log("  -> label sidebar cable")

    # Verification syntaxique
    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        log("  Restauration...")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Fichier restaure.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    log()
    log("=" * 72)
    log("SIDEBAR AJOUTEE")
    log("=" * 72)
    log()
    log("Relancez :")
    log("  $env:PYTHONIOENCODING = 'utf-8'")
    log("  python .\\memolibdev_gui_v4.py")
    log()
    log("Attendu :")
    log("  - Sidebar 200px a gauche")
    log("  - En-tete MemoLibDev + AI Workspace")
    log("  - 5 items : Dialogue IA (actif) / Missions / Fichiers")
    log("             / Propositions / Controles")
    log("  - Pied : 'Projet actif' + nom du projet")
    log("  - Chat a droite, fonctionnel comme avant")
    log()
    log("Les items de navigation sont VISUELS uniquement.")
    log("Ils seront actives dans les etapes suivantes.")
    log()
    log(f"Rollback : Copy-Item {BK.name}\\{TARGET.name} .\\{TARGET.name} -Force")
    return 0


if __name__ == "__main__":
    sys.exit(patch())