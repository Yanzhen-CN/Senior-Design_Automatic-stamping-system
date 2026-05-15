from __future__ import annotations

import base64
import copy
import hashlib
import sys
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .camera import capture_snapshot, create_placeholder, list_candidate_cameras
from .config import load_config, parse_config, save_config
from .documents import document_preview_path, render_document_preview, save_document_upload
from .document_matching import match_document_target_to_camera
from .firmware import default_firmware_settings, flash_firmware
from .mode_a import (
    load_mode_a_state,
    reset_mode_a_state,
    run_mode_a_cycle,
    run_repeat_cycle,
    save_mode_a_frame,
    update_compensation_from_frames,
)
from .paths import runtime_path, web_root
from .pipeline import (
    jog_axis,
    move_to_target,
    preview_target,
    serial_result_to_dict,
    stamp_target,
)
from .runtime_bounds import (
    apply_runtime_bounds,
    apply_runtime_bounds_to_raw,
    clear_runtime_bounds,
    get_runtime_bounds,
    set_runtime_bounds_enabled,
    set_runtime_bound_point,
)
from .serial_link import SerialTransport, get_serial_manager, list_serial_ports
from .targeting import PRESETS, TargetInput
from .vision import detect_paper_from_image


WEB_ROOT = web_root()

app = FastAPI(title="Automatic Stamping System")
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


class TargetRequest(BaseModel):
    source: Literal["pixel", "pixel_on_paper", "relative_paper", "paper_preset", "keyword", "real"] = "pixel"
    x: float | None = None
    y: float | None = None
    preset: str | None = None
    keyword: str | None = None
    offset_mm: tuple[float, float] = (0.0, 0.0)
    paper_quad: list[tuple[float, float]] | None = None

    def to_target_input(self) -> TargetInput:
        return TargetInput(
            source=self.source,
            x=self.x,
            y=self.y,
            preset=self.preset,
            keyword=self.keyword,
            offset_mm=self.offset_mm,
            paper_quad=self.paper_quad,
        )


class ExecuteTargetRequest(TargetRequest):
    dry_run: bool | None = Field(default=None)
    slow: bool = True


class JogRequest(BaseModel):
    axis: Literal["x", "y", "z", "X", "Y", "Z"]
    distance_mm: float
    dry_run: bool | None = None


class JogVectorRequest(BaseModel):
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    dz_mm: float = 0.0
    dry_run: bool | None = None


class MotionZeroRequest(BaseModel):
    target: Literal["xy", "z", "all"] = "xy"
    dry_run: bool | None = None


class JogHoldRequest(BaseModel):
    axis: Literal["x", "y", "z", "X", "Y", "Z"]
    direction: float


class JogHoldVectorRequest(BaseModel):
    dx_sign: float = 0.0
    dy_sign: float = 0.0
    dz_sign: float = 0.0


class SerialConnectRequest(BaseModel):
    port: str
    baudrate: int = 115200
    dry_run: bool = False


class SaveConfigRequest(BaseModel):
    config: dict[str, Any]


class PaperFeedRequest(BaseModel):
    direction: Literal["forward", "backward"] = "forward"
    command: str | None = None
    dry_run: bool | None = None
    repeat: int = 1
    length_mm: float | None = None


class FirmwareFlashRequest(BaseModel):
    port: str
    board: str = "uno_atmega328p"
    mcu: str = "atmega328p"
    baudrate: int = 115200
    programmer: str = "arduino"
    hex_path: str
    avrdude_path: str | None = None
    avrdude_conf: str | None = None


class CalibrationPointRequest(BaseModel):
    label: str
    pixel: tuple[float, float]
    real_mm: tuple[float, float]


class CameraSetupRequest(BaseModel):
    index: int
    browser_device_id: str | None = None
    media_source: str | None = None
    stream_url: str | None = None
    width_px: int
    height_px: int
    height_mm: float
    calibration_points: list[CalibrationPointRequest] | None = None


class SnapshotUploadRequest(BaseModel):
    image_data: str


class DocumentMatchRequest(BaseModel):
    image_data: str
    relative_xy: tuple[float, float]


class ModeAFrameUploadRequest(BaseModel):
    stage: Literal["before", "after"]
    image_data: str


class ModeACycleRequest(BaseModel):
    relative_xy: tuple[float, float]
    offset_mm: tuple[float, float] = (0.0, 0.0)
    dry_run: bool | None = None
    detect_paper: bool = True
    feed_before: bool = False
    feed_after: bool = False
    return_xy_zero: bool = True
    apply_compensation: bool = False


class RepeatCycleRequest(TargetRequest):
    dry_run: bool | None = None
    detect_paper: bool = True
    feed_before: bool = False
    feed_after: bool = True
    return_xy_zero: bool = True


class ModeACompensationRequest(BaseModel):
    expected_pixel: tuple[float, float]
    gain: float = 0.35
    roi_radius_px: int = 150
    min_area_px: int = 45


class BoundCaptureRequest(BaseModel):
    point: Literal["origin", "xMax", "yMax"]
    x: float
    y: float


class BoundEnableRequest(BaseModel):
    enabled: bool


class DetectPaperRequest(BaseModel):
    fresh: bool = False
    use_calibration_roi: bool = True
    use_paper_roi: bool = True
    roi_points: list[tuple[float, float]] | None = None
    paper_color: Literal["auto", "white", "blue", "custom"] = "auto"
    paper_hsv_center: tuple[int, int, int] | None = None
    paper_hsv_tolerance: tuple[int, int, int] | None = None


def _latest_work_position(config) -> list[float] | None:
    def _wpos_from_position(position_payload: dict[str, object] | None) -> list[float] | None:
        if not isinstance(position_payload, dict):
            return None
        wpos = position_payload.get("wpos")
        if isinstance(wpos, list) and len(wpos) >= 3:
            try:
                return [float(wpos[0]), float(wpos[1]), float(wpos[2])]
            except Exception:
                return None
        mpos = position_payload.get("mpos")
        wco = position_payload.get("wco")
        if isinstance(mpos, list) and len(mpos) >= 3 and isinstance(wco, list) and len(wco) >= 3:
            try:
                return [
                    float(mpos[0]) - float(wco[0]),
                    float(mpos[1]) - float(wco[1]),
                    float(mpos[2]) - float(wco[2]),
                ]
            except Exception:
                return None
        return None

    manager = get_serial_manager()
    snapshot = manager.status(config)
    status = snapshot.get("position") if isinstance(snapshot, dict) else None
    position = _wpos_from_position(status if isinstance(status, dict) else None)
    if position is not None:
        return position
    if manager.is_connected:
        try:
            manager.query_status(config)
        except Exception:
            return None
        refreshed_snapshot = manager.status(config)
        refreshed = refreshed_snapshot.get("position") if isinstance(refreshed_snapshot, dict) else None
        position = _wpos_from_position(refreshed if isinstance(refreshed, dict) else None)
        if position is not None:
            return position
    return None


def _config_with_runtime_bounds(config):
    raw = copy.deepcopy(config.raw)
    bounded = apply_runtime_bounds_to_raw(raw)
    bounds = bounded.get("machine", {}).get("workspace_bounds", {})
    axes = bounded.get("machine", {}).get("axes", {})
    if isinstance(bounds, dict) and bool(bounds.get("enabled")) and isinstance(axes, dict):
        for axis_name in ("x", "y"):
            axis_bounds = bounds.get(axis_name)
            axis_cfg = axes.get(axis_name)
            if not isinstance(axis_bounds, dict) or not isinstance(axis_cfg, dict):
                continue
            if axis_bounds.get("min") is not None:
                axis_cfg["min_commanded_mm"] = float(axis_bounds["min"])
            if axis_bounds.get("max") is not None:
                axis_cfg["max_commanded_mm"] = float(axis_bounds["max"])
    return parse_config(bounded, config.path)


def _load_effective_config():
    return _config_with_runtime_bounds(load_config())


def _runtime_xy_bounds_active(config=None) -> bool:
    snapshot = get_runtime_bounds()
    if not isinstance(snapshot, dict):
        return False
    return bool(snapshot.get("enabled"))


def _validate_jog_target_bounds(
    config,
    dx_cmd: float = 0.0,
    dy_cmd: float = 0.0,
    dz_cmd: float = 0.0,
    *,
    enforce: bool,
) -> None:
    if not enforce:
        return
    current = _latest_work_position(config)
    if not current:
        raise ValueError("Cannot enforce workspace bounds: missing live position (click Status ? first).")
    if _runtime_xy_bounds_active(config):
        _validate_axis_target_with_recovery("x", current[0], current[0] + dx_cmd, config.machine.axes["x"])
        _validate_axis_target_with_recovery("y", current[1], current[1] + dy_cmd, config.machine.axes["y"])
    _validate_axis_target_with_recovery("z", current[2], current[2] + dz_cmd, config.machine.axes["z"])


def _validate_axis_target_with_recovery(axis: str, current: float, target: float, axis_config) -> None:
    epsilon = 1e-9
    min_limit = float(axis_config.min_commanded_mm)
    max_limit = float(axis_config.max_commanded_mm)
    if current < (min_limit - epsilon):
        # Already outside min edge: only allow moves that go back toward the workspace.
        if target <= (current + epsilon):
            raise ValueError(
                f"{axis.upper()} is below min boundary ({current:.3f} < {min_limit:.3f}); "
                f"move +{axis.upper()} to re-enter workspace."
            )
        return
    if current > (max_limit + epsilon):
        # Already outside max edge: only allow moves that go back toward the workspace.
        if target >= (current - epsilon):
            raise ValueError(
                f"{axis.upper()} is above max boundary ({current:.3f} > {max_limit:.3f}); "
                f"move -{axis.upper()} to re-enter workspace."
            )
        return
    axis_config.validate(target)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/config")
def get_config() -> dict[str, object]:
    config = load_config()
    axes = {
        name: {
            "theoretical_steps_per_mm": axis.theoretical_steps_per_mm,
            "configured_steps_per_mm": axis.steps_per_mm,
        }
        for name, axis in config.machine.axes.items()
    }
    return {
        "path": str(config.path),
        "python": sys.version,
        "config": config.raw,
        "axis_theory": axes,
        "presets": PRESETS,
        "runtime_bounds": get_runtime_bounds(),
    }


@app.post("/api/config")
def update_config(request: SaveConfigRequest) -> dict[str, object]:
    try:
        saved = save_config(request.config)
        return {"ok": True, "path": str(saved.path), "config": saved.raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cameras")
def cameras() -> dict[str, object]:
    config = load_config()
    return {
        "configured": {
            "index": config.camera.index,
            "width_px": config.camera.width_px,
            "height_px": config.camera.height_px,
            "height_mm": config.camera.height_mm,
        },
        "candidates": list_candidate_cameras(),
    }


@app.get("/api/serial/ports")
def serial_ports() -> dict[str, object]:
    config = load_config()
    return {
        "configured": {
            "port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "dry_run": config.serial.dry_run,
        },
        "status": get_serial_manager().status(config),
        "ports": list_serial_ports(),
    }


@app.get("/api/serial/status")
def serial_status() -> dict[str, object]:
    config = load_config()
    return {"status": get_serial_manager().status(config)}


@app.post("/api/serial/connect")
def serial_connect(request: SerialConnectRequest) -> dict[str, object]:
    try:
        config = load_config()
        raw = config.raw
        raw["serial"]["port"] = request.port
        raw["serial"]["baudrate"] = request.baudrate
        raw["serial"]["dry_run"] = request.dry_run
        saved = save_config(raw)
        result = get_serial_manager().connect(saved)
        return {
            "ok": True,
            "config": saved.raw,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(saved),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/disconnect")
def serial_disconnect() -> dict[str, object]:
    config = load_config()
    result = get_serial_manager().disconnect()
    return {
        "ok": True,
        "serial": serial_result_to_dict(result),
        "status": get_serial_manager().status(config),
    }


@app.post("/api/serial/unlock")
def serial_unlock() -> dict[str, object]:
    try:
        config = load_config()
        result = get_serial_manager().unlock(config)
        return {
            "ok": True,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/query")
def serial_query() -> dict[str, object]:
    try:
        config = load_config()
        result = get_serial_manager().query_status(config)
        return {
            "ok": True,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/reset")
def serial_reset() -> dict[str, object]:
    try:
        config = load_config()
        result = get_serial_manager().reset(config)
        return {
            "ok": True,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/paper-feed/run")
def paper_feed_run(request: PaperFeedRequest) -> dict[str, object]:
    try:
        config = load_config()
        raw_feed = config.raw.get("paper_feed", {})
        forward = str(raw_feed.get("command", config.paper_feed.command)).strip()
        backward = str(raw_feed.get("reverse_command", "M101")).strip()
        configured_step_mm = float(raw_feed.get("feed_length_mm", config.paper_feed.feed_length_mm))
        configured_step_mm = configured_step_mm if configured_step_mm > 0 else 0.0

        chosen = (request.command or "").strip()
        if not chosen:
            chosen = forward if request.direction == "forward" else backward
        if not chosen:
            raise ValueError("Paper feed command is empty")

        target_length_mm = (
            float(request.length_mm)
            if request.length_mm is not None and request.length_mm > 0
            else configured_step_mm
        )
        repeat = int(request.repeat) if request.repeat > 0 else 1
        repeat = max(1, min(500, repeat))

        if "{length_mm}" in chosen:
            length_text = f"{target_length_mm:.3f}".rstrip("0").rstrip(".")
            chosen = chosen.replace("{length_mm}", length_text)
        if "{direction}" in chosen:
            chosen = chosen.replace("{direction}", request.direction)

        lines = [chosen for _ in range(repeat)]
        result = SerialTransport(config, force_dry_run=request.dry_run).execute(lines)
        effective_length_mm = configured_step_mm * repeat if configured_step_mm > 0 else None
        return {
            "ok": True,
            "command": chosen,
            "repeat": repeat,
            "configured_step_mm": configured_step_mm,
            "requested_length_mm": target_length_mm,
            "effective_length_mm": effective_length_mm,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/motion/go-zero")
def motion_go_zero(request: MotionZeroRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        enforce_xy = _runtime_xy_bounds_active(config)
        lines = ["G21", "G90"]
        if request.target == "xy":
            if enforce_xy:
                config.machine.axes["x"].validate(0.0)
                config.machine.axes["y"].validate(0.0)
            lines.append(
                f"G0 X0 Y0 F{config.machine.travel_feed_mm_min:.3f}".rstrip("0").rstrip(".")
            )
        elif request.target == "z":
            config.machine.axes["z"].validate(0.0)
            lines.append(
                f"G0 Z0 F{config.machine.z_feed_mm_min:.3f}".rstrip("0").rstrip(".")
            )
        else:
            config.machine.axes["z"].validate(0.0)
            if enforce_xy:
                config.machine.axes["x"].validate(0.0)
                config.machine.axes["y"].validate(0.0)
            lines.append(
                f"G0 Z0 F{config.machine.z_feed_mm_min:.3f}".rstrip("0").rstrip(".")
            )
            lines.append(
                f"G0 X0 Y0 F{config.machine.travel_feed_mm_min:.3f}".rstrip("0").rstrip(".")
            )

        result = SerialTransport(config, force_dry_run=request.dry_run).execute(lines)
        return {
            "ok": True,
            "gcode": lines,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/motion/set-work-zero")
def motion_set_work_zero(request: MotionZeroRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        manager = get_serial_manager()
        lines = ["G21", "G90"]
        if request.target == "xy":
            lines.append("G10 L20 P1 X0 Y0")
        elif request.target == "z":
            lines.append("G10 L20 P1 Z0")
        else:
            lines.append("G10 L20 P1 X0 Y0")
            lines.append("G10 L20 P1 Z0")

        result = SerialTransport(config, force_dry_run=request.dry_run).execute(lines)
        effective_dry_run = config.serial.dry_run if request.dry_run is None else bool(request.dry_run)
        if manager.is_connected and not effective_dry_run:
            try:
                manager.query_status(config)
            except Exception:
                pass
        return {
            "ok": True,
            "gcode": lines,
            "serial": serial_result_to_dict(result),
            "status": manager.status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/motion/bounds")
def motion_bounds() -> dict[str, object]:
    return {"ok": True, "bounds": get_runtime_bounds()}


@app.post("/api/motion/bounds/capture")
def motion_bounds_capture(request: BoundCaptureRequest) -> dict[str, object]:
    bounds = set_runtime_bound_point(request.point, (request.x, request.y))
    return {"ok": True, "bounds": bounds}


@app.post("/api/motion/bounds/clear")
def motion_bounds_clear() -> dict[str, object]:
    bounds = clear_runtime_bounds()
    return {"ok": True, "bounds": bounds}


@app.post("/api/motion/bounds/apply")
def motion_bounds_apply() -> dict[str, object]:
    try:
        bounds = apply_runtime_bounds()
        return {"ok": True, "bounds": bounds}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/motion/bounds/enable")
def motion_bounds_enable(request: BoundEnableRequest) -> dict[str, object]:
    try:
        bounds = set_runtime_bounds_enabled(bool(request.enabled))
        return {"ok": True, "bounds": bounds}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/firmware/settings")
def firmware_settings() -> dict[str, object]:
    config = load_config()
    defaults = default_firmware_settings()
    configured = config.raw.get("firmware", {})
    merged = {**defaults, **configured}
    return {
        "configured": merged,
        "ports": list_serial_ports(),
    }


@app.post("/api/firmware/upload")
async def firmware_upload(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        name = (file.filename or "").lower()
        if not name.endswith(".hex"):
            raise ValueError("Please upload a .hex file")
        data = await file.read()
        if not data:
            raise ValueError("Uploaded HEX file is empty")

        target_dir = runtime_path("runtime/firmware")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "uploaded_firmware.hex"
        with target.open("wb") as handle:
            handle.write(data)
        sha1 = hashlib.sha1(data).hexdigest()
        return {
            "ok": True,
            "filename": file.filename,
            "path": str(target.resolve()),
            "size": len(data),
            "sha1": sha1,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/firmware/flash")
def firmware_flash(request: FirmwareFlashRequest) -> dict[str, object]:
    try:
        config = load_config()
        manager = get_serial_manager()
        if manager.is_connected:
            manager.disconnect()

        outcome = flash_firmware(
            port=request.port,
            hex_path=request.hex_path,
            mcu=request.mcu,
            baudrate=request.baudrate,
            programmer=request.programmer,
            avrdude_path=request.avrdude_path,
            avrdude_conf=request.avrdude_conf,
        )

        raw = config.raw
        raw["firmware"] = {
            "board": request.board,
            "mcu": request.mcu,
            "baudrate": request.baudrate,
            "programmer": request.programmer,
            "hex_path": request.hex_path,
            "avrdude_path": request.avrdude_path or "",
            "avrdude_conf": request.avrdude_conf or "",
        }
        save_config(raw)

        return {
            "ok": outcome["ok"],
            "flash": outcome,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jog/hold-start")
def jog_hold_start(request: JogHoldRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        manager = get_serial_manager()
        result = manager.start_continuous_jog(
            request.axis,
            request.direction,
            config,
        )
        return {
            "ok": True,
            "gcode": result.sent_lines,
            "serial": serial_result_to_dict(result),
            "status": manager.status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jog/hold-start-vector")
def jog_hold_start_vector(request: JogHoldVectorRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        manager = get_serial_manager()
        result = manager.start_continuous_vector_jog(
            request.dx_sign,
            request.dy_sign,
            request.dz_sign,
            config,
        )
        return {
            "ok": True,
            "gcode": result.sent_lines,
            "serial": serial_result_to_dict(result),
            "status": manager.status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jog/hold-stop")
def jog_hold_stop() -> dict[str, object]:
    try:
        config = load_config()
        result = get_serial_manager().cancel_jog(config)
        return {
            "ok": True,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/camera/setup")
def update_camera_setup(request: CameraSetupRequest) -> dict[str, object]:
    try:
        config = load_config()
        raw = config.raw
        raw["camera"]["index"] = request.index
        raw["camera"]["browser_device_id"] = request.browser_device_id or ""
        raw["camera"]["media_source"] = request.media_source or "local"
        raw["camera"]["stream_url"] = request.stream_url or ""
        raw["camera"]["width_px"] = request.width_px
        raw["camera"]["height_px"] = request.height_px
        raw["camera"]["height_mm"] = request.height_mm
        if request.calibration_points is not None:
            raw["calibration"]["points"] = [
                {
                    "label": point.label,
                    "pixel": [point.pixel[0], point.pixel[1]],
                    "real_mm": [point.real_mm[0], point.real_mm[1]],
                }
                for point in request.calibration_points
            ]
        saved = save_config(raw)
        return {"ok": True, "path": str(saved.path), "config": saved.raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/document")
async def upload_document(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        data = await file.read()
        path = save_document_upload(file.filename or "uploaded_document", data)
        return render_document_preview(path).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/document/preview")
def document_preview() -> FileResponse:
    path = document_preview_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="No document preview has been uploaded")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/document/match")
def document_match(request: DocumentMatchRequest) -> dict[str, object]:
    try:
        config = load_config()
        return match_document_target_to_camera(
            camera_image_data=request.image_data,
            relative_xy=request.relative_xy,
            config=config,
        ).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/snapshot")
def snapshot() -> Response:
    config = load_config()
    try:
        path = capture_snapshot(config)
        return FileResponse(path, media_type="image/jpeg")
    except Exception as exc:
        try:
            return Response(content=create_placeholder(config), media_type="image/jpeg")
        except Exception:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/snapshot/upload")
def snapshot_upload(request: SnapshotUploadRequest) -> dict[str, object]:
    try:
        config = load_config()
        image_data = request.image_data.strip()
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        data = base64.b64decode(image_data, validate=True)
        if not data:
            raise ValueError("Uploaded camera frame is empty")
        target = config.camera.snapshot_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"ok": True, "path": str(target), "size": len(data)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mode-a/state")
def mode_a_state() -> dict[str, object]:
    return {"ok": True, "state": load_mode_a_state().to_dict()}


@app.post("/api/mode-a/state/reset")
def mode_a_state_reset() -> dict[str, object]:
    return {"ok": True, "state": reset_mode_a_state().to_dict()}


@app.post("/api/mode-a/frame")
def mode_a_frame(request: ModeAFrameUploadRequest) -> dict[str, object]:
    try:
        config = load_config()
        saved = save_mode_a_frame(request.image_data, request.stage, config=config)
        return {"ok": True, "stage": request.stage, "path": str(saved)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mode-a/cycle")
def mode_a_cycle(request: ModeACycleRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        result = run_mode_a_cycle(
            config=config,
            relative_xy=request.relative_xy,
            user_offset_mm=request.offset_mm,
            dry_run=request.dry_run,
            detect_paper=request.detect_paper,
            feed_before=request.feed_before,
            feed_after=request.feed_after,
            return_xy_zero=request.return_xy_zero,
            apply_compensation=request.apply_compensation,
        )
        result["status"] = get_serial_manager().status(config)
        return {"ok": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/repeat/cycle")
def repeat_cycle(request: RepeatCycleRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        result = run_repeat_cycle(
            config=config,
            target=request.to_target_input(),
            dry_run=request.dry_run,
            detect_paper=request.detect_paper,
            feed_before=request.feed_before,
            feed_after=request.feed_after,
            return_xy_zero=request.return_xy_zero,
        )
        result["status"] = get_serial_manager().status(config)
        return {"ok": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mode-a/compensation/update")
def mode_a_compensation_update(request: ModeACompensationRequest) -> dict[str, object]:
    try:
        config = load_config()
        result = update_compensation_from_frames(
            config=config,
            expected_pixel=request.expected_pixel,
            gain=request.gain,
            roi_radius_px=request.roi_radius_px,
            min_area_px=request.min_area_px,
        )
        return {"ok": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/detect-paper")
def detect_paper(request: DetectPaperRequest | None = None, fresh: bool = False) -> dict[str, object]:
    config = load_config()
    try:
        payload = request or DetectPaperRequest()
        use_fresh = bool(fresh or payload.fresh)
        path = config.camera.snapshot_path
        if use_fresh or not path.exists():
            path = capture_snapshot(config)
        return detect_paper_from_image(
            path,
            config,
            roi_points=payload.roi_points,
            use_calibration_roi=payload.use_calibration_roi,
            use_paper_roi=payload.use_paper_roi,
            paper_color=payload.paper_color,
            paper_hsv_center=payload.paper_hsv_center,
            paper_hsv_tolerance=payload.paper_hsv_tolerance,
        ).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/preview")
def preview(request: TargetRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        return preview_target(request.to_target_input(), config=config).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/move")
def move(request: ExecuteTargetRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        preview_result, serial_result = move_to_target(
            request.to_target_input(),
            dry_run=request.dry_run,
            slow=request.slow,
            config=config,
        )
        return {
            "preview": preview_result.to_dict(),
            "serial": serial_result_to_dict(serial_result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/stamp")
def stamp(request: ExecuteTargetRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        preview_result, serial_result = stamp_target(
            request.to_target_input(),
            dry_run=request.dry_run,
            config=config,
        )
        return {
            "preview": preview_result.to_dict(),
            "serial": serial_result_to_dict(serial_result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jog")
def jog(request: JogRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        effective_dry_run = config.serial.dry_run if request.dry_run is None else bool(request.dry_run)
        axis = request.axis.lower()
        axis_cfg = config.machine.axes[axis]
        commanded_delta = axis_cfg.real_delta_to_commanded(request.distance_mm)
        dx_cmd = commanded_delta if axis == "x" else 0.0
        dy_cmd = commanded_delta if axis == "y" else 0.0
        dz_cmd = commanded_delta if axis == "z" else 0.0
        _validate_jog_target_bounds(
            config,
            dx_cmd=dx_cmd,
            dy_cmd=dy_cmd,
            dz_cmd=dz_cmd,
            enforce=not effective_dry_run,
        )
        plan, result = jog_axis(request.axis, request.distance_mm, request.dry_run, config=config)
        return {
            "gcode": plan.lines,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jog/vector")
def jog_vector(request: JogVectorRequest) -> dict[str, object]:
    try:
        config = _load_effective_config()
        effective_dry_run = config.serial.dry_run if request.dry_run is None else bool(request.dry_run)
        deltas: list[str] = []
        dx_cmd = 0.0
        dy_cmd = 0.0
        dz_cmd = 0.0
        if abs(request.dx_mm) > 1e-9:
            dx_cmd = config.machine.axes["x"].real_delta_to_commanded(request.dx_mm)
            deltas.append(f"X{dx_cmd:.3f}".rstrip("0").rstrip("."))
        if abs(request.dy_mm) > 1e-9:
            dy_cmd = config.machine.axes["y"].real_delta_to_commanded(request.dy_mm)
            deltas.append(f"Y{dy_cmd:.3f}".rstrip("0").rstrip("."))
        if abs(request.dz_mm) > 1e-9:
            dz_cmd = config.machine.axes["z"].real_delta_to_commanded(request.dz_mm)
            deltas.append(f"Z{dz_cmd:.3f}".rstrip("0").rstrip("."))
        if not deltas:
            raise ValueError("At least one delta must be non-zero")
        _validate_jog_target_bounds(
            config,
            dx_cmd=dx_cmd,
            dy_cmd=dy_cmd,
            dz_cmd=dz_cmd,
            enforce=not effective_dry_run,
        )

        has_xy = any(item.startswith("X") or item.startswith("Y") for item in deltas)
        has_z = any(item.startswith("Z") for item in deltas)
        if has_xy and has_z:
            feed = min(config.machine.jog_feed_mm_min, config.machine.z_feed_mm_min)
        elif has_xy:
            feed = config.machine.jog_feed_mm_min
        else:
            feed = config.machine.z_feed_mm_min
        lines = ["G21", "G91", f"G0 {' '.join(deltas)} F{feed:.3f}".rstrip("0").rstrip("."), "G90"]
        result = SerialTransport(config, force_dry_run=request.dry_run).execute(lines)
        return {
            "gcode": lines,
            "serial": serial_result_to_dict(result),
            "status": get_serial_manager().status(config),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
