"""
AutoCore — progress.py
Terminal progress bar og spinner til lange operationer.

Format:
  → OpenCore              [██████████████████░░░░░░░░░░]  63%  3.2 MB/s  ETA 4s
"""

import sys

_BAR_WIDTH   = 26
_LABEL_WIDTH = 22
_FILL        = "█"
_EMPTY       = "░"
_SPIN_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_spin_idx    = 0


def _spin():
    global _spin_idx
    c = _SPIN_FRAMES[_spin_idx % len(_SPIN_FRAMES)]
    _spin_idx += 1
    return c


def _label(text):
    """Pad label to fixed width."""
    return f"{text:<{_LABEL_WIDTH}}"


def update(label, current, total, speed_mbps=None, eta_s=None):
    """
    Print a progress bar that overwrites the current terminal line.
    Call done() when complete.
    """
    if total > 0:
        pct   = min(current / total, 1.0)
        filled = int(pct * _BAR_WIDTH)
        pct_str = f"{int(pct * 100):3d}%"
    else:
        filled  = 0
        pct_str = "  ?"

    bar = _FILL * filled + _EMPTY * (_BAR_WIDTH - filled)

    extras = []
    if speed_mbps is not None:
        extras.append(f"{speed_mbps:.1f} MB/s")
    if eta_s is not None and eta_s > 0:
        extras.append(f"ETA {eta_s}s")
    extra = "  " + "  ".join(extras) if extras else ""

    line = f"\r  {_label(label)} [{bar}] {pct_str}{extra}"
    print(line.ljust(78), end="", flush=True)


def done(label, note="✓"):
    """Print a completed (full) progress bar and move to next line."""
    bar = _FILL * _BAR_WIDTH
    print(f"\r  {_label(label)} [{bar}] 100%  {note}".ljust(78))


def indeterminate(label, downloaded_bytes=0):
    """Spinner line for downloads where total size is unknown."""
    spin = _spin()
    if downloaded_bytes >= 1024 * 1024:
        size_str = f"{downloaded_bytes / (1024 * 1024):.0f} MB"
    elif downloaded_bytes >= 1024:
        size_str = f"{downloaded_bytes / 1024:.0f} KB"
    else:
        size_str = f"{downloaded_bytes} B"
    line = f"\r  {_label(label)} {spin} {size_str}..."
    print(line.ljust(78), end="", flush=True)


def error(label, message):
    """Print an error line (replaces progress bar line)."""
    print(f"\r  {_label(label)} ! {message}".ljust(78))
