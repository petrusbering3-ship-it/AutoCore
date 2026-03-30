"""
AutoCore — kexts.py
Vælger, downloader og klargør alle kexts + USB mapping baseret på hardware.
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

# ─── Auto-installer manglende Python pakker ───────────────────────────────────

def _ensure_deps():
    try:
        import requests
        return requests
    except ImportError:
        print("  [AutoCore] Installerer manglende pakke: requests...", end=" ", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "requests", "--quiet"],
            check=True
        )
        print("✓")
        import requests
        return requests

requests = _ensure_deps()


# ─── Version pins ─────────────────────────────────────────────────────────────
# Lås kexts til en bestemt version. Format: "KextNavn": "v1.6.7"
# Lad tomt for altid-seneste.
VERSION_PINS = {
    # "Lilu": "v1.6.7",
    # "WhateverGreen": "v1.6.6",
}


# ─── Kext database ────────────────────────────────────────────────────────────
# Format: navn → { repo, always, description, extract, macos_max }
# always=True  → altid med
# always=False → vælges baseret på hardware
# extract      → liste af .kext navne der skal udpakkes fra ZIP
# macos_max    → højeste macOS version kexten virker på (None = alle)

KEXT_DB = {
    # ── Fundament (altid) ──────────────────────────────────────────────────
    "Lilu": {
        "repo": "acidanthera/Lilu",
        "always": True,
        "description": "Krævet af næsten alle andre kexts",
        "extract": ["Lilu.kext"],
        "macos_max": None,
    },
    "VirtualSMC": {
        "repo": "acidanthera/VirtualSMC",
        "always": True,
        "description": "SMC emulering — krævet for at macOS starter",
        "extract": ["VirtualSMC.kext", "SMCProcessor.kext", "SMCSuperIO.kext"],
        "macos_max": None,
    },
    "WhateverGreen": {
        "repo": "acidanthera/WhateverGreen",
        "always": True,
        "description": "GPU patches, iGPU framebuffer, HDMI/DP fix",
        "extract": ["WhateverGreen.kext"],
        "macos_max": None,
    },
    "AppleALC": {
        "repo": "acidanthera/AppleALC",
        "always": True,
        "description": "Lyd — headphones, mikrofon, HDMI audio",
        "extract": ["AppleALC.kext"],
        "macos_max": None,
    },
    "NVMeFix": {
        "repo": "acidanthera/NVMeFix",
        "always": False,
        "description": "NVMe strømstyring og kompatibilitet",
        "extract": ["NVMeFix.kext"],
        "match": {"has_nvme": True},
        "macos_max": None,
    },
    "RestrictEvents": {
        "repo": "acidanthera/RestrictEvents",
        "always": True,
        "description": "CPU navn i Om denne Mac + RAM advarsler",
        "extract": ["RestrictEvents.kext"],
        "macos_max": None,
    },

    # ── USB (altid) ───────────────────────────────────────────────────────
    "USBToolBox": {
        "repo": "USBToolBox/Tool",
        "always": True,
        "description": "USB controller mapping (auto-discovery ved første boot)",
        "extract": ["USBToolBox.kext"],
        "usb": True,
        "macos_max": None,
    },

    # ── Ethernet ──────────────────────────────────────────────────────────
    "IntelMausi": {
        "repo": "acidanthera/IntelMausi",
        "always": False,
        "description": "Intel I211/I219/I218 ethernet",
        "extract": ["IntelMausi.kext"],
        "match": {"ethernet": ["intel"]},
        "macos_max": None,
    },
    "RealtekRTL8111": {
        "repo": "Mieze/RTL8111_driver_for_OS_X",
        "always": False,
        "description": "Realtek RTL8111/8168 ethernet",
        "extract": ["RealtekRTL8111.kext"],
        "match": {"ethernet": ["realtek", "rtl"]},
        "macos_max": None,
    },

    # ── WiFi ──────────────────────────────────────────────────────────────
    "AirportItlwm": {
        "repo": "OpenIntelWireless/itlwm",
        "always": False,
        "description": "Intel WiFi — native Airport UI + AirDrop support",
        "extract": None,  # Håndteres særskilt (macOS-version specifik)
        "match": {"wifi": ["intel"]},
        "wifi_vendor": "intel",
        "macos_max": None,
    },
    "AirportBrcmFixup": {
        "repo": "acidanthera/AirportBrcmFixup",
        "always": False,
        "description": "Broadcom WiFi — AirDrop, Handoff, AirPlay support",
        "extract": ["AirportBrcmFixup.kext"],
        "match": {"wifi": ["broadcom", "bcm"]},
        "wifi_vendor": "broadcom",
        "macos_max": None,
    },

    # ── Bluetooth ─────────────────────────────────────────────────────────
    "IntelBluetoothFirmware": {
        "repo": "OpenIntelWireless/IntelBluetoothFirmware",
        "always": False,
        "description": "Intel Bluetooth — Handoff, AirDrop (delvist), Continuity",
        "extract": ["IntelBluetoothFirmware.kext", "IntelBTPatcher.kext"],
        "match": {"wifi": ["intel"]},
        "macos_max": None,
    },
    "BlueToolFixup": {
        "repo": "acidanthera/BrcmPatchRAM",
        "always": False,
        "description": "Bluetooth fix til macOS 12+ (Monterey og nyere)",
        "extract": ["BlueToolFixup.kext"],
        "match": {"wifi": ["intel", "broadcom", "bcm"]},
        "macos_min": "Monterey",
        "macos_max": None,
    },
    "BrcmPatchRAM": {
        "repo": "acidanthera/BrcmPatchRAM",
        "always": False,
        "description": "Broadcom Bluetooth firmware loader",
        "extract": ["BrcmPatchRAM3.kext", "BrcmFirmwareData.kext", "BrcmBluetoothInjector.kext"],
        "match": {"wifi": ["broadcom", "bcm"]},
        "macos_max": None,
    },

    # ── Laptop specifik ───────────────────────────────────────────────────
    "VoodooPS2": {
        "repo": "acidanthera/VoodooPS2",
        "always": False,
        "description": "Tastatur (næsten alle laptop tastaturer bruger PS/2 internt)",
        "extract": ["VoodooPS2Controller.kext"],
        "laptop_only": True,
        "macos_max": None,
    },
    "VoodooI2C": {
        "repo": "VoodooI2C/VoodooI2C",
        "always": False,
        "description": "I2C trackpad — bruges sammen med VoodooPS2 på moderne laptops",
        "extract": ["VoodooI2C.kext", "VoodooI2CHID.kext"],
        "laptop_only": True,
        "match": {"trackpad_i2c": True},
        "macos_max": None,
    },
    "ECEnabler": {
        "repo": "1Revenger1/ECEnabler",
        "always": False,
        "description": "Batteri status og Embedded Controller fix",
        "extract": ["ECEnabler.kext"],
        "laptop_only": True,
        "macos_max": None,
    },
    "SMCBatteryManager": {
        "repo": "acidanthera/VirtualSMC",
        "always": False,
        "description": "Batteri procent og status i menulinjen",
        "extract": ["SMCBatteryManager.kext"],
        "laptop_only": True,
        "macos_max": None,
    },
    "BrightnessKeys": {
        "repo": "acidanthera/BrightnessKeys",
        "always": False,
        "description": "Lysstyrke-taster (Fn+F5/F6) på laptop",
        "extract": ["BrightnessKeys.kext"],
        "laptop_only": True,
        "macos_max": None,
    },
    "CPUFriend": {
        "repo": "acidanthera/CPUFriend",
        "always": False,
        "description": "CPU strømstyring og frekvens",
        "extract": ["CPUFriend.kext"],
        "laptop_only": True,
        "macos_max": None,
    },
}

MACOS_VERSIONS = ["Ventura", "Sonoma", "Sequoia"]
MACOS_ORDER = ["Monterey", "Ventura", "Sonoma", "Sequoia"]
MACOS_MIN_BLUETOOTH_FIX = ["Monterey", "Ventura", "Sonoma", "Sequoia"]


# ─── GitHub release downloader med retry ─────────────────────────────────────

def _get_latest_release(repo, pinned_version=None):
    """Hent release info. Bruger pinned_version hvis sat i VERSION_PINS."""
    pin = pinned_version or VERSION_PINS.get(repo.split("/")[-1])

    if pin:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{pin}"
        try:
            r = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
            if r.status_code == 200:
                return r.json()
            # Tag not found — fall through to latest
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
        print(f"\n    ! Kunne ikke hente release fra {repo}: {e}")
        return None


def _download_file_with_retry(url, dest_path, retries=3, delay=2):
    """Download med op til 3 forsøg og pause mellem hvert."""
    for attempt in range(retries):
        try:
            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print(f"\n    ! Download fejlede efter {retries} forsøg: {e}")
    return False


def _find_asset(assets, keywords, exclude=None):
    """Find det bedste asset fra en release baseret på keywords"""
    exclude = exclude or []
    for asset in assets:
        name = asset["name"].lower()
        if any(ex.lower() in name for ex in exclude):
            continue
        if all(kw.lower() in name for kw in keywords):
            return asset
    return None


# ─── macOS-kompatibilitetstjek per kext ──────────────────────────────────────

def _check_kext_compat(name, macos_version):
    """Returner True hvis kexten er kompatibel med den valgte macOS-version."""
    info = KEXT_DB.get(name, {})
    macos_max = info.get("macos_max")
    if macos_max and macos_max in MACOS_ORDER and macos_version in MACOS_ORDER:
        max_idx = MACOS_ORDER.index(macos_max)
        cur_idx = MACOS_ORDER.index(macos_version)
        if cur_idx > max_idx:
            return False, f"{name} understøtter ikke {macos_version} (max: {macos_max})"
    return True, None


# ─── Kext valg baseret på hardware ───────────────────────────────────────────

def select_kexts(hardware, macos_version):
    """Returnerer liste af kext-navne der skal bruges baseret på faktisk hardware"""
    selected = []
    wifi = hardware.get("wifi", "").lower()
    ethernet = ", ".join(hardware.get("ethernet", [])).lower()
    is_laptop = hardware.get("is_laptop", False)
    has_nvme = hardware.get("has_nvme", False)
    trackpad_i2c = hardware.get("trackpad_i2c", None)
    needs_bt_fix = macos_version in MACOS_MIN_BLUETOOTH_FIX

    for name, info in KEXT_DB.items():
        if info.get("always"):
            selected.append(name)
            continue

        if info.get("laptop_only") and not is_laptop:
            continue

        if info.get("macos_min") and not needs_bt_fix:
            continue

        match = info.get("match", {})
        matched = True

        if "wifi" in match:
            matched = matched and any(kw in wifi for kw in match["wifi"])
        if "ethernet" in match:
            matched = matched and any(kw in ethernet for kw in match["ethernet"])
        if "has_nvme" in match:
            matched = matched and (has_nvme == match["has_nvme"])
        if "trackpad_i2c" in match:
            if trackpad_i2c is None:
                matched = True
            else:
                matched = matched and (trackpad_i2c == match["trackpad_i2c"])

        if not match and info.get("laptop_only") and is_laptop:
            matched = True
        elif not match:
            matched = False

        if matched:
            selected.append(name)

    if is_laptop and "SMCBatteryManager" not in selected:
        selected.append("SMCBatteryManager")

    # Tjek kompatibilitet og vis advarsler
    incompatible = []
    for name in selected[:]:
        ok, msg = _check_kext_compat(name, macos_version)
        if not ok:
            print(f"  ⚠  {msg}")
            incompatible.append(name)
    for name in incompatible:
        selected.remove(name)

    return selected


# ─── AirportItlwm — macOS-version specifik ───────────────────────────────────

ITLWM_MACOS_MAP = {
    "Ventura":  "AirportItlwm_v2.3.0_stable_Ventura.kext.zip",
    "Sonoma":   "AirportItlwm_v2.3.0_stable_Sonoma.kext.zip",
    "Sequoia":  "AirportItlwm_v2.3.0_stable_Sequoia.kext.zip",
}

def _download_airportitlwm(macos_version, dest_dir):
    print(f"    → AirportItlwm ({macos_version})...", end=" ", flush=True)
    release = _get_latest_release("OpenIntelWireless/itlwm")
    if not release:
        return False

    assets = release.get("assets", [])
    target = _find_asset(assets, ["airportitlwm", macos_version.lower()], exclude=["itlwm_v"])
    if not target:
        target = _find_asset(assets, ["airportitlwm"])

    if not target:
        print(f"FEJL — asset ikke fundet")
        return False

    zip_path = os.path.join(dest_dir, "airportitlwm.zip")
    if _download_file_with_retry(target["browser_download_url"], zip_path):
        _extract_kext(zip_path, dest_dir, ["AirportItlwm.kext"])
        os.remove(zip_path)
        print("✓")
        return True
    return False


# ─── Udpak kexts fra ZIP ─────────────────────────────────────────────────────

def _extract_kext(zip_path, dest_dir, kext_names):
    """Udpak specifikke .kext mapper fra en ZIP fil"""
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
        print(f"\n    ! Udpak fejlede for {zip_path}: {e}")
    return extracted


# ─── Download alle valgte kexts ───────────────────────────────────────────────

def download_kexts(selected_names, hardware, macos_version, dest_dir):
    """Download og udpak alle valgte kexts til dest_dir"""
    os.makedirs(dest_dir, exist_ok=True)
    wifi = hardware.get("wifi", "").lower()
    failed = []

    # AirportItlwm håndteres særskilt
    if "AirportItlwm" in selected_names and "intel" in wifi:
        # Offline: check om kexten allerede eksisterer
        if os.path.isdir(os.path.join(dest_dir, "AirportItlwm.kext")):
            print(f"    → AirportItlwm ({macos_version})... ✓ (fra cache)")
        else:
            _download_airportitlwm(macos_version, dest_dir)
        selected_names = [n for n in selected_names if n != "AirportItlwm"]

    # Grupér kexts der deler samme repo (undgå dobbelt download)
    repo_groups = {}
    for name in selected_names:
        if name not in KEXT_DB:
            continue
        repo = KEXT_DB[name]["repo"]
        if repo not in repo_groups:
            repo_groups[repo] = []
        repo_groups[repo].append(name)

    downloaded_repos = set()

    for name in selected_names:
        if name not in KEXT_DB:
            continue
        info = KEXT_DB[name]
        repo = info["repo"]
        extract = info.get("extract", [])

        if not extract:
            continue

        print(f"    → {name}...", end=" ", flush=True)

        # Offline: tjek om kexten allerede er i cache
        kext_file = extract[0] if extract else None
        if kext_file and os.path.isdir(os.path.join(dest_dir, kext_file)):
            print("✓ (fra cache)")
            downloaded_repos.add(repo)
            continue

        if repo in downloaded_repos:
            print("✓ (fra cache)")
            continue

        release = _get_latest_release(repo)
        if not release:
            failed.append(name)
            continue

        assets = release.get("assets", [])
        asset = _find_asset(assets, [".zip"], exclude=["debug", "dsym", "source"])
        if not asset:
            print("FEJL — ingen ZIP fundet")
            failed.append(name)
            continue

        zip_path = os.path.join(dest_dir, f"{name}.zip")
        if _download_file_with_retry(asset["browser_download_url"], zip_path):
            extracted = _extract_kext(zip_path, dest_dir, extract)
            os.remove(zip_path)
            downloaded_repos.add(repo)
            if extracted:
                print("✓")
            else:
                print("! (filer ikke fundet i ZIP)")
                failed.append(name)
        else:
            failed.append(name)

    return failed


# ─── Print oversigt ──────────────────────────────────────────────────────────

def print_kext_summary(selected, hardware, macos_version):
    is_laptop = hardware.get("is_laptop", False)
    wifi = hardware.get("wifi", "")

    print("\n" + "=" * 52)
    print("  KEXTS — AUTOCORE VALG")
    print("=" * 52)
    print(f"  macOS version : {macos_version}")
    print(f"  System type   : {'Laptop' if is_laptop else 'Desktop'}")
    print(f"  WiFi          : {wifi}")
    print(f"\n  {len(selected)} kexts valgt:\n")
    for name in selected:
        desc = KEXT_DB.get(name, {}).get("description", "")
        tag = "[altid]" if KEXT_DB.get(name, {}).get("always") else "[hardware]"
        print(f"    {tag:10} {name:30} {desc}")
    print("=" * 52 + "\n")


# ─── Hoved ───────────────────────────────────────────────────────────────────

def select_and_download(hardware, macos_version, dest_dir):
    """Kaldes fra main.py — returnerer liste af valgte kexts"""
    print(f"[3/6] Vælger kexts til {macos_version}...", end=" ", flush=True)
    selected = select_kexts(hardware, macos_version)
    print(f"✓ ({len(selected)} kexts)")

    print_kext_summary(selected, hardware, macos_version)

    print(f"[3/6] Downloader kexts...")
    failed = download_kexts(selected, hardware, macos_version, dest_dir)

    if failed:
        print(f"\n  ! Følgende kexts fejlede: {', '.join(failed)}")
    else:
        print(f"  ✓ Alle kexts downloadet til: {dest_dir}")

    return selected, failed


if __name__ == "__main__":
    test_hw = {
        "cpu": "Intel Core i5-6200U",
        "wifi": "Intel (itlwm:)",
        "ethernet": ["Intel I219V"],
        "is_laptop": True,
        "gpus": ["Intel HD Graphics 620"],
    }
    selected, failed = select_and_download(test_hw, "Sonoma", "/tmp/autocore_kexts_test")
