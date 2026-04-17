"""Runtime keypress signal for aborting in-process retry loops.

Why this exists
---------------
The embedder halves batch size on CUDA OOM and retries each batch. When an
operator sees OOM backoff happening repeatedly, they should be able to press
any key to short-circuit the remaining retries and move on - instead of
waiting out the backoff chain they already know is going to fail.

Design
------
- Windows-only (``msvcrt.kbhit``). Non-TTY / non-Windows is a no-op.
- Between-attempts abort, not hard-interrupt. A retry in flight finishes
  before the skip takes effect.
- Context manager arms a background daemon thread for the duration of a
  retry phase, resets the flag on exit so one keypress only affects one
  ``watching`` block.
- Instructions print once per process so long runs do not spam the log.

NOTE: This is runtime interrupt logic. It has nothing to do with
``src.skip`` which is the ingest-time file-skip / deferred-hash module.

Usage
-----
.. code-block:: python

    from src.util import skip_signal

    with skip_signal.watching("embed OOM backoff"):
        while True:
            try:
                do_encode()
                break
            except RuntimeError as exc:
                if not is_oom(exc):
                    raise
                if skip_signal.pressed():
                    logger.info("embed: skip requested, aborting OOM backoff")
                    raise
                reduce_batch()
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

try:
    import msvcrt  # type: ignore[import-not-found]
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

_lock = threading.Lock()
_pressed = False
_stop_event: threading.Event | None = None
_poll_thread: threading.Thread | None = None
_instructions_shown = False


def _is_interactive_tty() -> bool:
    """True only on Windows with an attached console stdin (keypress detectable)."""
    if not _HAS_MSVCRT:
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _poll_loop(label: str, stop_event: threading.Event) -> None:
    """Daemon loop: set the pressed flag on the first key hit."""
    global _pressed
    while not stop_event.is_set():
        try:
            if msvcrt.kbhit():  # type: ignore[union-attr]
                try:
                    msvcrt.getch()  # type: ignore[union-attr]  # consume the key
                except Exception:
                    pass
                with _lock:
                    _pressed = True
                logger.info(
                    "[skip-signal] key pressed during %s - remaining retries will be skipped "
                    "after the current attempt finishes",
                    label,
                )
                return
        except Exception:
            return
        time.sleep(0.1)


@contextmanager
def watching(label: str) -> Iterator[None]:
    """Arm the keypress watcher for a retry phase."""
    global _pressed, _stop_event, _poll_thread, _instructions_shown

    if not _is_interactive_tty():
        yield
        return

    with _lock:
        _pressed = False

    if not _instructions_shown:
        print(
            "[skip-signal] Press any key during a retry to skip the remaining retries "
            "after the current attempt. This message shows once per process.",
            flush=True,
        )
        _instructions_shown = True

    _stop_event = threading.Event()
    _poll_thread = threading.Thread(
        target=_poll_loop,
        args=(label, _stop_event),
        daemon=True,
        name=f"skip_signal:{label}",
    )
    _poll_thread.start()
    try:
        yield
    finally:
        if _stop_event is not None:
            _stop_event.set()
        if _poll_thread is not None and _poll_thread.is_alive():
            _poll_thread.join(timeout=0.5)
        with _lock:
            _pressed = False
        _stop_event = None
        _poll_thread = None


def pressed() -> bool:
    """Return True if a key was pressed during the current ``watching`` phase."""
    with _lock:
        return _pressed
