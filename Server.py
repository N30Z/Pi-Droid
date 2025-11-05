# server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import threading, json, subprocess, time, os

TOTAL = 1_000_000
STATE_FILE = Path("state.json")
LOCK = threading.Lock()

# Pfad/Command für den Worker: "{number}" wird ersetzt (kein shell=True)
COMMAND_TEMPLATE = ["python3", "worker.py", "{number}"]
WORK_DIR = Path.cwd()  # ggf. anpassen

class State(BaseModel):
    current: int = -1              # -1 => noch keine Zahl ausgegeben
    last_number: str | None = None
    last_pid: int | None = None
    last_started_ts: float | None = None

def load_state() -> State:
    if STATE_FILE.exists():
        try:
            return State(**json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return State()

def save_state(state: State) -> None:
    STATE_FILE.write_text(json.dumps(state.model_dump(), ensure_ascii=False), encoding="utf-8")

def fmt(n: int) -> str:
    return f"{n:06d}"

def build_cmd(number_str: str) -> list[str]:
    return [arg.replace("{number}", number_str) for arg in COMMAND_TEMPLATE]

def proc_running(pid: int | None) -> bool:
    if pid is None: 
        return False
    try:
        os.kill(pid, 0)  # Unix: check existence
        return True
    except Exception:
        return False

app = FastAPI(title="Number Progress Server", version="1.0.0")
STATE = load_state()

@app.get("/status")
def status():
    with LOCK:
        current_num = STATE.current
        current_str = fmt(current_num) if current_num >= 0 else None
        done = max(current_num, -1) + 1         # ausgegebene Menge
        remaining = TOTAL - done if done >= 0 else TOTAL
        percent = (done / TOTAL * 100.0) if done >= 0 else 0.0
        return {
            "current_index": current_num,
            "current_value": current_str,       # z. B. "000123"
            "done": done,
            "remaining": remaining,
            "percent": round(percent, 6),
            "last": {
                "number": STATE.last_number,
                "pid": STATE.last_pid,
                "started_ts": STATE.last_started_ts,
                "process_running": proc_running(STATE.last_pid),
            },
            "total": TOTAL
        }

@app.get("/next")
def next_number():
    """
    - erhöht den internen Zähler (Wrap bei 999999)
    - startet worker.py <NUMBER> asynchron (kein Timeout)
    - liefert die neue Nummer + PID zurück
    """
    with LOCK:
        nxt = 0 if STATE.current < 0 else (STATE.current + 1) % TOTAL
        STATE.current = nxt
        number_str = fmt(nxt)

    # Worker außerhalb des Locks starten
    cmd = build_cmd(number_str)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(WORK_DIR),
            stdout=subprocess.DEVNULL,   # bei Bedarf auf Datei/Pipe ändern
            stderr=subprocess.DEVNULL,
            text=True
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Konnte Kommando nicht starten: {e}")

    started_ts = time.time()
    with LOCK:
        STATE.last_pid = proc.pid
        STATE.last_number = number_str
        STATE.last_started_ts = started_ts
        save_state(STATE)

    return {
        "number": number_str,
        "pid": proc.pid,
        "executed": cmd,
        "started_ts": started_ts
    }