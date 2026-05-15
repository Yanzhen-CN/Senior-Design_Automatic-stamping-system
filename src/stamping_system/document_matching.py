from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import AppConfig
from .documents import document_preview_path

Point = tuple[float, float]


@dataclass(frozen=True)
class DocumentMatchResult:
    found: bool
    target_pixel: Point | None
    message: str
    debug_image_data: str | None = None
    matches: int = 0
    inliers: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def match_document_target_to_camera(
    *,
    camera_image_data: str,
    relative_xy: Point,
    config: AppConfig,
) -> DocumentMatchResult:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for Mode C document matching") from exc

    doc_path = document_preview_path()
    doc = cv2.imread(str(doc_path))
    if doc is None:
        raise RuntimeError(f"Cannot read document preview: {doc_path}")

    camera = _decode_image_data(camera_image_data)
    if camera is None:
        raise RuntimeError("Cannot decode camera image")

    doc_gray = _preprocess_for_features(doc)
    cam_gray = _preprocess_for_features(camera)

    roi_polygon = _scaled_roi_polygon(config, camera.shape[1], camera.shape[0])
    cam_feature_gray = cam_gray
    if roi_polygon is not None:
        mask = np.zeros(cam_gray.shape[:2], dtype=np.uint8)
        pts = np.asarray(roi_polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    else:
        mask = None

    detector = cv2.AKAZE_create()
    kp_doc, des_doc = detector.detectAndCompute(doc_gray, None)
    kp_cam, des_cam = detector.detectAndCompute(cam_feature_gray, mask)

    if des_doc is None or des_cam is None or len(kp_doc) < 12 or len(kp_cam) < 12:
        message = f"Not enough document features (doc={len(kp_doc)}, camera={len(kp_cam)})."
        return _result(False, None, message, camera, doc, roi_polygon=roi_polygon)

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(des_doc, des_cam, k=2)
    good = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        a, b = pair
        if a.distance < 0.78 * b.distance:
            good.append(a)

    if len(good) < 10:
        message = f"Not enough reliable matches ({len(good)})."
        return _result(False, None, message, camera, doc, roi_polygon=roi_polygon, matches=len(good))

    src = np.float32([kp_doc[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_cam[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
    if homography is None or inliers < 8:
        message = f"Cannot compute document homography (matches={len(good)}, inliers={inliers})."
        return _result(False, None, message, camera, doc, roi_polygon=roi_polygon, matches=len(good), inliers=inliers)

    rx = max(0.0, min(1.0, float(relative_xy[0])))
    ry = max(0.0, min(1.0, float(relative_xy[1])))
    doc_h, doc_w = doc.shape[:2]
    src_point = np.float32([[[rx * doc_w, ry * doc_h]]])
    mapped = cv2.perspectiveTransform(src_point, homography)[0][0]
    target = (float(mapped[0]), float(mapped[1]))

    if not (0 <= target[0] < camera.shape[1] and 0 <= target[1] < camera.shape[0]):
        message = f"Matched target is outside camera image: ({target[0]:.1f}, {target[1]:.1f})."
        return _result(False, target, message, camera, doc, homography=homography, roi_polygon=roi_polygon, matches=len(good), inliers=inliers)

    message = f"Document matched: matches={len(good)}, inliers={inliers}."
    return _result(True, target, message, camera, doc, homography=homography, roi_polygon=roi_polygon, matches=len(good), inliers=inliers)


def _decode_image_data(image_data: str):
    import cv2
    import numpy as np

    payload = image_data.strip()
    if "," in payload:
        payload = payload.split(",", 1)[1]
    data = base64.b64decode(payload, validate=True)
    array = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def _preprocess_for_features(image):
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def _scaled_roi_polygon(config: AppConfig, image_width: int, image_height: int) -> list[Point] | None:
    vision_raw = config.raw.get("vision", {}) if isinstance(config.raw, dict) else {}
    points = list(vision_raw.get("paper_roi_points") or [])[:4] if isinstance(vision_raw, dict) else []
    if len(points) != 4:
        return None
    sx = image_width / max(1.0, float(config.camera.width_px))
    sy = image_height / max(1.0, float(config.camera.height_px))
    return [(float(x) * sx, float(y) * sy) for x, y in points]


def _result(
    found: bool,
    target: Point | None,
    message: str,
    camera,
    document,
    *,
    homography=None,
    roi_polygon: list[Point] | None = None,
    matches: int = 0,
    inliers: int = 0,
) -> DocumentMatchResult:
    return DocumentMatchResult(
        found=found,
        target_pixel=target,
        message=message,
        debug_image_data=_render_debug(camera, document, target, message, homography=homography, roi_polygon=roi_polygon),
        matches=matches,
        inliers=inliers,
    )


def _render_debug(camera, document, target: Point | None, message: str, *, homography=None, roi_polygon: list[Point] | None = None) -> str | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    dbg = camera.copy()
    if roi_polygon:
        pts = np.asarray([[int(round(x)), int(round(y))] for x, y in roi_polygon], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(dbg, [pts], True, (0, 120, 255), 2, cv2.LINE_AA)

    if homography is not None:
        h, w = document.shape[:2]
        corners = np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]])
        mapped = cv2.perspectiveTransform(corners, homography)
        cv2.polylines(dbg, [np.int32(mapped)], True, (40, 210, 40), 3, cv2.LINE_AA)

    if target is not None:
        x, y = int(round(target[0])), int(round(target[1]))
        radius = max(12, min(dbg.shape[:2]) // 45)
        cv2.circle(dbg, (x, y), radius, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(dbg, (x, y), radius, (255, 255, 255), 3, cv2.LINE_AA)

    text = str(message or "")
    if len(text) > 120:
        text = text[:117] + "..."
    cv2.putText(dbg, text, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (25, 25, 25), 3, cv2.LINE_AA)
    cv2.putText(dbg, text, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 1, cv2.LINE_AA)

    longest = max(dbg.shape[:2])
    if longest > 1600:
        scale = 1600.0 / float(longest)
        dbg = cv2.resize(dbg, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ok, buffer = cv2.imencode(".jpg", dbg, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")
