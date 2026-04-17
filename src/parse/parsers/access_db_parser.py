"""
Access database parser -- reads Microsoft Access databases
(.accdb / .mdb).

Plain English: instead of dumping a whole database (which could be
huge), this parser produces a searchable summary: every user table is
listed with its column names and up to 50 sample rows. Hidden system
tables (``MSys*``, ``~*``) are skipped. A reviewer can then recognize
the database by its schema and sample data without Forge needing to
index millions of rows.

Uses the ``access-parser`` library. If it isn't installed the parser
returns empty text rather than failing.
"""

from __future__ import annotations

from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument


class AccessDbParser:
    """Extract schema and sample rows from Microsoft Access .accdb/.mdb files."""

    MAX_ROWS_PER_TABLE = 50  # keeps output size reasonable for big databases

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open an Access database and return table columns + sample rows as text."""
        path = Path(file_path)
        parts: list[str] = [f"Access Database: {path.name}"]
        table_count = 0

        try:
            from access_parser import AccessParser
        except ImportError:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            db = AccessParser(str(path))
        except Exception:
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            for table_name in db.catalog:
                if table_name.startswith("MSys") or table_name.startswith("~"):
                    continue

                table_count += 1
                parts.append(f"\n--- Table: {table_name} ---")

                try:
                    table = db.parse_table(table_name)
                    columns = list(table.keys()) if isinstance(table, dict) else []
                    if columns:
                        parts.append(f"Columns: {', '.join(columns)}")
                        row_count = len(table[columns[0]]) if columns else 0
                        cap = min(row_count, self.MAX_ROWS_PER_TABLE)

                        for i in range(cap):
                            row_parts = []
                            for col in columns:
                                val = table[col][i] if i < len(table[col]) else ""
                                if isinstance(val, bytes):
                                    val = val.decode("utf-8", errors="ignore")
                                row_parts.append(f"{col}={val}")
                            parts.append("  " + " | ".join(row_parts))

                        if row_count > cap:
                            parts.append(f"  ... {row_count - cap} more rows")
                except Exception as exc:
                    parts.append(f"  [ERROR reading table: {exc}]")
        except Exception:
            pass

        text = "\n".join(parts).strip()
        quality = 0.8 if table_count else 0.2
        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality if text else 0.0,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )
