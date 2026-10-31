#!/usr/bin/env python3
"""
MemoLibDev - Lot 1 (F1 + F2) : api_facade.py / handle_approve
=============================================================

Deplace `registry.begin_approval(run_id)` APRES toutes les validations qui
peuvent echouer (run inconnu, mauvais etat, approver invalide, resolution du
projet, construction du provider). Un echec de validation ne laisse plus le run
en EXECUTING.

Ce script :
  - est en SIMULATION par defaut : il affiche le diff et n'ecrit RIEN ;
  - avec --apply : sauvegarde le fichier, puis l'ecrit ;
  - refuse de travailler si l'empreinte SHA-256 ne correspond pas a la version
    auditee, si une ancre de ligne ne correspond pas, ou si le resultat n'est
    pas du Python syntaxiquement valide ;
  - ne lance NI git, NI tests, NI serveur, NI reseau, NI Ollama ;
  - n'utilise que la bibliotheque standard.

Usage (PowerShell) :
  python apply_lot1_f1_f2.py                 # simulation
  python apply_lot1_f1_f2.py --apply         # applique, avec sauvegarde
  python apply_lot1_f1_f2.py --path D:\\autre\\api_facade.py
"""

from __future__ import annotations

import argparse
import ast
import datetime
import difflib
import hashlib
import shutil
import sys
from pathlib import Path

DEFAULT_PATH = r"C:\Users\moros\MemoLibDev\v3\api_facade.py"

# Version auditee (commit 5832c40d..., 611 lignes).
EXPECTED_SHA256 = "8445F3DBC65D555246C914BBA6CB996F7F402A37F86504A2707FEB3ABFBD0B61"
EXPECTED_LINES = 611

# Ancres : numero de ligne (1-indexe) -> contenu attendu (apres strip).
ANCHORS = {
    382: "def handle_approve(self, body: dict) -> ApiResult:",
    407: "record = self.registry.begin_approval(run_id)",
    420: '"approbation anonyme"})',
    429: "target, err = self._resolve(record.project)",
    430: "if err is not None:",
    431: "return err",
    462: "approver=approver.strip(),",
    463: "provider=self._provider(self._model),",
}

# Remplace les lignes 407-420.
NEW_PRE = '''\
        # Pre-controles SANS changement d'etat : toute sortie ici laisse le
        # run en AWAITING_AUTHORIZATION (approuvable ou refusable ensuite).
        known = self.registry.get(run_id)
        if known is None:
            return ApiResult(404, {"error": "UNKNOWN_RUN",
                                   "reason": f"run_id inconnu: {run_id}"})
        if known.state != MissionState.AWAITING_AUTHORIZATION:
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": f"approbation impossible depuis {known.state}"})

        # Fail-closed : approbation anonyme interdite.
        if not isinstance(approver, str) or not approver.strip():
            return ApiResult(400, {"error": "NO_APPROVER",
                                   "reason": "approver manquant : aucune "
                                             "approbation anonyme"})'''.split("\n")

# Remplace les lignes 429-431.
NEW_RESOLVE = '''\
        target, err = self._resolve(known.project)
        if err is not None:
            return err
        provider = self._provider(self._model)

        # Transition atomique, DERNIERE etape avant le moteur : un
        # double-clic ne peut lancer qu'un seul apply.
        record = self.registry.begin_approval(run_id)
        if record is None:
            current = self.registry.get(run_id)
            state = current.state if current is not None else "inconnu"
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": f"approbation impossible depuis {state}"})'''.split("\n")

# Remplace la ligne 463.
NEW_PROVIDER = ["            provider=provider,"]


def fail(msg: str) -> "None":
    print(f"[ABANDON] {msg}")
    print("Aucun fichier n'a ete modifie.")
    sys.exit(1)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description="Applique le lot 1 (F1+F2).")
    ap.add_argument("--path", default=DEFAULT_PATH, help="chemin de api_facade.py")
    ap.add_argument("--apply", action="store_true",
                    help="ecrit le fichier (sinon simulation)")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_file():
        fail(f"fichier introuvable : {path}")

    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest().upper()
    print(f"Fichier   : {path}")
    print(f"SHA-256   : {sha}")
    if sha != EXPECTED_SHA256:
        fail("empreinte differente de la version auditee "
             f"({EXPECTED_SHA256}). Le fichier a change depuis l'audit : "
             "renvoie-moi le nouveau contenu.")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"le fichier n'est pas de l'UTF-8 valide : {exc}")

    eol = "\r\n" if "\r\n" in text else "\n"
    if eol == "\r\n" and text.count("\n") != text.count("\r\n"):
        fail("fins de ligne melangees (CRLF et LF) : abandon par prudence.")
    lines = text.split(eol)
    if len(lines) - (1 if lines and lines[-1] == "" else 0) != EXPECTED_LINES:
        fail(f"nombre de lignes inattendu (attendu {EXPECTED_LINES}).")

    for num, expected in ANCHORS.items():
        actual = lines[num - 1].strip()
        if actual != expected:
            fail(f"ancre ligne {num} differente.\n  attendu : {expected!r}\n"
                 f"  trouve  : {actual!r}")

    # Modifications de bas en haut pour conserver la numerotation.
    new_lines = list(lines)
    new_lines[462:463] = NEW_PROVIDER      # ligne 463
    new_lines[428:431] = NEW_RESOLVE       # lignes 429-431
    new_lines[406:420] = NEW_PRE           # lignes 407-420
    new_text = eol.join(new_lines)

    # Controles du resultat (aucune execution du code).
    try:
        ast.parse(new_text)
    except SyntaxError as exc:
        fail(f"le resultat n'est pas du Python valide : {exc}")
    if new_text.count("self.registry.begin_approval(") != 1:
        fail("begin_approval doit etre appele exactement une fois.")
    if new_text.count("provider=provider,") != 1:
        fail("remplacement du provider inattendu.")

    diff = list(difflib.unified_diff(
        lines, new_lines, "api_facade.py (avant)", "api_facade.py (apres)",
        lineterm="", n=2))
    print("\n--- DIFF ---")
    for d in diff:
        print(d)
    print("--- FIN DIFF ---\n")

    if not args.apply:
        print("SIMULATION : rien n'a ete ecrit. Relance avec --apply pour appliquer.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.backup_lot1_{stamp}")
    shutil.copy2(path, backup)
    print(f"Sauvegarde : {backup}")

    path.write_bytes(new_text.encode("utf-8"))
    new_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    print(f"Ecrit      : {path}")
    print(f"Nouveau SHA-256 : {new_sha}")
    print("\nVerifie maintenant avec : git diff -- api_facade.py")
    print("Pour annuler : recopie la sauvegarde par-dessus api_facade.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())