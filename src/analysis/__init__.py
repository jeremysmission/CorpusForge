"""Offline analysis helpers used outside the main pipeline.

These modules are run by operators and PMs when planning corpus work,
not during a production ingest run. They read a source tree or an
existing Forge export and produce summary JSON/Markdown reports that
help decide skip/defer policy, spot duplicates, and verify that the
Forge -> V2 metadata contract is being honored.

Modules:
  - ``corpus_profiler``         : scans a raw source tree and reports
                                  on extensions, signals, and repeated
                                  folders.
  - ``export_artifact_analyzer``: inspects a completed export plus a
                                  failure artifact and highlights
                                  corpus-adaptation opportunities.
  - ``export_metadata_contract``: compares an export against the
                                  planned V2 metadata contract.
"""

from .corpus_profiler import build_markdown_report, profile_source_tree

__all__ = ["build_markdown_report", "profile_source_tree"]
