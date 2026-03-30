#!/usr/bin/env python3
"""
AutoCore — main.py
Guides the user from hardware scan to finished hackintosh USB.
"""

import os
import sys
import tempfile
import platform


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
    desktop = os.path.expanduser("~/Desktop")
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


# ─── Translations ─────────────────────────────────────────────────────────────

_T = {
    "DA": {
        "banner":           "  AutoCore — Automatiseret Hackintosh USB-installer",
        "select_version":   "[2/6] Vælg macOS version:",
        "version_prompt":   "  Version [1-{n}]: ",
        "version_chosen":   "  macOS version valgt: {v}",
        "aborted":          "\n\n  Afbrudt.",
        "hw_fail":          "  ✗ Hardware-scanning fejlede. Afslutter.",
        "hw_issues_header": "  ┌─ HARDWARE-PROBLEMER ──────────────────────────────────────",
        "hw_issues_footer": "  └───────────────────────────────────────────────────────────",
        "hw_continue":      "  Hardware er muligvis ikke macOS-kompatibelt. Fortsæt alligevel? [j/N]: ",
        "hw_continue_key":  "j",
        "exiting":          "  Afslutter.",
        "kexts_failed":     "  ! {n} kexts fejlede — fortsætter uden: {names}",
        "efi_fail":         "  ✗ EFI-build fejlede. Afslutter.",
        "plist_fail":       "  ✗ config.plist generering fejlede. Afslutter.",
        "coresync_ready":   "  ✓ CoreSync.app klar — kopieres til USB og gemt på Skrivebordet\n",
        "done_title":       "  ║  ✓  AutoCore fuldført!                               ║",
        "done_next":        "  Hvad sker der nu:",
        "done_step1":       "  1. Sæt USB i din hackintosh og boot fra den (F12/Del/F2)",
        "done_step2":       "  2. Vælg 'Install macOS' i OpenCore-pickeren",
        "done_step3":       "  3. Installer macOS normalt",
        "done_step4":       "  4. Kør CoreSync.app (på USB) for at installere OpenCore",
        "done_step4b":      "     permanent på din harddisk",
        "flash_fail":       "  USB-flash annulleret eller fejlet.",
        "efi_available":    "  EFI-mappen er stadig tilgængelig i: {path}",
        "vm_warning":       "  ⚠  Kører i virtuel maskine — USB-adgang kan være upålidelig",
        "net_check":        "  Tjekker netværksforbindelse...",
        "net_ok":           "  ✓ Netværk OK",
        "net_fail":         "  ✗ Ingen netværksforbindelse — downloads vil fejle",
        "net_continue":     "  Fortsæt alligevel? [j/N]: ",
        "net_continue_key": "j",
        "log_saved":        "  Log gemt til: {path}",
        "hw_report":        "  Hardware-rapport gemt til: {path}",
        "bios_title":       "  ┌─ BIOS-INDSTILLINGER (VIGTIGT) ─────────────────────────────",
        "bios_body": [
            "  │  Inden du booter fra USB — sæt disse indstillinger i BIOS:",
            "  │",
            "  │  ✓ Secure Boot          → Disabled",
            "  │  ✓ CSM / Legacy Boot    → Disabled  (ren UEFI)",
            "  │  ✓ VT-d                 → Disabled  (eller aktiver DisableIoMapper i OC)",
            "  │  ✓ CFG Lock             → Disabled  (hvis muligt)",
            "  │  ✓ XHCI Hand-off        → Enabled",
            "  │  ✓ Above 4G Decoding    → Enabled   (desktop: kræves for GPU)",
            "  │  ✓ DVMT Pre-Alloc       → 64 MB     (laptop: iGPU framebuffer)",
            "  │  ✓ Fast Boot            → Disabled",
            "  │  ✓ OS Type              → Other OS  (eller Windows UEFI)",
        ],
        "bios_footer": "  └───────────────────────────────────────────────────────────",
    },
    "EN": {
        "banner":           "  AutoCore — Automated Hackintosh USB Installer",
        "select_version":   "[2/6] Select macOS version:",
        "version_prompt":   "  Version [1-{n}]: ",
        "version_chosen":   "  macOS version selected: {v}",
        "aborted":          "\n\n  Aborted.",
        "hw_fail":          "  ✗ Hardware scan failed. Exiting.",
        "hw_issues_header": "  ┌─ HARDWARE ISSUES ─────────────────────────────────────────",
        "hw_issues_footer": "  └───────────────────────────────────────────────────────────",
        "hw_continue":      "  Hardware may not be macOS-compatible. Continue anyway? [y/N]: ",
        "hw_continue_key":  "y",
        "exiting":          "  Exiting.",
        "kexts_failed":     "  ! {n} kexts failed — continuing without: {names}",
        "efi_fail":         "  ✗ EFI build failed. Exiting.",
        "plist_fail":       "  ✗ config.plist generation failed. Exiting.",
        "coresync_ready":   "  ✓ CoreSync.app ready — copied to USB and saved to Desktop\n",
        "done_title":       "  ║  ✓  AutoCore complete!                               ║",
        "done_next":        "  What happens next:",
        "done_step1":       "  1. Plug USB into your hackintosh and boot from it (F12/Del/F2)",
        "done_step2":       "  2. Select 'Install macOS' in the OpenCore picker",
        "done_step3":       "  3. Install macOS normally",
        "done_step4":       "  4. Run CoreSync.app (on the USB) to install OpenCore",
        "done_step4b":      "     permanently onto your hard drive",
        "flash_fail":       "  USB flash cancelled or failed.",
        "efi_available":    "  EFI folder is still available at: {path}",
        "vm_warning":       "  ⚠  Running inside a virtual machine — USB access may be unreliable",
        "net_check":        "  Checking network connection...",
        "net_ok":           "  ✓ Network OK",
        "net_fail":         "  ✗ No network connection — downloads will fail",
        "net_continue":     "  Continue anyway? [y/N]: ",
        "net_continue_key": "y",
        "log_saved":        "  Log saved to: {path}",
        "hw_report":        "  Hardware report saved to: {path}",
        "bios_title":       "  ┌─ BIOS SETTINGS (IMPORTANT) ────────────────────────────────",
        "bios_body": [
            "  │  Before booting from USB — set these options in BIOS:",
            "  │",
            "  │  ✓ Secure Boot          → Disabled",
            "  │  ✓ CSM / Legacy Boot    → Disabled  (pure UEFI)",
            "  │  ✓ VT-d                 → Disabled  (or enable DisableIoMapper in OC)",
            "  │  ✓ CFG Lock             → Disabled  (if available)",
            "  │  ✓ XHCI Hand-off        → Enabled",
            "  │  ✓ Above 4G Decoding    → Enabled   (desktop: required for GPU)",
            "  │  ✓ DVMT Pre-Alloc       → 64 MB     (laptop: iGPU framebuffer)",
            "  │  ✓ Fast Boot            → Disabled",
            "  │  ✓ OS Type              → Other OS  (or Windows UEFI)",
        ],
        "bios_footer": "  └───────────────────────────────────────────────────────────",
    },
}

LANG = "DA"  # set by _ask_language()


def t(key, **kwargs):
    """Returns the translated string for the current language."""
    s = _T[LANG].get(key, _T["EN"].get(key, key))
    return s.format(**kwargs) if kwargs else s


# ─── Language selector ────────────────────────────────────────────────────────

def _ask_language():
    global LANG
    print()
    print("  Vælg sprog / Select language:")
    print("    [1] Dansk")
    print("    [2] English")
    print()
    while True:
        try:
            val = input("  [1/2]: ").strip()
            if val == "1":
                LANG = "DA"
                return
            if val == "2":
                LANG = "EN"
                return
        except (ValueError, KeyboardInterrupt):
            print()
            sys.exit(0)


# ─── Network check ────────────────────────────────────────────────────────────

def _check_network():
    print(t("net_check"), end=" ", flush=True)
    try:
        import urllib.request
        urllib.request.urlopen("https://github.com", timeout=8)
        print(t("net_ok"))
        return True
    except Exception:
        pass
    # Second try: Apple CDN
    try:
        urllib.request.urlopen("https://oscdn.apple.com", timeout=8)
        print(t("net_ok"))
        return True
    except Exception:
        pass

    print(t("net_fail"))
    try:
        val = input(t("net_continue")).strip().lower()
        return val == t("net_continue_key")
    except (KeyboardInterrupt, EOFError):
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ask_macos_version():
    from kexts import MACOS_VERSIONS
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
        return val == t("hw_continue_key")
    except KeyboardInterrupt:
        return False


def _print_bios_checklist():
    print()
    print(t("bios_title"))
    for line in t("bios_body"):
        print(line)
    print(t("bios_footer"))
    print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Language selector — always shown first, bilingual prompt
    _ask_language()

    # Start logging to ~/Desktop/autocore_log.txt
    log_path = _start_log()

    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║                                                      ║")
    print(f"  ║  {t('banner'):<52}  ║")
    print(f"  ║                                                      ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    # ── Netværkstjek / Network check ─────────────────────────────────────────
    if not _check_network():
        print(t("exiting"))
        _stop_log()
        sys.exit(0)

    print()

    # ── Trin 1 / Step 1: Hardware ─────────────────────────────────────────────
    import hardware
    hw = hardware.scan()
    if not hw:
        print(t("hw_fail"))
        _stop_log()
        sys.exit(1)
    hardware.print_summary(hw, lang=LANG)

    # VM advarsel
    if hw.get("is_vm"):
        print(t("vm_warning"))
        print()

    if not _confirm_compatibility(hw):
        print(t("exiting"))
        _stop_log()
        sys.exit(0)

    # Gem hardware-rapport til skrivebordet
    report_path = hardware.save_report(hw)
    if report_path:
        print(t("hw_report", path=report_path))

    # ── Trin 2 / Step 2: macOS version ───────────────────────────────────────
    macos_version = _ask_macos_version()
    print(t("version_chosen", v=macos_version))

    # ── Output directory ──────────────────────────────────────────────────────
    output_dir = os.path.join(tempfile.gettempdir(), "autocore_build")
    kexts_dir  = os.path.join(output_dir, "_kexts")
    os.makedirs(output_dir, exist_ok=True)

    print()

    # ── Trin 3 / Step 3: Kexts ───────────────────────────────────────────────
    import kexts
    selected, failed = kexts.select_and_download(hw, macos_version, kexts_dir)
    if failed:
        print(t("kexts_failed", n=len(failed), names=", ".join(failed)))

    print()

    # ── Trin 4 / Step 4: EFI + OpenCore + recovery ───────────────────────────
    import efi_builder
    build_result = efi_builder.build(macos_version, kexts_dir, output_dir, hardware=hw)
    if not build_result.get("ok"):
        print(t("efi_fail"))
        _stop_log()
        sys.exit(1)

    print()

    # ── Trin 5 / Step 5: config.plist ────────────────────────────────────────
    import config_plist
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

    # ── OC Validate ──────────────────────────────────────────────────────────
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

    # ── BIOS tjekliste ────────────────────────────────────────────────────────
    _print_bios_checklist()

    # ── Trin 6 / Step 6: Flash USB ───────────────────────────────────────────
    import usb
    success = usb.flash_usb(output_dir)

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
