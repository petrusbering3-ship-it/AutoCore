"""AutoCore — utils.py
Shared utilities: dependency installer and internet connectivity check.
"""

import sys
import subprocess

_NO_WINDOW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def force_utf8_output():
    """Make stdout/stderr UTF-8 with errors='replace'.

    On Windows the console defaults to a legacy code page (e.g. cp1252) that
    can't encode glyphs like ✓ / ✗ / —. Printing one then raises
    UnicodeEncodeError. AutoCore prints these constantly (progress, summaries),
    and in the kext downloader that error was caught and mis-reported as a
    *download failure*. Reconfiguring to UTF-8 with errors='replace' means a
    glyph can never crash a print, so output — and download success — is
    consistent no matter how AutoCore is launched. Call once at startup.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Older / wrapped streams without reconfigure — ignore.
            pass


def _ensure_deps():
    """Auto-install missing Python packages (requests)."""
    missing = []
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")

    if missing:
        print(f"  [AutoCore] Installing missing packages: {', '.join(missing)}...", end=" ", flush=True)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing + ["--quiet"],
                check=True, **_NO_WINDOW,
            )
            print("✓")
        except Exception as e:
            print(f"FAILED ({e})")
            print("  Please run:  pip install " + " ".join(missing))

    import requests
    return requests


def check_internet():
    """Ping api.github.com. Returns True if reachable, False otherwise."""
    import urllib.request
    import urllib.error
    # An HTTP error response (403 rate limit, 404, …) still proves the
    # network is up — only treat transport-level failures as offline.
    try:
        urllib.request.urlopen("https://api.github.com", timeout=6)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        pass
    # Second try: Apple CDN
    try:
        urllib.request.urlopen("https://oscdn.apple.com", timeout=6)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
