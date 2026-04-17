"""
Certificate parser -- reads X.509 security certificates.

Plain English: handles .cer / .crt / .pem files, which hold the
identity and signing info for servers, code-signing keys, and similar
security artifacts. This parser pulls out the human-readable details
(Subject, Issuer, Serial, validity dates, DNS names, signature
algorithm) and returns them as text so the Forge pipeline can index
them alongside regular documents.

Uses the optional ``cryptography`` library. If it isn't installed, the
parser returns empty text and logs a debug note -- the pipeline keeps
moving.

Ported from V1 (src/parsers/certificate_parser.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


class CertificateParser:
    """Extract identity and validity fields from X.509 .cer/.crt/.pem files."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open a certificate file and return its fields as text."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        try:
            from cryptography import x509
        except ImportError:
            logger.debug("cryptography not installed, cannot parse %s", path.name)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        try:
            raw = path.read_bytes()
        except Exception as e:
            logger.debug("Cannot read certificate %s: %s", path.name, e)
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=path.suffix.lower(),
                file_size=path.stat().st_size if path.exists() else 0,
            )

        # Try PEM first, then DER
        cert = None
        try:
            cert = x509.load_pem_x509_certificate(raw)
        except Exception:
            try:
                cert = x509.load_der_x509_certificate(raw)
            except Exception as e:
                logger.debug("Not a valid certificate %s: %s", path.name, e)
                return ParsedDocument(
                    source_path=str(path),
                    text="",
                    parse_quality=0.0,
                    file_ext=path.suffix.lower(),
                    file_size=path.stat().st_size if path.exists() else 0,
                )

        parts: list[str] = [f"X.509 Certificate: {path.name}"]
        try:
            parts.append(f"Subject: {cert.subject.rfc4514_string()}")
            parts.append(f"Issuer: {cert.issuer.rfc4514_string()}")
            parts.append(f"Serial: {cert.serial_number}")
            parts.append(f"Not Before: {cert.not_valid_before_utc}")
            parts.append(f"Not After: {cert.not_valid_after_utc}")
            parts.append(f"Signature Algorithm: {cert.signature_algorithm_oid.dotted_string}")
            parts.append(f"Version: {cert.version}")

            # Subject Alternative Names
            try:
                san = cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                )
                names = san.value.get_values_for_type(x509.DNSName)
                if names:
                    parts.append(f"SAN DNS Names: {', '.join(names)}")
            except x509.ExtensionNotFound:
                pass

        except Exception as e:
            logger.debug("Certificate field extraction error for %s: %s", path.name, e)

        text = "\n".join(parts).strip()
        quality = 0.8 if len(parts) > 3 else 0.4

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=path.suffix.lower(),
            file_size=path.stat().st_size if path.exists() else 0,
        )
