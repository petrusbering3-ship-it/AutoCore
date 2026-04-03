"""
AutoCore — usb.py
Scans USB drives, lets user select, formats and flashes EFI + macOS recovery.
Works on macOS, Windows and Linux.
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
from datetime import datetime

from lang import t


def _run(cmd, shell=False, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", -1
    except Exception as e:
        return "", str(e), -1


# ─── List USB drives ──────────────────────────────────────────────────────────

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
        name = (info.get("MediaName") or info.get("IORegistryEntryName") or "USB Drive").strip()
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
                "device":  str(d.get("Number", "?")),
                "name":    (d.get("FriendlyName") or "USB Drive").strip(),
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
        size_gb = _parse_lsblk_size(d.get("size", "0"))
        drives.append({
            "device":  f"/dev/{d['name']}",
            "name":    (d.get("model") or "USB Drive").strip(),
            "size_gb": size_gb,
        })
    return drives


def _parse_lsblk_size(s):
    s = s.strip().upper()
    try:
        if s.endswith("T"): return float(s[:-1]) * 1024
        if s.endswith("G"): return float(s[:-1])
        if s.endswith("M"): return float(s[:-1]) / 1024
        if s.endswith("K"): return float(s[:-1]) / (1024 ** 2)
    except ValueError:
        pass
    return 0.0


# ─── EFI backup ───────────────────────────────────────────────────────────────

def _backup_existing_efi_macos(device):
    """
    Try to mount first partition of USB and back up EFI if config.plist exists.
    Returns True if backup was made, False if no EFI found, None on error.
    """
    part = device + "s1"
    mount_point = tempfile.mkdtemp(prefix="autocore_efi_check_")
    try:
        _, _, rc = _run(["diskutil", "mount", "-mountPoint", mount_point, part], timeout=15)
        if rc != 0:
            return None  # mount failed — treat as error

        efi_check = os.path.join(mount_point, "EFI", "OC", "config.plist")
        if not os.path.exists(efi_check):
            return False  # no EFI found

        # Existing EFI found — back up to Desktop
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop    = os.path.expanduser("~/Desktop")
        backup_dir = os.path.join(desktop, f"AutoCore_EFI_backup_{timestamp}")
        efi_src    = os.path.join(mount_point, "EFI")
        shutil.copytree(efi_src, os.path.join(backup_dir, "EFI"))
        print(f"  ✓ Existing EFI backed up to: {backup_dir}")
        return True

    except Exception:
        return None  # exception — treat as error
    finally:
        _run(["diskutil", "unmount", mount_point], timeout=10)
        try:
            os.rmdir(mount_point)
        except OSError:
            pass


# ─── Size validation ──────────────────────────────────────────────────────────

MIN_USB_GB = 16.0

def _warn_size(drive):
    """Return True if user wants to continue despite small USB."""
    size_gb = drive["size_gb"]
    if size_gb >= MIN_USB_GB:
        return True
    print()
    print(f"  ⚠  {drive['device']} is only {size_gb:.1f} GB.")
    print(f"     AutoCore recommends minimum {MIN_USB_GB:.0f} GB (recovery is ~750 MB + EFI).")
    try:
        val = input(t("usb_continue_small")).strip().lower()
        return val in ("j", "y", "ja", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


# ─── Format ───────────────────────────────────────────────────────────────────

def _format_macos(device):
    _, err, rc = _run(
        ["diskutil", "eraseDisk", "FAT32", "AUTOCORE", "MBR", device],
        timeout=60
    )
    return rc == 0, err


def _format_windows(disk_number):
    script = "\n".join([
        f"select disk {disk_number}", "clean", "convert mbr",
        "create partition primary", "format quick fs=fat32 label=AUTOCORE",
        "assign letter=E", "exit", "",
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
    _run(f"umount {device}* 2>/dev/null", shell=True)
    _, err1, rc1 = _run(["parted", "-s", device, "mklabel", "msdos"])
    if rc1 != 0:
        return False, f"parted mklabel failed: {err1}"
    _, err2, rc2 = _run(["parted", "-s", device, "mkpart", "primary", "fat32", "1MiB", "100%"])
    if rc2 != 0:
        return False, f"parted mkpart failed: {err2}"
    time.sleep(1)
    partition = device + ("p1" if device[-1].isdigit() else "1")
    if not os.path.exists(partition):
        partition = device + "1"
    _, err3, rc3 = _run(["mkfs.fat", "-F", "32", "-n", "AUTOCORE", partition])
    if rc3 != 0:
        return False, f"mkfs.fat failed: {err3}"
    return True, ""


# ─── Mount ────────────────────────────────────────────────────────────────────

def _mount_macos(device):
    for _ in range(10):
        vol = "/Volumes/AUTOCORE"
        if os.path.exists(vol):
            return vol
        time.sleep(1)
    _run(["diskutil", "mount", device + "s1"])
    time.sleep(2)
    return "/Volumes/AUTOCORE" if os.path.exists("/Volumes/AUTOCORE") else ""


def _mount_windows(_disk_number):
    time.sleep(2)
    return "E:\\"


def _mount_linux(device):
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


# ─── Eject ────────────────────────────────────────────────────────────────────

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


# ─── Copy with progress ───────────────────────────────────────────────────────

def _copy_with_progress(src, dst, label):
    total  = sum(len(files) for _, _, files in os.walk(src))
    copied = 0
    for root, dirs, files in os.walk(src):
        rel     = os.path.relpath(root, src)
        dst_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(dst_dir, exist_ok=True)
        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(dst_dir, fname))
            copied += 1
            pct = int(copied / total * 100) if total > 0 else 100
            print(f"\r  Copying {label:<28} {pct:3d}%", end="", flush=True)
    print(f"\r  Copying {label:<28} ✓   ")


# ─── NEXT_STEPS.md ────────────────────────────────────────────────────────────

def _write_next_steps(mount_point, hardware=None):
    """Write a BIOS checklist to the USB root as NEXT_STEPS.md."""
    gen_num = 0
    if hardware:
        import re
        m = re.search(r'(\d+)\. gen', hardware.get("cpu_generation", ""))
        gen_num = int(m.group(1)) if m else 0

    lines = [
        "# AutoCore — Next Steps\n\n",
        "## BIOS Settings (set BEFORE booting from USB)\n\n",
        "- [ ] **Secure Boot** → Disabled\n",
        "- [ ] **Fast Boot** → Disabled\n",
        "- [ ] **SATA Mode** → AHCI (not RAID or IDE)\n",
        "- [ ] **CSM / Legacy Boot** → Disabled (pure UEFI)\n",
        "- [ ] **VT-d** → Disabled (or enable DisableIoMapper in OpenCore)\n",
        "- [ ] **CFG Lock** → Disabled (if option available in BIOS)\n",
        "- [ ] **XHCI Hand-off** → Enabled\n",
        "- [ ] **DVMT Pre-Alloc** → 64 MB or higher (laptop iGPU)\n",
    ]
    if gen_num >= 12:
        lines.append("- [ ] **Above 4G Decoding** → Enabled (required for gen 12+ GPU)\n")
        lines.append("- [ ] **Resizable BAR / SAM** → Disabled (can cause boot issues)\n")

    lines += [
        "\n## After installing macOS\n\n",
        "1. Run **CoreSync.app** (on this USB) to install OpenCore to your internal drive\n",
        "2. Verify your serial is invalid at https://checkcoverage.apple.com\n",
        "3. Set up iCloud/iMessage with your new SMBIOS\n",
        "\n## Support\n\n",
        "- OpenCore Guide: https://dortania.github.io/OpenCore-Install-Guide/\n",
        "- AutoCore GitHub: https://github.com/petrusbering3-ship-it/autocore\n",
    ]

    try:
        path = os.path.join(mount_point, "NEXT_STEPS.md")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


# ─── Public API ───────────────────────────────────────────────────────────────

def list_drives():
    os_name = platform.system()
    if os_name == "Darwin":  return _list_macos()
    if os_name == "Windows": return _list_windows()
    if os_name == "Linux":   return _list_linux()
    return []


def select_drive():
    drives = list_drives()
    safe   = [d for d in drives if 4 <= d["size_gb"] <= 512]

    if not safe:
        print(t("usb_no_drives"))
        print(t("usb_plug_in"))
        return None

    print()
    print(t("usb_available"))
    for i, d in enumerate(safe, 1):
        size_warn = " ⚠ <16 GB" if d["size_gb"] < MIN_USB_GB else ""
        print(f"    [{i}] {d['device']:14}  {d['name']:<28}  {d['size_gb']:.1f} GB{size_warn}")
    print()

    while True:
        try:
            val = input(t("usb_select_prompt", n=len(safe))).strip()
            idx = int(val) - 1
            if 0 <= idx < len(safe):
                chosen = safe[idx]
                if not _warn_size(chosen):
                    return None
                return chosen
        except (ValueError, EOFError):
            pass
        except KeyboardInterrupt:
            print()
            return None
        print(t("usb_invalid_choice"))


def flash_usb(output_dir, hardware=None):
    """
    Main function — select USB, backup existing EFI, format, copy EFI + recovery.
    Returns True on success, False on failure or cancellation.
    """
    print("[6/6] Flash to USB...")

    drive = select_drive()
    if not drive:
        return False

    device  = drive["device"]
    name    = drive["name"]
    size_gb = drive["size_gb"]
    os_name = platform.system()

    # ── Confirmation ──────────────────────────────────────────────────────────
    print()
    print(t("usb_confirm_delete", device=device, name=name, size=size_gb))
    print()
    try:
        confirm = input(t("usb_confirm_prompt")).strip().upper()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{t('usb_cancelled')}")
        return False

    if confirm not in ("JA", "YES", "J", "Y"):
        print(t("usb_cancelled"))
        return False

    print()

    # ── Backup existing EFI (macOS only) ─────────────────────────────────────
    if os_name == "Darwin":
        print("  → Checking for existing EFI on USB...", end=" ", flush=True)
        result = _backup_existing_efi_macos(device)
        if result is False:
            print("none found")
        elif result is None:
            print("(could not check)")

    # ── Format ───────────────────────────────────────────────────────────────
    print(f"  → Formatting {device}...", end=" ", flush=True)
    if os_name == "Darwin":
        ok, err = _format_macos(device)
    elif os_name == "Windows":
        ok, err = _format_windows(device)
    elif os_name == "Linux":
        ok, err = _format_linux(device)
    else:
        print(t("scan_unknown_os"))
        return False

    if not ok:
        print(f"ERROR\n  ! {err}")
        if os_name == "Linux":
            print("  Tip: run with sudo / as root")
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
        print(f"  ! Could not mount {device} after formatting")
        return False

    # ── Copy EFI ──────────────────────────────────────────────────────────────
    efi_src = os.path.join(output_dir, "EFI")
    if os.path.exists(efi_src):
        _copy_with_progress(efi_src, os.path.join(mount_point, "EFI"), "EFI")
    else:
        print(f"  ! EFI folder not found in: {output_dir}")

    # ── Copy macOS recovery ───────────────────────────────────────────────────
    recovery_src = os.path.join(output_dir, "com.apple.recovery.boot")
    if os.path.exists(recovery_src):
        _copy_with_progress(
            recovery_src,
            os.path.join(mount_point, "com.apple.recovery.boot"),
            "macOS recovery"
        )
    else:
        print("  ! com.apple.recovery.boot not found — skipping")

    # ── Copy CoreSync.app ─────────────────────────────────────────────────────
    coresync_src = os.path.join(output_dir, "CoreSync.app")
    if os.path.exists(coresync_src):
        dst = os.path.join(mount_point, "CoreSync.app")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(coresync_src, dst)
        print("    → CoreSync.app ✓")

    # ── Write NEXT_STEPS.md ───────────────────────────────────────────────────
    _write_next_steps(mount_point, hardware=hardware)

    # ── Eject ─────────────────────────────────────────────────────────────────
    print(t("usb_eject"), end=" ", flush=True)
    if os_name == "Darwin":
        _eject_macos(device)
    elif os_name == "Windows":
        _eject_windows(device)
    else:
        _eject_linux(device, mount_point)
    print("✓")

    print()
    print(t("usb_done"))
    print(t("usb_next1"))
    print(t("usb_next2"))
    print()
    return True


# ─── Standalone test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"USB drives on {platform.system()}:")
    drives = list_drives()
    if drives:
        for d in drives:
            size_warn = " ⚠ <16 GB" if d["size_gb"] < MIN_USB_GB else ""
            print(f"  {d['device']:14}  {d['name']:<28}  {d['size_gb']:.1f} GB{size_warn}")
    else:
        print("  No USB drives found")
