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
