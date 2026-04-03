"""AutoCore — utils.py
Shared utilities: dependency installer and internet connectivity check.
"""

import sys
import subprocess


def _ensure_deps():
    """Auto-install missing Python packages (requests, rich)."""
    missing = []
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")
    try:
        import rich  # noqa: F401
    except ImportError:
        missing.append("rich")

    if missing:
        print(f"  [AutoCore] Installing missing packages: {', '.join(missing)}...", end=" ", flush=True)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing + ["--quiet"],
                check=True
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
