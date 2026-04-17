"""Skip manager — stage 3 of the Forge pipeline.

Decides which files should be hashed-but-not-parsed. Examples: zero-byte
files, files over the size limit, encrypted PDFs or Office docs,
temporary files, files whose extension is deferred for this run, and
image assets when OCR is turned off.

Key rule: Forge never silently drops a file. Every skipped file is
still hashed and recorded in ``skip_manifest.json`` next to the export,
so operators can see exactly what was set aside and why.
"""

from .skip_manager import SkipManager

__all__ = ["SkipManager"]
