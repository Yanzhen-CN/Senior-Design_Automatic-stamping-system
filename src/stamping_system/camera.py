from __future__ import annotations

import platform
import time
from pathlib import Path

from .config import AppConfig

_LOGGING_CONFIGURED = False


def _configure_opencv_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    try:
        import cv2

        if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass
    _LOGGING_CONFIGURED = True


def _open_camera(index: int):
    import cv2

    _configure_opencv_logging()

    backends: list[int | None] = []
    if platform.system().lower().startswith("win"):
        # Try multiple Windows backends and swallow backend-specific C++ exceptions.
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]
    else:
        backends = [None]

    for backend in backends:
        camera = None
        try:
            if backend is not None:
                camera = cv2.VideoCapture(index, backend)
            else:
                camera = cv2.VideoCapture(index)
            if camera.isOpened():
                return camera
        except Exception:
            pass
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
    return None


def capture_snapshot(config: AppConfig) -> Path:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for camera capture") from exc

    target = config.camera.snapshot_path
    target.parent.mkdir(parents=True, exist_ok=True)
    camera = _open_camera(config.camera.index)
    if camera is None:
        if target.exists():
            # Keep using the latest snapshot so UI remains available.
            return target
        raise RuntimeError(f"Cannot open USB camera index {config.camera.index}")
    try:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera.width_px)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera.height_px)
        for _ in range(2):
            camera.read()
            time.sleep(0.01)
        ok, frame = camera.read()
        if (not ok or frame is None) and (
            config.camera.width_px > 1280 or config.camera.height_px > 720
        ):
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            ok, frame = camera.read()
        if not ok or frame is None:
            if target.exists():
                return target
            raise RuntimeError("Camera returned an empty frame")
        cv2.imwrite(str(target), frame)
    finally:
        camera.release()
    return target


def create_placeholder(config: AppConfig) -> bytes:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv-python and numpy are required for placeholder images") from exc

    width = config.camera.placeholder_width_px
    height = config.camera.placeholder_height_px
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    paper_margin_x = int(width * 0.18)
    paper_margin_y = int(height * 0.08)
    paper_tl = (paper_margin_x, paper_margin_y)
    paper_br = (width - paper_margin_x, height - paper_margin_y)
    cv2.rectangle(image, paper_tl, paper_br, (185, 185, 185), 2)
    cv2.line(image, (width // 2, 0), (width // 2, height), (210, 210, 210), 1)
    cv2.line(image, (0, height // 2), (width, height // 2), (210, 210, 210), 1)
    cv2.putText(
        image,
        "USB camera is not available - placeholder frame",
        (paper_margin_x, max(34, paper_margin_y - 22)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (60, 60, 60),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "Click image, set calibration marks, preview G-code",
        (paper_margin_x + 20, paper_margin_y + 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (90, 90, 90),
        2,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("Failed to encode placeholder image")
    return encoded.tobytes()


def list_candidate_cameras(max_index: int = 6) -> list[dict[str, object]]:
    try:
        import cv2
    except ImportError:
        return []

    result: list[dict[str, object]] = []
    for index in range(max_index):
        camera = _open_camera(index)
        opened = bool(camera and camera.isOpened())
        width = camera.get(cv2.CAP_PROP_FRAME_WIDTH) if opened else 0
        height = camera.get(cv2.CAP_PROP_FRAME_HEIGHT) if opened else 0
        if camera:
            camera.release()
        result.append(
            {
                "index": index,
                "available": bool(opened),
                "width": float(width),
                "height": float(height),
            }
        )
    return result
