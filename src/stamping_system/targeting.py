from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calibration import (
    commanded_to_real,
    pixel_to_relative_on_quad,
    pixel_to_commanded_in_stamp_region,
    pixel_to_real,
    real_to_commanded,
    real_to_paper,
    relative_paper_to_real,
    relative_to_pixel_on_quad,
    stamp_region_mapping_available,
)
from .config import AppConfig
from .ocr import find_keyword_pixel


TargetSource = Literal["pixel", "pixel_on_paper", "relative_paper", "paper_preset", "keyword", "real"]


PRESETS: dict[str, tuple[float, float]] = {
    "center": (0.5, 0.5),
    "bottom_right_stamp": (0.78, 0.84),
    "bottom_center_stamp": (0.5, 0.84),
    "top_right_stamp": (0.78, 0.18),
    "signature_area": (0.62, 0.78),
}


@dataclass(frozen=True)
class TargetInput:
    source: TargetSource
    x: float | None = None
    y: float | None = None
    preset: str | None = None
    keyword: str | None = None
    offset_mm: tuple[float, float] = (0.0, 0.0)
    paper_quad: list[tuple[float, float]] | None = None


@dataclass(frozen=True)
class TargetResult:
    source: str
    input_point: tuple[float, float] | None
    pixel_xy: tuple[float, float] | None
    paper_xy_mm: tuple[float, float] | None
    relative_xy: tuple[float, float] | None
    real_xy_mm: tuple[float, float]
    commanded_xy_mm: tuple[float, float]
    note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_target(target: TargetInput, config: AppConfig) -> TargetResult:
    if target.source == "pixel":
        if target.x is None or target.y is None:
            raise ValueError("pixel target requires x and y")
        pixel = (target.x, target.y)
        if stamp_region_mapping_available(config):
            commanded = pixel_to_commanded_in_stamp_region(pixel, config)
            real = commanded_to_real(commanded, config)
            paper = real_to_paper(real, config)
            return TargetResult(
                source="pixel",
                input_point=pixel,
                pixel_xy=pixel,
                paper_xy_mm=paper,
                relative_xy=(paper[0] / config.paper.width_mm, paper[1] / config.paper.height_mm),
                real_xy_mm=real,
                commanded_xy_mm=commanded,
                note="Resolved from stamp/detect region hand-eye mapping.",
            )
        real = pixel_to_real(pixel, config)
        paper = real_to_paper(real, config)
        commanded = real_to_commanded(real, config)
        return TargetResult(
            source="pixel",
            input_point=pixel,
            pixel_xy=pixel,
            paper_xy_mm=paper,
            relative_xy=(paper[0] / config.paper.width_mm, paper[1] / config.paper.height_mm),
            real_xy_mm=real,
            commanded_xy_mm=commanded,
            note="Resolved from image pixel.",
        )

    if target.source == "pixel_on_paper":
        if target.x is None or target.y is None:
            raise ValueError("pixel_on_paper target requires x and y")
        if not target.paper_quad:
            raise ValueError("pixel_on_paper target requires a detected paper quad")
        pixel = (target.x, target.y)
        rx, ry = pixel_to_relative_on_quad(pixel, target.paper_quad)
        return _resolve_relative(rx, ry, target, config, "Resolved from clicked pixel on detected paper.")

    if target.source == "relative_paper":
        if target.x is None or target.y is None:
            raise ValueError("relative_paper target requires x and y")
        return _resolve_relative(target.x, target.y, target, config, "Resolved from relative paper coordinate.")

    if target.source == "real":
        if target.x is None or target.y is None:
            raise ValueError("real target requires x and y")
        real = (target.x + target.offset_mm[0], target.y + target.offset_mm[1])
        paper = real_to_paper(real, config)
        commanded = real_to_commanded(real, config)
        return TargetResult(
            source="real",
            input_point=(target.x, target.y),
            pixel_xy=None,
            paper_xy_mm=paper,
            relative_xy=(paper[0] / config.paper.width_mm, paper[1] / config.paper.height_mm),
            real_xy_mm=real,
            commanded_xy_mm=commanded,
            note="Resolved from current machine work position.",
        )

    if target.source == "paper_preset":
        if not target.preset:
            raise ValueError("paper_preset target requires preset")
        if target.preset not in PRESETS:
            raise ValueError(f"Unknown preset: {target.preset}")
        rx, ry = PRESETS[target.preset]
        return _resolve_relative(rx, ry, target, config, f"Resolved from preset: {target.preset}.")

    if target.source == "keyword":
        if not target.keyword:
            raise ValueError("keyword target requires keyword")
        pixel = find_keyword_pixel(target.keyword, config.camera.snapshot_path, config)
        real = pixel_to_real(pixel, config)
        real = (real[0] + target.offset_mm[0], real[1] + target.offset_mm[1])
        paper = real_to_paper(real, config)
        commanded = real_to_commanded(real, config)
        return TargetResult(
            source="keyword",
            input_point=None,
            pixel_xy=pixel,
            paper_xy_mm=paper,
            relative_xy=(paper[0] / config.paper.width_mm, paper[1] / config.paper.height_mm),
            real_xy_mm=real,
            commanded_xy_mm=commanded,
            note="Resolved from OCR keyword.",
        )

    raise ValueError(f"Unsupported target source: {target.source}")


def _resolve_relative(
    rx: float,
    ry: float,
    target: TargetInput,
    config: AppConfig,
    note: str,
) -> TargetResult:
    pixel = None
    if config.paper.use_detected_quad_for_relative_targets and target.paper_quad:
        pixel = relative_to_pixel_on_quad(rx, ry, target.paper_quad)
        real = pixel_to_real(pixel, config)
        note += " Detected paper quad was used."
    else:
        real = relative_paper_to_real(rx, ry, config)
        note += " Static paper origin was used."

    real = (real[0] + target.offset_mm[0], real[1] + target.offset_mm[1])
    paper = (rx * config.paper.width_mm, ry * config.paper.height_mm)
    commanded = real_to_commanded(real, config)
    return TargetResult(
        source=target.source,
        input_point=(rx, ry),
        pixel_xy=pixel,
        paper_xy_mm=paper,
        relative_xy=(rx, ry),
        real_xy_mm=real,
        commanded_xy_mm=commanded,
        note=note,
    )
