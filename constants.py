"""AutoCore — constants.py
Shared constants used across multiple modules.

MACOS_VERSIONS is the single source of truth for which releases AutoCore
supports, ordered oldest → newest. Index-based logic in kexts.py and
config_plist.py (XhciPortLimit, macos_min/max checks, etc.) relies on
this ordering, so never reorder it — only append/insert in place.
"""

# Ordered oldest → newest. The order is load-bearing (see module docstring).
MACOS_VERSIONS = [
    "High Sierra",   # 10.13
    "Catalina",      # 10.15
    "Big Sur",       # 11
    "Monterey",      # 12
    "Ventura",       # 13
    "Sonoma",        # 14
    "Sequoia",       # 15
    "Tahoe",         # 26
]
MACOS_ORDER = MACOS_VERSIONS   # alias — kept for compatibility, same list

# Presentation metadata for the GUI macOS picker. Keeps the list "orderly
# sorted so you know which one is which": version number, year and a tag.
# tag ∈ {latest, recommended, stable, legacy}
MACOS_INFO = {
    "High Sierra": {"number": "10.13", "year": 2017, "tag": "legacy",
                    "note": "Oldest supported. Best for very old Intel hardware."},
    "Catalina":    {"number": "10.15", "year": 2019, "tag": "legacy",
                    "note": "Last release with 32-bit-friendly tooling. Good for older Macs."},
    "Big Sur":     {"number": "11",    "year": 2020, "tag": "stable",
                    "note": "First Big Sur redesign. Mature and reliable."},
    "Monterey":    {"number": "12",    "year": 2021, "tag": "stable",
                    "note": "Stable all-rounder for most Intel builds."},
    "Ventura":     {"number": "13",    "year": 2022, "tag": "recommended",
                    "note": "Recommended for AMD Ryzen and modern Intel."},
    "Sonoma":      {"number": "14",    "year": 2023, "tag": "recommended",
                    "note": "Great balance of stability and hardware support."},
    "Sequoia":     {"number": "15",    "year": 2024, "tag": "stable",
                    "note": "Recent release. Requires reasonably modern hardware."},
    "Tahoe":       {"number": "26",    "year": 2025, "tag": "latest",
                    "note": "Newest macOS. Needs AVX2-capable CPU and a supported GPU."},
}
