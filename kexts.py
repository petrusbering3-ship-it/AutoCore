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
from utils import _ensure_deps

requests = _ensure_deps()

# ─── Version pins ─────────────────────────────────────────────────────────────
VERSION_PINS = {
    # "Lilu": "v1.6.7",
}

MACOS_MIN_BLUETOOTH_FIX = ["Monterey", "Ventura", "Sonoma", "Sequoia"]

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
        "repo": "USBToolBox/Tool", "always": True,
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
    "VoodooPS2": {
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
        "laptop_only": True, "match": {"cpu_gen_min": 6}, "macos_max": None,
    },
    # ── GPU / Display ─────────────────────────────────────────────────────
    "RadeonSensor": {
        "repo": "aluveitie/RadeonSensor", "always": False,
        "description": "AMD GPU temperature monitoring",
        "extract": ["RadeonSensor.kext"],
        "match": {"gpu": ["amd", "radeon", "rx "]}, "macos_max": None,
    },
    "SMCRadeonGPU": {
        "repo": "aluveitie/RadeonSensor", "always": False,
        "description": "Exposes AMD GPU temps to VirtualSMC sensors",
        "extract": ["SMCRadeonGPU.kext"],
        "match": {"gpu": ["amd", "radeon", "rx "]}, "macos_max": None,
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
}


# ─── GitHub release downloader ────────────────────────────────────────────────

def _get_latest_release(repo, pinned_version=None):
    pin = pinned_version or VERSION_PINS.get(repo.split("/")[-1])
    if pin:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{pin}"
        try:
            r = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            url_list = f"https://api.github.com/repos/{repo}/releases"
            r2 = requests.get(url_list, timeout=10, headers={"Accept": "application/vnd.github+json"})
            r2.raise_for_status()
            releases = r2.json()
            return releases[0] if releases else None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"\n    ! Could not fetch release from {repo}: {e}")
        return None


def _download_file_with_retry(url, dest_path, retries=3, delay=2, label=""):
    """Download with progress output and up to 3 retries."""
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
                        print(f"\r  {label:<30} {pct:3d}%  {mb:.1f} MB", end="", flush=True)
            mb_total = downloaded / (1024 * 1024)
            print(f"\r  {label:<30} ✓  {mb_total:.1f} MB")
            return True
        except Exception as e:
            if attempt < retries - 1:
                print(f"\n  ! {label} attempt {attempt + 1} failed — retrying...")
                time.sleep(delay)
            else:
                print(f"\n  ! {label} download failed after {retries} attempts: {e}")
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
    # Fix: strip spaces so "Big Sur" -> "bigsur" to match "BigSur" in filename
    ver_key = macos_version.lower().replace(" ", "")
    target = _find_asset(assets, ["airportitlwm", ver_key], exclude=["itlwm_v"])
    if not target:
        target = _find_asset(assets, ["airportitlwm"], exclude=["itlwm_v"])
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
    target = _find_asset(assets, ["itlwm_v", ".zip"])
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

def _extract_kext(zip_path, dest_dir, kext_names):
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            all_entries = z.namelist()
            for kext_name in kext_names:
                kext_entries = [e for e in all_entries if kext_name in e]
                if not kext_entries:
                    continue
                for entry in kext_entries:
                    parts = entry.split(kext_name)
                    relative = kext_name + parts[1] if len(parts) > 1 else kext_name
                    dest = os.path.join(dest_dir, relative)
                    if entry.endswith('/'):
                        os.makedirs(dest, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with z.open(entry) as src, open(dest, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                extracted.append(kext_name)
    except Exception as e:
        print(f"\n    ! Extract failed for {zip_path}: {e}")
    return extracted


# ─── Download all selected kexts ──────────────────────────────────────────────

def download_kexts(selected_names, hardware, macos_version, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    wifi   = hardware.get("wifi", "").lower()
    failed = []

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
        info    = KEXT_DB[name]
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

        assets = release.get("assets", [])
        asset  = _find_asset(assets, [".zip"], exclude=["debug", "dsym", "source"])
        if not asset:
            print(f"  ! No ZIP found for {repo}")
            failed.extend(names)
            continue

        zip_path = os.path.join(dest_dir, f"{repo.replace('/', '_')}.zip")
        if _download_file_with_retry(asset["browser_download_url"], zip_path, label=label):
            extracted = _extract_kext(zip_path, dest_dir, extracts)
            os.remove(zip_path)
            if not extracted:
                print(f"  ! No kexts found in ZIP for {repo}")
                failed.extend(names)
        else:
            failed.extend(names)

    return failed


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
    failed = download_kexts(list(selected), hardware, macos_version, dest_dir)

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
