"""
AutoCore — kexts.py
Selects, downloads and prepares all kexts based on hardware.
"""

import sys
import subprocess
import platform
import os
import re
import json
import zipfile
import shutil
import time

from lang import t
from constants import MACOS_VERSIONS, MACOS_ORDER
from utils import _ensure_deps, force_utf8_output

force_utf8_output()   # never let an un-encodable glyph crash a print/download
requests = _ensure_deps()


def _safe_print(*args, **kwargs):
    """print() that can never raise — last-resort guard for legacy consoles."""
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            text = " ".join(str(a) for a in args)
            sys.stdout.write(text.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass

# ─── Version pins ─────────────────────────────────────────────────────────────
VERSION_PINS = {
    # "Lilu": "v1.6.7",
}

MACOS_MIN_BLUETOOTH_FIX = ["Monterey", "Ventura", "Sonoma", "Sequoia", "Tahoe"]

# ─── Kext database ────────────────────────────────────────────────────────────
KEXT_DB = {
    # ── Foundation (always) ──────────────────────────────────────────────
    "Lilu": {
        "repo": "acidanthera/Lilu", "always": True,
        "description": "Required by almost all other kexts",
        "extract": ["Lilu.kext"], "macos_max": None,
    },
    "VirtualSMC": {
        "repo": "acidanthera/VirtualSMC", "always": True,
        "description": "SMC emulation — required for macOS to boot",
        "extract": ["VirtualSMC.kext", "SMCProcessor.kext", "SMCSuperIO.kext"], "macos_max": None,
    },
    "WhateverGreen": {
        "repo": "acidanthera/WhateverGreen", "always": True,
        "description": "GPU patches, iGPU framebuffer, HDMI/DP fix",
        "extract": ["WhateverGreen.kext"], "macos_max": None,
    },
    "AppleALC": {
        "repo": "acidanthera/AppleALC", "always": True,
        "description": "Audio — headphones, microphone, HDMI audio",
        "extract": ["AppleALC.kext"], "macos_max": None,
    },
    "RestrictEvents": {
        "repo": "acidanthera/RestrictEvents", "always": True,
        "description": "CPU name in About This Mac + RAM warnings",
        "extract": ["RestrictEvents.kext"], "macos_max": None,
    },
    "NVMeFix": {
        "repo": "acidanthera/NVMeFix", "always": False,
        "description": "NVMe power management and compatibility",
        "extract": ["NVMeFix.kext"], "match": {"has_nvme": True}, "macos_max": None,
    },
    # ── USB (always) ─────────────────────────────────────────────────────
    "USBToolBox": {
        # The kext lives in USBToolBox/Kext (RELEASE zip); USBToolBox/Tool only
        # ships the mapping tool binary, which is why this used to fail.
        "repo": "USBToolBox/Kext", "always": True,
        "description": "USB controller mapping",
        "extract": ["USBToolBox.kext"], "macos_max": None,
    },
    # ── Ethernet ─────────────────────────────────────────────────────────
    "IntelMausi": {
        "repo": "acidanthera/IntelMausi", "always": False,
        "description": "Intel I211/I219/I218 ethernet",
        "extract": ["IntelMausi.kext"], "match": {"ethernet": ["intel"]}, "macos_max": None,
    },
    "RealtekRTL8111": {
        "repo": "Mieze/RTL8111_driver_for_OS_X", "always": False,
        "description": "Realtek RTL8111/8168 ethernet",
        "extract": ["RealtekRTL8111.kext"], "match": {"ethernet": ["realtek", "rtl"]}, "macos_max": None,
    },
    "AtherosE2200Ethernet": {
        "repo": "Mieze/AtherosE2200Ethernet", "always": False,
        "description": "Atheros/Killer E2200/E2400/E2500 ethernet",
        "extract": ["AtherosE2200Ethernet.kext"],
        "match": {"ethernet": ["atheros", "killer e2200", "qualcomm"]}, "macos_max": None,
    },
    "LucyRTL8125Ethernet": {
        "repo": "Mieze/LucyRTL8125Ethernet", "always": False,
        "description": "Realtek RTL8125 2.5GbE ethernet",
        "extract": ["LucyRTL8125Ethernet.kext"],
        "match": {"ethernet": ["rtl8125", "realtek 2.5g"]}, "macos_max": None,
    },
    "AppleIGB": {
        "repo": "donatengit/AppleIGB", "always": False,
        "description": "Intel I210/I211/I350 server-grade ethernet",
        "extract": ["AppleIGB.kext"],
        "match": {"ethernet": ["i210", "i211", "i350"]}, "macos_max": None,
    },
    # ── WiFi ─────────────────────────────────────────────────────────────
    "AirportItlwm": {
        "repo": "OpenIntelWireless/itlwm", "always": False,
        "description": "Intel WiFi — native Airport UI + AirDrop support",
        "extract": None, "match": {"wifi": ["intel"]}, "macos_max": None,
    },
    "itlwm": {
        "repo": "OpenIntelWireless/itlwm", "always": False,
        "description": "Intel WiFi alternative — more stable, no AirDrop",
        "extract": ["itlwm.kext"], "match": {"wifi": ["intel"]}, "macos_max": None,
    },
    "AirportBrcmFixup": {
        "repo": "acidanthera/AirportBrcmFixup", "always": False,
        "description": "Broadcom WiFi — AirDrop, Handoff, AirPlay support",
        "extract": ["AirportBrcmFixup.kext"],
        "match": {"wifi": ["broadcom", "bcm"]}, "macos_max": None,
    },
    # ── Bluetooth ────────────────────────────────────────────────────────
    "IntelBluetoothFirmware": {
        "repo": "OpenIntelWireless/IntelBluetoothFirmware", "always": False,
        "description": "Intel Bluetooth — Handoff, Continuity",
        "extract": ["IntelBluetoothFirmware.kext"],
        "match": {"wifi": ["intel"]}, "macos_max": None,
    },
    "IntelBTPatcher": {
        "repo": "OpenIntelWireless/IntelBluetoothFirmware", "always": False,
        "description": "Intel Bluetooth patcher required alongside IntelBluetoothFirmware",
        "extract": ["IntelBTPatcher.kext"],
        "match": {"wifi": ["intel"]}, "macos_max": None,
    },
    "BlueToolFixup": {
        "repo": "acidanthera/BrcmPatchRAM", "always": False,
        "description": "Bluetooth fix for macOS 12+ (Monterey and newer)",
        "extract": ["BlueToolFixup.kext"],
        "match": {"wifi": ["intel", "broadcom", "bcm"]},
        "macos_min": "Monterey", "macos_max": None,
    },
    "BrcmPatchRAM": {
        "repo": "acidanthera/BrcmPatchRAM", "always": False,
        "description": "Broadcom Bluetooth firmware loader",
        "extract": ["BrcmPatchRAM3.kext", "BrcmFirmwareData.kext", "BrcmBluetoothInjector.kext"],
        "match": {"wifi": ["broadcom", "bcm"]}, "macos_max": None,
    },
    # ── Trackpad / Input ─────────────────────────────────────────────────
    "VoodooPS2Controller": {
        "repo": "acidanthera/VoodooPS2", "always": False,
        "description": "Keyboard (most laptop keyboards use PS/2 internally)",
        "extract": ["VoodooPS2Controller.kext"], "laptop_only": True, "macos_max": None,
    },
    "VoodooI2C": {
        "repo": "VoodooI2C/VoodooI2C", "always": False,
        "description": "I2C trackpad — used with VoodooPS2 on modern laptops",
        "extract": ["VoodooI2C.kext", "VoodooI2CHID.kext"],
        "laptop_only": True, "match": {"trackpad_i2c": True}, "macos_max": None,
    },
    "VoodooRMI": {
        "repo": "VoodooSMBus/VoodooRMI", "always": False,
        "description": "Synaptics trackpad via RMI — smoother than PS2",
        "extract": ["VoodooRMI.kext"],
        "laptop_only": True, "match": {"trackpad_vendor": "synaptics"}, "macos_max": None,
    },
    "VoodooSMBus": {
        "repo": "VoodooSMBus/VoodooSMBus", "always": False,
        "description": "SMBUS controller driver required by VoodooRMI",
        "extract": ["VoodooSMBus.kext"],
        "laptop_only": True, "match": {"trackpad_vendor": "synaptics"}, "macos_max": None,
    },
    "AlpsHID": {
        "repo": "blankmac/AlpsHID", "always": False,
        "description": "Alps trackpad support via HID protocol",
        "extract": ["AlpsHID.kext"],
        "laptop_only": True, "match": {"trackpad_vendor": "alps"}, "macos_max": None,
    },
    # ── Laptop specific ───────────────────────────────────────────────────
    "ECEnabler": {
        "repo": "1Revenger1/ECEnabler", "always": False,
        "description": "Battery status and Embedded Controller fix",
        "extract": ["ECEnabler.kext"], "laptop_only": True, "macos_max": None,
    },
    "SMCBatteryManager": {
        "repo": "acidanthera/VirtualSMC", "always": False,
        "description": "Battery percentage and status in menu bar",
        "extract": ["SMCBatteryManager.kext"], "laptop_only": True, "macos_max": None,
    },
    "BrightnessKeys": {
        "repo": "acidanthera/BrightnessKeys", "always": False,
        "description": "Brightness keys (Fn+F5/F6) on laptop",
        "extract": ["BrightnessKeys.kext"], "laptop_only": True, "macos_max": None,
    },
    "CPUFriend": {
        "repo": "acidanthera/CPUFriend", "always": False,
        "description": "CPU power management and frequency",
        "extract": ["CPUFriend.kext"], "laptop_only": True, "macos_max": None,
    },
    "HibernationFixup": {
        "repo": "acidanthera/HibernationFixup", "always": False,
        "description": "Fixes hibernation and sleep/wake issues on laptops",
        "extract": ["HibernationFixup.kext"], "laptop_only": True, "macos_max": None,
    },
    "NoTouchID": {
        "repo": "al3xtjames/NoTouchID", "always": False,
        "description": "Disables TouchID prompt that causes login hangs",
        "extract": ["NoTouchID.kext"],
        "laptop_only": True, "match": {"cpu_vendor": "Intel", "cpu_gen_min": 6}, "macos_max": None,
    },
    # ── GPU / Display ─────────────────────────────────────────────────────
    "SMCRadeonSensors": {
        "repo": "ChefKissInc/SMCRadeonSensors", "always": False,
        "description": "AMD GPU temperature monitoring and VirtualSMC sensor plugin",
        "extract": ["SMCRadeonSensors.kext"],
        "match": {"gpu": ["amd", "radeon", "rx "]}, "macos_max": None,
    },
    "Polaris22Fixup": {
        "repo": "osy/Polaris22Fixup", "always": False,
        "description": "Fixes graphical glitches on AMD Polaris RX 400/500 GPUs",
        "extract": ["Polaris22Fixup.kext"],
        "match": {"gpu": ["rx 46", "rx 47", "rx 48", "rx 55", "rx 56", "rx 57", "rx 58", "rx 59", "polaris"]},
        "macos_max": None,
    },
    # ── CPU / Power ───────────────────────────────────────────────────────
    "CpuTscSync": {
        "repo": "acidanthera/CpuTscSync", "always": False,
        "description": "TSC sync fix for Intel desktop CPUs — prevents random freezes",
        "extract": ["CpuTscSync.kext"],
        "desktop_only": True, "match": {"cpu_vendor": "Intel"}, "macos_max": None,
    },
    "AmdTscSync": {
        "repo": "naveenkrdy/AmdTscSync", "always": False,
        "description": "TSC sync fix for AMD CPUs",
        "extract": ["AmdTscSync.kext"],
        "match": {"cpu_vendor": "AMD"}, "macos_max": None,
    },
    "AMDRyzenCPUPowerManagement": {
        "repo": "trulyspinach/SMCAMDProcessor", "always": False,
        "description": "AMD CPU power management and frequency scaling",
        "extract": ["AMDRyzenCPUPowerManagement.kext"],
        "match": {"cpu_vendor": "AMD"}, "macos_max": None,
    },
    "SMCAMDProcessor": {
        "repo": "trulyspinach/SMCAMDProcessor", "always": False,
        "description": "Exposes AMD CPU temps and frequency to VirtualSMC",
        "extract": ["SMCAMDProcessor.kext"],
        "match": {"cpu_vendor": "AMD"}, "macos_max": None,
    },
    # ── Stability / Fixes ─────────────────────────────────────────────────
    "RTCMemoryFixup": {
        "repo": "acidanthera/RTCMemoryFixup", "always": False,
        "description": "Fixes RTC memory issues that cause BIOS reset on reboot",
        "extract": ["RTCMemoryFixup.kext"],
        "match": {"cpu_vendor": "Intel", "cpu_gen_min": 6}, "macos_max": None,
    },
    "FeatureUnlock": {
        "repo": "acidanthera/FeatureUnlock", "always": False,
        "description": "Unlocks AirPlay to Mac, Sidecar, Universal Control on unsupported hardware",
        "extract": ["FeatureUnlock.kext"],
        "macos_min": "Monterey", "macos_max": None,
    },
    "CryptexFixup": {
        "repo": "acidanthera/CryptexFixup", "always": False,
        "description": "Required for Ventura+ on older CPUs — fixes cryptex mounting errors",
        "extract": ["CryptexFixup.kext"],
        "macos_min": "Ventura", "match": {"cpu_vendor": "Intel", "cpu_gen_max": 10}, "macos_max": None,
    },
    # ── USB ───────────────────────────────────────────────────────────────
    "GenericUSBXHCI": {
        "repo": "RattletraPM/GenericUSBXHCI", "always": False,
        "description": "Generic XHCI driver for non-Intel USB controllers",
        "extract": ["GenericUSBXHCI.kext"],
        "match": {"cpu_vendor": "AMD"}, "macos_max": None,
    },
    # ── Card Readers ──────────────────────────────────────────────────────
    "RealtekCardReader": {
        "repo": "0xFireWolf/RealtekCardReader", "always": False,
        "description": "Realtek PCIe/USB SD card reader driver",
        "extract": ["RealtekCardReader.kext"],
        "laptop_only": True, "match": {"card_reader": True}, "macos_max": None,
    },
    "RealtekCardReaderFriend": {
        "repo": "0xFireWolf/RealtekCardReaderFriend", "always": False,
        "description": "Makes Realtek card reader appear as native Apple SD reader",
        "extract": ["RealtekCardReaderFriend.kext"],
        "laptop_only": True, "match": {"card_reader": True}, "macos_max": None,
    },
    # ── Laptop vendor specific ────────────────────────────────────────────
    "AsusSMC": {
        "repo": "hieplpvip/AsusSMC", "always": False,
        "description": "ASUS laptop keyboard backlight, fan control, battery health",
        "extract": ["AsusSMC.kext"],
        "laptop_only": True, "match": {"system_vendor": ["asus"]}, "macos_max": None,
    },
    "YogaSMC": {
        "repo": "zhen-zen/YogaSMC", "always": False,
        "description": "Lenovo ThinkPad/IdeaPad fan control, keyboard backlight, battery",
        "extract": ["YogaSMC.kext"],
        "laptop_only": True, "match": {"system_vendor": ["lenovo"]}, "macos_max": None,
    },
    # ── VirtualSMC extra plugins ──────────────────────────────────────────────
    "SMCLightSensor": {
        "repo": "acidanthera/VirtualSMC", "always": False,
        "description": "Ambient light sensor (ALS) support — some laptops only",
        "extract": ["SMCLightSensor.kext"], "laptop_only": True, "macos_max": None,
    },
    "SMCDellSensors": {
        "repo": "acidanthera/VirtualSMC", "always": False,
        "description": "Dell laptop fan speed and temperature sensors",
        "extract": ["SMCDellSensors.kext"],
        "laptop_only": True, "match": {"system_vendor": ["dell"]}, "macos_max": None,
    },
    # ── Ethernet extras ───────────────────────────────────────────────────────
    "SmallTreeIntel82576": {
        "repo": "khronokernel/SmallTree-I211-AT-patch", "always": False,
        "description": "Intel I211-AT ethernet for AMD platform boards lacking IntelMausi support",
        "extract": ["SmallTreeIntel82576.kext"],
        "match": {"ethernet": ["i211-at", "82576"]}, "macos_max": None,
    },
    "AtherosL1cEthernet": {
        "repo": "al3xtjames/AtherosL1cEthernet", "always": False,
        "description": "Atheros AR813x/AR815x gigabit ethernet",
        "extract": ["AtherosL1cEthernet.kext"],
        "match": {"ethernet": ["ar813", "ar815", "l1c"]}, "macos_max": None,
    },
    "AppleIGC": {
        "repo": "SongXiaoXi/AppleIGC", "always": False,
        "description": "Intel I225/I226 2.5GbE ethernet (Tiger Lake+ platform boards)",
        "extract": ["AppleIGC.kext"],
        "match": {"ethernet": ["i225", "i226"]}, "macos_max": None,
    },
    "AppleIntelE1000e": {
        "repo": "chris1111/AppleIntelE1000e", "always": False,
        "description": "Intel Pro/1000 (82574/82573/82566) gigabit ethernet",
        "extract": ["AppleIntelE1000e.kext"],
        "match": {"ethernet": ["82574", "82573", "82566", "e1000"]}, "macos_max": None,
    },
    "RealtekRTL8100": {
        "repo": "Mieze/RealtekRTL8100", "always": False,
        "description": "Realtek RTL8100/8101 fast ethernet",
        "extract": ["RealtekRTL8100.kext"],
        "match": {"ethernet": ["rtl8100", "rtl8101"]}, "macos_max": None,
    },
    "BCM5722D": {
        "repo": "chris1111/BCM5722D", "always": False,
        "description": "Broadcom BCM5722 gigabit ethernet",
        "extract": ["BCM5722D.kext"],
        "match": {"ethernet": ["bcm5722", "broadcom 5722"]}, "macos_max": None,
    },
    # ── WiFi extras ───────────────────────────────────────────────────────────
    "ATH9KFixup": {
        "repo": "chunnann/ATH9KFixup", "always": False,
        "description": "Enables Atheros AR9xxx WiFi chipsets",
        "extract": ["ATH9KFixup.kext"],
        "match": {"wifi": ["ar9", "ath9k", "atheros ar9"]}, "macos_max": None,
    },
    # ── USB extras ────────────────────────────────────────────────────────────
    "USBWakeFixup": {
        "repo": "osy/USBWakeFixup", "always": False,
        "description": "Fixes USB device wake-from-sleep issues",
        "extract": ["USBWakeFixup.kext"], "macos_max": None,
    },
    # ── Storage extras ────────────────────────────────────────────────────────
    "EmeraldSDHC": {
        "repo": "acidanthera/EmeraldSDHC", "always": False,
        "description": "Intel SD card reader driver (SDHC/SDXC)",
        "extract": ["EmeraldSDHC.kext"],
        "laptop_only": True, "match": {"card_reader": True}, "macos_max": None,
    },
    # ── CPU / Power extras ────────────────────────────────────────────────────
    "AppleMCEReporterDisabler": {
        "repo": "acidanthera/bugtracker", "always": False,
        "description": "Disables AppleMCEReporter — required for AMD dual-socket/multi-die to prevent panic",
        "extract": ["AppleMCEReporterDisabler.kext"],
        "match": {"cpu_vendor": "AMD"},
        "manual_download": True,
        "download_url": "https://github.com/acidanthera/bugtracker/files/3703498/AppleMCEReporterDisabler.kext.zip",
        "macos_max": None,
    },
    "CPUTopologyRebuild": {
        "repo": "b00t0x/CpuTopologyRebuild", "always": False,
        "description": "Fixes CPU topology for AMD Zen 3+ multi-die CPUs",
        "extract": ["CpuTopologyRebuild.kext"],
        "match": {"cpu_vendor": "AMD"}, "macos_max": None,
    },
    # ── Laptop input extras ───────────────────────────────────────────────────
    "VoodooInput": {
        "repo": "acidanthera/VoodooInput", "always": False,
        "description": "Multi-touch support engine required by VoodooI2C for gestures",
        "extract": ["VoodooInput.kext"],
        "laptop_only": True, "match": {"trackpad_i2c": True}, "macos_max": None,
    },
    "GK701HIDDevice": {
        "repo": "osy/GK701HIDDevice", "always": False,
        "description": "ASUS ROG laptop macro keys and media key support",
        "extract": ["GK701HIDDevice.kext"],
        "laptop_only": True, "match": {"system_vendor": ["asus"]}, "macos_max": None,
    },
    # ── Extras / Debug ────────────────────────────────────────────────────────
    "DebugEnhancer": {
        "repo": "acidanthera/DebugEnhancer", "always": False,
        "description": "Enhanced debug output — enable only for troubleshooting",
        "extract": ["DebugEnhancer.kext"],
        "manual_only": True, "macos_max": None,
    },
}


# ─── GitHub release downloader ────────────────────────────────────────────────

# Per-run cache so the same repo is never queried twice (saves API quota).
_RELEASE_CACHE = {}


def _gh_headers():
    """GitHub API headers, with a token if one is in the environment.

    Unauthenticated requests are capped at 60/hour per IP — enough for a single
    build but easily exhausted by a couple of rebuilds, which shows up as
    intermittent '403 rate limit exceeded' kext failures. Setting GITHUB_TOKEN
    (or GH_TOKEN) raises the limit to 5000/hour and makes downloads reliable.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _gh_get(url, retries=3):
    """GET the GitHub API with retries and rate-limit awareness.

    Returns the Response (caller checks status) or None on network failure.
    On a rate-limit 403/429 it waits for the reset (capped) once, then retries.
    """
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=15, headers=_gh_headers())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"\n    ! Network error contacting GitHub: {e}")
            return None

        # Rate limited — wait for the reset (bounded) and retry once.
        remaining = r.headers.get("X-RateLimit-Remaining")
        if r.status_code in (403, 429) and remaining == "0":
            reset = r.headers.get("X-RateLimit-Reset")
            wait = 0
            if reset and reset.isdigit():
                wait = max(0, int(reset) - int(time.time())) + 2
            if 0 < wait <= 90 and attempt < retries - 1:
                print(f"\n    ! GitHub rate limit hit — waiting {wait}s for reset...")
                time.sleep(wait)
                continue
            print("\n    ! GitHub API rate limit exceeded (60/hour unauthenticated).")
            print("      Set a GITHUB_TOKEN env var to raise it to 5000/hour.")
            return r
        return r
    return None


def _get_latest_release(repo, pinned_version=None):
    if repo in _RELEASE_CACHE:
        return _RELEASE_CACHE[repo]

    result = None
    pin = pinned_version or VERSION_PINS.get(repo.split("/")[-1])
    if pin:
        r = _gh_get(f"https://api.github.com/repos/{repo}/releases/tags/{pin}")
        if r is not None and r.status_code == 200:
            result = r.json()

    if result is None:
        r = _gh_get(f"https://api.github.com/repos/{repo}/releases/latest")
        if r is not None and r.status_code == 404:
            # No "latest" (only pre-releases) — fall back to the releases list.
            r = _gh_get(f"https://api.github.com/repos/{repo}/releases")
            if r is not None and r.status_code == 200:
                releases = r.json()
                result = releases[0] if releases else None
        elif r is not None and r.status_code == 200:
            result = r.json()
        elif r is not None:
            print(f"\n    ! Could not fetch release from {repo}: HTTP {r.status_code}")

    if result is not None:
        _RELEASE_CACHE[repo] = result
    return result


def _download_file_with_retry(url, dest_path, retries=3, delay=2, label=""):
    """Download with progress output and up to 3 retries.

    The actual transfer happens in the ``try``; progress/success printing is
    kept in ``else`` so a print error (e.g. an un-encodable glyph on a legacy
    console) can never be caught here and mis-reported as a download failure.
    """
    for attempt in range(retries):
        try:
            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()
            total      = int(r.headers.get("content-length", 0))
            downloaded = 0
            start      = time.time()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start
                    if elapsed > 0.5 and total > 0:
                        pct = int(downloaded / total * 100)
                        mb  = downloaded / (1024 * 1024)
                        _safe_print(f"\r  {label:<30} {pct:3d}%  {mb:.1f} MB", end="", flush=True)
        except Exception as e:
            if attempt < retries - 1:
                _safe_print(f"\n  ! {label} attempt {attempt + 1} failed — retrying...")
                time.sleep(delay)
            else:
                _safe_print(f"\n  ! {label} download failed after {retries} attempts: {e}")
                return False
        else:
            mb_total = downloaded / (1024 * 1024)
            _safe_print(f"\r  {label:<30} ✓  {mb_total:.1f} MB")
            return True
    return False


def _find_asset(assets, keywords, exclude=None):
    exclude = exclude or []
    for asset in assets:
        name = asset["name"].lower()
        if any(ex.lower() in name for ex in exclude):
            continue
        if all(kw.lower() in name for kw in keywords):
            return asset
    return None


def _pick_zip_assets(assets, extracts):
    """Return .zip assets ordered best-first for the kexts we want to extract.

    Some repos publish several zips per release (e.g. USBToolBox ships the
    mapping tool *and* the kext). Picking the first .zip blindly grabbed the
    big tool archive, which contains no kext. We rank by whether the asset name
    mentions a target kext and/or "kext", then by smallest size, so the actual
    kext archive is tried first.
    """
    targets = [e.lower().replace(".kext", "") for e in extracts]
    skip    = ("debug", "dsym", "source")
    zips = [
        a for a in assets
        if a.get("name", "").lower().endswith(".zip")
        and not any(s in a["name"].lower() for s in skip)
    ]

    def rank(a):
        n = a["name"].lower()
        name_match = any(t in n for t in targets)
        has_kext   = "kext" in n
        if name_match and has_kext:
            p = 0
        elif has_kext:
            p = 1
        elif name_match:
            p = 2
        else:
            p = 3
        return (p, a.get("size", 1 << 62))

    return sorted(zips, key=rank)


# ─── kext compatibility check ─────────────────────────────────────────────────

def _check_kext_compat(name, macos_version):
    info = KEXT_DB.get(name, {})
    macos_max = info.get("macos_max")
    if macos_max and macos_max in MACOS_ORDER and macos_version in MACOS_ORDER:
        if MACOS_ORDER.index(macos_version) > MACOS_ORDER.index(macos_max):
            return False, f"{name} {t('kext_no_support')} {macos_version} (max: {macos_max})"
    return True, None


# ─── kext selection ───────────────────────────────────────────────────────────

def select_kexts(hardware, macos_version):
    selected = []
    wifi          = hardware.get("wifi", "").lower()
    ethernet      = ", ".join(hardware.get("ethernet", [])).lower()
    is_laptop     = hardware.get("is_laptop", False)
    has_nvme      = hardware.get("has_nvme", False)
    trackpad_i2c  = hardware.get("trackpad_i2c", None)
    trackpad_v    = hardware.get("trackpad_vendor", "unknown")
    cpu_vendor    = hardware.get("cpu_vendor", "Intel")
    system_vendor = hardware.get("system_vendor", "").lower()
    gpus          = " ".join(g.lower() for g in hardware.get("gpus", []))
    has_card      = hardware.get("has_card_reader", False)

    gen_str = hardware.get("cpu_generation", "")
    import re as _re
    _m = _re.search(r'(\d+)\. gen', gen_str)
    gen_num = int(_m.group(1)) if _m else 8

    macos_idx = MACOS_ORDER.index(macos_version) if macos_version in MACOS_ORDER else 0

    for name, info in KEXT_DB.items():
        # Always-include kexts
        if info.get("always"):
            selected.append(name)
            continue

        # Laptop/desktop filters
        if info.get("laptop_only") and not is_laptop:
            continue
        if info.get("desktop_only") and is_laptop:
            continue

        # Skip kexts that require manual installation
        if info.get("manual_only"):
            continue

        # macOS version range check
        if info.get("macos_min"):
            min_v = info["macos_min"]
            if min_v in MACOS_ORDER and macos_idx < MACOS_ORDER.index(min_v):
                continue
        if info.get("macos_max"):
            max_v = info["macos_max"]
            if max_v in MACOS_ORDER and macos_idx > MACOS_ORDER.index(max_v):
                continue

        match = info.get("match", {})

        # No match dict: select if passes all preliminary filters
        if not match:
            selected.append(name)
            continue

        # Evaluate match conditions (all must pass)
        ok = True
        if "wifi"          in match: ok = ok and any(kw in wifi     for kw in match["wifi"])
        if "ethernet"      in match: ok = ok and any(kw in ethernet for kw in match["ethernet"])
        if "has_nvme"      in match: ok = ok and (has_nvme == match["has_nvme"])
        if "trackpad_i2c"  in match:
            if trackpad_i2c is not None:
                ok = ok and (trackpad_i2c == match["trackpad_i2c"])
        if "trackpad_vendor" in match: ok = ok and (trackpad_v    == match["trackpad_vendor"])
        if "gpu"           in match: ok = ok and any(kw in gpus    for kw in match["gpu"])
        if "cpu_vendor"    in match: ok = ok and (cpu_vendor       == match["cpu_vendor"])
        if "cpu_gen_min"   in match: ok = ok and (gen_num          >= match["cpu_gen_min"])
        if "cpu_gen_max"   in match: ok = ok and (gen_num          <= match["cpu_gen_max"])
        if "system_vendor" in match: ok = ok and any(kw in system_vendor for kw in match["system_vendor"])
        if "card_reader"   in match: ok = ok and has_card

        if ok:
            selected.append(name)

    # Always add SMCBatteryManager for laptops
    if is_laptop and "SMCBatteryManager" not in selected:
        selected.append("SMCBatteryManager")

    # Enforce mutual exclusion: AirportItlwm and itlwm are alternatives, not complements
    if "AirportItlwm" in selected and "itlwm" in selected:
        selected.remove("itlwm")

    # Drop incompatible kexts
    incompatible = []
    for name in selected[:]:
        ok, msg = _check_kext_compat(name, macos_version)
        if not ok:
            print(f"  ⚠  {msg}")
            incompatible.append(name)
    for name in incompatible:
        selected.remove(name)

    return selected


# ─── AirportItlwm special downloader ──────────────────────────────────────────

def _download_airportitlwm(macos_version, dest_dir):
    label = f"AirportItlwm ({macos_version})"
    release = _get_latest_release("OpenIntelWireless/itlwm")
    if not release:
        print(f"  ! Could not fetch release for AirportItlwm")
        return False

    assets = release.get("assets", [])
    # OpenIntelWireless names assets like "AirportItlwm_v2.3.0_stable_Sonoma.kext.zip"
    # (multi-word releases use underscores, e.g. "Big_Sur"). Match on the macOS
    # name in any space form, preferring the stable build. Do NOT exclude
    # "itlwm_v" — that substring also lives inside "airportitlwm_v…", which is
    # exactly the file we want (this was the long-standing match bug).
    v = macos_version.lower()
    ver_keys = [v.replace(" ", "_"), v.replace(" ", ""), v.replace(" ", "-")]
    target = None
    for vk in ver_keys:
        target = (_find_asset(assets, ["airportitlwm", "stable", vk])
                  or _find_asset(assets, ["airportitlwm", vk]))
        if target:
            break
    if not target:
        print(f"  ! AirportItlwm asset not found for {macos_version}")
        return False

    zip_path = os.path.join(dest_dir, "airportitlwm.zip")
    if _download_file_with_retry(target["browser_download_url"], zip_path, label=label):
        _extract_kext(zip_path, dest_dir, ["AirportItlwm.kext"])
        os.remove(zip_path)
        return True
    return False


def _download_itlwm(dest_dir):
    label = "itlwm"
    release = _get_latest_release("OpenIntelWireless/itlwm")
    if not release:
        print(f"  ! Could not fetch release for itlwm")
        return False

    assets = release.get("assets", [])
    # Plain itlwm asset: "itlwm_v2.3.0_stable.kext.zip". Exclude "airport" so we
    # don't accidentally grab the AirportItlwm build.
    target = (_find_asset(assets, ["itlwm_v", "stable", ".zip"], exclude=["airport"])
              or _find_asset(assets, ["itlwm_v", ".zip"], exclude=["airport"]))
    if not target:
        print("  ! itlwm asset not found")
        return False

    zip_path = os.path.join(dest_dir, "itlwm.zip")
    if _download_file_with_retry(target["browser_download_url"], zip_path, label=label):
        _extract_kext(zip_path, dest_dir, ["itlwm.kext"])
        os.remove(zip_path)
        return True
    return False


# ─── Extract kexts from ZIP ───────────────────────────────────────────────────

def _write_zip_member(z, entry, dest, retries=3):
    """Write one zip member to dest, retrying briefly on PermissionError.

    On Windows, antivirus/Search indexer can momentarily lock a freshly written
    file inside a .kext, raising [Errno 13]. A short retry makes extraction
    reliable instead of intermittently failing the whole kext.
    """
    for attempt in range(retries):
        try:
            with z.open(entry) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return True
        except PermissionError:
            time.sleep(0.4)
        except Exception:
            return False
    return False


def _extract_kext(zip_path, dest_dir, kext_names):
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            all_entries = z.namelist()
            for kext_name in kext_names:
                kext_entries = [e for e in all_entries if kext_name in e]
                if not kext_entries:
                    continue
                for entry in kext_entries:
                    parts = entry.split(kext_name)
                    relative = kext_name + parts[1] if len(parts) > 1 else kext_name
                    dest = os.path.join(dest_dir, relative)
                    # Directory entries: trailing slash, the bare kext folder
                    # stored without one, or any path that resolves to a dir.
                    if (entry.endswith("/") or relative == kext_name
                            or not os.path.basename(entry)):
                        os.makedirs(dest, exist_ok=True)
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.isdir(dest):
                        continue  # a deeper entry already created this as a dir
                    _write_zip_member(z, entry, dest)
                # Success = the .kext folder exists and actually has files in it,
                # so one locked file no longer fails the whole extraction.
                kext_root = os.path.join(dest_dir, kext_name)
                if os.path.isdir(kext_root) and os.listdir(kext_root):
                    extracted.append(kext_name)
    except Exception as e:
        print(f"\n    ! Extract failed for {zip_path}: {e}")
    return extracted


# ─── Download all selected kexts ──────────────────────────────────────────────

def download_kexts(selected_names, hardware, macos_version, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    wifi     = hardware.get("wifi", "").lower()
    failed   = []
    # Snapshot the requested kexts up front: the WiFi special-cases below
    # reassign `selected_names`, so we return this original list (not the
    # mutated one) to keep the selection intact for config.plist generation.
    requested = list(selected_names)

    # AirportItlwm — special per-macOS-version download
    if "AirportItlwm" in selected_names and "intel" in wifi:
        cached = os.path.isdir(os.path.join(dest_dir, "AirportItlwm.kext"))
        if cached:
            print(f"  AirportItlwm ({macos_version})              ✓ (cache)")
        else:
            if not _download_airportitlwm(macos_version, dest_dir):
                failed.append("AirportItlwm")
        selected_names = [n for n in selected_names if n != "AirportItlwm"]

    # itlwm — special download (different asset from same repo as AirportItlwm)
    if "itlwm" in selected_names and "intel" in wifi:
        cached = os.path.isdir(os.path.join(dest_dir, "itlwm.kext"))
        if cached:
            print(f"  itlwm                                  ✓ (cache)")
        else:
            if not _download_itlwm(dest_dir):
                failed.append("itlwm")
        selected_names = [n for n in selected_names if n != "itlwm"]

    # Group remaining kexts by repo, collecting all extract lists per repo
    repo_groups = {}
    for name in selected_names:
        if name not in KEXT_DB:
            continue
        info = KEXT_DB[name]
        if info.get("manual_download"):
            url = info.get("download_url", f"https://github.com/{info.get('repo', '')}")
            print(f"  {name:<38} ⚠ manual — {url}")
            continue
        repo    = info["repo"]
        extract = info.get("extract") or []
        if not extract:
            continue
        if repo not in repo_groups:
            repo_groups[repo] = {"names": [], "extracts": []}
        repo_groups[repo]["names"].append(name)
        for kext in extract:
            if kext not in repo_groups[repo]["extracts"]:
                repo_groups[repo]["extracts"].append(kext)

    for repo, data in repo_groups.items():
        names    = data["names"]
        extracts = data["extracts"]
        label    = names[0] if len(names) == 1 else f"{names[0]}+{len(names)-1}"

        # Cache check: all kexts for this repo already present?
        all_cached = all(
            os.path.isdir(os.path.join(dest_dir, kx))
            for kx in extracts
        )
        if all_cached:
            for n in names:
                print(f"  {n:<38} ✓ (cache)")
            continue

        release = _get_latest_release(repo)
        if not release:
            print(f"  ! Could not fetch release from {repo}")
            failed.extend(names)
            continue

        assets     = release.get("assets", [])
        candidates = _pick_zip_assets(assets, extracts)
        if not candidates:
            print(f"  ! No ZIP found for {repo}")
            failed.extend(names)
            continue

        # Try candidates in order (best-named / smallest first) until one
        # actually yields the kext(s). Repos like USBToolBox ship several zips
        # (tool + kext); the wrong one has no kext, so we fall through to the
        # next instead of failing.
        zip_path  = os.path.join(dest_dir, f"{repo.replace('/', '_')}.zip")
        extracted = []
        for asset in candidates[:3]:
            if not _download_file_with_retry(asset["browser_download_url"], zip_path, label=label):
                continue
            extracted = _extract_kext(zip_path, dest_dir, extracts)
            try:
                os.remove(zip_path)
            except OSError:
                pass
            if extracted:
                break
        if not extracted:
            print(f"  ! No kexts found in ZIP for {repo}")
            failed.extend(names)

    # Always return (requested_kexts, failed) — callers unpack a 2-tuple.
    return requested, failed


# ─── Print summary ────────────────────────────────────────────────────────────

def print_kext_summary(selected, hardware, macos_version):
    is_laptop = hardware.get("is_laptop", False)
    wifi      = hardware.get("wifi", "")

    print("\n" + "=" * 52)
    print(f"  {t('kexts_title')}")
    print("=" * 52)
    print(f"  macOS version : {macos_version}")
    print(f"  System type   : {'Laptop' if is_laptop else 'Desktop'}")
    print(f"  WiFi          : {wifi}")
    print(f"\n  {t('kexts_selected', n=len(selected))}\n")
    for name in selected:
        desc = KEXT_DB.get(name, {}).get("description", "")
        tag  = t("kexts_tag_always") if KEXT_DB.get(name, {}).get("always") else t("kexts_tag_hw")
        print(f"    {tag:10} {name:34} {desc}")
    print("=" * 52 + "\n")


# ─── Main entry ───────────────────────────────────────────────────────────────

def select_and_download(hardware, macos_version, dest_dir):
    print(t("kexts_selecting", v=macos_version), end=" ", flush=True)
    selected = select_kexts(hardware, macos_version)
    print(f"✓ ({len(selected)} kexts)")

    print_kext_summary(selected, hardware, macos_version)

    print(f"[3/6] Downloading kexts...")
    _, failed = download_kexts(list(selected), hardware, macos_version, dest_dir)

    if failed:
        print(f"\n  ! {t('kexts_failed_dl', names=', '.join(failed))}")
    else:
        print(t("kexts_all_ok", path=dest_dir))

    return selected, failed


if __name__ == "__main__":
    test_hw = {
        "cpu": "Intel Core i5-6200U", "cpu_vendor": "Intel", "cpu_generation": "Skylake (6. gen)",
        "wifi": "Intel (itlwm)", "ethernet": ["Intel I219V"],
        "is_laptop": True, "gpus": ["Intel HD Graphics 620"],
        "trackpad_vendor": "elan", "system_vendor": "Lenovo",
    }
    selected, failed = select_and_download(test_hw, "Sonoma", "/tmp/autocore_kexts_test")
