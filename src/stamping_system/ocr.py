from __future__ import annotations

from pathlib import Path

from .config import AppConfig


def find_keyword_pixel(keyword: str, image_path: Path, config: AppConfig) -> tuple[float, float]:
    if not config.vision.ocr_enabled:
        raise ValueError("OCR is disabled in config. Enable vision.ocr_enabled first.")
    if not keyword.strip():
        raise ValueError("Keyword cannot be empty")
    if config.vision.ocr_engine != "pytesseract":
        raise ValueError(f"Unsupported OCR engine: {config.vision.ocr_engine}")
    if not image_path.exists():
        raise ValueError(f"Snapshot does not exist: {image_path}")

    try:
        import cv2
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("pytesseract and opencv-python are required for keyword OCR") from exc

    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    data = pytesseract.image_to_data(
        image,
        lang=config.vision.ocr_language,
        output_type=Output.DICT,
    )
    needle = keyword.casefold()
    best_index = None
    best_confidence = -1.0
    for index, text in enumerate(data.get("text", [])):
        if needle not in str(text).casefold():
            continue
        try:
            confidence = float(data["conf"][index])
        except (ValueError, TypeError):
            confidence = 0.0
        if confidence > best_confidence:
            best_confidence = confidence
            best_index = index

    if best_index is None:
        raise ValueError(f"Keyword was not found by OCR: {keyword}")

    left = float(data["left"][best_index])
    top = float(data["top"][best_index])
    width = float(data["width"][best_index])
    height = float(data["height"][best_index])
    return (left + width / 2.0, top + height / 2.0)

