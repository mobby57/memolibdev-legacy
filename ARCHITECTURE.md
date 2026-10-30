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
