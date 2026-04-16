"""
PDF parser — multi-stage extraction with OCR fallback.

Pipeline: pypdf (fast) → pdfplumber (layout-aware) → Tesseract OCR (scanned).
Ported from V1 (src/parsers/pdf_parser.py + pdf_ocr_fallback.py).
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


def _resolve_poppler_bin() -> tuple[str | None, str]:
    env_dir = os.getenv("HYBRIDRAG_POPPLER_BIN", "").strip()
    if env_dir:
        candidate = Path(env_dir) / "pdftoppm.exe"
        if candidate.exists():
            return str(candidate.parent), "env:HYBRIDRAG_POPPLER_BIN"

    found = shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")
    if found:
        return str(Path(found).parent), "PATH"

    for candidate in (
        r"C:\tools\poppler\Library\bin\pdftoppm.exe",
        r"C:\Program Files\poppler\Library\bin\pdftoppm.exe",
        r"C:\Program Files\poppler\bin\pdftoppm.exe",
        r"C:\poppler\Library\bin\pdftoppm.exe",
        r"C:\poppler\bin\pdftoppm.exe",
    ):
        if Path(candidate).exists():
            return str(Path(candidate).parent), "fallback path"
    return None, "missing"

def _ocr_mode() -> str:
    return os.getenv("HYBRIDRAG_OCR_MODE", "auto")


def _ocr_trigger_min_chars() -> int:
    return int(os.getenv("HYBRIDRAG_OCR_TRIGGER_MIN_CHARS", "20"))


def _ocr_max_pages() -> int:
    return int(os.getenv("HYBRIDRAG_OCR_MAX_PAGES", "200"))


def _ocr_dpi() -> int:
    return int(os.getenv("HYBRIDRAG_OCR_DPI", "200"))


def _ocr_timeout_s() -> int:
    return int(os.getenv("HYBRIDRAG_OCR_TIMEOUT_S", "20"))


def _ocr_lang() -> str:
    return os.getenv("HYBRIDRAG_OCR_LANG", "eng")


class PdfParser:
    """Parse PDF files with multi-stage extraction."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0
        trigger_min_chars = _ocr_trigger_min_chars()
        docling_mode = get_docling_mode()

        if docling_mode == "prefer":
            text = extract_with_docling(path)

        # Stage 1: Try pypdf (fastest)
        if len(text.strip()) < trigger_min_chars:
            pypdf_text = self._try_pypdf(path)
            if len(pypdf_text) > len(text):
                text = pypdf_text

        # Stage 2: Try pdfplumber if pypdf got nothing
        if len(text.strip()) < trigger_min_chars:
            plumber_text = self._try_pdfplumber(path)
            if len(plumber_text) > len(text):
                text = plumber_text

        if len(text.strip()) < trigger_min_chars and docling_mode in {"fallback", "prefer"}:
            docling_text = extract_with_docling(path)
            if len(docling_text) > len(text):
                text = docling_text

        # Stage 3: OCR fallback for scanned PDFs
        if len(text.strip()) < trigger_min_chars and _ocr_mode() != "skip":
            ocr_text = self._try_ocr(path)
            if len(ocr_text) > len(text):
                text = ocr_text

        quality = self._score_quality(text)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=".pdf",
            file_size=path.stat().st_size,
        )

    def _try_pypdf(self, path: Path) -> str:
        """Extract text using pypdf (fast, works on digital PDFs)."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages[:_ocr_max_pages()]:
                try:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append(text)
                except Exception:
                    continue
            return "\n\n".join(pages)
        except Exception as e:
            logger.debug("pypdf failed for %s: %s", path.name, e)
            return ""

    def _try_pdfplumber(self, path: Path) -> str:
        """Extract text using pdfplumber (layout-aware, handles tables better)."""
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages[:_ocr_max_pages()]:
                    try:
                        text = page.extract_text() or ""
                        if text.strip():
                            pages.append(text)
                    except Exception:
                        continue
            return "\n\n".join(pages)
        except Exception as e:
            logger.debug("pdfplumber failed for %s: %s", path.name, e)
            return ""

    def _try_ocr(self, path: Path) -> str:
        """OCR scanned PDF using Tesseract + pdf2image."""
        try:
            from pdf2image import convert_from_path
            import pytesseract

            tesseract_cmd, tesseract_source = _resolve_tesseract_cmd()
            if not tesseract_cmd:
                _warn_once(
                    "pdf_tesseract_missing",
                    "PDF OCR unavailable: no usable Tesseract binary found. "
                    "Install Tesseract, add it to PATH, or set TESSERACT_CMD.",
                )
                return ""
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            if tesseract_source == "fallback path":
                _warn_once(
                    "pdf_tesseract_fallback",
                    f"PDF OCR using fallback Tesseract path: {tesseract_cmd}",
                )

            poppler_bin, poppler_source = _resolve_poppler_bin()
            if not poppler_bin:
                _warn_once(
                    "pdf_poppler_missing",
                    "Scanned-PDF OCR unavailable: no usable pdftoppm.exe found. "
                    "Install Poppler, add it to PATH, or set HYBRIDRAG_POPPLER_BIN.",
                )
                return ""
            if poppler_source == "fallback path":
                _warn_once(
                    "pdf_poppler_fallback",
                    f"PDF OCR using fallback Poppler path: {poppler_bin}",
                )

            kwargs = {
                "dpi": _ocr_dpi(),
                "poppler_path": poppler_bin,
            }

            images = convert_from_path(str(path), **kwargs)
            pages = []
            for i, img in enumerate(images[:_ocr_max_pages()]):
                try:
                    text = pytesseract.image_to_string(
                        img, lang=_ocr_lang(),
                        config="--oem 1 --psm 3",
                        timeout=_ocr_timeout_s(),
                    )
                    if text.strip():
                        pages.append(f"[OCR_PAGE={i+1}]\n{text}")
                except Exception:
                    continue
            return "\n\n".join(pages)
        except ImportError:
            logger.debug("OCR deps not available for %s", path.name)
            return ""
        except Exception as e:
            logger.debug("OCR failed for %s: %s", path.name, e)
            return ""

    def _score_quality(self, text: str) -> float:
        if not text.strip():
            return 0.0
        if len(text.strip()) < 50:
            return 0.3
        # Check for OCR garbage (high ratio of non-alpha)
        alpha_ratio = sum(1 for c in text[:2000] if c.isalpha()) / max(len(text[:2000]), 1)
        if alpha_ratio < 0.3:
            return 0.4
        return 0.9
