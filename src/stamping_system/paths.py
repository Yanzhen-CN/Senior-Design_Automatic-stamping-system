from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "AutomaticStampingSystem"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    env_root = os.environ.get("STAMPING_RESOURCE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[2]


def project_root() -> Path:
    env_root = os.environ.get("STAMPING_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def user_data_root() -> Path:
    env_root = os.environ.get("STAMPING_USER_DATA")
    if env_root:
        root = Path(env_root).resolve()
    elif is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data or Path.home()) / APP_NAME
    else:
        root = project_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def web_root() -> Path:
    env_root = os.environ.get("STAMPING_WEB_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return resource_root() / "web"


def default_config_template_path() -> Path:
    env_path = os.environ.get("STAMPING_DEFAULT_CONFIG")
    if env_path:
        return Path(env_path).resolve()
    return resource_root() / "config" / "machine.toml"


def config_path() -> Path:
    env_path = os.environ.get("STAMPING_CONFIG")
    if env_path:
        return Path(env_path).resolve()

    if is_frozen() or os.environ.get("STAMPING_USER_DATA"):
        target = user_data_root() / "config" / "machine.toml"
        if not target.exists():
            template = default_config_template_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, target)
        return target.resolve()

    return (project_root() / "config" / "machine.toml").resolve()


def runtime_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if is_frozen() or os.environ.get("STAMPING_USER_DATA"):
        return user_data_root() / path
    return project_root() / path

