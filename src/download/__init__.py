"""Download and source-state helpers — stages 1-2 of the Forge pipeline.

Despite the package name, "download" here is really "get-to-local":
these modules handle hashing each file, deciding which files are new or
changed, tracking nightly deltas from an upstream source, and copying
files into a local mirror for the pipeline to process.

Modules:
  - ``hasher``         : SHA-256 fingerprinting backed by a SQLite
                         state database (stage 1, also reused by skip
                         and dedup stages).
  - ``deduplicator``   : keeps the work list down to new or changed
                         files and drops _1/_2 suffix copies (stage 2).
  - ``delta_tracker``  : scheduled nightly scanner that records which
                         upstream files need to be mirrored locally.
  - ``syncer``         : verified copy engine that mirrors source files
                         into the local staging folder with hash
                         verification and resume support.
"""
