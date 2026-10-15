#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MemoLibDev GUI v4 - Autonome.
Cherche memolibdev_cli.py a cote de lui.
Verifie Ollama au demarrage.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

# --- V2 : assistant conversationnel ---
try:
    from assistant_v2 import AssistantV2
    from codebase_index import CodebaseIndex
    _V2_AVAILABLE = True
except Exception as _v2_err:
    _V2_AVAILABLE = False
    _V2_IMPORT_ERR = str(_v2_err)

# --- Chemins relatifs (fonctionne dans un .exe PyInstaller) ---
def _base_dir() -> Path:
    """Dossier contenant les modules Python.
    En mode .exe : sys._MEIPASS (PyInstaller extrait les --add-data la).
    En mode .py : le dossier du script."""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = _base_dir()
CLI_PATH = BASE_DIR / "memolibdev_cli.py"


def find_cli_executable():
    """Trouve MemoLibDev-cli.exe.
    Cherche a cote de l'exe (sys.executable), puis dans _MEIPASS, puis a cote du script."""
    candidates = []
    if getattr(sys, "frozen", False):
        # A cote du .exe (cas normal : les deux .exe dans le meme dossier)
        candidates.append(Path(sys.executable).parent / "MemoLibDev-cli.exe")
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "MemoLibDev-cli.exe")
    candidates.append(Path(__file__).parent / "MemoLibDev-cli.exe")
    candidates.append(BASE_DIR / "MemoLibDev-cli.exe")

    for c in candidates:
        if c.is_file():
            return c
    return None


DEFAULT_MODEL = "memolibdev-qwen7b-16k:latest"
OLLAMA_URL = "http://localhost:11434"
CLI_TIMEOUT_SECONDS = 600
PROCESS_STOP_GRACE_SECONDS = 5


def _get_project_identity(project_path: str) -> dict:
    """Identifie le depot Git cible avec des commandes locales en lecture seule."""
    def git_value(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", project_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=True,
        )
        return result.stdout.strip()

    return {
        "root": git_value("rev-parse", "--show-toplevel"),
        "branch": git_value("branch", "--show-current") or "(HEAD detachee)",
        "head": git_value("rev-parse", "--short", "HEAD"),
    }


def _detect_mission_mode(mission: str) -> str:
    """Conserve la regle de detection du mode de la GUI."""
    mission_lower = mission.lower()
    keywords_analyse = (
        "decris", "décris", "analyse", "explique", "liste",
        "documente", "cherche", "trouve", "signale", "identifie",
        "verifie", "vérifie", "resume", "résume", "presente",
        "présente", "explore", "inspecte", "comprends",
    )
    if any(k in mission_lower for k in keywords_analyse):
        return "READ_ONLY"
    return "PROPOSE"


@dataclass(frozen=True)
class ProcessOutput:
    lines: list[str]
    timed_out: bool
    termination_confirmed: bool
    reader_error: str | None
    returncode: int | None


def _stop_process_tree(proc: subprocess.Popen) -> bool:
    """Arrête la CLI et ses descendants, jamais le service Ollama externe."""
    if proc.poll() is not None:
        return True

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PROCESS_STOP_GRACE_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                proc.kill()
        else:
            proc.terminate()
        proc.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
            proc.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
            return True
        except (OSError, subprocess.SubprocessError):
            return proc.poll() is not None


def _decode_cli_line(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace").rstrip("\r\n")


def _collect_process_output(
    proc: subprocess.Popen,
    timeout_seconds: float,
) -> ProcessOutput:
    """Lit stdout sans laisser une sortie silencieuse contourner le timeout."""
    output: queue.Queue[tuple[str, str | None]] = queue.Queue()
    lines: list[str] = []
    reader_error: str | None = None
    stdout_closed = False

    def read_stdout() -> None:
        try:
            if proc.stdout is None:
                output.put(("reader_error", "stdout indisponible"))
                return
            for raw in iter(proc.stdout.readline, b""):
                output.put(("line", _decode_cli_line(raw)))
        except (OSError, ValueError) as exc:
            output.put(("reader_error", str(exc)))
        finally:
            output.put(("eof", None))

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    termination_confirmed = True

    try:
        while proc.poll() is None or not stdout_closed:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                termination_confirmed = _stop_process_tree(proc)
                break
            try:
                kind, payload = output.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if kind == "line" and payload:
                lines.append(payload)
            elif kind == "reader_error":
                reader_error = payload
            elif kind == "eof":
                stdout_closed = True
    finally:
        if proc.poll() is None:
            termination_confirmed = _stop_process_tree(proc)
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass
        reader.join(timeout=PROCESS_STOP_GRACE_SECONDS)

    return ProcessOutput(
        lines=lines,
        timed_out=timed_out,
        termination_confirmed=termination_confirmed,
        reader_error=reader_error,
        returncode=proc.poll(),
    )

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG = "#f8f5ed"
CARD = "#fefcf7"
BORDER = "#d6d1c4"
TEXT = "#3a3733"
MUTED = "#8a8479"
ACCENT = "#4a6b8a"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"
USER = "#4d6d8a"


def check_ollama() -> tuple[bool, str]:
    """Verifie qu'Ollama repond sur localhost:11434."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            import json
            data = json.load(r)
            models = [m.get("name", "") for m in data.get("models", [])]
            return (True, f"Ollama OK ({len(models)} modele(s))")
    except Exception as e:
        return (False, f"Ollama injoignable : {e}")


def check_cli() -> tuple[bool, str]:
    if not CLI_PATH.is_file():
        return (False, f"memolibdev_cli.py introuvable dans {BASE_DIR}")
    return (True, f"CLI trouve : {CLI_PATH.name}")


class MemoLibDevApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MemoLibDev")
        self.geometry("960x820")
        self.minsize(720, 600)
        self.configure(fg_color=BG)

        self.update_idletasks()
        w, h = 960, 820
        x = (self.winfo_screenwidth() - w) // 2
        y = max(20, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.project_path = ctk.StringVar(value="(aucun projet)")
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.busy = False

        # --- V2 : initialisation de l'assistant conversationnel ---
        if _V2_AVAILABLE:
            try:
                self._v2_index = CodebaseIndex(Path(".").resolve())
                self._v2_index.build()
                self._v2_assistant = AssistantV2(
                    Path(".").resolve(),
                    index=self._v2_index,
                )
                self._v2_ready = True
                print("[V2] Assistant conversationnel pret.")
            except Exception as _e:
                self._v2_ready = False
                print(f"[V2] init echouee : {_e}")
        else:
            self._v2_ready = False
            print(f"[V2] modules indisponibles : {_V2_IMPORT_ERR}")
        self.messages = []  # historique pour export
        self._closing = False
        self._ui_events: queue.Queue[tuple[object, tuple]] = queue.Queue()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen | None = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(100, self._check_env)
        self.after(50, self._drain_ui_events)

    def _post_ui(self, callback, *args) -> None:
        if not self._closing:
            self._ui_events.put((callback, args))

    def _drain_ui_events(self) -> None:
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except tk.TclError:
                return
        if not self._closing:
            try:
                self.after(50, self._drain_ui_events)
            except tk.TclError:
                pass

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        with self._process_lock:
            proc = self._active_process
        if proc is not None and proc.poll() is None:
            threading.Thread(
                target=_stop_process_tree,
                args=(proc,),
                daemon=False,
            ).start()
        self.destroy()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Sidebar gauche (navigation) ---
        sidebar = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=0, width=200
        )
        sidebar.grid(row=0, column=0, rowspan=5, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        # En-tete sidebar
        sb_head = ctk.CTkFrame(sidebar, fg_color="transparent")
        sb_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 4))
        ctk.CTkLabel(
            sb_head, text="MemoLibDev",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=ACCENT, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            sb_head, text="AI Workspace",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=MUTED, anchor="w",
        ).pack(fill="x")

        # Separateur
        ctk.CTkFrame(
            sidebar, fg_color=BORDER, height=1,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(12, 8))

        # Items de navigation (visuels uniquement pour l'instant)
        nav_items = [
            ("Dialogue IA", True),
            ("Missions", False),
            ("Fichiers", False),
            ("Propositions", False),
            ("Controles", False),
        ]
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="ew", padx=8)
        for idx, (label, actif) in enumerate(nav_items):
            fg = ACCENT if actif else "transparent"
            tc = "#ffffff" if actif else TEXT
            ctk.CTkLabel(
                nav_frame, text=f"  {label}",
                font=ctk.CTkFont(size=12),
                text_color=tc, fg_color=fg,
                anchor="w", height=32,
            ).pack(fill="x", pady=1, padx=4)

        # Pied : projet actif
        sidebar.grid_rowconfigure(3, weight=1)
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 16))
        ctk.CTkFrame(
            footer, fg_color=BORDER, height=1,
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            footer, text="Projet actif",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=MUTED, anchor="w",
        ).pack(fill="x")
        self._sidebar_project_label = ctk.CTkLabel(
            footer, text="(aucun)",
            font=ctk.CTkFont(size=11),
            text_color=TEXT, anchor="w",
        )
        self._sidebar_project_label.pack(fill="x")

        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=64)
        header.grid(row=0, column=1, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="  MemoLibDev",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=ACCENT).grid(row=0, column=0, sticky="w", padx=(16, 8), pady=16)

        self.project_label = ctk.CTkLabel(header, textvariable=self.project_path,
                                          font=ctk.CTkFont(size=10, slant="italic"),
                                          text_color=MUTED)
        self.project_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(header, text="Choisir projet",
                      command=self._choose_project,
                      width=140, height=34,
                      fg_color=CARD, hover_color="#e8e3d5",
                      border_width=1, border_color=BORDER, text_color=TEXT).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(header, text="Sauver log",
                      command=self._save_log,
                      width=100, height=34,
                      fg_color=CARD, hover_color="#e8e3d5",
                      border_width=1, border_color=BORDER, text_color=TEXT).grid(row=0, column=3, padx=(0, 16))

        self.chat = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self.chat.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        self.chat.grid_columnconfigure(0, weight=1)

        sug = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        sug.grid(row=2, column=1, sticky="ew", padx=16, pady=(8, 4))

        for label in ["Decrire", "Erreurs", "Documenter", "Tests", "Securite"]:
            ctk.CTkButton(sug, text=label, command=lambda l=label: self._suggest(l),
                          width=100, height=30, fg_color=CARD,
                          hover_color="#e8e3d5", border_width=1, border_color=BORDER, text_color=TEXT
                          ).pack(side="left", padx=(0, 6))

        inp = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        inp.grid(row=3, column=1, sticky="ew", padx=16, pady=(4, 6))
        inp.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkTextbox(inp, height=70, fg_color=CARD,
                                     text_color=TEXT, wrap="word", border_width=0)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=10)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(inp, text="Envoyer", command=self._on_send,
                                       width=120, height=50,
                                       fg_color=ACCENT, hover_color="#3a5670",
                                       text_color="#0d1117")
        self.send_btn.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.status = ctk.CTkLabel(self, text="Prêt.", text_color=MUTED)
        self.status.grid(row=4, column=1, sticky="w", padx=20, pady=(0, 8))

    def _check_env(self):
        cli_ok, cli_msg = check_cli()
        ollama_ok, ollama_msg = check_ollama()

        if not cli_ok:
            self._assistant(f"ERREUR : {cli_msg}\n\nPlacez ce programme a cote de memolibdev_cli.py.")
            self.status.configure(text="ERREUR : CLI introuvable")
            return
        if not ollama_ok:
            self._assistant(
                "Ollama n'est pas accessible.\n\n"
                "Pour utiliser MemoLibDev, vous devez :\n"
                "1. Telecharger Ollama sur https://ollama.com/download\n"
                "2. L'installer\n"
                "3. Lancer Ollama\n"
                "4. Telecharger un modele : ollama pull qwen2.5-coder:7b\n\n"
                "Puis relancez MemoLibDev.")
            self.status.configure(text="Ollama non disponible")
            return

        self._assistant(
            f"Bonjour.\n\n{cli_msg}\n{ollama_msg}\n\n"
            "Choisissez un projet (bouton en haut a droite), "
            "puis decrivez ce que vous voulez faire en francais.\n\n"
            "Je ne modifie rien sans votre accord.")

    def _choose_project(self):
        if (
            getattr(self, "_identity_check_pending", False)
            or getattr(self, "busy", False)
        ):
            self._system(
                "Choix du projet indisponible pendant une operation."
            )
            return

        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
            try:
                self._sidebar_project_label.configure(text=Path(d).name)
            except Exception:
                pass
            self._reinit_v2_for_project(Path(d))

    def _suggest(self, label):
        m = {"Decrire": "Decris la structure du projet",
             "Erreurs": "Analyse le code et signale les erreurs",
             "Documenter": "Documente les fonctions principales",
             "Tests": "Identifie les tests et ce qu'ils verifient",
             "Securite": "Cherche les patterns de securite sensibles"}
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", m.get(label, label))

    def _on_enter(self, event):
        if event.state & 0x0001:
            return None
        self._on_send()
        return "break"

    def _reinit_v2_for_project(self, project_root: Path):
        """Reconstruit l'index et l'assistant V2 pour le projet choisi."""
        if not getattr(self, "_v2_ready", False):
            return
        try:
            self._system("Reconstruction de l'index...")
            self._v2_index = CodebaseIndex(project_root.resolve())
            n = self._v2_index.build()
            stats = self._v2_index.stats()
            self._v2_assistant = AssistantV2(
                project_root.resolve(),
                index=self._v2_index,
            )
            try:
                self._v2_assistant.new_conversation()
                self._system("Nouvelle conversation V2")
            except Exception:
                pass
            self._system(
                f"Index : {stats['files']} fichiers, "
                f"{stats['symbols']} symboles"
            )
        except Exception as e:
            self._system(f"Reconstruction index echouee : {e}")

    def _show_spinner(self, message: str = "En cours"):
        """Affiche un indicateur anime dans le status."""
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = 0
        self._spinner_msg = message
        self._spinner_active = True
        self._tick_spinner()

    def _tick_spinner(self):
        if not getattr(self, "_spinner_active", False):
            return
        try:
            frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
            self._spinner_idx += 1
            self.status.configure(
                text=f"{frame}  {self._spinner_msg}",
                text_color=ACCENT,
            )
            self.after(100, self._tick_spinner)
        except Exception:
            pass

    def _stop_spinner(self, final_text: str = "Prêt."):
        self._spinner_active = False
        try:
            self.status.configure(text=final_text, text_color=MUTED)
        except Exception:
            pass

    def _update_spinner(self, message: str):
        self._spinner_msg = message

    def v2_chat(self, text: str) -> bool:
        """Chat V2 avec etapes visibles + streaming, sans bloquer Tkinter."""
        if not getattr(self, "_v2_ready", False):
            return False

        self._user(text)
        self.send_btn.configure(state="disabled")
        self._show_spinner("Preparation...")

        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=8)
        b = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14)
        b.pack(anchor="w", padx=(0, 20), fill="x")

        header = ctk.CTkFrame(b, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            header, text="MemoLibDev", text_color=ACCENT,
            font=ctk.CTkFont(size=10, weight="bold"), anchor="w",
        ).pack(side="left")

        progress_lbl = ctk.CTkLabel(
            b, text="Recherche...", text_color=MUTED,
            font=ctk.CTkFont(size=10, slant="italic"), anchor="w",
        )
        progress_lbl.pack(fill="x", padx=14, pady=(0, 4))

        content = ctk.CTkTextbox(
            b, height=120, wrap="word",
            fg_color=CARD, text_color=TEXT,
            border_width=0, font=ctk.CTkFont(size=12),
        )
        content.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        content.insert("1.0", "")
        content.configure(state="disabled")

        self._stream_box = content
        self._stream_started = False

        def on_token(chunk):
            if not self._stream_started:
                self._stream_started = True
                self._post_ui(self._v2_set_progress, progress_lbl, "Redaction...")
                self._post_ui(self._update_spinner, "Redaction de la reponse...")
            self._post_ui(self._append_stream, chunk)

        def on_event(event):
            self._post_ui(self._show_tool_event, event)

        def worker():
            try:
                response = self._v2_assistant.chat_with_tools(
                    text, on_token=on_token, on_event=on_event
                )
                self._post_ui(self._v2_done_ok, response, progress_lbl)
            except Exception as e:
                self._post_ui(self._v2_done_err, str(e), progress_lbl)

        threading.Thread(
            target=worker, daemon=True, name="MemoLibDev-V2Chat"
        ).start()
        return True

    def _show_tool_event(self, event):
        """Affiche un evenement d'outil dans le chat (bulle systeme)."""
        try:
            kind = event.get("kind")
            if kind == "tool_call":
                name = event.get("name", "?")
                args = event.get("args", {})
                arg_repr = ", ".join(
                    f"{k}={v}" for k, v in list(args.items())[:2]
                )
                txt = f"\u2699 {name}({arg_repr})"
                self._system(txt)
            elif kind == "tool_result":
                name = event.get("name", "?")
                ok = event.get("ok", False)
                mark = "\u2713" if ok else "\u2717"
                summary = (event.get("summary") or "")[:120]
                self._system(f"{mark} {name} \u2192 {summary}")
        except Exception:
            pass

    def _v2_set_progress(self, lbl, text):
        try:
            if lbl.winfo_exists():
                lbl.configure(text=text)
        except Exception:
            pass

    def _v2_done_ok(self, response, progress_lbl):
        self.messages.append(f"[MemoLibDev] {response}")
        try:
            progress_lbl.destroy()
        except Exception:
            pass
        self._stop_spinner("Pret.")
        self.send_btn.configure(state="normal")

    def _v2_done_err(self, err, progress_lbl):
        self._system(f"V2 erreur : {err}")
        try:
            progress_lbl.destroy()
        except Exception:
            pass
        self._stop_spinner("Erreur.")
        self.send_btn.configure(state="normal")

    def _append_stream(self, chunk: str):
        """Ajoute un token a la bulle de streaming."""
        box = getattr(self, "_stream_box", None)
        if box is None:
            return
        try:
            box.configure(state="normal")
            box.insert("end", chunk)
            box.see("end")
            box.configure(state="disabled")
            self.after(10, self._scroll)
        except Exception:
            pass

    def _on_send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return

        if getattr(self, "_identity_check_pending", False):
            return


        # --- V2 : priorite si disponible ---
        if getattr(self, "_v2_ready", False):
            self.entry.delete("1.0", "end")
            if self.v2_chat(text):
                return
        # --- sinon, continuer avec la CLI existante ---

        proj = self.project_path.get()
        if not proj or proj.startswith("("):
            self._assistant(
                "Aucun projet selectionne. Cliquez sur 'Choisir projet'. "
                "Votre texte a ete conserve."
            )
            return

        self._identity_check_pending = True
        self.send_btn.configure(state="disabled")
        self._system("Verification du depot Git en cours...")

        def verify_target():
            try:
                identity = _get_project_identity(proj)
                error = None
            except Exception as exc:
                identity = None
                error = f"{type(exc).__name__}: {exc}"

            self._post_ui(
                self._on_project_identity_checked,
                text,
                proj,
                identity,
                error,
            )

        try:
            threading.Thread(
                target=verify_target,
                name="MemoLibDev-GitIdentity",
                daemon=True,
            ).start()
        except Exception as exc:
            self._identity_check_pending = False
            self.send_btn.configure(state="normal")
            self._assistant(
                f"Verification impossible : {type(exc).__name__}: {exc}\n"
                "Votre texte a ete conserve."
            )

    def _on_project_identity_checked(self, text, proj, identity, error):
        self._identity_check_pending = False
        self.send_btn.configure(state="normal")

        if error or identity is None:
            self._assistant(
                "Mission non lancee : depot Git non verifiable. "
                f"Detail : {error or 'identite absente'}\\n"
                "Votre texte a ete conserve."
            )
            return

        # Refuser une confirmation devenue obsolette.
        if self.project_path.get() != proj:
            self._system("Mission annulee : le projet selectionne a change.")
            return

        if self.entry.get("1.0", "end").strip() != text:
            self._system(
                "Mission annulee : le texte a change pendant la verification. "
                "Relisez votre texte puis relancez la demande."
            )
            return

        mode = _detect_mission_mode(text)
        confirmation = (
            "Confirmer le lancement de cette mission ?\\n\\n"
            f"Depot : {identity['root']}\\n"
            f"Branche : {identity['branch']}\\n"
            f"Commit : {identity['head']}\\n"
            f"Mode : {mode}\\n\\n"
            f"Mission :\\n{text}\\n\\n"
            "La confirmation autorise le lancement, pas "
            "l'application automatique d'un changement."
        )

        if not messagebox.askyesno(
            "Confirmer la mission MemoLibDev",
            confirmation,
            parent=self,
        ):
            self._system("Mission annulee par l'utilisateur.")
            return

        # Garder le verrou pendant la seconde verification Git.
        self._identity_check_pending = True
        self.send_btn.configure(state="disabled")
        self._system("Nouvelle verification Git avant lancement...")

        def verify_final_target():
            try:
                final_identity = _get_project_identity(proj)
                final_error = None
            except Exception as exc:
                final_identity = None
                final_error = f"{type(exc).__name__}: {exc}"

            self._post_ui(
                self._on_final_identity_checked,
                text,
                proj,
                identity,
                final_identity,
                final_error,
            )

        try:
            threading.Thread(
                target=verify_final_target,
                name="MemoLibDev-GitFinalCheck",
                daemon=True,
            ).start()
        except Exception as exc:
            self._identity_check_pending = False
            self.send_btn.configure(state="normal")
            self._assistant(
                f"Verification finale impossible : "
                f"{type(exc).__name__}: {exc}\\n"
                "Mission non lancee. Texte conserve."
            )

    def _on_final_identity_checked(
        self, text, proj, identity, final_identity, error
    ):
        self._identity_check_pending = False
        self.send_btn.configure(state="normal")

        if error or final_identity is None:
            self._assistant(
                "Mission non lancee : seconde verification Git impossible. "
                f"Detail : {error or 'identite absente'}\\n"
                "Votre texte a ete conserve."
            )
            return

        if self.project_path.get() != proj:
            self._system(
                "Mission annulee : le projet selectionne a change."
            )
            return

        if self.entry.get("1.0", "end").strip() != text:
            self._system(
                "Mission annulee : le texte a change pendant la "
                "verification finale. Texte conserve."
            )
            return

        keys = ("root", "branch", "head")
        if any(
            final_identity.get(key) != identity.get(key)
            for key in keys
        ):
            self._assistant(
                "Mission non lancee : l'identite Git a change "
                "depuis la confirmation. Verifiez le depot et relancez. "
                "Votre texte a ete conserve."
            )
            return

        self.entry.delete("1.0", "end")
        self._user(text)
        self._run(final_identity["root"], text)

    def _user(self, t):
        self._bubble(t, "user")

    def _assistant(self, t):
        self._bubble(t, "assistant")

    def _system(self, t):
        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(
            f,
            text=t,
            text_color=MUTED,
            font=ctk.CTkFont(size=10, slant="italic"),
            anchor="w",
            justify="left",
            wraplength=800,
        ).pack(fill="x")
        self.messages.append(f"[Système] {t}")

    def _bubble(self, text, role):
        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=8)

        if role == "user":
            bg, fg, anchor, padx, author = (
                USER, "#ffffff", "e", (60, 0), "Vous"
            )
        else:
            bg, fg, anchor, padx, author = (
                CARD, TEXT, "w", (0, 20), "MemoLibDev"
            )

        b = ctk.CTkFrame(f, fg_color=bg, corner_radius=14)
        b.pack(anchor=anchor, padx=padx, fill="x")

        header = ctk.CTkFrame(b, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 2))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=author,
            text_color=ACCENT if role == "assistant" else "#ffffff",
            font=ctk.CTkFont(size=10, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if role == "assistant":
            ctk.CTkButton(
                header,
                text="Copier",
                width=76,
                height=28,
                command=lambda value=text: self._copy_text(value), text_color=TEXT
            ).grid(row=0, column=1, padx=(8, 0))

            visible_lines = min(text.count("\n") + 1, 18)
            content = ctk.CTkTextbox(
                b,
                height=max(90, visible_lines * 22),
                wrap="word",
                fg_color=bg,
                text_color=fg,
                border_width=0,
                font=ctk.CTkFont(size=12),
            )
            content.pack(fill="x", expand=True, padx=10, pady=(0, 10))
            content.insert("1.0", text)
            content.configure(state="disabled")
        else:
            ctk.CTkLabel(
                b,
                text=text,
                text_color=fg,
                font=ctk.CTkFont(size=12),
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(fill="x", padx=14, pady=(0, 10))

        self.messages.append(f"[{author}] {text}")
        self.after(80, self._scroll)

    def _copy_text(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            self.status.configure(
                text="Réponse copiée dans le presse-papiers."
            )
        except Exception as exc:
            self.status.configure(
                text=f"Copie impossible : {type(exc).__name__}"
            )

    def _scroll(self):
        try:
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _save_log(self):
        from tkinter import filedialog
        import datetime
        p = filedialog.asksaveasfilename(
            title="Sauver le log",
            defaultextension=".txt",
            initialfile=f"memolibdev_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Texte", "*.txt"), ("Tous", "*.*")],
        )
        if not p:
            return
        try:
            Path(p).write_text("\n".join(self.messages), encoding="utf-8")
            self._system(f"Log sauve : {p}")
        except Exception as e:
            self._assistant(f"Erreur sauvegarde : {e}")

    def _run(self, project, mission):
        self.busy = True
        self.send_btn.configure(state="disabled")
        self.status.configure(text="En cours...")

        def worker():
            proc = None
            completion_status = "Pret."
            # Trouver le CLI : MemoLibDev-cli.exe a cote, sinon memolibdev_cli.py
            cli_exe = find_cli_executable()
            cli_py = BASE_DIR / "memolibdev_cli.py"

            env = os.environ.copy()
            env["MEMOLIBDEV_TARGET"] = project
            env["PYTHONIOENCODING"] = "utf-8"

            if cli_exe is not None:
                cmd = [str(cli_exe)]
                self._post_ui(self._system, f"CLI : {cli_exe}")
            elif cli_py.is_file():
                cmd = [sys.executable, str(cli_py)]
                self._post_ui(self._system, f"CLI (python) : {cli_py}")
            else:
                completion_status = "Erreur : CLI introuvable."
                self._post_ui(
                    self._assistant,
                    f"CLI introuvable. Cherche dans :\n"
                    f"  {Path(sys.executable).parent}\n"
                    f"  {BASE_DIR}",
                )
                self._post_ui(self._done, completion_status)
                return

            # Detecter automatiquement le mode selon la mission
            mode = _detect_mission_mode(mission)

            self._post_ui(self._system, f"Mode : {mode}")

            # La CLI Python connue accepte --project.
            # Pour un executable precompile, conserver MEMOLIBDEV_TARGET
            # tant que sa compatibilite avec --project n'est pas verifiee.
            if cli_exe is None:
                cmd += ["--project", str(project)]

            cmd += [
                "--mission", mission,
                "--mode", mode,
                "--model", self.model_var.get().strip(),
                "--timeout", "300",
            ]

            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt":
                    creationflags |= getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                    )
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(BASE_DIR),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                with self._process_lock:
                    self._active_process = proc

                output = _collect_process_output(proc, CLI_TIMEOUT_SECONDS)
                if output.lines:
                    self._post_ui(self._assistant, "\n".join(output.lines))
                if output.reader_error:
                    self._post_ui(
                        self._assistant,
                        f"Lecture CLI : {output.reader_error}",
                    )
                if output.timed_out:
                    completion_status = "Timeout : CLI arretee."
                    message = (
                        "Delai global depasse. La CLI et ses processus "
                        "enfants ont ete arretes."
                    )
                    if not output.termination_confirmed:
                        message = (
                            "Delai global depasse ; arret du processus "
                            "non confirme."
                        )
                    self._post_ui(self._assistant, message)
                elif output.returncode:
                    completion_status = (
                        f"CLI terminee avec le code {output.returncode}."
                    )
                    self._post_ui(self._assistant, completion_status)
            except OSError as exc:
                completion_status = "Erreur de lancement CLI."
                self._post_ui(
                    self._assistant,
                    f"Erreur de lancement : {type(exc).__name__}: {exc}",
                )
            except Exception as exc:
                completion_status = "Erreur inattendue de supervision."
                self._post_ui(
                    self._assistant,
                    f"Erreur : {type(exc).__name__}: {exc}",
                )
            finally:
                if proc is not None and proc.poll() is None:
                    _stop_process_tree(proc)
                with self._process_lock:
                    if self._active_process is proc:
                        self._active_process = None
                self._post_ui(self._done, completion_status)

        threading.Thread(target=worker, daemon=True).start()

    def _display(self, raw):
        if not raw.strip():
            self._assistant("(aucune sortie)")
            return
        for line in raw.splitlines():
            if line.strip():
                self._assistant(line)

    def _done(self, status_text="Pret."):
        self.busy = False
        self.send_btn.configure(state="normal")
        self.status.configure(text=status_text)


def main():
    app = MemoLibDevApp()
    app.mainloop()


if __name__ == "__main__":
    main()
