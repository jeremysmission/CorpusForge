"""
Optional Docling bridge for higher-fidelity document conversion.

Docling is deliberately not a hard dependency. This module must degrade
cleanly when the package is absent, misconfigured, or disabled.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ALLOWED_MODES = {"off", "fallback", "prefer"}
_DOC_EXTS = {
    ".pdf",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
}
_CONVERTER = None
_IMPORT_ATTEMPTED = False


def get_docling_mode() -> str:
    """Return the configured Docling mode."""
    mode = os.getenv("HYBRIDRAG_DOCLING_MODE", "off").strip().lower()
    if mode not in _ALLOWED_MODES:
        return "off"
    return mode


def should_try_docling(path: Path) -> bool:
    """Whether this file should attempt Docling conversion."""
    return get_docling_mode() != "off" and path.suffix.lower() in _DOC_EXTS


def extract_with_docling(path: Path) -> str:
    """
    Convert a document with Docling and return text/markdown.

    Returns an empty string when Docling is disabled, unavailable, or the
    conversion result contains no useful serialized text.
    """
    if not should_try_docling(path):
        return ""

    converter = _get_converter()
    if converter is None:
        return ""

    try:
        result = converter.convert(str(path))
        document = getattr(result, "document", None)
        if document is None:
            return ""

        for attr in ("export_to_markdown", "export_to_text", "export_to_html"):
            exporter = getattr(document, attr, None)
            if callable(exporter):
                text = exporter() or ""
                if text.strip():
                    return text.strip()

        text = str(document or "").strip()
        return text
    except Exception as exc:
        logger.debug("Docling conversion failed for %s: %s", path.name, exc)
        return ""


def _get_converter():
    """Lazy-load and cache the Docling converter."""
    global _CONVERTER, _IMPORT_ATTEMPTED

    if _CONVERTER is not None:
        return _CONVERTER
    if _IMPORT_ATTEMPTED:
        return None

    _IMPORT_ATTEMPTED = True
    try:
        from docling.document_converter import DocumentConverter

        _CONVERTER = DocumentConverter()
        logger.info("Docling converter available for optional parser fallback.")
        return _CONVERTER
    except ImportError:
        logger.info("Docling not installed; continuing with built-in parsers only.")
        return None
    except Exception as exc:
        logger.warning("Docling import failed; built-in parsers remain active: %s", exc)
        return None
