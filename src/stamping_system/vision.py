from __future__ import annotations

import base64
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import AppConfig


Point = tuple[float, float]


@dataclass(frozen=True)
class PaperDetection:
    found: bool
    quad: list[Point]
    center: Point | None
    message: str
    debug_image_data: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_paper_from_image(
    path: Path,
    config: AppConfig,
    *,
    roi_points: list[Point] | None = None,
    use_calibration_roi: bool = False,
    use_paper_roi: bool = True,
    paper_color: str = "auto",
    paper_hsv_center: tuple[int, int, int] | None = None,
    paper_hsv_tolerance: tuple[int, int, int] | None = None,
) -> PaperDetection:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for paper detection") from exc

    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Cannot read image: {path}")

    work, scale = _resize_for_detection(image, max_dim=1500)
    h, w = work.shape[:2]
    roi_polygon = _resolve_roi_polygon(
        config,
        width=w,
        height=h,
        roi_points=roi_points,
        use_paper_roi=use_paper_roi,
        use_calibration_roi=use_calibration_roi,
        scale=scale,
    )
    roi_mask = _polygon_mask(w, h, roi_polygon)
    roi_area = _polygon_area(roi_polygon) if roi_polygon else None
    area_base = roi_area if roi_area and roi_area > 1 else float(w * h)

    min_area_ratio = float(config.vision.paper_min_area_ratio)
    min_area = max(500.0, area_base * min_area_ratio)
    expected_ratio = _paper_aspect_ratio(config)
    hint = _normalize_paper_color_hint(paper_color)

    contour_sets = _candidate_contour_sets(
        work,
        roi_mask,
        hint,
        paper_hsv_center=paper_hsv_center,
        paper_hsv_tolerance=paper_hsv_tolerance,
    )

    best = _select_best_quad(
        contour_sets,
        min_area=min_area,
        area_base=area_base,
        width=w,
        height=h,
        expected_ratio=expected_ratio,
        strict=True,
        preferred_color=hint,
        roi_area=roi_area,
    )
    if best is None:
        best = _select_best_quad(
            contour_sets,
            min_area=max(250.0, min_area * 0.45),
            area_base=area_base,
            width=w,
            height=h,
            expected_ratio=expected_ratio,
            strict=False,
            preferred_color=hint,
            roi_area=roi_area,
        )

    if best is None and roi_mask is not None:
        # ROI may be slightly off; one more pass without ROI constraint.
        contour_sets_no_roi = _candidate_contour_sets(
            work,
            None,
            hint,
            paper_hsv_center=paper_hsv_center,
            paper_hsv_tolerance=paper_hsv_tolerance,
        )
        best = _select_best_quad(
            contour_sets_no_roi,
            min_area=max(250.0, min_area * 0.40),
            area_base=float(w * h),
            width=w,
            height=h,
            expected_ratio=expected_ratio,
            strict=False,
            preferred_color=hint,
            roi_area=None,
        )

    if best is None:
        best = _fallback_largest_quad(
            contour_sets,
            min_area=max(180.0, min_area * 0.30),
            area_base=area_base,
        )

    roi_polygon_original = _polygon_rescaled(roi_polygon, 1.0 / scale) if roi_polygon else None
    if best is None:
        message = f"No paper-like quadrilateral detected (hint={hint})."
        return PaperDetection(
            found=False,
            quad=[],
            center=None,
            message=message,
            debug_image_data=_render_debug_image_data(
                image,
                quad=None,
                center=None,
                message=message,
                roi_polygon=roi_polygon_original,
            ),
        )

    quad_work = best["quad"]
    quad_orig = _polygon_rescaled(quad_work, 1.0 / scale)
    ordered = order_quad(quad_orig)
    center = (
        sum(point[0] for point in ordered) / 4.0,
        sum(point[1] for point in ordered) / 4.0,
    )
    message = f"Paper detected via {best['source']}, score={best['score']:.2f}."
    return PaperDetection(
        found=True,
        quad=ordered,
        center=center,
        message=message,
        debug_image_data=_render_debug_image_data(
            image,
            quad=ordered,
            center=center,
            message=message,
            roi_polygon=roi_polygon_original,
        ),
    )


def order_quad(points: list[Point]) -> list[Point]:
    if len(points) != 4:
        raise ValueError("quad requires exactly four points")
    sums = [point[0] + point[1] for point in points]
    diffs = [point[0] - point[1] for point in points]
    top_left = points[sums.index(min(sums))]
    bottom_right = points[sums.index(max(sums))]
    top_right = points[diffs.index(max(diffs))]
    bottom_left = points[diffs.index(min(diffs))]
    return [top_left, top_right, bottom_right, bottom_left]


def _resize_for_detection(image, *, max_dim: int = 1500):
    import cv2

    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= 0 or longest <= max_dim:
        return image, 1.0
    scale = float(max_dim) / float(longest)
    resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return resized, scale


def _normalize_paper_color_hint(value: str | None) -> str:
    hint = (value or "white").strip().lower()
    if hint in {"white", "custom"}:
        return hint
    # Backward compatibility for older frontend values.
    if hint in {"auto", "blue"}:
        return hint
    return "white"


def _resolve_roi_polygon(
    config: AppConfig,
    *,
    width: int,
    height: int,
    roi_points: list[Point] | None,
    use_paper_roi: bool,
    use_calibration_roi: bool,
    scale: float,
) -> list[Point] | None:
    points: list[Point] = []
    if roi_points and len(roi_points) >= 4:
        points = [(float(p[0]) * scale, float(p[1]) * scale) for p in roi_points[:4]]
    elif use_paper_roi:
        raw_points = config.raw.get("vision", {}).get("paper_roi_points")
        if isinstance(raw_points, list) and len(raw_points) >= 4:
            try:
                points = [(float(p[0]) * scale, float(p[1]) * scale) for p in raw_points[:4]]
            except Exception:
                points = []
    if not points and not use_calibration_roi:
        return None
    if not points and use_calibration_roi:
        try:
            points = [
                (float(item.pixel[0]) * scale, float(item.pixel[1]) * scale)
                for item in (config.calibration.points or [])
                if item.pixel and len(item.pixel) >= 2
            ][:4]
        except Exception:
            points = []
    if len(points) < 4:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if (
        min(xs) < -0.5 * width
        or min(ys) < -0.5 * height
        or max(xs) > 1.5 * width
        or max(ys) > 1.5 * height
    ):
        return None
    return order_quad(points)


def _polygon_mask(width: int, height: int, polygon: list[Point] | None):
    if not polygon or len(polygon) < 4:
        return None
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    pts = []
    for x, y in polygon:
        px = int(round(max(0.0, min(float(width - 1), float(x)))))
        py = int(round(max(0.0, min(float(height - 1), float(y)))))
        pts.append([px, py])
    arr = np.asarray(pts, dtype=np.int32)
    if arr.shape != (4, 2):
        return None
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [arr], 255)
    return mask


def _polygon_rescaled(polygon: list[Point], factor: float) -> list[Point]:
    if not polygon:
        return []
    return [(float(x) * factor, float(y) * factor) for x, y in polygon]


def _polygon_area(polygon: list[Point] | None) -> float | None:
    if not polygon or len(polygon) < 3:
        return None
    area = 0.0
    n = len(polygon)
    for idx in range(n):
        x1, y1 = polygon[idx]
        x2, y2 = polygon[(idx + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _candidate_contour_sets(
    image,
    roi_mask,
    paper_color_hint: str,
    *,
    paper_hsv_center: tuple[int, int, int] | None,
    paper_hsv_tolerance: tuple[int, int, int] | None,
):
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    kernel3 = np.ones((3, 3), np.uint8)
    kernel5 = np.ones((5, 5), np.uint8)

    def _apply_roi(mask):
        if roi_mask is None:
            return mask
        return cv2.bitwise_and(mask, roi_mask)

    sources: list[tuple[str, object]] = []

    # Baseline from common document-scanner examples.
    edges = cv2.Canny(blur, 75, 200)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel5, iterations=2)
    sources.append(("edges", _apply_roi(edges)))

    # Otsu binary + inverse binary.
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, otsu_inv = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel5, iterations=2)
    otsu_inv = cv2.morphologyEx(otsu_inv, cv2.MORPH_CLOSE, kernel5, iterations=2)
    sources.append(("otsu", _apply_roi(otsu)))
    sources.append(("otsu_inv", _apply_roi(otsu_inv)))

    # Adaptive threshold variants for uneven lighting.
    adaptive = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    adaptive_inv = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel3, iterations=1)
    adaptive_inv = cv2.morphologyEx(adaptive_inv, cv2.MORPH_CLOSE, kernel3, iterations=1)
    sources.append(("adaptive", _apply_roi(adaptive)))
    sources.append(("adaptive_inv", _apply_roi(adaptive_inv)))

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    if paper_color_hint in {"white", "auto"}:
        white = cv2.inRange(hsv, np.array([0, 0, 135]), np.array([180, 95, 255]))
        white = cv2.morphologyEx(white, cv2.MORPH_OPEN, kernel3, iterations=1)
        white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel5, iterations=2)
        sources.append(("color:white", _apply_roi(white)))

    if paper_color_hint in {"blue", "auto"}:
        blue = cv2.inRange(hsv, np.array([85, 45, 35]), np.array([140, 255, 255]))
        blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, kernel3, iterations=1)
        blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, kernel5, iterations=2)
        sources.append(("color:blue", _apply_roi(blue)))

    if paper_color_hint == "custom" and paper_hsv_center is not None:
        custom = _hsv_band_mask(hsv, paper_hsv_center, paper_hsv_tolerance or (12, 70, 70))
        custom = cv2.morphologyEx(custom, cv2.MORPH_OPEN, kernel3, iterations=1)
        custom = cv2.morphologyEx(custom, cv2.MORPH_CLOSE, kernel5, iterations=2)
        sources.append(("color:custom", _apply_roi(custom)))

    contour_sets: list[tuple[str, list[object]]] = []
    for source_name, mask in sources:
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contour_sets.append((source_name, contours))
    return contour_sets


def _hsv_band_mask(hsv_img, center_hsv: tuple[int, int, int], tol_hsv: tuple[int, int, int]):
    import cv2
    import numpy as np

    h, s, v = [int(value) for value in center_hsv]
    tol_h, tol_s, tol_v = [int(value) for value in tol_hsv]
    h = max(0, min(179, h))
    s = max(0, min(255, s))
    v = max(0, min(255, v))
    tol_h = max(1, min(60, abs(tol_h)))
    tol_s = max(1, min(255, abs(tol_s)))
    tol_v = max(1, min(255, abs(tol_v)))

    low_s = max(0, s - tol_s)
    high_s = min(255, s + tol_s)
    low_v = max(0, v - tol_v)
    high_v = min(255, v + tol_v)

    low_h = h - tol_h
    high_h = h + tol_h
    if 0 <= low_h and high_h <= 179:
        return cv2.inRange(
            hsv_img,
            np.array([low_h, low_s, low_v], dtype=np.uint8),
            np.array([high_h, high_s, high_v], dtype=np.uint8),
        )

    parts = []
    if low_h < 0:
        parts.append(
            cv2.inRange(
                hsv_img,
                np.array([0, low_s, low_v], dtype=np.uint8),
                np.array([high_h, high_s, high_v], dtype=np.uint8),
            )
        )
        parts.append(
            cv2.inRange(
                hsv_img,
                np.array([180 + low_h, low_s, low_v], dtype=np.uint8),
                np.array([179, high_s, high_v], dtype=np.uint8),
            )
        )
    else:
        parts.append(
            cv2.inRange(
                hsv_img,
                np.array([low_h, low_s, low_v], dtype=np.uint8),
                np.array([179, high_s, high_v], dtype=np.uint8),
            )
        )
        parts.append(
            cv2.inRange(
                hsv_img,
                np.array([0, low_s, low_v], dtype=np.uint8),
                np.array([high_h - 180, high_s, high_v], dtype=np.uint8),
            )
        )
    merged = parts[0]
    for part in parts[1:]:
        merged = cv2.bitwise_or(merged, part)
    return merged


def _select_best_quad(
    contour_sets,
    *,
    min_area: float,
    area_base: float,
    width: int,
    height: int,
    expected_ratio: float,
    strict: bool,
    preferred_color: str,
    roi_area: float | None,
) -> dict[str, object] | None:
    best: dict[str, object] | None = None
    rect_threshold = 0.60 if strict else 0.48

    for source_name, contours in contour_sets:
        contours_sorted = sorted(contours, key=_contour_area, reverse=True)[:40]
        for contour in contours_sorted:
            contour_area = _contour_area(contour)
            if contour_area < min_area:
                continue
            quad = _contour_to_quad(contour)
            if quad is None:
                continue
            quad_area = _quad_area(quad)
            if quad_area < min_area:
                continue

            touches = _touches_frame(quad, width, height)
            if strict and touches:
                continue
            if touches and quad_area >= area_base * 0.97:
                continue
            if roi_area and strict and quad_area >= roi_area * 0.995:
                continue

            rect_score = _rectangularity_score(quad)
            if rect_score < rect_threshold:
                continue
            aspect_score = _aspect_score(quad, expected_ratio)
            axis_score = _axis_alignment_score(quad)
            fill_score = min(1.0, max(0.0, contour_area / max(1.0, quad_area)))
            area_score = min(1.0, quad_area / max(min_area, area_base * 0.58))
            source_bonus = _source_bonus(source_name, preferred_color)

            score = (
                0.34 * rect_score
                + 0.22 * aspect_score
                + 0.16 * axis_score
                + 0.16 * fill_score
                + 0.12 * area_score
                + source_bonus
            )

            if best is None or score > float(best["score"]):
                best = {
                    "quad": quad,
                    "score": float(score),
                    "source": source_name,
                    "area": float(quad_area),
                }
    return best


def _fallback_largest_quad(contour_sets, *, min_area: float, area_base: float) -> dict[str, object] | None:
    best: dict[str, object] | None = None
    for source_name, contours in contour_sets:
        for contour in sorted(contours, key=_contour_area, reverse=True)[:60]:
            contour_area = _contour_area(contour)
            if contour_area < min_area:
                continue
            quad = _contour_to_quad(contour)
            if quad is None:
                continue
            quad_area = _quad_area(quad)
            if quad_area < min_area or quad_area >= area_base * 0.995:
                continue
            if best is None or quad_area > float(best["area"]):
                best = {
                    "quad": quad,
                    "score": 0.22,
                    "source": f"{source_name}:fallback",
                    "area": float(quad_area),
                }
    return best


def _contour_to_quad(contour) -> list[Point] | None:
    import cv2
    import numpy as np

    if contour is None or len(contour) < 4:
        return None

    peri = float(cv2.arcLength(contour, True))
    if peri <= 1e-6:
        return None

    for eps_ratio in (0.015, 0.02, 0.025, 0.03):
        approx = cv2.approxPolyDP(contour, eps_ratio * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return [(float(p[0][0]), float(p[0][1])) for p in approx]

    hull = cv2.convexHull(contour)
    hull_peri = float(cv2.arcLength(hull, True))
    if hull_peri > 1e-6:
        approx_hull = cv2.approxPolyDP(hull, 0.02 * hull_peri, True)
        if len(approx_hull) == 4 and cv2.isContourConvex(approx_hull):
            return [(float(p[0][0]), float(p[0][1])) for p in approx_hull]

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    if box is None or len(box) != 4:
        return None
    quad = [(float(p[0]), float(p[1])) for p in box]
    area = abs(float(cv2.contourArea(np.asarray(quad, dtype=np.float32))))
    if area <= 1.0:
        return None
    return quad


def _contour_area(contour) -> float:
    try:
        import cv2

        return float(cv2.contourArea(contour))
    except Exception:
        return 0.0


def _rectangularity_score(quad: list[Point]) -> float:
    import numpy as np

    if len(quad) != 4:
        return 0.0
    ordered = order_quad(quad)
    pts = np.asarray(ordered, dtype=np.float32)
    sides = []
    for idx in range(4):
        a = pts[idx]
        b = pts[(idx + 1) % 4]
        sides.append(float(np.linalg.norm(b - a)))
    if min(sides) <= 1e-6:
        return 0.0

    opp_ratio = (min(sides[0], sides[2]) / max(sides[0], sides[2])) * (
        min(sides[1], sides[3]) / max(sides[1], sides[3])
    )

    def _cos_angle(a, b, c):
        v1 = a - b
        v2 = c - b
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        if denom <= 1e-9:
            return 1.0
        return abs(float(np.dot(v1, v2) / denom))

    angle_dev = (
        _cos_angle(pts[3], pts[0], pts[1])
        + _cos_angle(pts[0], pts[1], pts[2])
        + _cos_angle(pts[1], pts[2], pts[3])
        + _cos_angle(pts[2], pts[3], pts[0])
    ) / 4.0
    angle_score = 1.0 - min(1.0, angle_dev)
    return 0.58 * opp_ratio + 0.42 * angle_score


def _paper_aspect_ratio(config: AppConfig) -> float:
    try:
        w = float(config.paper.width_mm)
        h = float(config.paper.height_mm)
        if w > 1e-6 and h > 1e-6:
            return w / h
    except Exception:
        pass
    return 210.0 / 297.0


def _aspect_score(quad: list[Point], expected_ratio: float) -> float:
    import numpy as np

    ordered = order_quad(quad)
    pts = np.asarray(ordered, dtype=np.float32)
    top = float(np.linalg.norm(pts[1] - pts[0]))
    bottom = float(np.linalg.norm(pts[2] - pts[3]))
    left = float(np.linalg.norm(pts[3] - pts[0]))
    right = float(np.linalg.norm(pts[2] - pts[1]))
    width = max(1e-6, (top + bottom) * 0.5)
    height = max(1e-6, (left + right) * 0.5)
    observed = width / height

    r1 = max(1e-6, expected_ratio)
    r2 = max(1e-6, 1.0 / expected_ratio)
    err = min(abs(math.log(observed / r1)), abs(math.log(observed / r2)))
    return max(0.0, 1.0 - err / 0.65)


def _axis_alignment_score(quad: list[Point]) -> float:
    ordered = order_quad(quad)
    (tl, tr, br, bl) = ordered

    def _angle(a: Point, b: Point) -> float:
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def _horizontal_dev(theta: float) -> float:
        t = abs(theta) % math.pi
        return min(t, abs(math.pi - t))

    def _vertical_dev(theta: float) -> float:
        t = abs(theta) % math.pi
        return abs(t - math.pi * 0.5)

    dev = (
        _horizontal_dev(_angle(tl, tr))
        + _horizontal_dev(_angle(bl, br))
        + _vertical_dev(_angle(tl, bl))
        + _vertical_dev(_angle(tr, br))
    ) / 4.0
    return max(0.0, 1.0 - dev / (math.pi / 6.0))


def _source_bonus(source_name: str, hint: str) -> float:
    if hint == "white" and source_name == "color:white":
        return 0.12
    if hint == "custom" and source_name == "color:custom":
        return 0.16
    if hint == "blue" and source_name == "color:blue":
        return 0.12
    if source_name.startswith("color:"):
        return 0.03
    return 0.0


def _quad_area(quad: list[Point]) -> float:
    if len(quad) != 4:
        return 0.0
    area = 0.0
    for idx in range(4):
        x1, y1 = quad[idx]
        x2, y2 = quad[(idx + 1) % 4]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _touches_frame(quad: list[Point], width: int, height: int) -> bool:
    if len(quad) != 4:
        return True
    margin = max(8.0, float(min(width, height)) * 0.012)
    left = margin
    top = margin
    right = float(width - 1) - margin
    bottom = float(height - 1) - margin
    hits = 0
    for x, y in quad:
        if x <= left or x >= right or y <= top or y >= bottom:
            hits += 1
    return hits >= 2


def _render_debug_image_data(
    image,
    *,
    quad: list[Point] | None,
    center: Point | None,
    message: str,
    roi_polygon: list[Point] | None = None,
) -> str | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    dbg = image.copy()
    if roi_polygon and len(roi_polygon) >= 3:
        pts = np.asarray(
            [[int(round(p[0])), int(round(p[1]))] for p in roi_polygon],
            dtype=np.int32,
        ).reshape((-1, 1, 2))
        cv2.polylines(dbg, [pts], True, (40, 130, 235), 2, cv2.LINE_AA)

    if quad and len(quad) == 4:
        pts = np.asarray(
            [[int(round(p[0])), int(round(p[1]))] for p in quad],
            dtype=np.int32,
        ).reshape((-1, 1, 2))
        cv2.polylines(dbg, [pts], True, (0, 0, 255), 3, cv2.LINE_AA)
        for x, y in quad:
            cv2.circle(dbg, (int(round(x)), int(round(y))), 6, (0, 0, 255), 2, cv2.LINE_AA)
    if center:
        cx, cy = int(round(center[0])), int(round(center[1]))
        cv2.drawMarker(dbg, (cx, cy), (0, 180, 255), cv2.MARKER_CROSS, 24, 2, cv2.LINE_AA)

    text = str(message or "")
    if len(text) > 120:
        text = text[:117] + "..."
    cv2.putText(dbg, text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(dbg, text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)

    max_side = max(dbg.shape[0], dbg.shape[1])
    if max_side > 1280:
        scale = 1280.0 / float(max_side)
        dbg = cv2.resize(dbg, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ok, buffer = cv2.imencode(".jpg", dbg, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")
