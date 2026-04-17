# ============================================================================
# safe_after -- schedule tkinter callbacks that survive widget destruction.
#
# Tkinter is NOT thread-safe.  Calling widget.after() from a background
# thread can silently succeed but produce undefined behavior (buttons stop
# working, intermittent Tcl errors).  This module guarantees that only the
# main thread ever touches widget.after(); background-thread callers are
# routed to a thread-safe queue drained by drain_ui_queue().
#
# Usage:
#   from src.gui.safe_after import safe_after, drain_ui_queue
#
#   # Any thread (background or main):
#   safe_after(widget, 0, callback, arg1, arg2)
#
#   # Main-thread pump loop (harness or app):
#   root.update_idletasks()
#   root.update()
#   drain_ui_queue()
# ============================================================================

"""Safe scheduling helper for Tkinter UI callbacks.

Tkinter expects the main UI thread to be the one touching widgets. This
module queues background-thread updates so the main thread can apply them
later without corrupting the GUI state.

Plain-English view: Forge runs the heavy work (discover, dedup, parse,
chunk, enrich, embed, export) in background threads. Those threads
cannot touch the window directly - if they did, buttons could stop
working or the app could crash silently. Every "update the stats
panel", "append a log line", or "disable the Start button" call from a
background thread is routed through :func:`safe_after`, which puts the
request on a thread-safe queue. The main UI thread drains that queue
(see :func:`drain_ui_queue`, called from the launcher's pump loop) and
applies the updates for real.
"""

import logging
import os
import queue as _queue_mod
import threading

logger = logging.getLogger(__name__)

# Thread-safe queue for callbacks scheduled from background threads.
# Drained by drain_ui_queue() on the main thread during pump loops.
_ui_queue = _queue_mod.Queue()


def _enqueue(fn, args):
    """Enqueue a callback for main-thread drain."""
    if args:
        _ui_queue.put(lambda: fn(*args))
    else:
        _ui_queue.put(fn)


def safe_after(widget, ms, fn, *args):
    """Schedule fn on the tkinter main thread.

    Routing logic (in order):
      1. Headless mode (CORPUSFORGE_HEADLESS=1) -- enqueue; no mainloop.
      2. Background thread -- enqueue; widget.after() is NOT safe off
         the main thread (undefined behavior, silent Tcl corruption).
      3. Main thread -- use widget.after() directly (processed by
         mainloop).  RuntimeError/TclError still caught as safety net.

    Returns the after-ID on success, or None if enqueued/dropped.
    """
    # In headless mode, always queue -- after() is unreliable
    if os.environ.get("CORPUSFORGE_HEADLESS") == "1":
        _enqueue(fn, args)
        return None

    # Background threads must never call widget.after() -- enqueue instead
    if threading.current_thread() is not threading.main_thread():
        _enqueue(fn, args)
        return None

    # Main-thread path: widget.after() is safe here
    try:
        return widget.after(ms, fn, *args)
    except RuntimeError:
        # "main thread is not in main loop" -- enqueue for drain
        _enqueue(fn, args)
        return None
    except Exception:
        # TclError: "application has been destroyed" -- truly gone,
        # no point queueing since there's no UI to update.
        return None


def drain_ui_queue():
    """Drain pending UI callbacks on the main thread.

    Call this after root.update() in any pump loop (harness, boot,
    or manual event processing). Safe to call when the queue is empty.
    """
    while True:
        try:
            fn = _ui_queue.get_nowait()
        except _queue_mod.Empty:
            break
        try:
            fn()
        except Exception as exc:
            logger.debug("drain_ui_queue callback failed: %s", exc)
