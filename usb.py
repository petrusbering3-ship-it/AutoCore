"""
AutoCore — usb.py
Scanner USB-drev, lader brugeren vælge, formaterer og flasher EFI + macOS recovery.
Virker på macOS, Windows og Linux.
"""

import os
import sys
import subprocess
import platform
import plistlib
import shutil
import tempfile
import time
import json


def _run(cmd, shell=False, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", -1
    except Exception as e:
        return "", str(e), -1


# ─── Liste USB-drev ───────────────────────────────────────────────────────────

def _list_macos():
    stdout, _, rc = _run(["diskutil", "list", "-plist", "external", "physical"])
    if rc != 0:
        return []
    try:
        data = plistlib.loads(stdout.encode())
    except Exception:
        return []

    drives = []
    for disk in data.get("WholeDisks", []):
        info_out, _, _ = _run(["diskutil", "info", "-plist", disk])
        try:
            info = plistlib.loads(info_out.encode())
        except Exception:
            continue
        size_gb = info.get("TotalSize", 0) / (1024 ** 3)
        name = (info.get("MediaName") or info.get("IORegistryEntryName") or "USB Drev").strip()
        drives.append({"device": f"/dev/{disk}", "name": name, "size_gb": size_gb})
    return drives


def _list_windows():
    ps = (
        "Get-Disk | Where-Object {$_.BusType -eq 'USB'} | "
        "Select-Object Number, FriendlyName, "
        "@{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}} | "
        "ConvertTo-Json"
    )
    stdout, _, rc = _run(["powershell", "-NoProfile", "-Command", ps])
    if rc != 0 or not stdout:
        return []
    try:
        raw = json.loads(stdout)
        if isinstance(raw, dict):
            raw = [raw]
        return [
            {
                "device": str(d.get("Number", "?")),
                "name":   (d.get("FriendlyName") or "USB Drev").strip(),
                "size_gb": float(d.get("SizeGB") or 0),
            }
            for d in raw
        ]
    except Exception:
        return []


def _list_linux():
    stdout, _, rc = _run("lsblk -d -o NAME,SIZE,TRAN,MODEL --json", shell=True)
    if rc != 0:
        return []
    try:
        devices = json.loads(stdout).get("blockdevices", [])
    except Exception:
        return []

    drives = []
    for d in devices:
        if d.get("tran") != "usb":
            continue
        size_str = d.get("size", "0")
        size_gb = _parse_lsblk_size(size_str)
        drives.append({
            "device":  f"/dev/{d['name']}",
            "name":    (d.get("model") or "USB Drev").strip(),
            "size_gb": size_gb,
        })
    return drives


def _parse_lsblk_size(s):
    s = s.strip().upper()
    try:
        if s.endswith("T"):   return float(s[:-1]) * 1024
        if s.endswith("G"):   return float(s[:-1])
        if s.endswith("M"):   return float(s[:-1]) / 1024
        if s.endswith("K"):   return float(s[:-1]) / (1024 ** 2)
    except ValueError:
        pass
    return 0.0


# ─── Formatér ─────────────────────────────────────────────────────────────────

def _format_macos(device):
    """Formaterer hele disken som én FAT32 partition (MBR)"""
    _, err, rc = _run(
        ["diskutil", "eraseDisk", "FAT32", "AUTOCORE", "MBR", device],
        timeout=60
    )
    return rc == 0, err


def _format_windows(disk_number):
    """Formaterer disk som FAT32 via diskpart og tildeler drevbogstav E"""
    script = "\n".join([
        f"select disk {disk_number}",
        "clean",
        "convert mbr",
        "create partition primary",
        "format quick fs=fat32 label=AUTOCORE",
        "assign letter=E",
        "exit",
        "",
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(script)
        script_path = f.name
    _, err, rc = _run(["diskpart", "/s", script_path], timeout=120)
    try:
        os.unlink(script_path)
    except OSError:
        pass
    return rc == 0, err


def _format_linux(device):
    """Formaterer disk som FAT32 med MBR via parted + mkfs.fat"""
    # Afmonter eventuelle partitioner
    _run(f"umount {device}* 2>/dev/null", shell=True)

    _, err1, rc1 = _run(["parted", "-s", device, "mklabel", "msdos"])
    if rc1 != 0:
        return False, f"parted mklabel fejlede: {err1}"

    _, err2, rc2 = _run(["parted", "-s", device, "mkpart", "primary", "fat32", "1MiB", "100%"])
    if rc2 != 0:
        return False, f"parted mkpart fejlede: {err2}"

    time.sleep(1)  # Vent på kernel partition-opdatering

    partition = device + ("p1" if device[-1].isdigit() else "1")
    if not os.path.exists(partition):
        partition = device + "1"

    _, err3, rc3 = _run(["mkfs.fat", "-F", "32", "-n", "AUTOCORE", partition])
    if rc3 != 0:
        return False, f"mkfs.fat fejlede: {err3}"

    return True, ""


# ─── Find mount point ─────────────────────────────────────────────────────────

def _mount_macos(device):
    """Venter på at /Volumes/AUTOCORE dukker op efter eraseDisk"""
    for _ in range(10):
        vol = "/Volumes/AUTOCORE"
        if os.path.exists(vol):
            return vol
        time.sleep(1)

    # Forsøg manuel mount af første partition
    _run(["diskutil", "mount", device + "s1"])
    time.sleep(2)
    if os.path.exists("/Volumes/AUTOCORE"):
        return "/Volumes/AUTOCORE"
    return ""


def _mount_windows(_disk_number):
    """Windows diskpart assign letter=E — mount point er altid E:\\"""
    time.sleep(2)
    return "E:\\"


def _mount_linux(device):
    """Monterer USB-partition til en temp-mappe"""
    partition = device + ("p1" if device[-1].isdigit() else "1")
    if not os.path.exists(partition):
        partition = device + "1"

    mount_point = tempfile.mkdtemp(prefix="autocore_usb_")
    _, _, rc = _run(["mount", partition, mount_point])
    if rc != 0:
        try:
            os.rmdir(mount_point)
        except OSError:
            pass
        return ""
    return mount_point


# ─── Skub ud ──────────────────────────────────────────────────────────────────

def _eject_macos(device):
    _run(["diskutil", "eject", device])


def _eject_windows(_disk_number):
    ps = "(New-Object -comObject Shell.Application).Namespace(17).ParseName('E:').InvokeVerb('Eject')"
    _run(["powershell", "-NoProfile", "-Command", ps])


def _eject_linux(device, mount_point):
    if mount_point and os.path.exists(mount_point):
        _run(["umount", mount_point])
        try:
            os.rmdir(mount_point)
        except OSError:
            pass
    _run(["eject", device])


# ─── Kopi med progress ────────────────────────────────────────────────────────

def _copy_with_progress(src, dst, label):
    total = sum(len(files) for _, _, files in os.walk(src))
    copied = 0

    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dst_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(dst_dir, exist_ok=True)

        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(dst_dir, fname))
            copied += 1
            pct = int(copied / total * 100) if total else 100
            print(f"\r    → {label} {pct}%", end="", flush=True)

    print(f"\r    → {label} ✓        ")


# ─── Public API ───────────────────────────────────────────────────────────────

def list_drives():
    os_name = platform.system()
    if os_name == "Darwin":   return _list_macos()
    if os_name == "Windows":  return _list_windows()
    if os_name == "Linux":    return _list_linux()
    return []


def select_drive():
    """
    Viser tilgængelige USB-drev og lader brugeren vælge.
    Returnerer valgt drev-dict eller None hvis annulleret.
    """
    drives = list_drives()
    safe   = [d for d in drives if 4 <= d["size_gb"] <= 512]

    if not safe:
        print("  ! Ingen USB-drev fundet (forventet 4–512 GB).")
        print("  Tilslut en USB (min. 8 GB anbefalet) og prøv igen.")
        return None

    print()
    print("  USB-drev tilgængelige:")
    for i, d in enumerate(safe, 1):
        print(f"    [{i}] {d['device']:14}  {d['name']:<28}  {d['size_gb']:.1f} GB")
    print()

    while True:
        try:
            val = input(f"  Vælg USB [1-{len(safe)}]: ").strip()
            idx = int(val) - 1
            if 0 <= idx < len(safe):
                return safe[idx]
        except (ValueError, EOFError):
            pass
        except KeyboardInterrupt:
            print()
            return None
        print(f"  Ugyldigt valg.")


def flash_usb(output_dir):
    """
    Hoved-funktion — vælg USB, formatér, kopier EFI + recovery.

    output_dir : mappen med EFI/ og com.apple.recovery.boot/ (fra efi_builder.py)
    Returnerer True ved succes, False ved fejl eller annullering.
    """
    print("[6/6] Flash til USB...")

    drive = select_drive()
    if not drive:
        return False

    device  = drive["device"]
    name    = drive["name"]
    size_gb = drive["size_gb"]
    os_name = platform.system()

    # ── Bekræftelse ──────────────────────────────────────────────────────────
    print()
    print(f"  ⚠  ADVARSEL: {device} ({name}, {size_gb:.1f} GB) vil blive SLETTET!")
    print()
    try:
        confirm = input("  Skriv 'JA' for at fortsætte: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n  Annulleret.")
        return False

    if confirm != "JA":
        print("  Annulleret.")
        return False

    print()

    # ── Formatér ─────────────────────────────────────────────────────────────
    print(f"  → Formaterer {device}...", end=" ", flush=True)

    if os_name == "Darwin":
        ok, err = _format_macos(device)
    elif os_name == "Windows":
        ok, err = _format_windows(device)
    elif os_name == "Linux":
        ok, err = _format_linux(device)
    else:
        print("FEJL — ukendt OS")
        return False

    if not ok:
        print(f"FEJL\n  ! {err}")
        if os_name == "Linux":
            print("  Tip: kør med sudo / som root")
        return False
    print("✓")

    # ── Mount ─────────────────────────────────────────────────────────────────
    if os_name == "Darwin":
        mount_point = _mount_macos(device)
    elif os_name == "Windows":
        mount_point = _mount_windows(device)
    else:
        mount_point = _mount_linux(device)

    if not mount_point or not os.path.exists(mount_point):
        print(f"  ! Kunne ikke mounte {device} efter formatering")
        return False

    # ── Kopier EFI ───────────────────────────────────────────────────────────
    efi_src = os.path.join(output_dir, "EFI")
    if os.path.exists(efi_src):
        _copy_with_progress(efi_src, os.path.join(mount_point, "EFI"), "EFI")
    else:
        print(f"  ! EFI mappe ikke fundet i: {output_dir}")

    # ── Kopier macOS recovery ─────────────────────────────────────────────────
    recovery_src = os.path.join(output_dir, "com.apple.recovery.boot")
    if os.path.exists(recovery_src):
        _copy_with_progress(
            recovery_src,
            os.path.join(mount_point, "com.apple.recovery.boot"),
            "macOS recovery"
        )
    else:
        print("  ! com.apple.recovery.boot ikke fundet — springer over")

    # ── Kopier CoreSync.app (post-install tool) ────────────────────────────────
    coresync_src = os.path.join(output_dir, "CoreSync.app")
    if os.path.exists(coresync_src):
        dst = os.path.join(mount_point, "CoreSync.app")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(coresync_src, dst)
        print("    → CoreSync.app ✓")

    # ── Skub ud ───────────────────────────────────────────────────────────────
    print("  → Skubber ud...", end=" ", flush=True)
    if os_name == "Darwin":
        _eject_macos(device)
    elif os_name == "Windows":
        _eject_windows(device)
    else:
        _eject_linux(device, mount_point)
    print("✓")

    print()
    print("  ✓ USB klar!")
    print("  → Tilslut USB til din hackintosh og vælg den i BIOS boot menu")
    print("  → OpenCore picker vises — vælg 'Install macOS ...'")
    print()
    return True


# ─── Standalone test (liste drev) ────────────────────────────────────────────

if __name__ == "__main__":
    print(f"USB-drev på {platform.system()}:")
    drives = list_drives()
    if drives:
        for d in drives:
            print(f"  {d['device']:14}  {d['name']:<28}  {d['size_gb']:.1f} GB")
    else:
        print("  Ingen USB-drev fundet")
