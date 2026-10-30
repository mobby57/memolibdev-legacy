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
