"""
PDF parser — multi-stage extraction with OCR fallback.

Pipeline: pypdf (fast) → pdfplumber (layout-aware) → Tesseract OCR (scanned).
Ported from V1 (src/parsers/pdf_parser.py + pdf_ocr_fallback.py).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

# OCR config from environment
_OCR_MODE = os.getenv("HYBRIDRAG_OCR_MODE", "auto")  # auto | skip
_OCR_TRIGGER_MIN_CHARS = int(os.getenv("HYBRIDRAG_OCR_TRIGGER_MIN_CHARS", "20"))
_OCR_MAX_PAGES = int(os.getenv("HYBRIDRAG_OCR_MAX_PAGES", "200"))
_OCR_DPI = int(os.getenv("HYBRIDRAG_OCR_DPI", "200"))
_OCR_TIMEOUT_S = int(os.getenv("HYBRIDRAG_OCR_TIMEOUT_S", "20"))
_OCR_LANG = os.getenv("HYBRIDRAG_OCR_LANG", "eng")


class PdfParser:
    """Parse PDF files with multi-stage extraction."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        # Stage 1: Try pypdf (fastest)
        text = self._try_pypdf(path)

        # Stage 2: Try pdfplumber if pypdf got nothing
        if len(text.strip()) < _OCR_TRIGGER_MIN_CHARS:
            plumber_text = self._try_pdfplumber(path)
            if len(plumber_text) > len(text):
                text = plumber_text

        # Stage 3: OCR fallback for scanned PDFs
        if len(text.strip()) < _OCR_TRIGGER_MIN_CHARS and _OCR_MODE != "skip":
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
            for page in reader.pages[:_OCR_MAX_PAGES]:
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
                for page in pdf.pages[:_OCR_MAX_PAGES]:
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

            poppler_bin = os.getenv("HYBRIDRAG_POPPLER_BIN", "")
            kwargs = {"dpi": _OCR_DPI}
            if poppler_bin:
                kwargs["poppler_path"] = poppler_bin

            images = convert_from_path(str(path), **kwargs)
            pages = []
            for i, img in enumerate(images[:_OCR_MAX_PAGES]):
                try:
                    text = pytesseract.image_to_string(
                        img, lang=_OCR_LANG,
                        config="--oem 1 --psm 3",
                        timeout=_OCR_TIMEOUT_S,
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
