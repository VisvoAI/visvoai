"""Detect the terminal's background color via the OSC 11 query.

Terminals answer `ESC ] 11 ; ?` with their background as `rgb:RRRR/GGGG/BBBB`.
We query it once at startup (before the Textual app takes over stdin) so the app
can paint that exact color — making the UI look seamless with the terminal
instead of a forced black/themed slab. Returns None if not a TTY, on Windows, or
if the terminal doesn't answer in time (caller falls back gracefully).
"""
from __future__ import annotations

import os
import re
import sys

_RESPONSE = re.compile(r"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")


def _scale(component: str) -> int:
    """OSC 11 components are 1–4 hex digits (usually 16-bit). Normalize to 8-bit."""
    value = int(component, 16)
    bits = len(component) * 4
    if bits <= 8:
        return value << (8 - bits)
    return value >> (bits - 8)


def detect_terminal_bg(timeout: float = 0.2) -> str | None:
    """Return the terminal background as '#rrggbb', or None if undetectable."""
    if not (sys.__stdin__ and sys.__stdout__ and sys.__stdin__.isatty() and sys.__stdout__.isatty()):
        return None
    try:
        import select
        import termios
        import tty
    except ImportError:
        return None  # non-POSIX (e.g. Windows)

    fd = sys.__stdin__.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        return None
    try:
        tty.setraw(fd)
        sys.__stdout__.write("\033]11;?\033\\")
        sys.__stdout__.flush()
        buf = ""
        while True:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                break
            buf += os.read(fd, 64).decode("latin-1", "ignore")
            if _RESPONSE.search(buf) and ("\033\\" in buf or "\a" in buf):
                break
            if len(buf) > 256:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    m = _RESPONSE.search(buf)
    if not m:
        return None
    r, g, b = (_scale(m.group(i)) for i in (1, 2, 3))
    return f"#{r:02x}{g:02x}{b:02x}"
