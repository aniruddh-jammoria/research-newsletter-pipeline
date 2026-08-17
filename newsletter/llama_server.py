import atexit
import subprocess
import time
from urllib.parse import urlparse

import requests

_processes: dict[str, subprocess.Popen] = {}


def _is_up(base_url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


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

    port = urlparse(base_url).port or 8080
    extra_args = [str(a) for a in block_cfg.get("local_server_args", [])]
    print(f"[llama] starting llama-server on port {port} ({model_path})...")

    process = subprocess.Popen(
        [server_exe, "-m", model_path, "--port", str(port), *extra_args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _processes[base_url] = process

    for _ in range(180):
        if _is_up(base_url):
            print("[llama] server ready")
            return base_url
        time.sleep(1)

    stop(base_url)
    raise RuntimeError("llama-server did not become ready within 180s")


def stop(base_url: str) -> None:
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
