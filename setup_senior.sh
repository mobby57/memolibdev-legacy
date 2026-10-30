#!/bin/bash
set -e
cd ~/memolib

echo "🧹 Nettoyage du dossier parasite..."
rm -rf 'C:\Users\moros\MemoLibDev_KnowledgeBase' 2>/dev/null || true

echo "📁 Création de la structure senior..."
mkdir -p src/memolibdev/core
mkdir -p src/memolibdev/services
mkdir -p src/memolibdev/adapters/stt
mkdir -p src/memolibdev/adapters/tts
mkdir -p src/memolibdev/adapters/llm
mkdir -p src/memolibdev/api
mkdir -p src/memolibdev/ui
mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p tests/security
mkdir -p docs/adr
mkdir -p scripts

# __init__.py partout
for d in "" core services adapters adapters/stt adapters/tts adapters/llm api ui; do
    touch "src/memolibdev/$d/__init__.py"
done
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/security/__init__.py
echo '"""MemoLibDev — Assistant de développement 100% local."""

__version__ = "0.1.0"' > src/memolibdev/__init__.py

echo "📦 Écriture de pyproject.toml..."
cat > pyproject.toml << 'PYEOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "memolibdev"
version = "0.1.0"
description = "Assistant de développement 100% local avec contrôle MSAFE"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Proprietary"}
authors = [{name = "MemoLibDev", email = "dev@memolib.dev"}]
keywords = ["ai", "local", "msafe", "assistant", "voice"]

dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.27",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
    "requests>=2.31",
    "faster-whisper>=1.0",
    "piper-tts>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "ruff>=0.4", "mypy>=1.10", "bandit>=1.7"]

[project.scripts]
memolibdev = "memolibdev.api.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers"
markers = ["slow: tests lents", "integration: nécessite Ollama", "security: tests MSAFE"]

[tool.coverage.run]
source = ["src/memolibdev"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 50
PYEOF

echo "📖 Écriture de README.md..."
cat > README.md << 'READMEEOF'
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
READMEEOF

echo "📐 Écriture de ARCHITECTURE.md..."
cat > ARCHITECTURE.md << 'ARCHEOF'
# Architecture MemoLibDev

## Vue d'ensemble

    Clients (Flutter / Tkinter / CLI)
        │
        ▼
    API FastAPI (src/memolibdev/api)
        │
        ▼
    Services (src/memolibdev/services) : MSAFE · IntentRouter · VoicePipeline
        │
        ├──► STT (adapters/stt)  Whisper
        ├──► LLM (adapters/llm)  Ollama
        └──► TTS (adapters/tts)  Piper / Kokoro

## Règles d'or

1. `core/` ne connaît rien de `adapters/` — il définit des Protocols.
2. `adapters/` sont interchangeables via variables d'environnement.
3. `services/` orchestre — reçoit des Protocols, pas des implémentations.
4. `api/` et `ui/` sont des fines couches — aucune logique métier.

## Modes de sécurité MSAFE

| Mode              | Écriture | Snapshot | Validation | Cas d'usage    |
|-------------------|----------|----------|------------|----------------|
| READ_ONLY         | ❌       | ❌       | ❌         | Lecture seule  |
| PROPOSE           | ❌       | ✅       | ❌         | Génération diff |
| SANDBOX           | ✅ (sandbox) | ✅   | ❌         | Test de code   |
| SUPERVISED_APPLY  | ✅ (prod) | ✅      | ✅ humain  | Application    |
ARCHEOF

echo "📋 Écriture des 3 ADR..."
cat > docs/adr/001-msafe.md << 'ADR1'
# ADR-001 : Chaîne de contrôle MSAFE

## Statut
Accepté — 2026

## Contexte
Les assistants IA peuvent modifier du code sans contrôle humain.
Risques : régressions silencieuses, failles, perte de code.

## Décision
Chaque modification IA passe par :
1. Propose (diff isolé)
2. Snapshot (copie + SHA256)
3. Validation humaine explicite
4. Apply (écriture atomique)
5. Preuve JSON signée

## Conséquences
+ Contrôle humain total
+ Audit trail cryptographique
+ Rollback possible
- Latence supplémentaire (~200ms)
- Complexité de mise en œuvre
ADR1

cat > docs/adr/002-tts-provider.md << 'ADR2'
# ADR-002 : Abstraction TTSProvider

## Statut
Accepté — 2026

## Contexte
Piper est rapide mais prononce mal les néologismes
(MemoLibDev → Mémoli-Bedev). Kokoro offre une meilleure qualité.

## Décision
Abstraire le TTS derrière un Protocol TTSProvider.
Implémentations : PiperProvider (défaut), KokoroProvider.
Sélection via TTS_PROVIDER=piper|kokoro.

## Conséquences
+ Switch de moteur sans modification de code
+ Benchmark A/B possible
- Couche d'abstraction supplémentaire
ADR2

cat > docs/adr/003-local-first.md << 'ADR3'
# ADR-003 : Local-first par défaut

## Statut
Accepté — 2026

## Contexte
Les outils IA modernes dépendent du cloud (OpenAI, Anthropic).
Problèmes : RGPD, souveraineté, latence, coût, fuites.

## Décision
MemoLibDev fonctionne 100% local par défaut :
- LLM : Ollama
- STT : faster-whisper
- TTS : Piper
- Recherche : DuckDuckGo
- Stockage : SQLite local

## Conséquences
+ Souveraineté totale, RGPD trivial
+ Coût d'exploitation : 0€
+ Latence prévisible
- Nécessite 8 Go RAM minimum
- Modèles plus petits que GPT-4
ADR3

echo ""
echo "✅ Structure créée :"
find src tests docs -type f | sort
echo ""
echo "🎉 Phase 1 terminée. Prochaine étape : pip install -e ."
