# Invariants MemoLibDev

Chaque invariant est verifie par au moins un test adversarial.

## 1. Jamais de commit/push automatique
result.committed et result.pushed restent False.
Violation -> ABORTED (Invariant 6 cote orchestrateur).
Tests : test_d59_controlled_apply.py S1/S2, test_d60_agent_loop.py G1/G2.

## 2. APPLIED != COMMITTED
APPLIED = working tree modifie, jamais commite.
Tests : test_d59_controlled_apply.py S1, test_d62_code_adapter.py E4.

## 3. Binding cryptographique du diff
Le hash valide porte sur les octets exacts transmis a D5.9, sans normalisation.
Tests : test_v041_diff_binding.py [1],[2],[3],[10],[11],[11b],
        test_v042_mandatory_binding.py M1/M3/M5/M11/M12.

## 4. Fail-closed par defaut
REQUIRE_DIFF_BINDING=True, CONTROL_PLANE_FILES interdit les modules noyau.
Tests : test_v042_mandatory_binding.py M2/M4/M6/M8/M9,
        test_d60_agent_loop.py G3/G4/G5/G6.

## 5. Rollback verifie
SHA initial == SHA final, aucun commit.
Tests : test_d59_controlled_apply.py S2, test_rollback_reel.py.

## 6. Aucune ecriture hors scope
Patch hors perimetre -> PRE_APPLY BLOCK, avant toute ecriture.
Tests : test_d59_controlled_apply.py S3, test_d60_agent_loop.py G3.

## 7. Decision humaine unique (L6)
Une seule transition AWAITING_AUTHORIZATION -> APPLIED par run.
Tests : test_d58_e2e_authorization.py J1-J6, test_lot1_f1_f2.py.

## Tests d'integration
test_d58_e2e_authorization.py exige :
  $env:MEMOLIBDEV_TARGET = 'C:\Users\moros\test_d58_target'
Fixture : reports/coder-authorization.json (head + fingerprint + SHA reels).
