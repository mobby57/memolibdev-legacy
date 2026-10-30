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
