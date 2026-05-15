from __future__ import annotations

from dataclasses import dataclass

from .calibration import z_real_to_commanded
from .config import AppConfig


@dataclass(frozen=True)
class GcodePlan:
    real_xy_mm: tuple[float, float] | None
    commanded_xy_mm: tuple[float, float] | None
    lines: list[str]


def format_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def build_move_gcode(
    real_xy_mm: tuple[float, float],
    commanded_xy_mm: tuple[float, float],
    config: AppConfig,
    feed_mm_min: float | None = None,
) -> GcodePlan:
    x_cmd, y_cmd = commanded_xy_mm
    safe_z = z_real_to_commanded(config.machine.safe_z_mm, config)
    config.machine.axes["x"].validate(x_cmd)
    config.machine.axes["y"].validate(y_cmd)
    config.machine.axes["z"].validate(safe_z)
    feed = feed_mm_min or config.machine.travel_feed_mm_min
    return GcodePlan(
        real_xy_mm=real_xy_mm,
        commanded_xy_mm=commanded_xy_mm,
        lines=[
            "G21",
            "G90",
            f"G0 Z{format_float(safe_z)}",
            f"G0 X{format_float(x_cmd)} Y{format_float(y_cmd)} F{format_float(feed)}",
        ],
    )


def build_stamp_gcode(
    real_xy_mm: tuple[float, float],
    commanded_xy_mm: tuple[float, float],
    config: AppConfig,
    include_paper_feed: bool = True,
) -> GcodePlan:
    plan = build_move_gcode(real_xy_mm, commanded_xy_mm, config)
    safe_z = z_real_to_commanded(config.machine.safe_z_mm, config)
    stamp_z = z_real_to_commanded(config.machine.stamp_z_mm, config)
    config.machine.axes["z"].validate(stamp_z)
    config.machine.axes["z"].validate(safe_z)
    lines = [
        *plan.lines,
        f"G1 Z{format_float(stamp_z)} F{format_float(config.machine.z_feed_mm_min)}",
        f"G4 P{format_float(config.machine.stamp_dwell_s)}",
        f"G1 Z{format_float(safe_z)} F{format_float(config.machine.z_feed_mm_min)}",
    ]
    if include_paper_feed and config.paper_feed.enabled and config.paper_feed.command:
        lines.append(config.paper_feed.command)
        if config.paper_feed.settle_s > 0:
            lines.append(f"G4 P{format_float(config.paper_feed.settle_s)}")
    return GcodePlan(real_xy_mm=real_xy_mm, commanded_xy_mm=commanded_xy_mm, lines=lines)


def build_jog_gcode(axis: str, distance_real_mm: float, config: AppConfig) -> GcodePlan:
    normalized = axis.lower()
    if normalized not in config.machine.axes:
        raise ValueError("axis must be X, Y, or Z")
    axis_config = config.machine.axes[normalized]
    commanded_delta = axis_config.real_delta_to_commanded(distance_real_mm)
    letter = normalized.upper()
    feed = config.machine.z_feed_mm_min if normalized == "z" else config.machine.jog_feed_mm_min
    return GcodePlan(
        real_xy_mm=None,
        commanded_xy_mm=None,
        lines=[
            "G21",
            "G91",
            f"G0 {letter}{format_float(commanded_delta)} F{format_float(feed)}",
            "G90",
        ],
    )
