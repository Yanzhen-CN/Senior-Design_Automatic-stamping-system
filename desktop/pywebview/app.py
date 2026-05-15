from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def _project_src() -> Path:
    return Path(__file__).resolve().parents[2] / "src"


if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(_project_src()))


def _free_port(preferred: int = 8000) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free localhost port found")


def _run_backend(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(
        "stamping_system.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="warning",
    )


def _wait_backend(url: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    health = f"{url}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=0.8) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency pywebview. Build from the SD environment after installing requirements.txt."
        ) from exc

    host = "127.0.0.1"
    port = int(os.environ.get("STAMPING_PORT", _free_port(8000)))
    url = f"http://{host}:{port}"

    backend_thread = threading.Thread(
        target=_run_backend,
        args=(host, port),
        daemon=True,
    )
    backend_thread.start()
    if not _wait_backend(url, timeout_s=8.0):
        raise SystemExit(
            f"Backend did not become ready at {url}. "
            "Check camera/serial dependencies in the SD environment."
        )

    webview.create_window(
        "Automatic Stamping System",
        url,
        width=1360,
        height=860,
        min_size=(1080, 720),
    )
    webview.start()


if __name__ == "__main__":
    main()
