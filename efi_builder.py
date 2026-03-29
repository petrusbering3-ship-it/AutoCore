"""
AutoCore — efi_builder.py
Bygger EFI mappestruktur, downloader OpenCore og macOS recovery.
Køres efter kexts.py og før config_plist.py.
"""

import os
import sys
import shutil
import zipfile
import subprocess

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
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"\n  ! Kunne ikke hente release fra {repo}: {e}")
        return None


def _download_file(url, dest_path, label=""):
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded / total * 100)
                    print(f"\r    → {label} {pct}%", end="", flush=True)
        print(f"\r    → {label} ✓        ")
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


# ─── Download OpenCore ────────────────────────────────────────────────────────

def _download_opencore(base_dir, tmp_dir):
    print("  → OpenCore (RELEASE)...", end=" ", flush=True)

    release = _get_latest_release(OPENCORE_REPO)
    if not release:
        return False, None

    version = release.get("tag_name", "ukendt")
    assets = release.get("assets", [])

    # Find RELEASE zip (ikke DEBUG)
    asset = next(
        (a for a in assets if "RELEASE" in a["name"] and a["name"].endswith(".zip")),
        None
    )
    if not asset:
        print("FEJL — ingen RELEASE zip fundet")
        return False, None

    zip_path = os.path.join(tmp_dir, "OpenCore.zip")
    if not _download_file(asset["browser_download_url"], zip_path, "OpenCore"):
        return False, None

    # Udpak og kopier EFI struktur
    extract_dir = os.path.join(tmp_dir, "OpenCore_extracted")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)
    os.remove(zip_path)

    # Kopier X64/EFI/BOOT og X64/EFI/OC (drivers, tools, resources)
    src_boot = os.path.join(extract_dir, "X64", "EFI", "BOOT")
    src_oc   = os.path.join(extract_dir, "X64", "EFI", "OC")
    dst_boot = os.path.join(base_dir, "EFI", "BOOT")
    dst_oc   = os.path.join(base_dir, "EFI", "OC")

    if os.path.exists(src_boot):
        shutil.copytree(src_boot, dst_boot, dirs_exist_ok=True)
    if os.path.exists(src_oc):
        # Kopier drivers, tools og resources — ikke kexts (dem håndterer kexts.py)
        for sub in ["Drivers", "Tools", "Resources"]:
            src_sub = os.path.join(src_oc, sub)
            dst_sub = os.path.join(dst_oc, sub)
            if os.path.exists(src_sub):
                shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)

    # Gem macrecovery.py til recovery download
    macrecovery_src = os.path.join(extract_dir, "Utilities", "macrecovery", "macrecovery.py")
    macrecovery_dst = os.path.join(tmp_dir, "macrecovery.py")
    if os.path.exists(macrecovery_src):
        shutil.copy2(macrecovery_src, macrecovery_dst)

    shutil.rmtree(extract_dir, ignore_errors=True)
    print(f"  ✓ OpenCore {version} klar")
    return True, macrecovery_dst if os.path.exists(macrecovery_dst) else None


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
        # Brug macrecovery.py fra OpenCore (mest pålidelig metode)
        result = subprocess.run(
            [
                sys.executable,
                macrecovery_path,
                "download",
                "--board-id", data["board_id"],
                "--mlb", data["mlb"],
                "--os-ver", data["os_ver"],
                "--outdir", recovery_dir,
            ],
            capture_output=False,
            timeout=600,
        )
        if result.returncode == 0:
            print(f"  ✓ macOS {macos_version} recovery downloadet")
            return True
        else:
            print(f"  ! macrecovery.py fejlede — prøver direkte download")

    # Fallback: direkte download via Apple CDN
    return _download_recovery_direct(data, macos_version, recovery_dir)


def _download_recovery_direct(data, macos_version, recovery_dir):
    """Direkte download fra Apples recovery server (som macrecovery.py gør)"""
    try:
        url = "https://osrecovery.apple.com/InstallationPayload/RecoveryImage"
        headers = {
            "Content-Type": "text/plain",
            "User-Agent": "InternetRecovery/1.0",
        }
        body = f"cid={data['board_id']}\nsn={data['mlb']}\nbid={data['board_id']}\nk=0\nfg=\n"

        r = requests.post(url, data=body, headers=headers, timeout=30)
        r.raise_for_status()

        # Parse svar — indeholder URLs til dmg og chunklist
        lines = {}
        for line in r.text.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                lines[k.strip()] = v.strip()

        dmg_url    = lines.get("b")
        chunk_url  = lines.get("bu")

        if not dmg_url:
            print("  ! Apple svarede ikke med en download URL")
            return False

        _download_file(dmg_url,   os.path.join(recovery_dir, "BaseSystem.dmg"),       "BaseSystem.dmg")
        if chunk_url:
            _download_file(chunk_url, os.path.join(recovery_dir, "BaseSystem.chunklist"), "BaseSystem.chunklist")

        print(f"  ✓ macOS {macos_version} recovery downloadet")
        return True

    except Exception as e:
        print(f"  ! Recovery download fejlede: {e}")
        return False


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

def build(macos_version, kexts_dir, output_dir):
    """
    Bygger komplet EFI mappe med OpenCore + kexts + macOS recovery.
    Kaldes fra main.py.

    macos_version : "Ventura" / "Sonoma" / "Sequoia"
    kexts_dir     : mappe med downloadede .kext filer (fra kexts.py)
    output_dir    : hvor EFI mappen og recovery skal lægges
    """
    tmp_dir = os.path.join(output_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n[4/6] Bygger EFI struktur...")

    # 1. Opret mapper
    _create_efi_structure(output_dir)

    # 2. Download OpenCore og kopier EFI filer
    ok, macrecovery_path = _download_opencore(output_dir, tmp_dir)
    if not ok:
        print("  ! OpenCore download fejlede — stopper")
        return False

    # 3. Flyt kexts ind i EFI/OC/Kexts/
    moved = _move_kexts_to_efi(kexts_dir, output_dir)
    print(f"  ✓ {len(moved)} kexts kopieret til EFI/OC/Kexts/")

    # 4. Download macOS recovery
    print(f"[4/6] Downloader macOS {macos_version} recovery...")
    _download_recovery(macos_version, output_dir, tmp_dir, macrecovery_path)

    # 5. Ryd op i tmp
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # 6. Vis struktur
    _print_efi_tree(output_dir)

    print(f"\n  ✓ EFI klar i: {output_dir}")
    print(f"  → Næste: config_plist.py genererer EFI/OC/config.plist\n")
    return True


if __name__ == "__main__":
    # Test — kræver at kexts er downloadet først
    build(
        macos_version="Sonoma",
        kexts_dir="/tmp/autocore_kexts_test",
        output_dir="/tmp/autocore_efi_test",
    )
