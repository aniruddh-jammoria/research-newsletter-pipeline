import atexit
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

_processes: dict[str, subprocess.Popen] = {}

# Records the PID of any llama-server this module starts, keyed by base_url,
# so a future run can spot and reap one left over from a run that was killed
# outright (e.g. Task Scheduler's execution time limit) — that kind of kill
# skips the `finally`/atexit cleanup below entirely, so without this the
# orphaned process just sits there holding the port and GPU memory.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PID_FILE = _DATA_DIR / "llama_server.pid.json"


def _is_up(base_url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _load_pids() -> dict[str, int]:
    try:
        return json.loads(_PID_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_pids(pids: dict[str, int]) -> None:
    _PID_FILE.parent.mkdir(exist_ok=True)
    _PID_FILE.write_text(json.dumps(pids))


def _image_name(pid: int) -> str | None:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    line = out.strip().splitlines()[0] if out.strip() else ""
    if not line or not line.startswith('"'):
        return None
    return line.split('","')[0].strip('"')


def _reap_stale(base_url: str, server_exe: str) -> None:
    pids = _load_pids()
    pid = pids.pop(base_url, None)
    if pid is None:
        return
    _save_pids(pids)
    if _image_name(pid) == Path(server_exe).name:
        print(f"[llama] reaping a llama-server (pid {pid}) left over from an earlier run...")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_running(block_cfg: dict) -> str | None:
    """Start llama-server for this config block if it isn't already reachable.

    `block_cfg` is a `filter:` or `summarize:` sub-config carrying its own
    provider/local_base_url/local_server_exe/local_model_path, plus an optional
    `local_server_args` list of extra CLI flags (e.g. `-c`, `-ngl`,
    `--reasoning-budget`) passed straight through to llama-server. Returns the
    base_url if this call started the server (caller must `stop()` it when
    done), or None if the provider isn't 'local' or a server was already
    running there (in which case its lifecycle isn't ours to manage).
    """
    if block_cfg.get("provider") != "local":
        return None

    base_url = block_cfg.get("local_base_url", "http://localhost:8080/v1")
    if _is_up(base_url):
        print(f"[llama] server already reachable at {base_url}")
        return None

    server_exe = block_cfg.get("local_server_exe")
    model_path = block_cfg.get("local_model_path")
    if not server_exe or not model_path:
        raise EnvironmentError(
            "llama-server is not running, and 'local_server_exe' / 'local_model_path' "
            "are not set for this block — cannot auto-start it. Either start "
            "llama-server manually first, or set both config keys."
        )

    _reap_stale(base_url, server_exe)

    port = urlparse(base_url).port or 8080
    extra_args = [str(a) for a in block_cfg.get("local_server_args", [])]
    print(f"[llama] starting llama-server on port {port} ({model_path})...")

    # `--log-file` uses llama-server's own logger rather than a redirected
    # stdout: a redirected stdout is fully-buffered when it isn't a terminal,
    # so if the process dies abruptly (crash, external kill) whatever it had
    # printed but not yet flushed is lost — which is exactly what happened the
    # first time this was tried, producing an empty log with no clue why the
    # server had gone unreachable.
    _DATA_DIR.mkdir(exist_ok=True)
    log_path = _DATA_DIR / f"llama_server_{port}.log"
    process = subprocess.Popen(
        [server_exe, "-m", model_path, "--port", str(port), "--log-file", str(log_path), *extra_args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _processes[base_url] = process
    pids = _load_pids()
    pids[base_url] = process.pid
    _save_pids(pids)

    for _ in range(180):
        if _is_up(base_url):
            print("[llama] server ready")
            return base_url
        time.sleep(1)

    stop(base_url)
    raise RuntimeError(f"llama-server did not become ready within 180s — see {log_path} for what it printed")


def stop(base_url: str) -> None:
    pids = _load_pids()
    if pids.pop(base_url, None) is not None:
        _save_pids(pids)

    process = _processes.pop(base_url, None)
    if process is None:
        return
    print(f"[llama] stopping llama-server at {base_url}...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _stop_all() -> None:
    for base_url in list(_processes.keys()):
        stop(base_url)


atexit.register(_stop_all)
