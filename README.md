# MemoLibDev

Assistant de développement **100% local** avec chaîne de contrôle MSAFE.
« L'IA propose, les contrôles vérifient, l'humain autorise. »

## Installation

    python -m venv venv && source venv/bin/activate
    pip install -e ".[dev]"

## Démarrage

    python -m memolibdev.api.app

## Structure

    src/memolibdev/
    ├── core/       Cœur métier (models, contracts)
    ├── services/   Orchestration (msafe, intent_router, voice_pipeline)
    ├── adapters/   Implémentations (stt, tts, llm)
    ├── api/        FastAPI
    └── ui/         Tkinter

Voir ARCHITECTURE.md et docs/adr/ pour les décisions.

## Sécurité

- 4 modes : READ_ONLY, PROPOSE, SANDBOX, SUPERVISED_APPLY
- Chaîne MSAFE (SHA256, snapshots, preuves)
- 136 tests de sécurité
- Commits signés GPG
