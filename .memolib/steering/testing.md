# Testing

- Chaque widget public doit avoir un test dans `test/` avec `WidgetTester`.
- Tests unitaires pour les usecases et repositories (mocks via `mocktail`).
- Pas de `Thread.sleep` ni `Future.delayed` dans les tests : utiliser `pumpAndSettle`.
- Coverage cible : 70% sur `lib/features/`, 100% sur `lib/core/` critique.
- Nommage : `test/<fichier_testé>_test.dart`.