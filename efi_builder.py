"""
AutoCore — efi_builder.py
Bygger EFI mappestruktur, downloader OpenCore og macOS recovery.
Køres efter kexts.py og før config_plist.py.
"""

import os
import re
import sys
import shutil
import zipfile
import subprocess
import time
import platform

# Auto-installer requests
def _ensure_deps():
    try:
        import requests
        return requests
    except ImportError:
        print("  [AutoCore] Installerer manglende pakke: requests...", end=" ", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "requests", "--quiet"], check=True)
        print("✓")
        import requests
        return requests

requests = _ensure_deps()


# ─── macOS version → recovery board-id ───────────────────────────────────────

RECOVERY_DATA = {
    "Ventura":  {"board_id": "Mac-27AD2F918AE68F61", "mlb": "00000000000000000", "os_ver": "13"},
    "Sonoma":   {"board_id": "Mac-827FAC58A8FDFA22", "mlb": "00000000000000000", "os_ver": "14"},
    "Sequoia":  {"board_id": "Mac-F60DEB81FF30ACF6", "mlb": "00000000000000000", "os_ver": "15"},
}

OPENCORE_REPO = "acidanthera/OpenCorePkg"


# ─── GitHub download hjælper ─────────────────────────────────────────────────

def _get_latest_release(repo):
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
        print(f"\n  ! Kunne ikke hente release fra {repo}: {e}")
        return None


def _download_file(url, dest_path, label=""):
    """Download med MB/s hastighed og ETA vist i terminalen."""
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        start = time.time()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start
                if total and elapsed > 0.5:
                    pct = int(downloaded / total * 100)
                    speed = downloaded / elapsed / (1024 * 1024)
                    remaining = int((total - downloaded) / (downloaded / elapsed)) if downloaded > 0 else 0
                    print(f"\r    → {label} {pct}%  {speed:.1f} MB/s  ETA {remaining}s   ", end="", flush=True)
        print(f"\r    → {label} ✓                                    ")
        return True
    except Exception as e:
        print(f"\n  ! Download fejlede ({label}): {e}")
        return False


# ─── EFI mappestruktur ────────────────────────────────────────────────────────

EFI_DIRS = [
    "EFI/BOOT",
    "EFI/OC/ACPI",
    "EFI/OC/Drivers",
    "EFI/OC/Kexts",
    "EFI/OC/Resources/Audio",
    "EFI/OC/Resources/Font",
    "EFI/OC/Resources/Image",
    "EFI/OC/Resources/Label",
    "EFI/OC/Tools",
]


def _create_efi_structure(base_dir):
    for d in EFI_DIRS:
        os.makedirs(os.path.join(base_dir, d), exist_ok=True)


# ─── SSDT valg baseret på hardware ───────────────────────────────────────────

def _select_ssdts(hardware):
    """Vælg hvilke pre-built SSDTs der er nødvendige baseret på hardware."""
    gen_str = hardware.get("cpu_generation", "")
    m = re.search(r'(\d+)\. gen', gen_str)
    gen = int(m.group(1)) if m else 8
    is_laptop = hardware.get("is_laptop", False)
    vendor = hardware.get("cpu_vendor", "Intel")

    needed = []

    if vendor == "Intel":
        if gen >= 12:
            needed.append("SSDT-PLUG-ALT.aml")
        # gen 4-11: SSDT-PLUG (hvis tilgængelig i OC samples)
        # tilføjes nedenfor fra hvad der faktisk er i pakken

        if is_laptop:
            needed.append("SSDT-EC-USBX-LAPTOP.aml")
        else:
            needed.append("SSDT-EC-USBX-DESKTOP.aml")

        if is_laptop:
            needed.append("SSDT-PNLF.aml")

        # PMC fix for 300-series desktop chipsets (Coffee Lake)
        if not is_laptop and gen in (8, 9):
            needed.append("SSDT-PMC.aml")

    return needed


# ─── Download OpenCore ────────────────────────────────────────────────────────

def _download_opencore(base_dir, tmp_dir):
    print("  → OpenCore (RELEASE)...", end=" ", flush=True)

    release = _get_latest_release(OPENCORE_REPO)
    if not release:
        return False, None, None, None

    version = release.get("tag_name", "ukendt")
    assets = release.get("assets", [])

    asset = next(
        (a for a in assets if "RELEASE" in a["name"] and a["name"].endswith(".zip")),
        None
    )
    if not asset:
        print("FEJL — ingen RELEASE zip fundet")
        return False, None, None, None

    zip_path = os.path.join(tmp_dir, "OpenCore.zip")
    if not _download_file(asset["browser_download_url"], zip_path, "OpenCore"):
        return False, None, None, None

    extract_dir = os.path.join(tmp_dir, "OpenCore_extracted")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)
    os.remove(zip_path)

    # Kopier X64/EFI/BOOT og X64/EFI/OC
    src_boot = os.path.join(extract_dir, "X64", "EFI", "BOOT")
    src_oc   = os.path.join(extract_dir, "X64", "EFI", "OC")
    dst_boot = os.path.join(base_dir, "EFI", "BOOT")
    dst_oc   = os.path.join(base_dir, "EFI", "OC")

    if os.path.exists(src_boot):
        shutil.copytree(src_boot, dst_boot, dirs_exist_ok=True)
    if os.path.exists(src_oc):
        for sub in ["Drivers", "Tools", "Resources"]:
            src_sub = os.path.join(src_oc, sub)
            dst_sub = os.path.join(dst_oc, sub)
            if os.path.exists(src_sub):
                shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)

    # macrecovery.py
    macrecovery_src = os.path.join(extract_dir, "Utilities", "macrecovery", "macrecovery.py")
    macrecovery_dst = os.path.join(tmp_dir, "macrecovery.py")
    if os.path.exists(macrecovery_src):
        shutil.copy2(macrecovery_src, macrecovery_dst)

    # ocvalidate binary
    ocvalidate_src = os.path.join(extract_dir, "Utilities", "ocvalidate", "ocvalidate")
    ocvalidate_dst = os.path.join(tmp_dir, "ocvalidate")
    if os.path.exists(ocvalidate_src):
        shutil.copy2(ocvalidate_src, ocvalidate_dst)
        try:
            os.chmod(ocvalidate_dst, 0o755)
        except OSError:
            pass

    # Pre-built ACPI samples
    acpi_src = os.path.join(extract_dir, "Docs", "AcpiSamples", "Binaries")
    acpi_samples_dir = None
    if os.path.exists(acpi_src):
        acpi_samples_dir = os.path.join(tmp_dir, "acpi_samples")
        shutil.copytree(acpi_src, acpi_samples_dir, dirs_exist_ok=True)

    shutil.rmtree(extract_dir, ignore_errors=True)
    print(f"  ✓ OpenCore {version} klar")
    return True, (macrecovery_dst if os.path.exists(macrecovery_dst) else None), \
           (ocvalidate_dst if os.path.exists(ocvalidate_dst) else None), acpi_samples_dir


# ─── Kopier SSDTs til EFI ────────────────────────────────────────────────────

def _copy_ssdts(hardware, acpi_samples_dir, base_dir):
    """Kopier relevante pre-built SSDTs til EFI/OC/ACPI/ og returner liste."""
    if not acpi_samples_dir or not os.path.exists(acpi_samples_dir):
        return []

    acpi_dst = os.path.join(base_dir, "EFI", "OC", "ACPI")
    os.makedirs(acpi_dst, exist_ok=True)

    needed = _select_ssdts(hardware)
    copied = []

    for ssdt in needed:
        src = os.path.join(acpi_samples_dir, ssdt)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(acpi_dst, ssdt))
            copied.append(ssdt)

    if copied:
        print(f"  ✓ {len(copied)} SSDTs kopieret: {', '.join(copied)}")
    else:
        print(f"  ⚠  Ingen pre-built SSDTs fundet i OpenCore-pakken")
        print(f"     Tilføj manuelt: {', '.join(needed)}")

    return copied


# ─── OpenCanopy — sæt OpenCanopy.efi til aktiv ───────────────────────────────

def _setup_opencanopy(base_dir):
    """Sørg for at OpenCanopy.efi eksisterer i Drivers (kopieret fra OC release)."""
    drivers_dir = os.path.join(base_dir, "EFI", "OC", "Drivers")
    canopy = os.path.join(drivers_dir, "OpenCanopy.efi")
    if os.path.exists(canopy):
        print("  ✓ OpenCanopy.efi klar (grafisk boot-menu)")
        return True
    print("  ⚠  OpenCanopy.efi ikke fundet i OC Drivers — bruger tekstpicker")
    return False


# ─── Flyt kexts ind i EFI ────────────────────────────────────────────────────

def _move_kexts_to_efi(kexts_dir, base_dir):
    dst = os.path.join(base_dir, "EFI", "OC", "Kexts")
    moved = []

    if not os.path.exists(kexts_dir):
        return moved

    for item in os.listdir(kexts_dir):
        if item.endswith(".kext"):
            src = os.path.join(kexts_dir, item)
            dst_kext = os.path.join(dst, item)
            if os.path.exists(dst_kext):
                shutil.rmtree(dst_kext)
            shutil.copytree(src, dst_kext)
            moved.append(item)

    return moved


# ─── Download macOS Recovery ──────────────────────────────────────────────────

def _download_recovery(macos_version, base_dir, tmp_dir, macrecovery_path):
    data = RECOVERY_DATA.get(macos_version)
    if not data:
        print(f"  ! Ukendt macOS version: {macos_version}")
        return False

    recovery_dir = os.path.join(base_dir, "com.apple.recovery.boot")
    os.makedirs(recovery_dir, exist_ok=True)

    print(f"  → macOS {macos_version} recovery (dette tager et øjeblik)...")

    if macrecovery_path and os.path.exists(macrecovery_path):
        for cmd_args in [
            ["download", "-b", data["board_id"], "-m", data["mlb"], "-o", recovery_dir],
            ["download", "-b", data["board_id"], "-m", data["mlb"]],
        ]:
            result = subprocess.run(
                [sys.executable, macrecovery_path] + cmd_args,
                capture_output=False,
                timeout=3600,
                cwd=recovery_dir,
            )
            if result.returncode == 0:
                files = os.listdir(recovery_dir)
                if any(f.lower().endswith((".dmg", ".chunklist")) for f in files):
                    print(f"  ✓ macOS {macos_version} recovery downloadet")
                    return True
        print(f"  ! macrecovery.py fejlede — prøver direkte download")

    return _download_recovery_direct(data, macos_version, recovery_dir)


def _download_recovery_direct(data, macos_version, recovery_dir):
    """Direkte download fra Apples recovery server med progress."""
    try:
        url = "https://osrecovery.apple.com/InstallationPayload/RecoveryImage"
        headers = {
            "Content-Type": "text/plain",
            "User-Agent": "InternetRecovery/1.0",
            "Host": "osrecovery.apple.com",
        }
        body = (
            f"cid={data['board_id']}\n"
            f"sn={data['mlb']}\n"
            f"bid={data['board_id']}\n"
            f"k=0\n"
            f"fg=\n"
        )

        r = requests.post(url, data=body.encode("ascii"), headers=headers, timeout=30)
        r.raise_for_status()

        response_data = {}
        for line in r.text.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                response_data[k.strip()] = v.strip()

        dmg_url   = response_data.get("b")
        chunk_url = response_data.get("bu")

        if not dmg_url:
            print(f"  ! Apple svarede ikke med download URL. Svar: {r.text[:200]}")
            return False

        ok = _download_file(dmg_url, os.path.join(recovery_dir, "BaseSystem.dmg"), "BaseSystem.dmg")
        if chunk_url:
            _download_file(chunk_url, os.path.join(recovery_dir, "BaseSystem.chunklist"), "BaseSystem.chunklist")

        if ok:
            print(f"  ✓ macOS {macos_version} recovery downloadet")
        return ok

    except Exception as e:
        print(f"  ! Recovery download fejlede: {e}")
        return False


# ─── OC Validate ─────────────────────────────────────────────────────────────

def run_ocvalidate(ocvalidate_path, config_path):
    """Kør ocvalidate på config.plist og vis eventuelle problemer."""
    if not ocvalidate_path or not os.path.exists(ocvalidate_path):
        return
    if not config_path or not os.path.exists(config_path):
        return
    if platform.system() != "Darwin":
        return  # Kun macOS binary

    print("  → Validerer config.plist...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [ocvalidate_path, config_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print("✓")
        else:
            print("⚠  problemer fundet:")
            for line in (result.stdout + result.stderr).splitlines()[:15]:
                if line.strip():
                    print(f"    {line}")
    except Exception as e:
        print(f"FEJL ({e})")


# ─── Print oversigt ──────────────────────────────────────────────────────────

def _print_efi_tree(base_dir):
    print("\n  EFI struktur:")
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        level = root.replace(base_dir, "").count(os.sep)
        indent = "    " + "  " * level
        folder = os.path.basename(root)
        if level == 0:
            continue
        print(f"{indent}{folder}/")
        subindent = "    " + "  " * (level + 1)
        for f in sorted(files):
            print(f"{subindent}{f}")


# ─── Hoved-funktion ──────────────────────────────────────────────────────────

def build(macos_version, kexts_dir, output_dir, hardware=None):
    """
    Bygger komplet EFI mappe med OpenCore + kexts + SSDTs + macOS recovery.
    Returnerer dict: {"ok": bool, "ssdts": [...], "ocvalidate": path, "opencanopy": bool, "smbios_model": str}
    """
    tmp_dir = os.path.join(output_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    result = {
        "ok": False,
        "ssdts": [],
        "ocvalidate": None,
        "opencanopy": False,
        "smbios_model": "iMac20,1",
    }

    print(f"\n[4/6] Bygger EFI struktur...")

    # 1. Opret mapper
    _create_efi_structure(output_dir)

    # 2. Download OpenCore
    ok, macrecovery_path, ocvalidate_path, acpi_samples_dir = _download_opencore(output_dir, tmp_dir)
    if not ok:
        print("  ! OpenCore download fejlede — stopper")
        return result

    result["ocvalidate"] = ocvalidate_path

    # 3. Kopier SSDTs
    if hardware:
        ssdts = _copy_ssdts(hardware, acpi_samples_dir, output_dir)
        result["ssdts"] = ssdts

    # 4. Flyt kexts ind i EFI/OC/Kexts/
    moved = _move_kexts_to_efi(kexts_dir, output_dir)
    print(f"  ✓ {len(moved)} kexts kopieret til EFI/OC/Kexts/")

    # 5. OpenCanopy
    result["opencanopy"] = _setup_opencanopy(output_dir)

    # 6. Download macOS recovery
    print(f"[4/6] Downloader macOS {macos_version} recovery...")
    _download_recovery(macos_version, output_dir, tmp_dir, macrecovery_path)

    # 7. Ryd op i tmp
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # 8. Vis struktur
    _print_efi_tree(output_dir)

    print(f"\n  ✓ EFI klar i: {output_dir}")
    print(f"  → Næste: config_plist.py genererer EFI/OC/config.plist\n")

    result["ok"] = True
    return result


if __name__ == "__main__":
    build(
        macos_version="Sonoma",
        kexts_dir="/tmp/autocore_kexts_test",
        output_dir="/tmp/autocore_efi_test",
    )
