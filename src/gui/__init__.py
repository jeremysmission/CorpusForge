"""Desktop user interface package.

This folder holds every piece of the Forge desktop application that an
operator can see or click. The pipeline itself (discovery, parse, chunk,
enrich, embed, export) lives elsewhere in ``src/``. Files here only draw
the window, wire up buttons, and show progress while the pipeline runs
in the background.

Typical entry points:
    * ``launch_gui.py``        - the full ingest GUI (pipeline monitor)
    * ``launch_dedup_gui.py``  - the standalone dedup-only recovery GUI
"""
