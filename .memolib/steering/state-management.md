# State Management

Regle projet : etat via Riverpod (Provider est legacy, BLoC est autorise
pour les features existantes qui l'utilisent deja).

- Declarer les providers dans `lib/features/<feature>/<feature>_providers.dart`.
- Pas d'acces direct a `BuildContext` dans les providers.
- Utiliser `AsyncValue` pour les etats asynchrones.
- Tests : `ProviderContainer` + `overrideWithValue` pour les mocks.