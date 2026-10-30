from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import sys, uvicorn, subprocess, tempfile, os, sqlite3, json, hashlib, datetime, re
import urllib.request as _urllib_req
from knowledge_base import get_context_for_prompt

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_env_root = os.environ.get("MEMOLIB_ROOT")
current_root = Path(_env_root) if _env_root else Path.home() / "Desktop"

if getattr(__import__('sys'), "frozen", False):
    _BASE_DIR = Path(__import__('sys').executable).parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

_env_msafe = os.environ.get("MEMOLIB_MSAFE")
MSAFE_SCRIPT = Path(_env_msafe) if _env_msafe else (_BASE_DIR / "vendor" / "memolib_safe_apply.py")

USER_DATA_DIR = Path(os.getenv('LOCALAPPDATA', Path.home())) / "MemoLibDev"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(USER_DATA_DIR / "memolib.db")
CONFIG_PATH = USER_DATA_DIR / "config.json"

def load_config():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except: pass
    return {"model": "qwen2.5-coder:1.5b"}

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg), encoding="utf-8")

CURRENT_CONFIG = load_config()

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
init_db()

def clean_ai_code(raw_code: str) -> str:
    lines = raw_code.splitlines()
    cleaned = [line for line in lines if not line.strip().startswith("```")]
    return chr(10).join(cleaned).strip()


def analyze_intent(prompt: str) -> dict:
    """Analyse l'intention reelle de l'utilisateur derriere sa demande."""
    prompt_lower = prompt.lower()
    
    # Intentions possibles
    intents = {
        "learn": ["explique", "pourquoi", "comment ça marche", "c'est quoi", "définition", 
                  "je ne comprends pas", "difference entre", "apprends-moi", "forme-moi",
                  "cours", "tutoriel", "concept", "principe", "quest-ce que"],
        "debug": ["bug", "erreur", "ça plante", "ne marche pas", "corrige", "répare",
                  "crash", "exception", "traceback", "fail", "broken"],
        "review": ["vérifie", "review", "audit", "analyse ce code", "regarde", "ameliore",
                   "refactorise", "optimise", "améliore"],
        "build": ["ajoute", "crée", "implemente", "génère", "ajoute une fonction", "crée un fichier",
                  "construis", "développe"],
        "explain_choice": ["pourquoi ce choix", "quelle est la meilleure", "quel est le meilleur",
                           "recommandation", "conseil", "quel langage", "quel framework"],
    }
    
    detected = []
    for intent_name, keywords in intents.items():
        if any(kw in prompt_lower for kw in keywords):
            detected.append(intent_name)
    
    # Si aucune intention détectée, on suppose "build" par défaut
    if not detected:
        detected = ["build"]
    
    return {
        "intents": detected,
        "is_learning": "learn" in detected or "explain_choice" in detected,
        "is_debugging": "debug" in detected,
        "is_reviewing": "review" in detected,
    }


def verify_code_syntax(file_rel: str, content: str):
    if file_rel.endswith(".py"):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8") as f:
            f.write(content); tmp = f.name
        try:
            res = subprocess.run(["python", "-m", "py_compile", tmp], capture_output=True, text=True)
            if res.returncode != 0: return False, res.stderr
        finally:
            import os; os.unlink(tmp)
    return True, "OK"

def get_smart_context(project_dir: Path, prompt: str, current_file: str) -> str:
    words = re.findall(r'\b[A-Za-z_]\w{4,}\b', prompt)
    if not words: return ""
    context = ""
    ignore = {".git", "node_modules", "build", "__pycache__", ".dart_tool", "dist", ".venv", "venv", ".turbo", ".next", ".memolib"}
    found = 0
    try:
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ignore]
            for f in files:
                if found >= 2: break
                rel_path = (Path(root) / f).relative_to(project_dir).as_posix()
                if rel_path == current_file: continue
                if f.endswith(('.py', '.js', '.ts', '.dart')):
                    try:
                        content = (Path(root) / f).read_text(encoding="utf-8", errors="ignore")
                        if any(word in content for word in words):
                            context += chr(10) + "--- Fichier lie : '" + rel_path + "' ---" + chr(10)
                            context += content[:1500]
                            found += 1
                    except: pass
            if found >= 2: break
    except: pass
    return context

class RootConfig(BaseModel): path: str
class FileWriteRequest(BaseModel):
    project: str
    file: str
    content: str
    secure: bool = False
class TalkRequest(BaseModel):
    prompt: str
    history: list = []

class ChatRequest(BaseModel):
    project: str
    file: str
    content: str
    prompt: str
    history: list = []
class SettingsRequest(BaseModel):
    model: str

@app.get("/settings")
def get_settings():
    return CURRENT_CONFIG

@app.post("/settings")
def set_settings(req: SettingsRequest):
    global CURRENT_CONFIG
    CURRENT_CONFIG["model"] = req.model
    save_config(CURRENT_CONFIG)
    return {"status": "success", "config": CURRENT_CONFIG}

@app.get("/health")
def health_check():
    ollama_ok = False
    try:
        req = _urllib_req.Request("http://127.0.0.1:11434/api/tags")
        with _urllib_req.urlopen(req, timeout=2) as resp:
            ollama_ok = resp.status == 200
    except: 
        # AUTO-START : On tente de lancer Ollama si il est eteint
        print("[AUTO-START] Ollama n'est pas lance. Tentative de demarrage...")
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            import time
            time.sleep(4) # On attend qu'il demarre
            req = _urllib_req.Request("http://127.0.0.1:11434/api/tags")
            with _urllib_req.urlopen(req, timeout=3) as resp:
                ollama_ok = resp.status == 200
                if ollama_ok:
                    print("[AUTO-START] Ollama demarre avec succes !")
        except Exception as e:
            print(f"[AUTO-START] Echec du demarrage automatique : {e}")
            ollama_ok = False

    return {"backend": "alive", "ollama": "alive" if ollama_ok else "dead"}

@app.get("/list")
def list_projects():
    try:
        items = [d.name for d in current_root.iterdir() if d.is_dir() and not d.name.startswith('.')]
        return {"projects": items, "current_root": str(current_root)}
    except: return {"projects": [], "current_root": str(current_root)}

@app.post("/config/root")
def set_root(req: RootConfig):
    global current_root
    p = Path(req.path)
    if p.is_dir():
        current_root = p
        return {"status": "success", "root": str(current_root)}
    raise HTTPException(400, "Dossier introuvable.")

@app.get("/files")
def list_files(project: str):
    try:
        proj_path = current_root / project
        if not proj_path.is_dir(): raise HTTPException(400, "Dossier introuvable")
        files = []
        ignore = {".dart_tool", "build", "node_modules", ".git", "dist", "__pycache__", ".venv", "venv", ".idea", ".vscode", ".memolib"}
        def handle_err(e): pass
        for root, dirs, filenames in os.walk(proj_path, onerror=handle_err):
            dirs[:] = [d for d in dirs if d not in ignore]
            for f in filenames:
                if f.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.dart', '.md', '.txt', '.json', '.html', '.css', '.yml', '.yaml')):
                    try: files.append((Path(root) / f).relative_to(proj_path).as_posix())
                    except: pass
        return {"files": sorted(list(set(files)))}
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/read")
def read_file(project: str, file: str):
    try:
        file_path = current_root / project / file
        return {"content": file_path.read_text(encoding="utf-8", errors="replace")}
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/write")
def write_file(req: FileWriteRequest):
    try:
        project_dir = current_root / req.project
        file_rel = req.file.replace(os.sep, "/")
        if ":" in file_rel or file_rel.startswith("/") or ".." in file_rel:
            file_rel = Path(file_rel).name
        file_path = project_dir / file_rel

        git_dir = project_dir / ".git"
        if git_dir.is_dir():
            exclude_file = git_dir / "info" / "exclude"
            exclude_file.parent.mkdir(parents=True, exist_ok=True)
            if exclude_file.exists():
                excl_content = exclude_file.read_text(encoding="utf-8")
                if ".memolib/" not in excl_content:
                    exclude_file.write_text(excl_content + chr(10) + ".memolib/" + chr(10), encoding="utf-8")

        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(req.content, encoding="utf-8", newline="")
            return {"status": "success", "message": "Nouveau fichier APPLIED"}

        if not req.secure:
            file_path.write_text(req.content, encoding="utf-8", newline="")
            return {"status": "success", "message": "Sauvegarde"}

        is_git = subprocess.run(["git", "-C", str(project_dir), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True).returncode == 0
        if not is_git:
            file_path.write_text(req.content, encoding="utf-8", newline="")
            return {"status": "success", "message": "Pas un depot Git."}

        original_bytes = file_path.read_bytes()
        original = original_bytes.decode("utf-8", errors="replace")
        
        if original == req.content:
            return {"status": "success", "message": "Aucune modification"}

        file_path.write_text(req.content, encoding="utf-8", newline="")
        
        diff_proc = subprocess.run(["git", "-C", str(project_dir), "diff", "--no-color", "--", file_rel], capture_output=True, text=True, encoding="utf-8", errors="replace")
        diff = diff_proc.stdout

        file_path.write_bytes(original_bytes)

        if not diff.strip():
            return {"status": "success", "message": "Aucune modification"}

        normalized = diff.replace(chr(13) + chr(10), chr(10))
        if normalized and not normalized.endswith(chr(10)): normalized += chr(10)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".diff", mode="w", encoding="utf-8", newline="") as f:
            f.write(normalized); diff_path = f.name

        diff_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        proposal_id = "P-" + diff_sha[:24]
        
        aip_dir = project_dir / ".memolib" / "proofs"
        aip_dir.mkdir(parents=True, exist_ok=True)
        snap_dir = project_dir / ".memolib" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)

        import time
        ts = int(time.time())
        safe_name = file_rel.replace("/", "_").replace("\\", "_")
        (snap_dir / f"{safe_name}_{ts}.txt").write_bytes(original_bytes)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".auth.json", mode="w", encoding="utf-8") as f:
            json.dump({"proposal_id": proposal_id, "expected_diff_sha256": diff_sha}, f); auth_path = f.name

        result = subprocess.run(["python", str(MSAFE_SCRIPT), diff_path, "--file", file_rel, "--root", str(project_dir), "--authorization", auth_path], capture_output=True, text=True, encoding="utf-8", errors="replace")
        
        os.unlink(diff_path); os.unlink(auth_path)

        if result.returncode == 0:
            aip_data = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "file": file_rel,
                "sha256_before": hashlib.sha256(original_bytes).hexdigest(),
                "sha256_after": hashlib.sha256(req.content.encode("utf-8")).hexdigest(),
                "sha256_diff": diff_sha,
                "approver": "human"
            }
            (aip_dir / f"proof_{ts}.json").write_text(json.dumps(aip_data, indent=2), encoding="utf-8")
            return {"status": "success", "message": "Code APPLIED (msafe) + AIP"}
        elif result.returncode == 1:
            return {"status": "rolled_back", "message": "Rollback sur " + file_rel}
        else:
            return {"status": "error", "message": result.stdout + result.stderr}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}


class HistoryRequest(BaseModel):
    project: str
    file: str

@app.post("/history")
def get_history(req: HistoryRequest):
    try:
        project_dir = current_root / req.project
        safe_name = req.file.replace("/", "_").replace(os.sep, "_")
        snap_dir = project_dir / ".memolib" / "snapshots"
        
        history = []
        if snap_dir.exists():
            for f in snap_dir.glob(f"{safe_name}_*.txt"):
                ts_str = f.stem.split("_")[-1]
                import datetime
                dt = datetime.datetime.fromtimestamp(int(ts_str)).strftime('%Y-%m-%d %H:%M:%S')
                history.append({"id": f.name, "date": dt})
        return {"history": sorted(history, key=lambda x: x['date'], reverse=True)}
    except Exception as e:
        return {"history": [], "error": str(e)}

class RestoreRequest(BaseModel):
    project: str
    file: str
    snapshot_id: str

@app.post("/restore")
def restore_history(req: RestoreRequest):
    try:
        project_dir = current_root / req.project
        file_path = project_dir / req.file
        snap_path = project_dir / ".memolib" / "snapshots" / req.snapshot_id
        
        if snap_path.exists():
            content = snap_path.read_text(encoding="utf-8")
            file_path.write_text(content, encoding="utf-8", newline="")
            return {"status": "success", "content": content}
        return {"status": "error", "message": "Snapshot introuvable"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class AipListRequest(BaseModel):
    project: str

@app.post("/aip/list")
def list_aip(req: AipListRequest):
    try:
        project_dir = current_root / req.project
        aip_dir = project_dir / ".memolib" / "proofs"
        if not aip_dir.exists():
            return {"proofs": []}
        
        proofs = []
        for f in sorted(aip_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                proofs.append({
                    "file": data.get("file", "inconnu"),
                    "timestamp": data.get("timestamp", ""),
                    "sha256": data.get("sha256_after", "")[:16],
                    "status": "APPLIED"
                })
            except: pass
        return {"proofs": proofs}
    except Exception as e:
        return {"proofs": [], "error": str(e)}


class LearnRequest(BaseModel):
    concept: str
    context: str = ""

@app.post("/learn")
def learn_concept(req: LearnRequest):
    """Mode Apprentissage : l'IA explique un concept en profondeur."""
    full_prompt = (
        "Tu es un Professeur d'Informatique. L'utilisateur veut apprendre le concept suivant : "
        + req.concept + chr(10) + chr(10) +
        (("Contexte du projet : " + req.context + chr(10) + chr(10)) if req.context else "") +
        "Structure ta reponse ainsi :" + chr(10) +
        "1. **Definition simple** (1 phrase, sans jargon)" + chr(10) +
        "2. **Pourquoi c'est important** (2 phrases)" + chr(10) +
        "3. **Exemple concret** (un bout de code de 5 lignes maximum)" + chr(10) +
        "4. **Erreur courante** (1 phrase)" + chr(10) +
        "5. **Pour aller plus loin** (1 phrase)" + chr(10) + chr(10) +
        "Sois pedagogue, encourageant et concret."
    )
    
    def generate():
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate"
        data = {"model": CURRENT_CONFIG.get("model", "qwen2.5-coder:1.5b"), "prompt": full_prompt, "stream": True, "keep_alive": "30m", "options": {"num_predict": 400}}
        req_obj = _urllib_req.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        
        full_content = ""
        try:
            with _urllib_req.urlopen(req_obj, timeout=300) as resp:
                for line in resp:
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            text_chunk = chunk.get("response", "")
                            full_content += text_chunk
                            yield "data: " + json.dumps({'chunk': text_chunk}) + chr(10) + chr(10)
                        except: pass
        except Exception as e:
            yield "data: " + json.dumps({'error': str(e)}) + chr(10) + chr(10)
            return
        yield "data: " + json.dumps({'status': 'chat', 'content': full_content}) + chr(10) + chr(10)
    
    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
# MODE VOCAL — Speech-to-Text et Text-to-Speech (100% local)
# ============================================================
import base64

VOICE_MODEL_DIR = Path(os.getenv("LOCALAPPDATA_VOICE", Path(os.getenv("LOCALAPPDATA", Path.home())) / "MemoLibDev" / "voice"))
VOICE_MODEL_DIR.mkdir(parents=True, exist_ok=True)

_whisper_model = None

def get_whisper():
    """Charge le modele Whisper en lazy (premier appel uniquement)."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("[VOICE] Chargement du modele Whisper (1er appel)...")
            _whisper_model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
            print("[VOICE] Whisper pret.")
        except Exception as e:
            print(f"[VOICE] Erreur chargement Whisper : {e}")
            raise
    return _whisper_model

class TranscribeRequest(BaseModel):
    audio_b64: str  # audio webm/mp3/wav encode en base64

@app.post("/transcribe")
def transcribe_audio(req: TranscribeRequest):
    """Recoit un audio en base64, transcrit en francais, retourne le texte."""
    try:
        import tempfile
        from faster_whisper import WhisperModel

        audio_bytes = base64.b64decode(req.audio_b64)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
            f.write(audio_bytes)
            audio_path = f.name

        model = get_whisper()
        segments, info = model.transcribe(audio_path, language="fr", beam_size=5)
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        os.unlink(audio_path)

        return {"text": transcript, "language": "fr", "duration": info.duration}
    except Exception as e:
        return {"error": str(e), "text": ""}

class SpeakRequest(BaseModel):
    text: str
    voice: str = "fr_FR-siwis-medium"  # voix par defaut Piper (fr)

@app.post("/speak")
def speak_text(req: SpeakRequest):
    try:
        import subprocess
        import tempfile
        import sys
        import re
        import os

        clean_text = re.sub(r'[*#_`>]', '', req.text)
        clean_text = clean_text.replace('\n', ' ').replace('\r', ' ')
        clean_text = re.sub(r'[^a-zA-Z0-9àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ\s.,!?;:]', '', clean_text)
        clean_text = " ".join(clean_text.split())[:400].strip()
        
        if not clean_text:
            return {"error": "Texte vide", "audio_b64": ""}

        print(f"🔊 [TTS] Texte envoye a Piper : '{clean_text}'")

        voice_file = VOICE_MODEL_DIR / (req.voice + ".onnx")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as out:
            output_path = out.name

        cmd = [sys.executable, "-m", "piper", "-m", str(voice_file), "-f", output_path]
        result = subprocess.run(cmd, input=(clean_text + "\n").encode("utf-8"), capture_output=True, timeout=60)

        if result.returncode != 0:
            print(f"❌ [TTS] Piper a echoue : {result.stderr.decode('utf-8', errors='ignore')[:200]}")
            return {"error": "Piper a echoue", "audio_b64": ""}

        with open(output_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("ascii")
        os.unlink(output_path)
        return {"audio_b64": audio_b64, "format": "wav"}
        
    except Exception as e:
        print("❌ [TTS] ERREUR CRITIQUE :", e)
        return {"error": str(e), "audio_b64": ""}

@app.post("/talk")
def talk_endpoint(req: TalkRequest):
    try:
        # --- ETAPE 1 : ROUTEUR ULTRA-RAPIDE (0 ms) ---
        # On cherche des mots-cles au lieu d'appeler un modele LLM (economie de RAM et latence)
        mots_web = ["qui", "quoi", "quand", "ou", "pourquoi", "comment", "actualite", "actualité", "nouvelle", "info", "cherche", "meteo", "météo", "president", "président", "monde", "aujourd'hui"]
        needs_search = any(mot in req.prompt.lower() for mot in mots_web)
        
        web_context = ""
        if needs_search:
            print(f"[ROUTEUR] Intention : Recherche Web | Mots-cles : {req.prompt}")
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(req.prompt, max_results=3))
                    if results:
                        web_context = "Voici des informations trouvees sur le web :" + chr(10)
                        for r in results:
                            web_context += "- " + str(r.get("title", "")) + " : " + str(r.get("body", "")) + chr(10)
            except Exception as e:
                print("[ACTION] Recherche web echouee :", e)
        else:
            print("[ROUTEUR] Intention : Conversation simple.")

        # --- ETAPE 2 : LE CERVEAU (Llama 3.2) ---
        history_block = ""
        for msg in req.history[-4:]:
            role = "Utilisateur" if msg.get("isUser") else "Assistant"
            history_block += role + ": " + msg.get("text", "") + chr(10)
            
        history_text = ("Historique :" + chr(10) + history_block) if history_block else ""

        full_prompt = (
            "Tu es un assistant vocal. Tu DOIS répondre UNIQUEMENT en français. Ne réponds JAMAIS en anglais." + chr(10) +
            "Ne fais pas de longues phrases." + chr(10) + chr(10) +
            web_context + chr(10) +
            history_text +
            "Utilisateur : " + req.prompt + chr(10) +
            "Assistant :"
        )

        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate"
        data = {
            "model": CURRENT_CONFIG.get("model", "llama3.2:latest"),
            "prompt": full_prompt, 
            "stream": True, 
            "keep_alive": -1,  # <--- LE CERVEAU RESTE EN RAM POUR TOUJOURS
            "options": {"num_predict": 40, "temperature": 0.2}
        }
        req_obj = _urllib_req.Request(url, data=json.dumps(data).encode('utf-8'),
                                      headers={'Content-Type': 'application/json'})
        
        def generate():
            full = ""
            try:
                with _urllib_req.urlopen(req_obj, timeout=120) as resp:
                    for line in resp:
                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                t = chunk.get("response", "")
                                full += t
                                yield "data: " + json.dumps({'chunk': t}) + chr(10) + chr(10)
                            except: pass
            except Exception as e:
                yield "data: " + json.dumps({'error': str(e)}) + chr(10) + chr(10)
                return
            yield "data: " + json.dumps({'status': 'chat', 'content': full}) + chr(10) + chr(10)

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        print("ERREUR CRITIQUE /talk :", str(e))
        return {"error": str(e)}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    # On recupere la date et l'heure systeme actuelles
    now = datetime.datetime.now()
    date_str = now.strftime("%A %d %B %Y, %H:%M")
    
    # On l'injecte dans le contexte pour que l'IA le lise
    safe_content = req.content[:8000] + (chr(10) + "... [Tronque]" if len(req.content) > 8000 else "")
    time_context = "[CONTEXTE TEMPOREL] Nous sommes actuellement le " + date_str + "." + chr(10)

    project_dir = current_root / req.project
    smart_ctx = "" # Desactive pour accelerer (on le remettra apres)
    if smart_ctx:
        smart_ctx = chr(10) + chr(10) + "[CONTEXTE AUTOMATIQUE DU PROJET]" + chr(10) + "Voici d'autres fichiers du projet qui pourraient t'aider :" + chr(10) + smart_ctx

    history_text = ""
    for msg in req.history[-5:]:
        role = "Utilisateur" if msg.get("isUser") else "Assistant"
        history_text += role + ": " + msg.get('text', '') + chr(10)

    prompt_lower = req.prompt.lower()
    mots_code = ["ajoute", "modifie", "supprime", "corrige", "refactorise", "cree", "change", "remplace", "bug"]
    veut_coder = bool(req.file) and any(mot in prompt_lower for mot in mots_code)

    if veut_coder:
        full_prompt = (
            "Tu es un Ingenieur Logiciel Senior expert. Tu modifies le fichier '" + req.file + "'." + chr(10) +
            "Voici le code actuel :" + chr(10) + "---" + chr(10) + safe_content + chr(10) + "---" + chr(10) +
            smart_ctx + chr(10) + chr(10) +
            "Demande de l'utilisateur : " + req.prompt + chr(10) + chr(10) +
            "REGLES STRICTES :" + chr(10) +
            "1. Ne casse pas le code existant qui fonctionne." + chr(10) +
            "2. Applique les bonnes pratiques (lisibilite, securite)." + chr(10) +
            "3. Ecris UNIQUEMENT le nouveau contenu complet du fichier." + chr(10) +
            "4. N'ajoute AUCUNE phrase avant ou apres le code."
        )
    else:
        ctx = ("L'utilisateur te parle du fichier '"  + req.file + "'.") if req.file else "Aucun fichier n'est ouvert. Si l'utilisateur demande une modification, dis-lui d'ouvrir un fichier."
        kb_context = get_context_for_prompt(req.prompt, k=3)
        full_prompt = (
            "Tu es MemoLibDev, un Mentor Pedagogue expert en developpement logiciel." + chr(10) +
            "Ta mission : non seulement repondre, mais AIDER L'UTILISATEUR A COMPRENDRE et A PROGRESSER." + chr(10) +
            "Quand tu expliques, tu dois toujours :" + chr(10) +
            "1. Donner la reponse directe (le 'QUOI')." + chr(10) +
            "2. Expliquer le raisonnement (le 'POURQUOI')." + chr(10) +
            "3. Citer une bonne pratique ou un concept associe (le 'COMMENT MIEUX FAIRE')." + chr(10) +
            "4. Proposer une piste d'apprentissage (le 'POUR ALLER PLUS LOIN')." + chr(10) +
            time_context + "Voici le contexte du fichier :" + chr(10) + ctx + chr(10) + smart_ctx + chr(10) +
            kb_context + chr(10) + "Historique de la discussion :" + chr(10) + history_text + chr(10) + chr(10) +
            "Demande de l'utilisateur : " + req.prompt + chr(10) + chr(10) +
            "INSTRUCTIONS DE COMPRÉHENSION :" + chr(10) +
            "1. Analyse les mots-clés de la demande. S'ils ont plusieurs sens (polysémie) ou si la phrase peut être interprétée de différentes manières, tu DOIS lister explicitement les différentes interprétations possibles." + chr(10) +
            "2. Si le texte est destiné à être mis en ligne (SEO, article, documentation), propose des variantes sémantiques et explique l'intention de recherche derrière chaque sens." + chr(10) +
            "3. Termine toujours par une question pour demander à l'utilisateur quel sens il privilégie avant de passer à l'action." + chr(10) +
            "Reponds de maniere conversationnelle et pédagogique."
        )

    def generate():
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate"
        data = {"model": CURRENT_CONFIG.get("model", "qwen2.5-coder:7b"), "prompt": full_prompt, "stream": True, "keep_alive": "30m", "options": {"num_predict": 40, "temperature": 0.7}}
        req_obj = _urllib_req.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})

        full_content = ""
        try:
            with _urllib_req.urlopen(req_obj, timeout=300) as resp:
                for line in resp:
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            text = chunk.get("response", "")
                            full_content += text
                            yield "data: " + json.dumps({'chunk': text}) + chr(10) + chr(10)
                        except: pass
        except Exception as e:
            yield "data: " + json.dumps({'error': str(e)}) + chr(10) + chr(10)
            return

        if veut_coder:
            full_content = clean_ai_code(full_content)
            is_valid, err_msg = verify_code_syntax(req.file, full_content)
            
            # --- BOUCLE D'AUTO-CORRECTION ---
            if not is_valid:
                yield "data: " + json.dumps({'chunk': chr(10) + chr(10) + "⚠️ Erreur de syntaxe detectee. L'IA se corrige toute seule..." + chr(10)}) + chr(10) + chr(10)
                
                fix_prompt = "Tu as fait une erreur de syntaxe. Voici le code rejete :" + chr(10) + full_content + chr(10) + chr(10) + "Voici l'erreur :" + chr(10) + err_msg + chr(10) + chr(10) + "Ecris UNIQUEMENT le code corrige, sans aucune phrase."
                fix_data = {"model": CURRENT_CONFIG.get("model", "qwen2.5-coder:7b"), "prompt": fix_prompt, "stream": False}
                
                try:
                    fix_req = _urllib_req.Request(url, data=json.dumps(fix_data).encode('utf-8'), headers={'Content-Type': 'application/json'})
                    with _urllib_req.urlopen(fix_req, timeout=300) as resp:
                        fix_res = json.loads(resp.read().decode('utf-8'))
                        full_content = clean_ai_code(fix_res.get("response", ""))
                        is_valid, err_msg = verify_code_syntax(req.file, full_content)
                        if not is_valid:
                            yield "data: " + json.dumps({'status': 'chat', 'content': "❌ L'IA n'arrive pas a corriger l'erreur. Essaie de reformuler ta demande."}) + chr(10) + chr(10)
                            return
                        else:
                            yield "data: " + json.dumps({'chunk': "✅ Correction reussie !" + chr(10)}) + chr(10) + chr(10)
                except:
                    yield "data: " + json.dumps({'status': 'chat', 'content': "❌ Echec de l'auto-correction."}) + chr(10) + chr(10)
                    return

            import difflib
            diff = list(difflib.unified_diff(req.content.splitlines(), full_content.splitlines(), fromfile="actuel", tofile="propose", lineterm=""))
            clean_diff = [l for l in diff if l.startswith(('+', '-', '@@'))]
            yield "data: " + json.dumps({'status': 'proposed', 'content': full_content, 'diff': chr(10).join(clean_diff)}) + chr(10) + chr(10)
        else:
            yield "data: " + json.dumps({'status': 'chat', 'content': full_content}) + chr(10) + chr(10)

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    print("Serveur demarre sur http://127.0.0.1:8000")
    uvicorn.run(app, host=os.getenv("MEMOLIB_HOST", "127.0.0.1"), port=int(os.getenv("MEMOLIB_PORT", "8000")))
