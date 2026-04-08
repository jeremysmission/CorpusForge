"""
CorpusForge GUI Testing -- Headless Boot

Boots the full GUI in headless mode for automated testing.
The app is created, updated once (so all widgets exist), but never
enters mainloop. Test code can then introspect and invoke widgets.
"""

from __future__ import annotations

import os
import sys
import logging

_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def boot_headless():
    """Create the full CorpusForgeApp without entering mainloop.

    Returns (root, app) with all widgets built and one update()
    cycle completed, ready for introspection.
    """
    os.environ["HYBRIDRAG_HEADLESS"] = "1"

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import tkinter as tk
    from src.config.schema import load_config

    config = load_config()
    root = tk.Tk()
    root.withdraw()

    from src.gui.app import CorpusForgeApp
    app = CorpusForgeApp(root, config=config)
    root.update()

    return root, app
