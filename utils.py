"""AutoCore — utils.py
Shared utilities: dependency installer and internet connectivity check.
"""

import sys
import subprocess

_NO_WINDOW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


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
    try:
        import urllib.request
        urllib.request.urlopen("https://api.github.com", timeout=6)
        return True
    except Exception:
        pass
    # Second try: Apple CDN
    try:
        import urllib.request
        urllib.request.urlopen("https://oscdn.apple.com", timeout=6)
        return True
    except Exception:
        return False
