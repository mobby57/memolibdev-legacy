# fix_secret_detector.py — Assouplit la detection de secrets
# (ne bloque plus sur process.env.X)
import re, shutil, sys, subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

def title(msg): print(f"\n{'=' * 60}\n {msg}\n{'=' * 60}")
def ok(msg):    print(f"  [OK] {msg}")
def ko(msg):    print(f"  [KO] {msg}")
def info(msg):  print(f"  [..] {msg}")
def warn(msg):  print(f"  [!!] {msg}")

# ============================================================
# 1. Localiser le detecteur
# ============================================================
title("1) Localisation du detecteur de secrets")

pattern_files = []
for p in ROOT.rglob("*.py"):
    if any(x in p.parts for x in (".venv", "venv", "__pycache__", ".git", "_backups")):
        continue
    if ".pre-" in p.name or ".before-" in p.name:
        continue
    try:
        src = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if "generic_assignment" in src or "secret détecté" in src or "secret detecte" in src:
        pattern_files.append(p)
        print(f"  [..] {p.relative_to(ROOT)}")

if not pattern_files:
    ko("Aucun fichier ne contient 'generic_assignment'")
    sys.exit(1)

print()
print(f"  {len(pattern_files)} fichier(s) trouve(s)")

# ============================================================
# 2. Lire le pattern
# ============================================================
title("2) Pattern actuel")

for p in pattern_files:
    src = p.read_text(encoding="utf-8", errors="ignore")
    # Cherche les definitions liees a generic_assignment
    for i, line in enumerate(src.splitlines(), 1):
        if "generic_assignment" in line or "generic-assignment" in line:
            print(f"  {p.name}:{i}")
            print(f"    {line.strip()[:120]}")
            print()
            # Affiche le contexte (+-5)
            lines = src.splitlines()
            start = max(0, i - 6)
            end = min(len(lines), i + 6)
            print(f"  --- Contexte ---")
            for j in range(start, end):
                marker = ">>>" if j == i - 1 else "   "
                print(f"  {marker} {j+1:4d}: {lines[j][:100]}")
            print()
            break

# ============================================================
# 3. Chercher le fichier de patterns secrets
# ============================================================
title("3) Recherche du fichier de patterns")

SECRET_FILES = [
    "llm/secret_guard.py",
    "llm/secret_scanner.py",
    "secret_guard.py",
    "secret_detector.py",
    "context/secret_scanner.py",
]

found_file = None
for name in SECRET_FILES:
    p = ROOT / name
    if p.exists():
        print(f"  [OK] {name}")
        found_file = p
        break

if not found_file:
    # Cherche par contenu
    info("Recherche par contenu...")
    for p in ROOT.rglob("*.py"):
        if any(x in p.parts for x in (".venv", "venv", "__pycache__", ".git")):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "generic_assignment" in src or "GENERIC_ASSIGNMENT" in src.upper():
            found_file = p
            print(f"  [OK] trouve : {p.relative_to(ROOT)}")
            break

if not found_file:
    warn("Fichier de patterns introuvable")
    info("Envoie-moi cette sortie, on patchera manuellement")
    sys.exit(1)

# ============================================================
# 4. Afficher le fichier complet pour analyse
# ============================================================
title("4) Contenu du fichier detecteur")

src = found_file.read_text(encoding="utf-8")
lines = src.splitlines()
print(f"  Fichier : {found_file.relative_to(ROOT)}")
print(f"  Taille  : {len(lines)} lignes")
print()
# Affiche les 80 premieres lignes
for i, line in enumerate(lines[:80], 1):
    print(f"  {i:4d}: {line[:110]}")

# ============================================================
# 5. Suggestion de patch
# ============================================================
title("5) Suggestion")

print("""
  Le pattern 'generic_assignment' matche probablement :
  
    const X = "long string"     -> BLOCK (correct)
    const X = process.env.Y     -> BLOCK (faux positif)
  
  Fix : ajouter une exception pour les lignes contenant
  'process.env.', 'import.meta.env.', 'os.environ', 'os.getenv'.
""")

print()
answer = input("  Voir le fichier et patcher manuellement ? (oui/non) : ").strip().lower()

if answer == "oui":
    # Backup
    backup = found_file.with_suffix(found_file.suffix + f".before-secretfix-{STAMP}")
    shutil.copy2(found_file, backup)
    print(f"\n  [OK] Backup : {backup.name}")
    print()
    print(f"  Ouvre ce fichier dans VS Code :")
    print(f"    code \"{found_file}\"")
    print()
    print("  Cherche 'generic_assignment' et ajoute une condition")
    print("  pour ignorer les lignes avec 'process.env.' ou 'os.environ'.")
else:
    print("  Annule.")
'@ | Set-Content fix_secret_detector.py -Encoding UTF8

python fix_secret_detector.py