# Flutter Style Guide

Regles de style injectees dans le prompt systeme.

- Preferer `const` constructors partout ou possible.
- `StatelessWidget` par defaut, `StatefulWidget` seulement si etat local necessaire.
- Nommer les fichiers en `snake_case.dart`.
- Une classe par fichier public.
- Imports groupes : `dart:`, puis `package:flutter/`, puis `package:`, puis relatifs.
- Pas de `print()` : utiliser `debugPrint` ou un logger injecte.
- Eviter les widgets de plus de 80 lignes : extraire.