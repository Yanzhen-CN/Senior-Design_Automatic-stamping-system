from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .config import AppConfig, CalibrationPoint


Point = tuple[float, float]


@dataclass(frozen=True)
class Homography:
    values: tuple[float, float, float, float, float, float, float, float, float]

    def transform(self, point: Point) -> Point:
        u, v = point
        h = self.values
        denom = h[6] * u + h[7] * v + h[8]
        if abs(denom) < 1e-12:
            raise ValueError("Homography denominator is too close to zero")
        x = (h[0] * u + h[1] * v + h[2]) / denom
        y = (h[3] * u + h[4] * v + h[5]) / denom
        return (x, y)


def build_homography(points: Iterable[CalibrationPoint]) -> Homography:
    items = list(points)
    return fit_homography([item.pixel for item in items], [item.real_mm for item in items])


def fit_homography(source_points: list[Point], target_points: list[Point]) -> Homography:
    if len(source_points) != len(target_points):
        raise ValueError("source_points and target_points must have the same length")
    if len(source_points) < 4:
        raise ValueError("At least four points are required")

    try:
        return _fit_homography_numpy(source_points, target_points)
    except ImportError:
        if len(source_points) != 4:
            raise RuntimeError("numpy is required for more than four points") from None
        return _fit_homography_four_point(source_points, target_points)


def pixel_to_real(point: Point, config: AppConfig) -> Point:
    if config.calibration.mode != "homography":
        raise ValueError(f"Unsupported calibration mode: {config.calibration.mode}")
    return build_homography(config.calibration.points).transform(point)


def real_to_commanded(point: Point, config: AppConfig) -> Point:
    return (
        config.machine.axes["x"].real_to_commanded(point[0]),
        config.machine.axes["y"].real_to_commanded(point[1]),
    )


def commanded_to_real(point: Point, config: AppConfig) -> Point:
    x_axis = config.machine.axes["x"]
    y_axis = config.machine.axes["y"]
    return (
        x_axis.commanded_delta_to_real(point[0] - x_axis.offset_commanded_mm),
        y_axis.commanded_delta_to_real(point[1] - y_axis.offset_commanded_mm),
    )


def stamp_region_mapping_available(config: AppConfig) -> bool:
    pixels = config.raw.get("vision", {}).get("paper_roi_points")
    machine = config.raw.get("vision", {}).get("stamp_region_machine_points")
    return _valid_point_list(pixels) and _valid_point_list(machine)


def pixel_to_commanded_in_stamp_region(point: Point, config: AppConfig) -> Point:
    pixels = _point_list(config.raw.get("vision", {}).get("paper_roi_points"))
    machine = _point_list(config.raw.get("vision", {}).get("stamp_region_machine_points"))
    if len(pixels) < 4 or len(machine) < 4:
        raise ValueError("Stamp/detect region machine mapping is incomplete")
    return fit_homography(pixels[:4], machine[:4]).transform(point)


def z_real_to_commanded(z_mm: float, config: AppConfig) -> float:
    return config.machine.axes["z"].real_to_commanded(z_mm)


def relative_paper_to_real(rx: float, ry: float, config: AppConfig) -> Point:
    validate_relative(rx, ry)
    local_x = rx * config.paper.width_mm
    local_y = ry * config.paper.height_mm
    theta = math.radians(config.paper.rotation_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    origin_x, origin_y = config.paper.origin_real_mm
    return (
        origin_x + local_x * cos_t - local_y * sin_t,
        origin_y + local_x * sin_t + local_y * cos_t,
    )


def real_to_paper(real: Point, config: AppConfig) -> Point:
    origin_x, origin_y = config.paper.origin_real_mm
    dx = real[0] - origin_x
    dy = real[1] - origin_y
    theta = -math.radians(config.paper.rotation_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    return (dx * cos_t - dy * sin_t, dx * sin_t + dy * cos_t)


def relative_to_pixel_on_quad(rx: float, ry: float, quad: list[Point]) -> Point:
    validate_relative(rx, ry)
    if len(quad) != 4:
        raise ValueError("paper quad must contain four points")
    source = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    return fit_homography(source, quad).transform((rx, ry))


def pixel_to_relative_on_quad(pixel: Point, quad: list[Point]) -> Point:
    if len(quad) != 4:
        raise ValueError("paper quad must contain four points")
    target = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    relative = fit_homography(quad, target).transform(pixel)
    validate_relative(relative[0], relative[1])
    return relative


def validate_relative(rx: float, ry: float) -> None:
    if rx < 0 or rx > 1 or ry < 0 or ry > 1:
        raise ValueError("Relative paper coordinates must be in [0, 1]")


def _valid_point_list(value: object) -> bool:
    return len(_point_list(value)) >= 4


def _point_list(value: object) -> list[Point]:
    if not isinstance(value, list):
        return []
    points: list[Point] = []
    for item in value:
        try:
            if not isinstance(item, list | tuple) or len(item) < 2:
                return []
            points.append((float(item[0]), float(item[1])))
        except Exception:
            return []
    return points


def _fit_homography_numpy(source_points: list[Point], target_points: list[Point]) -> Homography:
    import numpy as np

    rows: list[list[float]] = []
    targets: list[float] = []
    for (u, v), (x, y) in zip(source_points, target_points, strict=True):
        rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        targets.append(x)
        rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        targets.append(y)
    solution, *_ = np.linalg.lstsq(
        np.asarray(rows, dtype=float), np.asarray(targets, dtype=float), rcond=None
    )
    return Homography(tuple(float(value) for value in solution) + (1.0,))  # type: ignore[arg-type]


def _fit_homography_four_point(source_points: list[Point], target_points: list[Point]) -> Homography:
    rows: list[list[float]] = []
    targets: list[float] = []
    for (u, v), (x, y) in zip(source_points, target_points, strict=True):
        rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        targets.append(x)
        rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        targets.append(y)
    return Homography(tuple(_solve_linear_system(rows, targets)) + (1.0,))  # type: ignore[arg-type]


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [row[:] + [rhs] for row, rhs in zip(matrix, vector, strict=True)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise ValueError("Calibration points produce a singular matrix")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for index in range(col, n + 1):
            augmented[col][index] /= pivot_value
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            for index in range(col, n + 1):
                augmented[row][index] -= factor * augmented[col][index]
    return [augmented[row][n] for row in range(n)]
