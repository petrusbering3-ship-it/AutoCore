# AutoCore

Automated OpenCore USB installer. Open one file, answer a few questions, get a ready-to-boot hackintosh USB.
Works on **macOS, Windows and Linux**.

---

## How to use

```
python3 main.py
```

```
  Select language:
    [1] Dansk
    [2] English

[1/6] Scanning hardware...         ✓ Intel i5-6200U, Laptop, Intel WiFi
[2/6] Select macOS version?        > Ventura / Sonoma / Sequoia
[3/6] Selecting kexts...           ✓ 14 kexts selected
[4/6] Building EFI structure...    ✓ OpenCore downloaded
[5/6] Generating config.plist...   ✓ 14 kexts, SMBIOS: MacBookPro13,1
[6/6] Flash to USB...              ✓ Done!
```

---

## Files

| File | Status | What it does |
|------|--------|--------------|
| `hardware.py` | ✅ Done | Scans CPU, GPU, WiFi, ethernet, audio, NVMe, trackpad type and battery. Checks if hardware is macOS-compatible. Works on macOS, Windows and Linux. |
| `kexts.py` | ✅ Done | Automatically selects the correct kexts based on hardware and chosen macOS version. Downloads them from GitHub. Includes USB mapping via USBToolBox. |
| `efi_builder.py` | ✅ Done | Builds a complete EFI folder structure. Downloads OpenCore (RELEASE), copies kexts into EFI/OC/Kexts/, and downloads macOS recovery (com.apple.recovery.boot) directly from Apple. |
| `config_plist.py` | ✅ Done | Generates a complete and correct `config.plist` for OpenCore by modifying `sample.plist`. Platform Info (SMBIOS) is generated automatically using macserial — no placeholders. |
| `sample.plist` | ✅ Done | Base OpenCore config.plist with safe defaults for all sections. Modified by `config_plist.py`. |
| `usb.py` | ✅ Done | Lets the user select a USB drive. Formats and flashes the EFI folder + macOS recovery to the USB. |
| `main.py` | ✅ Done | Ties everything together. The only file the user needs to open. Guides through all 6 steps with language selection (Danish / English). |
| `build_coresync.py` | ✅ Done | Builds **CoreSync.app** — a standalone macOS post-install tool (no Python required) that copies the EFI from the USB to the internal disk after macOS is installed. |

---

## Post-install: CoreSync.app

After installing macOS, run **CoreSync.app** (found on the USB and on your Desktop) to install OpenCore permanently onto your internal drive.

- No Python or other dependencies required
- macOS only
- Backs up any existing EFI before overwriting
- Verifies the copy after installation
- Works by double-clicking — opens Terminal automatically

---

## Kexts selected automatically

### Always included
- **Lilu** — required by almost all other kexts
- **VirtualSMC** — SMC emulation
- **WhateverGreen** — GPU patches and iGPU framebuffer
- **AppleALC** — audio (headphones, microphone, HDMI)
- **RestrictEvents** — CPU name and RAM fix
- **USBToolBox** — USB port mapping

### Based on hardware
- **NVMeFix** — only if NVMe drive detected
- **IntelMausi** — Intel ethernet
- **RealtekRTL8111** — Realtek ethernet
- **AirportItlwm** — Intel WiFi (macOS version specific)
- **AirportBrcmFixup** — Broadcom WiFi
- **IntelBluetoothFirmware** — Intel Bluetooth
- **BlueToolFixup** — Bluetooth fix (Monterey and newer)
- **BrcmPatchRAM** — Broadcom Bluetooth
- **VoodooPS2** — laptop keyboard
- **VoodooI2C** — I2C trackpad (modern laptops)
- **ECEnabler** — battery and Embedded Controller
- **SMCBatteryManager** — battery percentage in menu bar
- **BrightnessKeys** — brightness keys
- **CPUFriend** — CPU power management

---

## Requirements

- Python 3.8+
- No other requirements — missing packages are installed automatically
