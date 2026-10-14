from pathlib import Path
import ast
import hashlib
import sys

ROOT = Path(r"C:\Users\moros\MemoLibDev\v3")
SCRIPT = ROOT / "apply_lot1_f1_f2.py"
TARGET = ROOT / "api_facade.py"
OUT = ROOT / "apply_lot1_f1_f2.py.proposed"

SCRIPT_SHA = "000D834AB078956100AB43B47C3EEB04AA6F4AF03FE6AB04B50EB918F118B18D"
TARGET_SHA = "8445F3DBC65D555246C914BBA6CB996F7F402A37F86504A2707FEB3ABFBD0B61"

def stop(message):
    sys.exit("ARRET : " + message)

if OUT.exists():
    stop("le fichier de proposition existe deja.")

if hashlib.sha256(SCRIPT.read_bytes()).hexdigest().upper() != SCRIPT_SHA:
    stop("empreinte du script original inattendue.")

if hashlib.sha256(TARGET.read_bytes()).hexdigest().upper() != TARGET_SHA:
    stop("empreinte de api_facade.py inattendue.")

source = SCRIPT.read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)

start = [i for i, line in enumerate(lines)
         if line.strip() == 'stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")']
if len(start) != 1:
    stop("l'ancre de debut doit apparaitre exactement une fois.")
start = start[0]

ends = [i for i in range(start, len(lines))
        if lines[i].strip() == "return 0"]
if not ends:
    stop("ancre return 0 absente.")
end = ends[0]

old = "".join(lines[start:end + 1])
if "shutil.copy2(path, backup)" not in old or "path.write_bytes(new_text.encode" not in old:
    stop("le bloc original ne correspond pas a celui audite.")

# Proposition limitée à la sécurisation de la phase d'écriture.
replacement = '''    # Application protegee : empreinte et sauvegarde exclusive.
    target_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if target_sha != EXPECTED_SHA256:
        fail("api_facade.py a change depuis l'audit ; application refusee.")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = path.with_name(f"{path.name}.backup_lot1_{stamp}")
    temp = path.with_name(f"{path.name}.tmp_lot1_{stamp}")
    new_bytes = new_text.encode("utf-8")
    expected_new_sha = hashlib.sha256(new_bytes).hexdigest().upper()
    original_bytes = path.read_bytes()

    if hashlib.sha256(original_bytes).hexdigest().upper() != EXPECTED_SHA256:
        fail("fichier cible modifie avant sauvegarde.")

    with backup.open("xb") as stream:
        stream.write(original_bytes)
        stream.flush()
        import os
        os.fsync(stream.fileno())

    if hashlib.sha256(backup.read_bytes()).hexdigest().upper() != EXPECTED_SHA256:
        fail("sauvegarde invalide ; cible non modifiee.")

    if hashlib.sha256(path.read_bytes()).hexdigest().upper() != EXPECTED_SHA256:
        fail("fichier cible modifie avant ecriture.")

    try:
        with temp.open("xb") as stream:
            stream.write(new_bytes)
            stream.flush()
            import os
            os.fsync(stream.fileno())

        if hashlib.sha256(path.read_bytes()).hexdigest().upper() != EXPECTED_SHA256:
            fail("fichier cible modifie avant remplacement.")

        os.replace(temp, path)
        new_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if new_sha != expected_new_sha:
            fail("empreinte apres ecriture inattendue ; verifier la sauvegarde.")
    finally:
        if temp.exists():
            temp.unlink()

    print(f"Sauvegarde : {backup}")
    print(f"Ecrit      : {path}")
    print(f"Nouveau SHA-256 : {new_sha}")
    return 0
'''

new_source = "".join(lines[:start]) + replacement + "".join(lines[end + 1:])

# Ajoute os aux imports globaux pour que le bloc proposé soit autonome.
if "\nimport os\n" not in new_source:
    anchor = "import hashlib\n"
    if new_source.count(anchor) != 1:
        stop("impossible de verifier l'ancre d'import hashlib.")
    new_source = new_source.replace(anchor, anchor + "import os\n", 1)

try:
    ast.parse(new_source)
except SyntaxError as exc:
    stop(f"syntaxe invalide : {exc}")

if "EXPECTED_TARGET_SHA" in new_source:
    stop("ancienne constante incorrecte detectee.")

if hashlib.sha256(SCRIPT.read_bytes()).hexdigest().upper() != SCRIPT_SHA:
    stop("le script original a change pendant la preparation.")

# Création exclusive : ne remplace jamais une proposition existante.
with OUT.open("xb") as stream:
    stream.write(new_source.encode("utf-8"))
    stream.flush()
    import os
    os.fsync(stream.fileno())

print("PROPOSITION CREEE :", OUT)
print("SHA-256 proposition :", hashlib.sha256(OUT.read_bytes()).hexdigest().upper())
print("Syntaxe Python : valide")
print("Aucun test, commit, push ou deploiement lance.")
print("api_facade.py et le script original restent inchanges.")