#!/usr/bin/env python3
"""
AutoCore — main.py
Guides the user from hardware scan to finished hackintosh USB.
"""

import os
import sys
import tempfile
import platform


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


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Language selector — always shown first, bilingual prompt
    _ask_language()

    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║                                                      ║")
    print(f"  ║  {t('banner'):<52}  ║")
    print(f"  ║                                                      ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    # ── Trin 1 / Step 1: Hardware ─────────────────────────────────────────────
    import hardware
    hw = hardware.scan()
    if not hw:
        print(t("hw_fail"))
        sys.exit(1)
    hardware.print_summary(hw)

    if not _confirm_compatibility(hw):
        print(t("exiting"))
        sys.exit(0)

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
    ok = efi_builder.build(macos_version, kexts_dir, output_dir)
    if not ok:
        print(t("efi_fail"))
        sys.exit(1)

    print()

    # ── Trin 5 / Step 5: config.plist ────────────────────────────────────────
    import config_plist
    config_path = config_plist.generate(hw, selected, macos_version, output_dir)
    if not config_path:
        print(t("plist_fail"))
        sys.exit(1)

    config_plist.print_summary(config_path, hw, selected)

    # ── CoreSync.app (macOS only) ─────────────────────────────────────────────
    if platform.system() == "Darwin":
        import build_coresync
        app_path = build_coresync.build(output_dir)
        if app_path:
            print(t("coresync_ready"))

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


if __name__ == "__main__":
    main()
