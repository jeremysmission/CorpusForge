"""
Parse dispatcher — routes files to the appropriate parser by extension.

Ported from V1 (src/parsers/registry.py + src/core/parse_dispatch.py).
Each parser returns a ParsedDocument. Unsupported formats are skipped.
Error isolation: single file failure never crashes the pipeline.

Format decisions: All placeholder and deferred formats are loaded from
the active runtime config (`config/config.yaml`) — zero hardcoded format
skips in this file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import TxtParser, ParsedDocument

logger = logging.getLogger(__name__)

# Lazy-import parsers to avoid loading heavy deps at module level
_PARSER_MAP: dict | None = None


def _build_parser_map(
    skip_list_path: str = "config/config.yaml",
    extra_deferred_exts: set[str] | None = None,
) -> dict:
    """Build extension → parser instance map. Called once on first use.

    Placeholder formats are loaded from the active runtime config — not
    hardcoded. To change which formats get placeholder treatment, edit
    `config/config.yaml`.

    ``extra_deferred_exts`` are merged with the ``deferred_formats`` list
    from the skip list and applied to the archive parser, so deferred
    extensions inside ZIP/TAR archives are skipped at extract time.
    """
    from src.parse.parsers.txt_parser import TxtParser
    from src.parse.parsers.pdf_parser import PdfParser
    from src.parse.parsers.docx_parser import DocxParser
    from src.parse.parsers.xlsx_parser import XlsxParser
    from src.parse.parsers.pptx_parser import PptxParser
    from src.parse.parsers.csv_parser import CsvParser
    from src.parse.parsers.msg_parser import MsgParser
    from src.parse.parsers.html_parser import HtmlParser
    from src.parse.parsers.rtf_parser import RtfParser
    from src.parse.parsers.json_parser import JsonParser
    from src.parse.parsers.xml_parser import XmlParser
    from src.parse.parsers.eml_parser import EmlParser
    from src.parse.parsers.mbox_parser import MboxParser
    from src.parse.parsers.xls_parser import XlsParser
    from src.parse.parsers.doc_parser import DocParser
    from src.parse.parsers.ppt_parser import PptParser
    from src.parse.parsers.archive_parser import ArchiveParser
    from src.parse.parsers.image_parser import ImageParser
    from src.parse.parsers.epub_parser import EpubParser
    from src.parse.parsers.opendocument_parser import OpenDocumentParser
    from src.parse.parsers.visio_parser import VisioParser
    from src.parse.parsers.certificate_parser import CertificateParser
    from src.parse.parsers.dxf_parser import DxfParser
    from src.parse.parsers.stl_parser import StlParser
    from src.parse.parsers.evtx_parser import EvtxParser
    from src.parse.parsers.pcap_parser import PcapParser
    from src.parse.parsers.access_db_parser import AccessDbParser
    from src.parse.parsers.psd_parser import PsdParser
    from src.parse.parsers.step_iges_parser import StepParser, IgesParser
    from src.parse.parsers.placeholder_parser import PlaceholderParser
    from src.skip.skip_manager import (
        load_placeholder_format_map,
        load_deferred_extension_map,
    )

    # Combine YAML-driven deferred_formats with any extras from config
    # (e.g., parse.defer_extensions). Both apply to archive members.
    archive_deferred: set[str] = set(
        load_deferred_extension_map(skip_list_path).keys()
    )
    for ext in extra_deferred_exts or ():
        ext = ext.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        archive_deferred.add(ext)

    txt = TxtParser()
    pdf = PdfParser()
    docx = DocxParser()
    xlsx = XlsxParser()
    pptx = PptxParser()
    csv_ = CsvParser()
    msg = MsgParser()
    html = HtmlParser()
    rtf = RtfParser()
    json_ = JsonParser()
    xml_ = XmlParser()
    eml = EmlParser()
    mbox = MboxParser()
    xls = XlsParser()
    doc = DocParser()
    ppt = PptParser()
    archive = ArchiveParser(deferred_exts=archive_deferred)
    image = ImageParser()
    epub = EpubParser()
    odt = OpenDocumentParser()
    visio = VisioParser()
    cert = CertificateParser()
    dxf = DxfParser()
    stl = StlParser()
    evtx = EvtxParser()
    pcap = PcapParser()
    access = AccessDbParser()
    psd = PsdParser()
    step = StepParser()
    iges = IgesParser()

    parser_map = {
        # Plain text
        ".txt": txt, ".md": txt, ".rst": txt, ".log": txt,
        ".ini": txt, ".cfg": txt, ".conf": txt,
        ".yaml": txt, ".yml": txt, ".properties": txt,
        ".reg": txt, ".sao": txt, ".rsf": txt,
        # Structured text
        ".csv": csv_, ".tsv": csv_,
        ".json": json_,
        ".xml": xml_,
        # Documents
        ".pdf": pdf, ".ai": pdf,
        ".docx": docx,
        ".doc": doc,
        ".xlsx": xlsx,
        ".xls": xls,
        ".pptx": pptx,
        ".ppt": ppt,
        ".rtf": rtf,
        # Email
        ".msg": msg,
        ".eml": eml,
        ".mbox": mbox,
        # Web
        ".html": html, ".htm": html,
        # Archives
        ".zip": archive, ".tar": archive, ".tgz": archive, ".gz": archive, ".7z": archive,
        # Images (OCR)
        ".jpg": image, ".jpeg": image,
        ".png": image, ".gif": image, ".webp": image,
        ".bmp": image, ".wmf": image, ".emf": image,
        ".tiff": image, ".tif": image,
        # eBooks
        ".epub": epub,
        # OpenDocument
        ".odt": odt, ".ods": odt, ".odp": odt,
        # Diagrams
        ".vsdx": visio, ".drawio": txt, ".svg": txt, ".dia": txt,
        # Certificates
        ".cer": cert, ".pem": cert, ".crt": cert,
        # CAD / 3D
        ".dxf": dxf,
        ".stp": step, ".step": step, ".ste": step,
        ".igs": iges, ".iges": iges,
        ".stl": stl,
        # Databases / layered images
        ".accdb": access, ".mdb": access,
        ".psd": psd,
        # Forensics / Security
        ".evtx": evtx,
        ".pcap": pcap, ".pcapng": pcap,
    }

    # Load placeholder formats from config — zero hardcoded format decisions
    placeholder_map = load_placeholder_format_map(skip_list_path)
    for ext in placeholder_map:
        if ext not in parser_map:
            parser_map[ext] = PlaceholderParser(ext)
    if placeholder_map:
        logger.info("Loaded %d placeholder formats from config: %s",
                     len(placeholder_map), ", ".join(sorted(placeholder_map)))

    return parser_map


def get_supported_extensions(skip_list_path: str = "config/config.yaml") -> set[str]:
    """Return all supported file extensions."""
    global _PARSER_MAP
    if _PARSER_MAP is None:
        _PARSER_MAP = _build_parser_map(skip_list_path)
    return set(_PARSER_MAP.keys())


def reset_parser_map() -> None:
    """Drop the cached parser map. Used by tests that change defer policy."""
    global _PARSER_MAP
    _PARSER_MAP = None


class ParseDispatcher:
    """Routes files to the appropriate parser based on extension."""

    def __init__(self, timeout_seconds: int = 60, max_chars: int = 5_000_000,
                 skip_list_path: str = "config/config.yaml",
                 extra_deferred_exts: set[str] | None = None):
        self.timeout = timeout_seconds
        self.max_chars = max_chars
        self._skip_list_path = skip_list_path
        self._extra_deferred_exts = set(extra_deferred_exts or ())

    def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a file using the registered parser for its extension.

        Returns ParsedDocument. Never raises — returns empty doc on failure.
        """
        global _PARSER_MAP
        if _PARSER_MAP is None:
            _PARSER_MAP = _build_parser_map(
                self._skip_list_path, self._extra_deferred_exts
            )

        ext = file_path.suffix.lower()
        parser = _PARSER_MAP.get(ext)

        if parser is None:
            logger.debug("Unsupported extension: %s (%s)", ext, file_path.name)
            return ParsedDocument(
                source_path=str(file_path),
                text="",
                parse_quality=0.0,
                file_ext=ext,
                file_size=file_path.stat().st_size if file_path.exists() else 0,
            )

        try:
            doc = parser.parse(file_path)
            # Clamp text length
            if len(doc.text) > self.max_chars:
                doc.text = doc.text[:self.max_chars]
            return doc
        except Exception as e:
            logger.error("Parse failed for %s: %s", file_path, e)
            return ParsedDocument(
                source_path=str(file_path),
                text="",
                parse_quality=0.0,
                file_ext=ext,
                file_size=file_path.stat().st_size if file_path.exists() else 0,
            )
