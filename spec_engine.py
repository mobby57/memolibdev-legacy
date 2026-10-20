"""spec_engine.py - Generation de specs Flutter (requirements, design, tasks).

Le module est PUR : il ne connait ni Ollama, ni le reseau. L'appelant injecte
un `llm_call(system, user) -> str` qui fait la requete. Cela permet de tester
la chaine sans dependre de la signature exacte de streaming.stream_ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


LLMCall = Callable[[str, str], str]  # (system, user) -> str


REQUIREMENTS_SYSTEM = """Tu es un analyste produit Flutter senior.

Produis un fichier `requirements.md` au format EARS :
- WHEN <condition>, THE SYSTEM SHALL <comportement observable>
- WHILE <etat>, THE SYSTEM SHALL <comportement>
- WHERE <contexte>, THE SYSTEM SHALL <comportement>
- IF <condition>, THEN THE SYSTEM SHALL <comportement>

REGLES :
- Chaque exigence doit etre TESTABLE (widget test ou integration test).
- Mentionne les widgets Flutter concernes si pertinent.
- Ne produis AUCUN code Dart.
- Ne produis AUCUNE architecture technique (c'est le role du design).
- Numeroate : REQ-01, REQ-02, etc.
- Regroupe par domaine fonctionnel avec des sous-titres H2.

Format attendu :
# Requirements - <feature>
## Contexte
<2-3 phrases>
## Exigences
### <domaine>
- **REQ-01** - WHEN ..., THE SYSTEM SHALL ...
"""

DESIGN_SYSTEM = """Tu es un architecte Flutter senior.

Produis un fichier `design.md` pour la feature decrite, en respectant :
- Architecture : Clean Architecture ou feature-first (lib/features/<feature>/, lib/core/).
- State management : precise un choix (Riverpod, BLoC, Provider) sans imposer.
- Structure de dossiers : arbre de fichiers concrets.
- Flux de donnees : UI -> state -> usecase -> repository -> datasource.
- Dependances pub.dev : liste avec versions recommandees et justification.
- Risques et tradeoffs : 3-5 points concrets.
- Pas de code Dart complet ; signatures/types si necessaire.

Format :
# Design - <feature>
## Architecture choisie
## Structure de dossiers
## Couches et flux
## Dependances pub.dev
## Tradeoffs
"""

TASKS_SYSTEM = """Tu es un lead dev Flutter.

A partir des exigences et du design fournis, produis un fichier `tasks.md`
avec une liste ordonnee de taches atomiques.

REGLES :
- Chaque tache doit etre realisable en moins de 30 minutes.
- Format : - [ ] TXX - <action precise> (<fichier cible>) (REQ-XX)
- Ordre incremental : scaffolding -> models -> state -> UI -> tests -> hookup.
- Chaque tache reference au moins une exigence REQ-XX.
- Derniere tache : `flutter analyze && flutter test`.
- Pas de taches de "reflexion" ou "recherche" : code ou tests uniquement.

Format :
# Tasks - <feature>
## Phase 1 - Scaffolding
- [ ] T01 - ... (REQ-01)
...
## Phase N - Validation
- [ ] TN - Lancer flutter analyze && flutter test
"""


@dataclass(frozen=True)
class SpecResult:
    slug: str
    spec_dir: Path
    requirements_path: Path
    design_path: Path
    tasks_path: Path


def _load_steering(project_root: Path) -> str:
    """Charge .memolib/steering/*.md, concatenes pour injection dans les prompts."""
    steering_dir = Path(project_root) / ".memolib" / "steering"
    if not steering_dir.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(steering_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if content:
            parts.append(f"=== {path.name} ===\n{content}")
    return "\n\n".join(parts)

def _slug(prompt: str, max_words: int = 5) -> str:
    words = [w for w in prompt.lower().split() if w.isalnum()][:max_words]
    return "-".join(words) if words else "spec"


def _write(path: Path, content: str) -> None:
    if not content or not content.strip():
        raise ValueError(f"contenu vide pour {path.name}")
    path.write_text(content, encoding="utf-8")


def generate_requirements(prompt: str, llm_call: LLMCall,
                          steering: str = "") -> str:
    user = prompt
    if steering:
        user = f"REGLES PROJET (a respecter) :\n{steering}\n\n---\n\n{prompt}"
    return llm_call(REQUIREMENTS_SYSTEM, user)


def generate_design(prompt: str, requirements: str, llm_call: LLMCall,
                    steering: str = "") -> str:
    user = f"Demande initiale :\n{prompt}\n\nExigences produites :\n{requirements}"
    if steering:
        user = f"REGLES PROJET (a respecter) :\n{steering}\n\n---\n\n{user}"
    return llm_call(DESIGN_SYSTEM, user)


def generate_tasks(prompt: str, requirements: str, design: str,
                   llm_call: LLMCall, steering: str = "") -> str:
    prefix = (
        f"REGLES PROJET (a respecter) :\n{steering}\n\n---\n\n"
        if steering else ""
    )
    user = (
        prefix
        + f"Demande :\n{prompt}\n\n"
        + f"Exigences :\n{requirements}\n\n"
        + f"Design :\n{design}"
    )
    return llm_call(TASKS_SYSTEM, user)


def generate_spec(
    project_root: Path,
    prompt: str,
    llm_call: LLMCall,
    slug: str | None = None,
) -> SpecResult:
    """Genere requirements.md, design.md, tasks.md dans .memolib/specs/<slug>/.

    Fail-closed : si l'un des appels LLM retourne vide, ValueError et aucun
    fichier n'est ecrit (l'ecriture se fait apres chaque generation reussie
    mais le dossier est cree avant ; si design echoue, requirements seul reste).
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt vide")
    slug = slug or _slug(prompt)
    spec_dir = Path(project_root) / ".memolib" / "specs" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)

    steering = _load_steering(project_root)

    req_text = generate_requirements(prompt, llm_call, steering=steering)
    req_path = spec_dir / "requirements.md"
    _write(req_path, req_text)

    design_text = generate_design(prompt, req_text, llm_call, steering=steering)
    design_path = spec_dir / "design.md"
    _write(design_path, design_text)

    tasks_text = generate_tasks(
        prompt, req_text, design_text, llm_call, steering=steering,
    )
    tasks_path = spec_dir / "tasks.md"
    _write(tasks_path, tasks_text)

    return SpecResult(
        slug=slug,
        spec_dir=spec_dir,
        requirements_path=req_path,
        design_path=design_path,
        tasks_path=tasks_path,
    )