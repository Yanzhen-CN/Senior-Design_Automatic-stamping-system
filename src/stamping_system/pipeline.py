from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import AppConfig, load_config
from .gcode import GcodePlan, build_jog_gcode, build_move_gcode, build_stamp_gcode
from .serial_link import SerialResult, SerialTransport
from .targeting import TargetInput, TargetResult, resolve_target


@dataclass(frozen=True)
class PreviewResult:
    target: TargetResult
    gcode: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.to_dict(),
            "gcode": self.gcode,
        }


def preview_target(
    target: TargetInput,
    config: AppConfig | None = None,
    include_paper_feed: bool = True,
) -> PreviewResult:
    cfg = config or load_config()
    resolved = resolve_target(target, cfg)
    plan = build_stamp_gcode(
        resolved.real_xy_mm,
        resolved.commanded_xy_mm,
        cfg,
        include_paper_feed=include_paper_feed,
    )
    return PreviewResult(target=resolved, gcode=plan.lines)


def move_to_target(
    target: TargetInput,
    dry_run: bool | None = None,
    slow: bool = True,
    config: AppConfig | None = None,
) -> tuple[PreviewResult, SerialResult]:
    cfg = config or load_config()
    resolved = resolve_target(target, cfg)
    feed = cfg.machine.jog_feed_mm_min if slow else cfg.machine.travel_feed_mm_min
    plan = build_move_gcode(resolved.real_xy_mm, resolved.commanded_xy_mm, cfg, feed)
    preview = PreviewResult(target=resolved, gcode=plan.lines)
    serial_result = SerialTransport(cfg, force_dry_run=dry_run).execute(plan.lines)
    return preview, serial_result


def stamp_target(
    target: TargetInput,
    dry_run: bool | None = None,
    config: AppConfig | None = None,
) -> tuple[PreviewResult, SerialResult]:
    cfg = config or load_config()
    preview = preview_target(target, cfg)
    result = SerialTransport(cfg, force_dry_run=dry_run).execute(preview.gcode)
    return preview, result


def jog_axis(
    axis: str,
    distance_mm: float,
    dry_run: bool | None = None,
    config: AppConfig | None = None,
) -> tuple[GcodePlan, SerialResult]:
    cfg = config or load_config()
    plan = build_jog_gcode(axis, distance_mm, cfg)
    result = SerialTransport(cfg, force_dry_run=dry_run).execute(plan.lines)
    return plan, result


def serial_result_to_dict(result: SerialResult) -> dict[str, object]:
    return asdict(result)

