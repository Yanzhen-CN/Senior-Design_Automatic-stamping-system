from __future__ import annotations

import shutil
import subprocess
import re
from pathlib import Path

from .paths import project_root, resource_root


DEFAULT_HEX_RELATIVE = Path("firmware/grbl3axis.hex")
DEFAULT_AVRDUDE_RELATIVE = Path("tools/avrdude/avrdude.exe")
DEFAULT_AVRDUDE_CONF_RELATIVE = Path("tools/avrdude/avrdude.conf")


def _resolve_from_project(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (project_root() / path).resolve()


def _resolve_from_resource(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (resource_root() / path).resolve()


def default_firmware_settings() -> dict[str, object]:
    return {
        "board": "uno_atmega328p",
        "mcu": "atmega328p",
        "baudrate": 115200,
        "programmer": "arduino",
        "hex_path": str(DEFAULT_HEX_RELATIVE),
        "avrdude_path": str(DEFAULT_AVRDUDE_RELATIVE),
        "avrdude_conf": str(DEFAULT_AVRDUDE_CONF_RELATIVE),
    }


def resolve_avrdude_binary(configured: str | None = None) -> Path:
    if configured:
        candidate = _resolve_from_project(configured)
        if candidate.exists():
            return candidate

    bundled = _resolve_from_resource(DEFAULT_AVRDUDE_RELATIVE)
    if bundled.exists():
        return bundled

    local = _resolve_from_project(DEFAULT_AVRDUDE_RELATIVE)
    if local.exists():
        return local

    found = shutil.which("avrdude")
    if found:
        return Path(found)

    raise FileNotFoundError(
        "avrdude was not found. Set avrdude path in Advanced -> Firmware Flash."
    )


def build_avrdude_command(
    *,
    avrdude_path: Path,
    avrdude_conf: str | None,
    port: str,
    mcu: str,
    baudrate: int,
    programmer: str,
    hex_path: Path,
) -> list[str]:
    command = [str(avrdude_path)]
    conf_path = (avrdude_conf or "").strip()
    if conf_path:
        command.extend(["-C", conf_path])
    command.extend(
        [
            "-v",
            f"-p{mcu}",
            f"-c{programmer}",
            f"-P{port}",
            f"-b{baudrate}",
            "-D",
            f"-Uflash:w:{hex_path}:i",
        ]
    )
    return command


def flash_firmware(
    *,
    port: str,
    hex_path: str,
    mcu: str,
    baudrate: int,
    programmer: str,
    avrdude_path: str | None = None,
    avrdude_conf: str | None = None,
    timeout_s: int = 120,
) -> dict[str, object]:
    if not port.strip():
        raise ValueError("Serial port is required for flashing")

    resolved_hex = _resolve_from_project(hex_path)
    if not resolved_hex.exists():
        resolved_hex = _resolve_from_resource(hex_path)
    if not resolved_hex.exists():
        raise FileNotFoundError(f"HEX file not found: {resolved_hex}")

    resolved_avrdude = resolve_avrdude_binary(avrdude_path)

    resolved_conf: Path | None = None
    if avrdude_conf:
        resolved_conf = _resolve_from_project(avrdude_conf)
        if not resolved_conf.exists():
            resource_conf = _resolve_from_resource(avrdude_conf)
            if resource_conf.exists():
                resolved_conf = resource_conf

    command = build_avrdude_command(
        avrdude_path=resolved_avrdude,
        avrdude_conf=str(resolved_conf) if resolved_conf else None,
        port=port.strip(),
        mcu=mcu.strip(),
        baudrate=int(baudrate),
        programmer=programmer.strip(),
        hex_path=resolved_hex,
    )

    run = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    feedback = parse_flash_feedback(run.stdout, run.stderr)
    return {
        "ok": run.returncode == 0,
        "returncode": run.returncode,
        "command": command,
        "hex_path": str(resolved_hex),
        "stdout": run.stdout[-8000:],
        "stderr": run.stderr[-8000:],
        "progress_percent": feedback["progress_percent"],
        "feedback_lines": feedback["feedback_lines"],
        "summary": feedback["summary"],
    }


def parse_flash_feedback(stdout: str, stderr: str) -> dict[str, object]:
    combined = f"{stdout}\n{stderr}".strip()
    if not combined:
        return {
            "progress_percent": 0,
            "feedback_lines": ["No avrdude output received"],
            "summary": "No output",
        }

    progress = 0
    for match in re.finditer(r"(\d{1,3})%", combined):
        value = int(match.group(1))
        if value > progress:
            progress = min(100, value)

    lines = []
    for raw in combined.splitlines():
        text = raw.strip()
        if not text:
            continue
        lowered = text.lower()
        if "writing" in lowered or "reading" in lowered or "verifying" in lowered:
            lines.append(text)
            continue
        if "bytes of flash written" in lowered or "bytes of flash verified" in lowered:
            lines.append(text)
            continue
        if "device signature" in lowered or "avrdude done" in lowered:
            lines.append(text)
            continue
        if "error" in lowered or "failed" in lowered:
            lines.append(text)

    if not lines:
        lines = combined.splitlines()[-8:]

    summary = "Flash completed" if progress >= 100 else "Flash in progress output captured"
    if any("error" in item.lower() or "failed" in item.lower() for item in lines):
        summary = "Flash reported errors"
    return {
        "progress_percent": progress,
        "feedback_lines": lines[-16:],
        "summary": summary,
    }
