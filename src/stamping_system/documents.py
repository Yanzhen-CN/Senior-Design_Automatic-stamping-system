from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import runtime_path


@dataclass(frozen=True)
class DocumentPreview:
    filename: str
    original_path: str
    preview_path: str
    preview_url: str
    width_px: int
    height_px: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def save_document_upload(filename: str, data: bytes) -> Path:
    safe_name = Path(filename).name or "uploaded_document"
    upload_dir = runtime_path("runtime/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / safe_name
    target.write_bytes(data)
    return target


def render_document_preview(path: Path) -> DocumentPreview:
    suffix = path.suffix.lower()
    preview_path = runtime_path("runtime/document_preview.jpg")
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    if suffix in {".jpg", ".jpeg", ".png", ".bmp"}:
        width, height = _render_image_preview(path, preview_path)
    elif suffix == ".pdf":
        width, height = _render_pdf_preview(path, preview_path)
    else:
        raise ValueError("Unsupported document type. Please upload a PDF or image file.")

    return DocumentPreview(
        filename=path.name,
        original_path=str(path),
        preview_path=str(preview_path),
        preview_url="/api/document/preview",
        width_px=width,
        height_px=height,
    )


def document_preview_path() -> Path:
    return runtime_path("runtime/document_preview.jpg")


def _render_image_preview(source: Path, target: Path) -> tuple[int, int]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is required for image preview") from exc

    image = cv2.imread(str(source))
    if image is None:
        raise RuntimeError(f"Cannot read image file: {source}")
    height, width = image.shape[:2]
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        shutil.copyfile(source, target)
    else:
        cv2.imwrite(str(target), image)
    return width, height


def _render_pdf_preview(source: Path, target: Path) -> tuple[int, int]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF preview") from exc

    document = fitz.open(str(source))
    if document.page_count == 0:
        raise RuntimeError("PDF has no pages")
    try:
        page = document.load_page(0)
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(str(target))
        return pixmap.width, pixmap.height
    finally:
        document.close()
