"""
STEP and IGES parsers -- read open CAD exchange files.

Plain English: STEP (.stp / .step / .ste) and IGES (.igs / .iges) are
the vendor-neutral formats engineers use to share 3D models between
different CAD tools. The geometry itself is not useful searchable
text, but the file headers contain valuable metadata: product name,
author, organization, CAD system of origin, schema, and entity count.

Both parsers return that metadata as a human-readable block so an
engineer can find a specific part by its name, organization, or CAD
system even though the actual geometry stays as an opaque file
reference.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument


class StepParser:
    """Extract searchable header metadata from STEP (.stp/.step/.ste) CAD files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a STEP CAD file and return its header metadata as text."""
        path = Path(file_path)
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = [f"STEP CAD File: {path.name}"]

        match = re.search(r"FILE_DESCRIPTION\s*\(\s*\('([^']*)'\)", raw)
        if match:
            parts.append(f"Description: {match.group(1)}")

        match = re.search(r"FILE_NAME\s*\(\s*'([^']*)'", raw)
        if match:
            parts.append(f"Name: {match.group(1)}")

        file_name_block = re.search(r"FILE_NAME\s*\([^)]*\)", raw, re.DOTALL)
        if file_name_block:
            strings = re.findall(r"'([^']+)'", file_name_block.group(0))
            if len(strings) >= 5:
                parts.append(f"Author: {strings[2]}")
                parts.append(f"Organization: {strings[3]}")
                parts.append(f"CAD System: {strings[4]}")

        match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", raw)
        if match:
            parts.append(f"Schema: {match.group(1)}")

        entity_count = len(re.findall(r"^#\d+\s*=", raw, re.MULTILINE))
        parts.append(f"Entities: {entity_count:,}")

        products = re.findall(r"PRODUCT\s*\(\s*'([^']*)'[^)]*'([^']*)'", raw)
        for pid, pname in products[:10]:
            parts.append(f"Product: {pid} -- {pname}")

        text = "\n".join(parts).strip()
        quality = 0.8 if entity_count else 0.3 if text else 0.0
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )


class IgesParser:
    """Extract searchable header metadata from IGES (.igs/.iges) CAD files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open an IGES CAD file and return its header metadata as text."""
        path = Path(file_path)
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        parts: list[str] = [f"IGES CAD File: {path.name}"]
        lines = raw.split("\n")
        start_lines: list[str] = []
        global_text: list[str] = []
        d_count = 0

        for line in lines:
            if len(line) >= 73:
                flag = line[72]
                if flag == "S":
                    start_lines.append(line[:72].strip())
                elif flag == "G":
                    global_text.append(line[:72].strip())
                elif flag == "D":
                    d_count += 1

        if start_lines:
            parts.append(f"Comment: {' '.join(start_lines)}")

        global_str = "".join(global_text)
        if global_str:
            strings = re.findall(r"\d+H([^,;]+)", global_str)
            if len(strings) >= 4:
                parts.append(f"Filename: {strings[1]}")
                parts.append(f"System ID: {strings[2]}")
                parts.append(f"Preprocessor: {strings[3]}")
            if len(strings) >= 6:
                parts.append(f"Author: {strings[5]}")
                if len(strings) > 6:
                    parts.append(f"Organization: {strings[6]}")

        entity_count = d_count // 2
        parts.append(f"Entities: {entity_count:,}")

        text = "\n".join(part for part in parts if part).strip()
        quality = 0.8 if entity_count else 0.3 if text else 0.0
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )
