"""assistant_v2.py - Orchestrateur V2 (conversation + streaming + tools)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable, Iterator

from conversation import Conversation
from streaming import stream_ollama
from codebase_index import CodebaseIndex
from tool_use import ToolRegistry, parse_tool_calls, make_standard_tools


SYSTEM_PROMPT = """Tu es MemoLibDev, assistant de code local.

OUTILS : read_file(path), list_files(pattern), find_symbol(name).

CONTEXTE TECHNIQUE :
- Si le projet contient package.json -> Next.js/TS/JS, utilise npx vitest, npx playwright, npm
- Si le projet contient pyproject.toml ou setup.py -> Python, utilise pytest, pip
- NE JAMAIS utiliser pytest sur un projet TypeScript

REGLES OUTILS :
- Utilisateur dit cherche/trouve/ou est -> utilise find_symbol
- Utilisateur dit lis/montre/que fait + fichier -> read_file
- Utilisateur dit liste/quels fichiers -> list_files
- Si tu ne sais pas ou chercher -> find_symbol d abord

REGLES :
- Reponds TOUJOURS en francais, directement.
- Pour lire un fichier, emets :
<tool_call>{"name": "read_file", "args": {"path": "..."}}</tool_call>
- Ne dis JAMAIS "je ne peux pas lire les fichiers".
- Reponds en 2-5 phrases concises."""


class AssistantV2:
    """Assistant conversationnel avec memoire, streaming et outils."""

    def __init__(
        self,
        project_root: Path,
        model: str = "memolibdev-qwen7b-16k:latest",
        db_path: Path | None = None,
        index: CodebaseIndex | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.model = model
        self.db_path = db_path or (self.project_root / "data" / "conv.db")
        self.conversation = Conversation(self.db_path)
        self.index = index
        self.registry = ToolRegistry()
        make_standard_tools(self.project_root, self.registry, index)
        from tools_file import register_file_tools
        register_file_tools(self.project_root, self.registry)
        from tools_shell import register_shell_tools
        register_shell_tools(self.project_root, self.registry)

    def build_prompt(self, user_text: str, max_turns: int = 15) -> str:
        parts = []
        if self.index:
            st = self.index.stats()
            parts.append(
                f"Projet: {self.project_root} | "
                f"{st['files']} fichiers, {st['symbols']} symboles indexes."
            )
        tools_desc = "\n".join(
            f"- {t.name}: {t.description}"
            for t in self.registry.tools.values()
        )
        if tools_desc:
            parts.append(f"Outils disponibles:\n{tools_desc}")

        history = self.conversation.summary_for_context()
        if history:
            parts.append(f"Historique recent:\n{history}")

        parts.append(f"Demande actuelle: {user_text}")
        return "\n\n".join(parts)

    def _run_agent_loop(self, prompt: str, max_iters: int = 3):
        """Execute les <tool_call> du modele jusqu'a reponse finale."""
        from tool_use import parse_tool_calls
        for _ in range(max_iters):
            response = ""
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                response += chunk

            calls = parse_tool_calls(response)
            if not calls:
                return response, []

            results = []
            for name, args in calls:
                res = self.registry.execute(name, args)
                results.append(f"[{name}] {res[:1500]}")

            prompt = (
                prompt
                + "\n\n--- Reponse precedente ---\n"
                + response
                + "\n\n--- Resultats outils ---\n"
                + "\n".join(results)
                + "\n\n--- Ta reponse finale en francais, sans tool_call ---\n"
            )
        return response, results

    def chat_with_tools(
        self,
        user_text: str,
        on_token=None,
    ) -> str:
        """Chat avec boucle agentique : execute les outils automatiquement."""
        self.conversation.add("user", user_text)
        prompt = self.build_prompt(user_text)
        response, _ = self._run_agent_loop(prompt)
        if on_token and response:
            on_token(response)
        self.conversation.add("assistant", response)
        return response

    def chat(
        self,
        user_text: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        self.conversation.add("user", user_text)
        prompt = self.build_prompt(user_text)

        full = []
        if on_token:
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                full.append(chunk)
                on_token(chunk)
        else:
            for chunk in stream_ollama(
                prompt, model=self.model, system=SYSTEM_PROMPT
            ):
                full.append(chunk)

        response = "".join(full)

        # Executer les tool calls si presents
        calls = parse_tool_calls(response)
        if calls:
            tool_results = []
            for name, args in calls:
                result = self.registry.execute(name, args)
                tool_results.append(f"[{name}] {result[:1000]}")
            response += "\n\n--- Resultats outils ---\n" + "\n".join(tool_results)

        self.conversation.add("assistant", response)
        return response

    def new_conversation(self):
        self.conversation = Conversation(self.db_path)

    def history(self) -> list[dict]:
        return [
            {"role": t.role, "content": t.content, "time": t.timestamp}
            for t in self.conversation.turns
        ]

