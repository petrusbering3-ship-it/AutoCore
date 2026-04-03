#!/usr/bin/env python3
"""
AutoCore — main.py
Guides the user from hardware scan to finished hackintosh USB.
"""

import os
import sys
import argparse
import tempfile
import platform
import json

# ── Auto-install packages before anything else ────────────────────────────────
import subprocess as _sp
def _bootstrap():
    missing = []
    try:
        import requests  # noqa
    except ImportError:
        missing.append("requests")
    if missing:
        print(f"  [AutoCore] Installing: {', '.join(missing)}...", end=" ", flush=True)
        _sp.run([sys.executable, "-m", "pip", "install"] + missing + ["--quiet"], check=True)
        print("✓")
_bootstrap()

# ── Imports after bootstrap ───────────────────────────────────────────────────
from lang import t, set_lang, LANG
import lang as _lang
import utils


# ─── Version ──────────────────────────────────────────────────────────────────
__version__ = "1.0.0"


# ─── Log file (tee stdout → ~/Desktop/autocore_log.txt) ──────────────────────

class _Tee:
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            s.write(data)
    def flush(self):
        for s in self._streams:
            s.flush()
    def fileno(self):
        return self._streams[0].fileno()


_log_file = None

def _start_log():
    global _log_file
    desktop  = os.path.expanduser("~/Desktop")
    log_path = os.path.join(desktop, "autocore_log.txt")
    try:
        _log_file = open(log_path, "w", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, _log_file)
        sys.stderr = _Tee(sys.__stderr__, _log_file)
        return log_path
    except Exception:
        return None


def _stop_log():
    global _log_file
    if _log_file:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        _log_file.close()
        _log_file = None


# ─── Language selector ────────────────────────────────────────────────────────

def _ask_language():
    print()
    print("  Vælg sprog / Select language:")
    print("    [1] Dansk")
    print("    [2] English")
    print()
    while True:
        try:
            val = input("  [1/2]: ").strip()
            if val == "1":
                set_lang("DA")
                return
            if val == "2":
                set_lang("EN")
                return
        except (ValueError, KeyboardInterrupt):
            print()
            sys.exit(0)


# ─── Network check ────────────────────────────────────────────────────────────

def _check_network():
    print(t("net_check"), end=" ", flush=True)
    if utils.check_internet():
        print(t("net_ok"))
        return True

    print(t("net_fail"))
    print(t("net_offline_warn"))
    try:
        val = input(t("net_continue")).strip().lower()
        return val in ("j", "y", "ja", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ask_macos_version():
    from constants import MACOS_VERSIONS
    print(f"\n{t('select_version')}")
    for i, v in enumerate(MACOS_VERSIONS, 1):
        print(f"    [{i}] {v}")
    while True:
        try:
            val = input(t("version_prompt", n=len(MACOS_VERSIONS))).strip()
            idx = int(val) - 1
            if 0 <= idx < len(MACOS_VERSIONS):
                return MACOS_VERSIONS[idx]
        except ValueError:
            pass
        except KeyboardInterrupt:
            print(t("aborted"))
            sys.exit(0)


def _confirm_compatibility(hw):
    c = hw.get("compatibility", {})
    if not c.get("issues"):
        return True
    print(f"\n{t('hw_issues_header')}")
    for issue in c["issues"]:
        print(f"  │  ✗ {issue}")
    print(t("hw_issues_footer"))
    print()
    try:
        val = input(t("hw_continue")).strip().lower()
        return val in ("j", "y", "ja", "yes")
    except KeyboardInterrupt:
        return False


def _print_bios_checklist():
    print()
    print(t("bios_title"))
    for line in t("bios_body"):
        print(line)
    print(t("bios_footer"))
    print()


def _ask_build_mode(output_dir):
    config_path = os.path.join(output_dir, "EFI", "OC", "config.plist")
    if not os.path.exists(config_path):
        return "fresh"
    print()
    print(t("update_found", path=output_dir))
    print(t("update_choice"))
    print()
    while True:
        try:
            val = input(t("update_prompt")).strip()
            if val == "1":
                return "update"
            if val == "2":
                return "fresh"
        except (KeyboardInterrupt, EOFError):
            print(t("aborted"))
            sys.exit(0)


def _save_hw_json(hw):
    """Save hardware dict to ~/Desktop/AutoCore_hardware.json."""
    desktop = os.path.expanduser("~/Desktop")
    path    = os.path.join(desktop, "AutoCore_hardware.json")
    try:
        # Convert non-serialisable types
        def _clean(obj):
            if isinstance(obj, bytes):
                return obj.hex()
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_clean(i) for i in obj]
            return obj
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_clean(hw), f, indent=2)
        return path
    except Exception:
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # ── CLI flags ─────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="autocore",
        description="Automated Hackintosh USB builder"
    )
    parser.add_argument("--version",    action="store_true", help="Print version and exit")
    parser.add_argument("--dry-run",    action="store_true", help="Scan + select without downloading or flashing")
    parser.add_argument("--export-efi", action="store_true", help="Build EFI to ~/Desktop/AutoCore_EFI instead of USB")
    args = parser.parse_args()

    if args.version:
        print(f"AutoCore {__version__}")
        sys.exit(0)

    # ── Language selector (always first, bilingual prompt) ────────────────────
    _ask_language()

    # ── Start log ─────────────────────────────────────────────────────────────
    log_path = _start_log()

    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║                                                      ║")
    banner = t("banner")
    print(f"  ║  {banner:<52}  ║")
    print(f"  ║                                                      ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    if args.dry_run:
        print(t("dry_run_notice"))
        print()

    # ── Internet check ────────────────────────────────────────────────────────
    if not args.dry_run:
        if not _check_network():
            print(t("exiting"))
            _stop_log()
            sys.exit(0)
        print()

    # ── Step 1: Hardware scan ─────────────────────────────────────────────────
    import hardware
    hw = hardware.scan()
    if not hw:
        print(t("hw_fail"))
        _stop_log()
        sys.exit(1)
    hardware.print_summary(hw, lang=_lang.LANG)

    if hw.get("is_vm"):
        print(t("vm_warning"))
        print()

    if not _confirm_compatibility(hw):
        print(t("exiting"))
        _stop_log()
        sys.exit(0)

    # Save hardware report + JSON
    report_path = hardware.save_report(hw)
    if report_path:
        print(t("hw_report", path=report_path))

    json_path = _save_hw_json(hw)
    if json_path:
        print(t("hw_json_saved", path=json_path))

    # ── Step 2: macOS version ─────────────────────────────────────────────────
    macos_version = _ask_macos_version()
    print(t("version_chosen", v=macos_version))

    # ── Step 3: Kext selection ────────────────────────────────────────────────
    import kexts
    output_dir = os.path.join(tempfile.gettempdir(), "autocore_build")
    kexts_dir  = os.path.join(output_dir, "_kexts")
    os.makedirs(output_dir, exist_ok=True)

    if args.dry_run:
        # Dry-run: just show selection and exit
        print(t("kexts_selecting", v=macos_version), end=" ", flush=True)
        selected = kexts.select_kexts(hw, macos_version)
        print(f"✓ ({len(selected)} kexts)")
        kexts.print_kext_summary(selected, hw, macos_version)
        print(t("dry_run_done"))
        _stop_log()
        sys.exit(0)

    print()

    # ── Build mode: new or update ─────────────────────────────────────────────
    build_mode = _ask_build_mode(output_dir)
    if build_mode == "update":
        print(t("update_mode"))
    print()

    # ── Step 3: Download kexts ────────────────────────────────────────────────
    selected, failed = kexts.select_and_download(hw, macos_version, kexts_dir)
    if failed:
        print(t("kexts_failed", n=len(failed), names=", ".join(failed)))
    print()

    import efi_builder
    import config_plist

    if build_mode == "update":
        update_result = efi_builder.update_efi(kexts_dir, output_dir, hardware=hw)
        if not update_result.get("ok"):
            print(t("efi_fail"))
            _stop_log()
            sys.exit(1)
        config_path = os.path.join(output_dir, "EFI", "OC", "config.plist")
        efi_builder.run_ocvalidate(update_result.get("ocvalidate"), config_path)

    else:
        # ── Step 4: EFI + OpenCore + recovery ────────────────────────────────
        build_result = efi_builder.build(macos_version, kexts_dir, output_dir, hardware=hw)
        if not build_result.get("ok"):
            print(t("efi_fail"))
            _stop_log()
            sys.exit(1)
        print()

        # ── Step 5: config.plist ──────────────────────────────────────────────
        config_path = config_plist.generate(
            hw, selected, macos_version, output_dir,
            ssdts=build_result.get("ssdts", []),
            opencanopy=build_result.get("opencanopy", False),
        )
        if not config_path:
            print(t("plist_fail"))
            _stop_log()
            sys.exit(1)

        config_plist.print_summary(config_path, hw, selected)
        efi_builder.run_ocvalidate(build_result.get("ocvalidate"), config_path)

    # ── USB Mapper (macOS only) ───────────────────────────────────────────────
    if platform.system() == "Darwin":
        import usb_mapper
        smbios = config_plist._get_smbios(hw)
        usb_mapper.run(smbios, kexts_dir, output_dir, config_path)

    # ── CoreSync.app (macOS only) ─────────────────────────────────────────────
    if platform.system() == "Darwin":
        import build_coresync
        app_path = build_coresync.build(output_dir)
        if app_path:
            print(t("coresync_ready"))

    # ── BIOS checklist ────────────────────────────────────────────────────────
    _print_bios_checklist()

    # ── Export EFI mode ───────────────────────────────────────────────────────
    if args.export_efi:
        import shutil
        export_path = os.path.join(os.path.expanduser("~/Desktop"), "AutoCore_EFI")
        print(t("export_notice", path=export_path))
        efi_src = os.path.join(output_dir, "EFI")
        if os.path.exists(export_path):
            shutil.rmtree(export_path)
        shutil.copytree(efi_src, export_path)
        print(t("export_done", path=export_path))
        if log_path:
            print(t("log_saved", path=log_path))
        _stop_log()
        sys.exit(0)

    # ── Step 6: Flash USB ─────────────────────────────────────────────────────
    import usb
    success = usb.flash_usb(output_dir, hardware=hw)

    if success:
        print()
        print("  ╔══════════════════════════════════════════════════════╗")
        print(t("done_title"))
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print(t("done_next"))
        print(t("done_step1"))
        print(t("done_step2"))
        print(t("done_step3"))
        print(t("done_step4"))
        print(t("done_step4b"))
        print()
    else:
        print()
        print(t("flash_fail"))
        print(t("efi_available", path=output_dir))
        print()

    if log_path:
        print(t("log_saved", path=log_path))
    _stop_log()


if __name__ == "__main__":
    main()
