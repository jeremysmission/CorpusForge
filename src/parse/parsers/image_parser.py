"""
Image parser -- pulls text out of images using OCR.

Plain English: a lot of operational documents arrive as image files
(photos of whiteboards, scanned memos, screenshots, phone captures).
This parser runs Optical Character Recognition (OCR) on each image
using Tesseract and returns whatever readable text it finds.

Supported formats: .jpg, .jpeg, .png, .gif, .bmp, .tiff, .tif.

Image preprocessing happens before OCR so accuracy is better: convert
to grayscale, auto-contrast, sharpen, and threshold to black-and-white.
Threshold is tunable via HYBRIDRAG_OCR_BIN_THRESHOLD.

If Docling is set to "prefer", it runs first. If the required OCR
libraries (Pillow, pytesseract) or the Tesseract binary itself are
missing, the parser falls back to returning just the image's metadata
(dimensions, color mode, file size) so the file still appears in the
corpus rather than vanishing.

Ported from V1 (src/parsers/image_parser.py).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from src.parse.parsers.docling_bridge import extract_with_docling, get_docling_mode
from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)
_WARNED_RUNTIME_ISSUES: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED_RUNTIME_ISSUES:
        return
    logger.warning(message)
    _WARNED_RUNTIME_ISSUES.add(key)


def _resolve_tesseract_cmd() -> tuple[str | None, str]:
    env_path = os.getenv("TESSERACT_CMD", "").strip()
    if env_path and Path(env_path).exists():
        return env_path, "env:TESSERACT_CMD"

    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        return found, "PATH"

    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).exists():
            return candidate, "fallback path"
    return None, "missing"


class ImageParser:
    """Run OCR on image files, falling back to metadata when OCR is unavailable."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open an image and return OCR text, or image metadata if OCR isn't available."""
        path = Path(file_path)
        text = ""
        quality = 0.0
        docling_mode = get_docling_mode()

        if docling_mode == "prefer":
            text = extract_with_docling(path)
            if text:
                quality = self._score_quality(text)
                return ParsedDocument(
                    source_path=str(path),
                    text=text,
                    parse_quality=quality,
                    file_ext=path.suffix.lower(),
                    file_size=path.stat().st_size if path.exists() else 0,
                )

        # Check dependencies
        try:
            from PIL import Image  # noqa: F811
        except ImportError:
            logger.debug("Pillow not installed -- image OCR unavailable")
            text = self._metadata_fallback(path)
            quality = 0.1 if text else 0.0
            return ParsedDocument(
                source_path=str(path), text=text, parse_quality=quality,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            import pytesseract  # noqa: F811
        except ImportError:
            logger.debug("pytesseract not installed -- image OCR unavailable")
            text = self._metadata_fallback(path)
            quality = 0.1 if text else 0.0
            return ParsedDocument(
                source_path=str(path), text=text, parse_quality=quality,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        tesseract_cmd, tesseract_source = _resolve_tesseract_cmd()
        if not tesseract_cmd:
            _warn_once(
                "image_tesseract_missing",
                "Image OCR unavailable: no usable Tesseract binary found. "
                "Install Tesseract, add it to PATH, or set TESSERACT_CMD.",
            )
            if docling_mode == "fallback":
                text = extract_with_docling(path)
            if text:
                quality = self._score_quality(text)
            else:
                text = self._metadata_fallback(path)
                quality = 0.1 if text else 0.0
            return ParsedDocument(
                source_path=str(path),
                text=text,
                parse_quality=quality,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        if tesseract_source == "fallback path":
            _warn_once(
                "image_tesseract_fallback",
                f"Image OCR using fallback Tesseract path: {tesseract_cmd}",
            )

        try:
            img = Image.open(path)
            img = self._preprocess(img)
            text = pytesseract.image_to_string(
                img, config="--oem 1 --psm 3"
            )
            text = (text or "").strip()

            if text:
                quality = self._score_quality(text)
            else:
                if docling_mode == "fallback":
                    text = extract_with_docling(path)
                if text:
                    quality = self._score_quality(text)
                else:
                    text = self._metadata_fallback(path)
                    quality = 0.1 if text else 0.0

        except Exception as e:
            logger.error("Image OCR failed for %s: %s", path.name, e)
            if docling_mode in {"fallback", "prefer"}:
                text = extract_with_docling(path)
            if text:
                quality = self._score_quality(text)
            else:
                text = self._metadata_fallback(path)
                quality = 0.1 if text else 0.0

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _preprocess(pil_image):
        """Clean up image for better OCR: grayscale, contrast, sharpen."""
        try:
            from PIL import ImageFilter, ImageOps
            img = pil_image.convert("L")
            img = ImageOps.autocontrast(img, cutoff=1)
            img = img.filter(ImageFilter.SHARPEN)
            threshold = int(os.getenv("HYBRIDRAG_OCR_BIN_THRESHOLD", "130"))
            img = img.point(lambda px: 255 if px > threshold else 0, mode="1")
            return img
        except Exception:
            return pil_image

    @staticmethod
    def _metadata_fallback(path: Path) -> str:
        """Return basic image metadata when OCR is unavailable."""
        lines = [f"[IMAGE_METADATA] file={path.name} ext={path.suffix.lower()}"]
        try:
            st = path.stat()
            lines.append(f"size_bytes={st.st_size}")
        except Exception:
            pass

        try:
            from PIL import Image
            img = Image.open(path)
            lines.append(f"format={getattr(img, 'format', 'unknown')}")
            lines.append(f"mode={getattr(img, 'mode', 'unknown')}")
            if hasattr(img, "size") and img.size:
                lines.append(f"width={img.size[0]}")
                lines.append(f"height={img.size[1]}")
        except Exception:
            pass

        return "\n".join(lines)

    @staticmethod
    def _score_quality(text: str) -> float:
        if not text.strip():
            return 0.0
        if len(text.strip()) < 30:
            return 0.3
        # Check for OCR garbage
        alpha_ratio = sum(1 for c in text[:2000] if c.isalpha()) / max(len(text[:2000]), 1)
        if alpha_ratio < 0.3:
            return 0.4
        return 0.8
