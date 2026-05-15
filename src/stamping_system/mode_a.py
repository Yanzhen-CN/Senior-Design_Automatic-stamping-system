from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .calibration import pixel_to_real
from .config import AppConfig
from .gcode import build_stamp_gcode
from .paths import runtime_path
from .serial_link import SerialResult, SerialTransport
from .targeting import TargetInput, resolve_target
from .vision import PaperDetection, detect_paper_from_image


@dataclass
class ModeAState:
    cycle_count: int = 0
    compensation_mm: tuple[float, float] = (0.0, 0.0)
    last_error_mm: tuple[float, float] | None = None
    last_expected_pixel: tuple[float, float] | None = None
    last_detected_pixel: tuple[float, float] | None = None
    last_detection_confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def mode_a_state_path() -> Path:
    return runtime_path("runtime/mode_a_state.json")


def mode_a_frame_path(stage: str) -> Path:
    normalized = stage.lower().strip()
    if normalized not in {"before", "after"}:
        raise ValueError("stage must be 'before' or 'after'")
    return runtime_path(f"runtime/mode_a_{normalized}.jpg")


def load_mode_a_state() -> ModeAState:
    path = mode_a_state_path()
    if not path.exists():
        return ModeAState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ModeAState()

    def _point(name: str) -> tuple[float, float] | None:
        value = payload.get(name)
        if not isinstance(value, list | tuple) or len(value) != 2:
            return None
        return (float(value[0]), float(value[1]))

    return ModeAState(
        cycle_count=int(payload.get("cycle_count", 0)),
        compensation_mm=_point("compensation_mm") or (0.0, 0.0),
        last_error_mm=_point("last_error_mm"),
        last_expected_pixel=_point("last_expected_pixel"),
        last_detected_pixel=_point("last_detected_pixel"),
        last_detection_confidence=(
            float(payload["last_detection_confidence"])
            if payload.get("last_detection_confidence") is not None
            else None
        ),
    )


def save_mode_a_state(state: ModeAState) -> ModeAState:
    path = mode_a_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def reset_mode_a_state() -> ModeAState:
    state = ModeAState()
    return save_mode_a_state(state)


def save_mode_a_frame(image_data: str, stage: str, config: AppConfig | None = None) -> Path:
    raw = image_data.strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    payload = base64.b64decode(raw, validate=True)
    if not payload:
        raise ValueError("Mode A frame data is empty")
    target = mode_a_frame_path(stage)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    if config is not None:
        config.camera.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        config.camera.snapshot_path.write_bytes(payload)
    return target


def detect_mode_a_paper(config: AppConfig) -> PaperDetection:
    if not config.camera.snapshot_path.exists():
        return PaperDetection(
            found=False,
            quad=[],
            center=None,
            message=f"Snapshot not found: {config.camera.snapshot_path}",
        )
    return detect_paper_from_image(config.camera.snapshot_path, config)


def run_mode_a_cycle(
    config: AppConfig,
    relative_xy: tuple[float, float],
    user_offset_mm: tuple[float, float],
    dry_run: bool | None = None,
    detect_paper: bool = True,
    feed_before: bool = False,
    feed_after: bool = False,
    return_xy_zero: bool = True,
    apply_compensation: bool = False,
) -> dict[str, object]:
    state = load_mode_a_state()
    total_offset = (
        float(user_offset_mm[0]) + (state.compensation_mm[0] if apply_compensation else 0.0),
        float(user_offset_mm[1]) + (state.compensation_mm[1] if apply_compensation else 0.0),
    )
    return run_repeat_cycle(
        config=config,
        target=TargetInput(
            source="relative_paper",
            x=float(relative_xy[0]),
            y=float(relative_xy[1]),
            offset_mm=total_offset,
        ),
        dry_run=dry_run,
        detect_paper=detect_paper,
        feed_before=feed_before,
        feed_after=feed_after,
        return_xy_zero=return_xy_zero,
        offset_report={"user": user_offset_mm, "compensation": state.compensation_mm, "total": total_offset},
    )


def run_repeat_cycle(
    config: AppConfig,
    target: TargetInput,
    dry_run: bool | None = None,
    detect_paper: bool = True,
    feed_before: bool = False,
    feed_after: bool = True,
    return_xy_zero: bool = True,
    offset_report: dict[str, object] | None = None,
) -> dict[str, object]:
    state = load_mode_a_state()
    serial_chunks: list[dict[str, object]] = []

    def _execute(lines: list[str], stage: str) -> None:
        result = SerialTransport(config, force_dry_run=dry_run).execute(lines)
        serial_chunks.append(
            {
                "stage": stage,
                "lines": lines,
                "serial": {
                    "dry_run": result.dry_run,
                    "sent_lines": result.sent_lines,
                    "responses": result.responses,
                    "port": result.port,
                },
            }
        )

    if feed_before:
        lines = paper_feed_lines(config, "forward", 1)
        if lines:
            _execute(lines, "paper_feed_before")

    if return_xy_zero:
        _execute(xy_zero_lines(config), "photo_pose_before")

    detection: PaperDetection | None = None
    target_input = target
    if detect_paper:
        detection = detect_mode_a_paper(config)
        if detection.found and target.source in {"relative_paper", "paper_preset"}:
            target_input = TargetInput(
                source=target.source,
                x=target.x,
                y=target.y,
                preset=target.preset,
                keyword=target.keyword,
                offset_mm=target.offset_mm,
                paper_quad=detection.quad,
            )

    resolved = resolve_target(target_input, config)
    stamp_plan = build_stamp_gcode(
        real_xy_mm=resolved.real_xy_mm,
        commanded_xy_mm=resolved.commanded_xy_mm,
        config=config,
        include_paper_feed=False,
    )
    _execute(stamp_plan.lines, "stamp")

    if return_xy_zero:
        _execute(xy_zero_lines(config), "photo_pose_after")

    if feed_after:
        lines = paper_feed_lines(config, "forward", 1)
        if lines:
            _execute(lines, "paper_feed_after")

    updated = ModeAState(
        cycle_count=state.cycle_count + 1,
        compensation_mm=state.compensation_mm,
        last_error_mm=state.last_error_mm,
        last_expected_pixel=state.last_expected_pixel,
        last_detected_pixel=state.last_detected_pixel,
        last_detection_confidence=state.last_detection_confidence,
    )
    save_mode_a_state(updated)

    return {
        "target": resolved.to_dict(),
        "gcode": stamp_plan.lines,
        "paper_detection": detection.to_dict() if detection else None,
        "offset_mm": offset_report,
        "serial_chunks": serial_chunks,
        "state": updated.to_dict(),
    }


def update_compensation_from_frames(
    config: AppConfig,
    expected_pixel: tuple[float, float],
    gain: float = 0.35,
    roi_radius_px: int = 150,
    min_area_px: int = 45,
) -> dict[str, object]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv-python and numpy are required for Mode A compensation") from exc

    before_path = mode_a_frame_path("before")
    after_path = mode_a_frame_path("after")
    before = cv2.imread(str(before_path))
    after = cv2.imread(str(after_path))
    if before is None or after is None:
        raise RuntimeError("Mode A before/after frames are missing")
    if before.shape[:2] != after.shape[:2]:
        after = cv2.resize(after, (before.shape[1], before.shape[0]), interpolation=cv2.INTER_LINEAR)

    before_gray = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    shift_xy, shift_conf = cv2.phaseCorrelate(before_gray.astype(np.float32), after_gray.astype(np.float32))
    warp = np.float32([[1.0, 0.0, -float(shift_xy[0])], [0.0, 1.0, -float(shift_xy[1])]])
    aligned_after = cv2.warpAffine(
        after,
        warp,
        (before.shape[1], before.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    before_lab = cv2.cvtColor(before, cv2.COLOR_BGR2LAB)
    after_lab = cv2.cvtColor(aligned_after, cv2.COLOR_BGR2LAB)
    delta_a = (after_lab[:, :, 1].astype(np.int16) - before_lab[:, :, 1].astype(np.int16)).clip(0, 255)
    delta_u8 = delta_a.astype(np.uint8)

    px, py = int(round(expected_pixel[0])), int(round(expected_pixel[1]))
    r = max(24, int(roi_radius_px))
    x0 = max(0, px - r)
    y0 = max(0, py - r)
    x1 = min(delta_u8.shape[1], px + r)
    y1 = min(delta_u8.shape[0], py + r)
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise RuntimeError("Expected pixel ROI is out of frame")

    roi = delta_u8[y0:y1, x0:x1]
    _, mask = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < float(min_area_px) or area < best_area:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 1e-6:
            continue
        cx = x0 + float(moments["m10"] / moments["m00"])
        cy = y0 + float(moments["m01"] / moments["m00"])
        best = (cx, cy)
        best_area = area

    state = load_mode_a_state()
    if best is None:
        state = ModeAState(
            cycle_count=state.cycle_count,
            compensation_mm=state.compensation_mm,
            last_error_mm=state.last_error_mm,
            last_expected_pixel=expected_pixel,
            last_detected_pixel=None,
            last_detection_confidence=float(shift_conf),
        )
        save_mode_a_state(state)
        return {
            "found": False,
            "message": "No red stamp cluster found in ROI.",
            "expected_pixel": expected_pixel,
            "state": state.to_dict(),
            "alignment_shift_px": (float(shift_xy[0]), float(shift_xy[1])),
            "alignment_confidence": float(shift_conf),
        }

    expected_real = pixel_to_real(expected_pixel, config)
    actual_real = pixel_to_real(best, config)
    error_mm = (actual_real[0] - expected_real[0], actual_real[1] - expected_real[1])
    blended = (
        state.compensation_mm[0] - float(gain) * error_mm[0],
        state.compensation_mm[1] - float(gain) * error_mm[1],
    )
    updated = ModeAState(
        cycle_count=state.cycle_count,
        compensation_mm=blended,
        last_error_mm=error_mm,
        last_expected_pixel=expected_pixel,
        last_detected_pixel=best,
        last_detection_confidence=float(shift_conf),
    )
    save_mode_a_state(updated)
    return {
        "found": True,
        "expected_pixel": expected_pixel,
        "detected_pixel": best,
        "error_mm": error_mm,
        "compensation_mm": blended,
        "mask_area_px": best_area,
        "alignment_shift_px": (float(shift_xy[0]), float(shift_xy[1])),
        "alignment_confidence": float(shift_conf),
        "state": updated.to_dict(),
    }


def xy_zero_lines(config: AppConfig) -> list[str]:
    config.machine.axes["x"].validate(0.0)
    config.machine.axes["y"].validate(0.0)
    return [
        "G21",
        "G90",
        f"G0 X0 Y0 F{format_float(config.machine.travel_feed_mm_min)}",
    ]


def paper_feed_lines(config: AppConfig, direction: str = "forward", repeat: int = 1) -> list[str]:
    raw_feed = config.raw.get("paper_feed", {})
    if direction == "backward":
        command = str(raw_feed.get("reverse_command", "M101")).strip()
    else:
        command = str(raw_feed.get("command", config.paper_feed.command)).strip()
    count = max(1, int(repeat))
    if not command:
        return []
    if "{direction}" in command:
        command = command.replace("{direction}", direction)
    if "{length_mm}" in command:
        length_text = format_float(float(raw_feed.get("feed_length_mm", config.paper_feed.feed_length_mm)))
        command = command.replace("{length_mm}", length_text)
    return [command for _ in range(count)]


def format_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
