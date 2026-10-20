# .memolib/ - Artefacts MemoLibDev (structure Kiro-like)

Ce dossier contient les artefacts du workflow agentique, a versionner
avec le projet.

- `specs/<slug>/` : requirements.md, design.md, tasks.md
- `steering/*.md`  : regles projet injectees dans le prompt systeme
- `hooks/`         : scripts pre_task / post_task (a brancher dans agent_loop)

Regles :
- Ne pas committer de secrets dans steering/.
- Les specs sont des livrables : les relire et les corriger avant implementation.
- Les hooks doivent etre idempotents et fail-closed (retourner ok=false bloque).