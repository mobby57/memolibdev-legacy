# Hooks - pre_task / post_task

A brancher dans `agent_loop.py` (avant / apres `run_controlled_apply`).

Contrat :
- Script Python dans ce dossier, nomme `pre_task_*.py` ou `post_task_*.py`.
- Recu sur stdin : JSON `{"diff": str, "target": {"git_root": str, ...}}`.
- Retourne sur stdout : JSON `{"ok": bool, "reason": str}`.
- `ok: false` sur pre_task BLOQUE l'apply (coherent avec D5.9 fail-closed).
- `ok: false` sur post_task peut declencher un rollback selon le cablage.

Exemples prevus (a implementer) :
- `pre_task_flutter_analyze.py` : `flutter analyze` -> bloque si erreurs.
- `post_task_flutter_test.py`  : `flutter test` sur le fichier modifie.