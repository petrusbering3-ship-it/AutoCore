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


# ─── Kext database ────────────────────────────────────────────────────────────
# Format: navn → { repo, always, description, extract }
# always=True  → altid med
# always=False → vælges baseret på hardware
# extract      → liste af .kext navne der skal udpakkes fra ZIP

KEXT_DB = {
    # ── Fundament (altid) ──────────────────────────────────────────────────
    "Lilu": {
        "repo": "acidanthera/Lilu",
        "always": True,
        "description": "Krævet af næsten alle andre kexts",
        "extract": ["Lilu.kext"],
    },
    "VirtualSMC": {
        "repo": "acidanthera/VirtualSMC",
        "always": True,
        "description": "SMC emulering — krævet for at macOS starter",
        "extract": ["VirtualSMC.kext", "SMCProcessor.kext", "SMCSuperIO.kext"],
    },
    "WhateverGreen": {
        "repo": "acidanthera/WhateverGreen",
        "always": True,
        "description": "GPU patches, iGPU framebuffer, HDMI/DP fix",
        "extract": ["WhateverGreen.kext"],
    },
    "AppleALC": {
        "repo": "acidanthera/AppleALC",
        "always": True,
        "description": "Lyd — headphones, mikrofon, HDMI audio",
        "extract": ["AppleALC.kext"],
    },
    "NVMeFix": {
        "repo": "acidanthera/NVMeFix",
        "always": False,
        "description": "NVMe strømstyring og kompatibilitet",
        "extract": ["NVMeFix.kext"],
        "match": {"has_nvme": True},
    },
    "RestrictEvents": {
        "repo": "acidanthera/RestrictEvents",
        "always": True,
        "description": "CPU navn i Om denne Mac + RAM advarsler",
        "extract": ["RestrictEvents.kext"],
    },

    # ── USB (altid — håndterer auto-mapping) ──────────────────────────────
    "USBToolBox": {
        "repo": "USBToolBox/UTB",
        "always": True,
        "description": "USB controller mapping (auto-discovery ved første boot)",
        "extract": ["USBToolBox.kext"],
        "usb": True,
    },

    # ── Ethernet ──────────────────────────────────────────────────────────
    "IntelMausi": {
        "repo": "acidanthera/IntelMausi",
        "always": False,
        "description": "Intel I211/I219/I218 ethernet",
        "extract": ["IntelMausi.kext"],
        "match": {"ethernet": ["intel"]},
    },
    "RealtekRTL8111": {
        "repo": "Mieze/RTL8111_driver_for_OS_X",
        "always": False,
        "description": "Realtek RTL8111/8168 ethernet",
        "extract": ["RealtekRTL8111.kext"],
        "match": {"ethernet": ["realtek", "rtl"]},
    },

    # ── WiFi ──────────────────────────────────────────────────────────────
    "AirportItlwm": {
        "repo": "OpenIntelWireless/itlwm",
        "always": False,
        "description": "Intel WiFi — native Airport UI + AirDrop support",
        "extract": None,  # Håndteres særskilt (macOS-version specifik)
        "match": {"wifi": ["intel"]},
        "wifi_vendor": "intel",
    },
    "AirportBrcmFixup": {
        "repo": "acidanthera/AirportBrcmFixup",
        "always": False,
        "description": "Broadcom WiFi — AirDrop, Handoff, AirPlay support",
        "extract": ["AirportBrcmFixup.kext"],
        "match": {"wifi": ["broadcom", "bcm"]},
        "wifi_vendor": "broadcom",
    },

    # ── Bluetooth ─────────────────────────────────────────────────────────
    "IntelBluetoothFirmware": {
        "repo": "OpenIntelWireless/IntelBluetoothFirmware",
        "always": False,
        "description": "Intel Bluetooth — Handoff, AirDrop (delvist), Continuity",
        "extract": ["IntelBluetoothFirmware.kext", "IntelBTPatcher.kext"],
        "match": {"wifi": ["intel"]},  # Intel WiFi = Intel BT
    },
    "BlueToolFixup": {
        "repo": "acidanthera/BrcmPatchRAM",
        "always": False,
        "description": "Bluetooth fix til macOS 12+ (Monterey og nyere)",
        "extract": ["BlueToolFixup.kext"],
        "match": {"wifi": ["intel", "broadcom", "bcm"]},
        "macos_min": "Monterey",
    },
    "BrcmPatchRAM": {
        "repo": "acidanthera/BrcmPatchRAM",
        "always": False,
        "description": "Broadcom Bluetooth firmware loader",
        "extract": ["BrcmPatchRAM3.kext", "BrcmFirmwareData.kext", "BrcmBluetoothInjector.kext"],
        "match": {"wifi": ["broadcom", "bcm"]},
    },

    # ── Laptop specifik ───────────────────────────────────────────────────
    "VoodooPS2": {
        "repo": "acidanthera/VoodooPS2",
        "always": False,
        "description": "Tastatur (næsten alle laptop tastaturer bruger PS/2 internt)",
        "extract": ["VoodooPS2Controller.kext"],
        "laptop_only": True,
    },
    "VoodooI2C": {
        "repo": "VoodooI2C/VoodooI2C",
        "always": False,
        "description": "I2C trackpad — bruges sammen med VoodooPS2 på moderne laptops",
        "extract": ["VoodooI2C.kext", "VoodooI2CHID.kext"],
        "laptop_only": True,
        "match": {"trackpad_i2c": True},
    },
    "ECEnabler": {
        "repo": "1Revenger1/ECEnabler",
        "always": False,
        "description": "Batteri status og Embedded Controller fix",
        "extract": ["ECEnabler.kext"],
        "laptop_only": True,
    },
    "SMCBatteryManager": {
        "repo": "acidanthera/VirtualSMC",
        "always": False,
        "description": "Batteri procent og status i menulinjen",
        "extract": ["SMCBatteryManager.kext"],
        "laptop_only": True,
    },
    "BrightnessKeys": {
        "repo": "acidanthera/BrightnessKeys",
        "always": False,
        "description": "Lysstyrke-taster (Fn+F5/F6) på laptop",
        "extract": ["BrightnessKeys.kext"],
        "laptop_only": True,
    },
    "CPUFriend": {
        "repo": "acidanthera/CPUFriend",
        "always": False,
        "description": "CPU strømstyring og frekvens",
        "extract": ["CPUFriend.kext"],
        "laptop_only": True,
    },
}

MACOS_VERSIONS = ["Ventura", "Sonoma", "Sequoia"]
MACOS_MIN_BLUETOOTH_FIX = ["Monterey", "Ventura", "Sonoma", "Sequoia"]


# ─── GitHub release downloader ────────────────────────────────────────────────

def _get_latest_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"\n    ! Kunne ikke hente release fra {repo}: {e}")
        return None


def _download_file(url, dest_path):
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"\n    ! Download fejlede: {e}")
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


# ─── Kext valg baseret på hardware ───────────────────────────────────────────

def select_kexts(hardware, macos_version):
    """Returnerer liste af kext-navne der skal bruges baseret på faktisk hardware"""
    selected = []
    wifi = hardware.get("wifi", "").lower()
    ethernet = ", ".join(hardware.get("ethernet", [])).lower()
    is_laptop = hardware.get("is_laptop", False)
    has_nvme = hardware.get("has_nvme", False)
    trackpad_i2c = hardware.get("trackpad_i2c", None)  # None = ukendt
    needs_bt_fix = macos_version in MACOS_MIN_BLUETOOTH_FIX

    for name, info in KEXT_DB.items():
        # Altid med
        if info.get("always"):
            selected.append(name)
            continue

        # Kun laptop
        if info.get("laptop_only") and not is_laptop:
            continue

        # Bluetooth fix kun på Monterey+
        if info.get("macos_min") and not needs_bt_fix:
            continue

        match = info.get("match", {})
        matched = True  # antag match medmindre vi finder en mismatch

        if "wifi" in match:
            matched = matched and any(kw in wifi for kw in match["wifi"])
        if "ethernet" in match:
            matched = matched and any(kw in ethernet for kw in match["ethernet"])
        if "has_nvme" in match:
            matched = matched and (has_nvme == match["has_nvme"])
        if "trackpad_i2c" in match:
            if trackpad_i2c is None:
                # Ukendt: inkludér begge trackpad kexts for sikkerhedens skyld
                matched = True
            else:
                matched = matched and (trackpad_i2c == match["trackpad_i2c"])

        # Laptop-only kexts uden specifik match → altid med på laptop
        if not match and info.get("laptop_only") and is_laptop:
            matched = True
        elif not match:
            matched = False

        if matched:
            selected.append(name)

    # SMCBatteryManager kommer fra VirtualSMC repo — kun laptop
    if is_laptop and "SMCBatteryManager" not in selected:
        selected.append("SMCBatteryManager")

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
    # Find asset der matcher macOS version og er AirportItlwm (ikke itlwm)
    target = _find_asset(assets, ["airportitlwm", macos_version.lower()], exclude=["itlwm_v"])
    if not target:
        # Prøv uden version i navn
        target = _find_asset(assets, ["airportitlwm"])

    if not target:
        print(f"FEJL — asset ikke fundet")
        return False

    zip_path = os.path.join(dest_dir, "airportitlwm.zip")
    if _download_file(target["browser_download_url"], zip_path):
        _extract_kext(zip_path, dest_dir, ["AirportItlwm.kext"])
        os.remove(zip_path)
        print("✓")
        return True
    return False


# ─── USB mapping ──────────────────────────────────────────────────────────────

def _setup_usb_mapping(dest_dir):
    """
    USBToolBox håndterer auto-discovery ved første boot.
    Vi genererer også en README til brugeren om næste skridt.
    """
    readme = os.path.join(dest_dir, "USB_MAPPING_LAES_MIG.txt")
    with open(readme, "w") as f:
        f.write("""AutoCore — USB Mapping Guide
=============================

USBToolBox.kext er inkluderet og scanner automatisk dine USB porte.

Efter første boot i macOS recovery/installationsmediet:
1. USB porte er aktiveret via USBToolBox.kext
2. For permanent mapping: download USBToolBox.exe (Windows) eller
   kør USBToolBox via terminal og generer UTBMap.kext
3. Placer UTBMap.kext i EFI/OC/Kexts/ og tilføj den til config.plist

Alternativt: AutoCore genererer en generisk UTBMap ved næste kørsel
baseret på din hardware — dette dækker de fleste porte automatisk.
""")


# ─── Udpak kexts fra ZIP ─────────────────────────────────────────────────────

def _extract_kext(zip_path, dest_dir, kext_names):
    """Udpak specifikke .kext mapper fra en ZIP fil"""
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            all_entries = z.namelist()
            for kext_name in kext_names:
                # Find alle filer der tilhører denne kext
                kext_entries = [e for e in all_entries if kext_name in e]
                if not kext_entries:
                    continue
                for entry in kext_entries:
                    # Beregn destination sti
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

    # Grupér kexts der deler samme repo (undgå dobbelt download)
    repo_groups = {}
    for name in selected_names:
        if name not in KEXT_DB:
            continue
        info = KEXT_DB[name]
        repo = info["repo"]
        if repo not in repo_groups:
            repo_groups[repo] = []
        repo_groups[repo].append(name)

    # AirportItlwm håndteres særskilt
    if "AirportItlwm" in selected_names and "intel" in wifi:
        _download_airportitlwm(macos_version, dest_dir)
        selected_names = [n for n in selected_names if n != "AirportItlwm"]

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

        # Tjek om vi allerede har hentet dette repo
        if repo in downloaded_repos:
            print("✓ (fra cache)")
            continue

        release = _get_latest_release(repo)
        if not release:
            failed.append(name)
            continue

        assets = release.get("assets", [])
        # Find ZIP asset — undgå debug og dSYM builds
        asset = _find_asset(assets, [".zip"], exclude=["debug", "dsym", "source"])
        if not asset:
            print("FEJL — ingen ZIP fundet")
            failed.append(name)
            continue

        zip_path = os.path.join(dest_dir, f"{name}.zip")
        if _download_file(asset["browser_download_url"], zip_path):
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

    # USB mapping setup
    _setup_usb_mapping(dest_dir)

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
    # Test uden hardware scanner
    test_hw = {
        "cpu": "Intel Core i5-6200U",
        "wifi": "Intel (itlwm:)",
        "ethernet": ["Intel I219V"],
        "is_laptop": True,
        "gpus": ["Intel HD Graphics 620"],
    }
    selected, failed = select_and_download(test_hw, "Sonoma", "/tmp/autocore_kexts_test")
