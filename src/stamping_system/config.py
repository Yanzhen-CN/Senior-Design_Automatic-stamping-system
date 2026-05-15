from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from .paths import (
    config_path as runtime_config_path,
    project_root,
    runtime_path,
)

PROJECT_ROOT = project_root()
DEFAULT_CONFIG_PATH = runtime_config_path()


@dataclass(frozen=True)
class AxisConfig:
    actual_mm_per_commanded_mm: float
    offset_commanded_mm: float
    invert: bool
    min_commanded_mm: float
    max_commanded_mm: float
    motor_steps_per_rev: int
    microsteps: int
    pulley_teeth: int
    belt_pitch_mm: float
    steps_per_mm: float

    def real_to_commanded(self, real_mm: float) -> float:
        commanded = self.offset_commanded_mm + self.real_delta_to_commanded(real_mm)
        self.validate(commanded)
        return commanded

    def real_delta_to_commanded(self, real_delta_mm: float) -> float:
        effective_ratio = self.effective_mm_per_commanded_mm
        if effective_ratio == 0:
            raise ValueError("actual_mm_per_commanded_mm cannot be zero")
        direction = -1.0 if self.invert else 1.0
        return direction * real_delta_mm / effective_ratio

    def commanded_delta_to_real(self, commanded_delta_mm: float) -> float:
        direction = -1.0 if self.invert else 1.0
        return direction * commanded_delta_mm * self.effective_mm_per_commanded_mm

    def validate(self, commanded: float) -> None:
        if commanded < self.min_commanded_mm or commanded > self.max_commanded_mm:
            raise ValueError(
                f"Commanded value {commanded:.3f} is outside "
                f"[{self.min_commanded_mm:.3f}, {self.max_commanded_mm:.3f}]"
            )

    @property
    def theoretical_steps_per_mm(self) -> float:
        travel_per_rev = self.pulley_teeth * self.belt_pitch_mm
        if travel_per_rev == 0:
            return 0.0
        return (self.motor_steps_per_rev * self.microsteps) / travel_per_rev

    @property
    def effective_mm_per_commanded_mm(self) -> float:
        theory = self.theoretical_steps_per_mm
        if theory <= 0:
            return self.actual_mm_per_commanded_mm
        configured = float(self.steps_per_mm)
        if configured <= 0:
            configured = theory
        # Base geometric correction from steps/mm, multiplied by user calibration ratio.
        return self.actual_mm_per_commanded_mm * (configured / theory)


@dataclass(frozen=True)
class MachineConfig:
    travel_feed_mm_min: float
    jog_feed_mm_min: float
    z_feed_mm_min: float
    safe_z_mm: float
    stamp_z_mm: float
    stamp_dwell_s: float
    axes: dict[str, AxisConfig]


@dataclass(frozen=True)
class SerialConfig:
    port: str
    baudrate: int
    timeout_s: float
    dry_run: bool


@dataclass(frozen=True)
class ControllerConfig:
    type: str
    line_ending: str
    wait_for_idle: bool
    idle_timeout_s: float


@dataclass(frozen=True)
class PaperConfig:
    width_mm: float
    height_mm: float
    origin_real_mm: tuple[float, float]
    rotation_deg: float
    use_detected_quad_for_relative_targets: bool


@dataclass(frozen=True)
class PaperFeedConfig:
    enabled: bool
    command: str
    settle_s: float
    feed_length_mm: float
    reserved_signal_pin: str


@dataclass(frozen=True)
class CameraConfig:
    index: int
    width_px: int
    height_px: int
    height_mm: float
    mount: str
    snapshot_path: Path
    placeholder_width_px: int
    placeholder_height_px: int


@dataclass(frozen=True)
class VisionConfig:
    paper_detection_enabled: bool
    paper_min_area_ratio: float
    ocr_enabled: bool
    ocr_engine: str
    ocr_language: str
    vlm_endpoint: str


@dataclass(frozen=True)
class CalibrationPoint:
    label: str
    pixel: tuple[float, float]
    real_mm: tuple[float, float]


@dataclass(frozen=True)
class CalibrationConfig:
    mode: str
    points: list[CalibrationPoint]


@dataclass(frozen=True)
class AppConfig:
    path: Path
    raw: dict[str, Any]
    serial: SerialConfig
    controller: ControllerConfig
    machine: MachineConfig
    paper: PaperConfig
    paper_feed: PaperFeedConfig
    camera: CameraConfig
    vision: VisionConfig
    calibration: CalibrationConfig


def config_path() -> Path:
    return Path(os.environ.get("STAMPING_CONFIG", runtime_config_path())).resolve()


def load_config(path: Path | None = None) -> AppConfig:
    resolved = (path or config_path()).resolve()
    with resolved.open("rb") as file:
        raw = tomllib.load(file)
    return parse_config(raw, resolved)


def parse_config(raw: dict[str, Any], path: Path | None = None) -> AppConfig:
    axes_raw = raw["machine"]["axes"]
    axes = {name: _axis(axis_data) for name, axis_data in axes_raw.items()}
    for name in ("x", "y", "z"):
        if name not in axes:
            raise KeyError(f"Missing machine.axes.{name}")

    camera_raw = raw["camera"]
    snapshot_path = runtime_path(camera_raw["snapshot_path"])

    calibration_points = [
        CalibrationPoint(
            label=str(item["label"]),
            pixel=(float(item["pixel"][0]), float(item["pixel"][1])),
            real_mm=(float(item["real_mm"][0]), float(item["real_mm"][1])),
        )
        for item in raw["calibration"]["points"]
    ]

    return AppConfig(
        path=(path or config_path()).resolve(),
        raw=raw,
        serial=SerialConfig(
            port=str(raw["serial"]["port"]),
            baudrate=int(raw["serial"]["baudrate"]),
            timeout_s=float(raw["serial"]["timeout_s"]),
            dry_run=bool(raw["serial"].get("dry_run", True)),
        ),
        controller=ControllerConfig(
            type=str(raw["controller"].get("type", "grbl")),
            line_ending=str(raw["controller"].get("line_ending", "\n")),
            wait_for_idle=bool(raw["controller"].get("wait_for_idle", True)),
            idle_timeout_s=float(raw["controller"].get("idle_timeout_s", 20.0)),
        ),
        machine=MachineConfig(
            travel_feed_mm_min=float(raw["machine"]["travel_feed_mm_min"]),
            jog_feed_mm_min=float(raw["machine"].get("jog_feed_mm_min", 500.0)),
            z_feed_mm_min=float(raw["machine"]["z_feed_mm_min"]),
            safe_z_mm=float(raw["machine"]["safe_z_mm"]),
            stamp_z_mm=float(raw["machine"]["stamp_z_mm"]),
            stamp_dwell_s=float(raw["machine"]["stamp_dwell_s"]),
            axes=axes,
        ),
        paper=PaperConfig(
            width_mm=float(raw["paper"]["width_mm"]),
            height_mm=float(raw["paper"]["height_mm"]),
            origin_real_mm=(
                float(raw["paper"]["origin_real_mm"][0]),
                float(raw["paper"]["origin_real_mm"][1]),
            ),
            rotation_deg=float(raw["paper"].get("rotation_deg", 0.0)),
            use_detected_quad_for_relative_targets=bool(
                raw["paper"].get("use_detected_quad_for_relative_targets", True)
            ),
        ),
        paper_feed=PaperFeedConfig(
            enabled=bool(raw["paper_feed"].get("enabled", False)),
            command=str(raw["paper_feed"].get("command", "")),
            settle_s=float(raw["paper_feed"].get("settle_s", 0.0)),
            feed_length_mm=float(raw["paper_feed"].get("feed_length_mm", 0.0)),
            reserved_signal_pin=str(raw["paper_feed"].get("reserved_signal_pin", "")),
        ),
        camera=CameraConfig(
            index=int(camera_raw["index"]),
            width_px=int(camera_raw["width_px"]),
            height_px=int(camera_raw["height_px"]),
            height_mm=float(camera_raw["height_mm"]),
            mount=str(camera_raw["mount"]),
            snapshot_path=snapshot_path,
            placeholder_width_px=int(camera_raw.get("placeholder_width_px", 1280)),
            placeholder_height_px=int(camera_raw.get("placeholder_height_px", 720)),
        ),
        vision=VisionConfig(
            paper_detection_enabled=bool(raw["vision"].get("paper_detection_enabled", True)),
            paper_min_area_ratio=float(raw["vision"].get("paper_min_area_ratio", 0.12)),
            ocr_enabled=bool(raw["vision"].get("ocr_enabled", False)),
            ocr_engine=str(raw["vision"].get("ocr_engine", "none")),
            ocr_language=str(raw["vision"].get("ocr_language", "eng")),
            vlm_endpoint=str(raw["vision"].get("vlm_endpoint", "")),
        ),
        calibration=CalibrationConfig(
            mode=str(raw["calibration"].get("mode", "homography")),
            points=calibration_points,
        ),
    )


def save_config(raw: dict[str, Any], path: Path | None = None) -> AppConfig:
    resolved = (path or config_path()).resolve()
    parse_config(raw, resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(dumps_toml(raw), encoding="utf-8")
    return load_config(resolved)


def _axis(data: dict[str, Any]) -> AxisConfig:
    return AxisConfig(
        actual_mm_per_commanded_mm=float(data["actual_mm_per_commanded_mm"]),
        offset_commanded_mm=float(data.get("offset_commanded_mm", 0.0)),
        invert=bool(data.get("invert", False)),
        min_commanded_mm=float(data.get("min_commanded_mm", -1_000_000.0)),
        max_commanded_mm=float(data.get("max_commanded_mm", 1_000_000.0)),
        motor_steps_per_rev=int(data.get("motor_steps_per_rev", 200)),
        microsteps=int(data.get("microsteps", 16)),
        pulley_teeth=int(data.get("pulley_teeth", 20)),
        belt_pitch_mm=float(data.get("belt_pitch_mm", 2.0)),
        steps_per_mm=float(data.get("steps_per_mm", 80.0)),
    )


def dumps_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            _dump_section(key, value, lines)
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines).strip() + "\n"


def _dump_section(prefix: str, data: dict[str, Any], lines: list[str]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    child_sections: list[tuple[str, dict[str, Any]]] = []
    table_arrays: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in data.items():
        if isinstance(value, dict):
            child_sections.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            table_arrays.append((key, value))
        else:
            scalar_items.append((key, value))

    if scalar_items:
        if lines:
            lines.append("")
        lines.append(f"[{prefix}]")
        for key, value in scalar_items:
            lines.append(f"{key} = {_toml_value(value)}")

    for key, value in child_sections:
        _dump_section(f"{prefix}.{key}", value, lines)

    for key, items in table_arrays:
        for item in items:
            if lines:
                lines.append("")
            lines.append(f"[[{prefix}.{key}]]")
            for item_key, item_value in item.items():
                lines.append(f"{item_key} = {_toml_value(item_value)}")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Cannot write value to TOML: {value!r}")
