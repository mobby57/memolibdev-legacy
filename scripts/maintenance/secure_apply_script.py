from pathlib import Path
import ast
import hashlib
import os
import sys
import datetime

script = Path(r"C:\Users\moros\MemoLibDev\v3\apply_lot1_f1_f2.py")
expected_sha = "000D834AB078956100AB43B47C3EEB04AA6F4AF03FE6AB04B50EB918F118B18D"
expected_target_sha = "8445F3DBC65D555246C914BBA6CB996F7F402A37F86504A2707FEB3ABFBD0B61"

raw = script.read_bytes()
if hashlib.sha256(raw).hexdigest().upper() != expected_sha:
    sys.exit("ARRET : SHA-256 du script inattendu.")

text = raw.decode("utf-8")
eol = "\r\n" if "\r\n" in text else "\n"
lines = text.splitlines(keepends=True)

start = next((i for i, line in enumerate(lines)
              if line.strip() == 'stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")'), None)
if start is None:
    sys.exit("ARRET : ancre de debut absente.")

end = next((i for i in range(start, len(lines))
            if lines[i].strip() == "return 0"), None)
if end is None or end - start != 11:
    sys.exit("ARRET : plage de remplacement inattendue.")

old_block = "".join(lines[start:end + 1])
if "shutil.copy2(path, backup)" not in old_block or "path.write_bytes(new_text.encode" not in old_block:
    sys.exit("ARRET : ancres internes absentes.")

replacement = '''    # Application protegee : empreinte, sauvegarde exclusive et controle final.
    target_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if target_sha != EXPECTED_TARGET_SHA:
        fail("api_facade.py a change depuis l'audit ; application refusee.")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = path.with_name(f"{path.name}.backup_lot1_{stamp}")
    temp = path.with_name(f"{path.name}.tmp_lot1_{stamp}")
    new_bytes = new_text.encode("utf-8")
    expected_new_sha = hashlib.sha256(new_bytes).hexdigest().upper()

    # Creation exclusive : refuse toute collision de sauvegarde.
    try:
        with backup.open("xb") as stream:
            stream.write(path.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        fail(f"sauvegarde deja existante : {backup}")

    if hashlib.sha256(backup.read_bytes()).hexdigest().upper() != EXPECTED_TARGET_SHA:
        fail("sauvegarde invalide ; fichier cible non modifie.")

    if hashlib.sha256(path.read_bytes()).hexdigest().upper() != EXPECTED_TARGET_SHA:
        fail("fichier cible modifie avant ecriture ; application refusee.")

    try:
        with temp.open("xb") as stream:
            stream.write(new_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)

        new_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if new_sha != expected_new_sha:
            restore = path.with_name(f"{path.name}.restore_lot1_{stamp}")
            with restore.open("xb") as stream:
                stream.write(backup.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(restore, path)
            fail("verification apres ecriture echouee ; sauvegarde restauree.")
    finally:
        if temp.exists():
            temp.unlink()

    print(f"Sauvegarde verifiee : {backup}")
    print(f"Ecrit               : {path}")
    print(f"Nouveau SHA-256     : {new_sha}")
    print("\\nVerifie ensuite avec : git diff -- api_facade.py")
    print("Aucun test, commit, push ou deploiement n'est lance.")
    return 0
'''

replacement = replacement.replace("\n", eol)
new_text = "".join(lines[:start]) + replacement + "".join(lines[end + 1:])

try:
    ast.parse(new_text)
except SyntaxError as exc:
    sys.exit(f"ARRET : script modifie invalide : {exc}")

# Le programme prepare uniquement un fichier de contrôle, pas le script cible.
out = script.with_name("apply_lot1_f1_f2.py.proposed")
if out.exists():
    sys.exit(f"ARRET : fichier de proposition deja existant : {out}")

with out.open("xb") as stream:
    stream.write(new_text.encode("utf-8"))
    stream.flush()
    os.fsync(stream.fileno())

print("PROPOSITION CREEE :", out)
print("SHA-256 original :", expected_sha)
print("SHA-256 proposition :", hashlib.sha256(out.read_bytes()).hexdigest().upper())
print("Syntaxe Python : valide")
print("Aucun fichier existant n'a ete remplace.")
print("api_facade.py et apply_lot1_f1_f2.py restent inchanges.")
