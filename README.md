<br>
<div align="center">

# 🍎 AutoCore

### Automated OpenCore USB installer.
### Answer a few questions. Get a bootable Hackintosh USB.

**Supports macOS · Windows · Linux**

**v1.2**

</div>

<br>

---

> ⚠️ **Fair warning before you continue:**
> AutoCore does not guarantee a working Hackintosh. If something goes wrong — and in the world of Hackintosh, things *will* go wrong — I am **NOT** responsible if you accidentally format your system. 🤯
>
> Back up your stuff. Seriously. I'm begging you.

---

<br>

## What is this?

AutoCore is my take on automating the OpenCore and Hackintosh process. OpenCore is a bootloader that lets you run macOS on non-Apple hardware — but setting it up manually involves scanning your own hardware, hunting down the right kexts, building an EFI folder, writing a `config.plist` from scratch, and flashing it all to a USB.

It's a lot of steps, and one wrong value in a plist can mean your system doesn't boot at all.

AutoCore handles all of that for you. It scans your hardware, picks the right kexts, builds the EFI, generates the config, and flashes the USB — in one go.

<br>

---

## How to use

```bash
python3 main.py
```

```
  Select language:
    [1] Dansk
    [2] English

[1/6] Scanning hardware...          ✓ Intel i5-6200U, Laptop, Intel WiFi
[2/6] Select macOS version?         > Ventura / Sonoma / Sequoia
[3/6] Selecting kexts...            ✓ 14 kexts selected
[4/6] Building EFI structure...     ✓ OpenCore downloaded
[5/6] Generating config.plist...    ✓ 14 kexts, SMBIOS: MacBookPro13,1
[6/6] Flash to USB...               ✓ Done!
```

That's it. No config files. No manual kext hunting. No crying.

### Flags

```bash
python3 main.py --dry-run      # Scan hardware + show kext selection. No downloads. No flashing. Safe to test.
python3 main.py --export-efi   # Build full EFI to ~/Desktop/AutoCore_EFI instead of flashing USB.
python3 main.py --version      # Print version and exit.
```

<br>

---

## Requirements

- Python 3.8+

Missing Python packages are installed automatically. You're welcome.

<br>

---

## Files

| File | What it does |
| --- | --- |
| `main.py` | Entry point. Ties all 6 steps together. Handles language selection, --dry-run, --export-efi, --version flags. |
| `hardware.py` | Scans CPU, GPU, WiFi, ethernet, audio, NVMe, trackpad, card reader, system vendor and battery. Works on macOS, Windows and Linux. |
| `kexts.py` | Selects and downloads the right kexts for your hardware and macOS version from GitHub. |
| `efi_builder.py` | Builds the full EFI folder. Downloads OpenCore (RELEASE), copies kexts, grabs macOS recovery from Apple. |
| `config_plist.py` | Generates a complete `config.plist`. SMBIOS, serial, MLB and UUID auto-generated via macserial. |
| `usb.py` | Selects, formats and flashes a USB drive. Writes `NEXT_STEPS.md` with BIOS settings to the USB root. |
| `lang.py` | All Danish / English translations. Import `t()` from here — never hardcode UI strings. |
| `utils.py` | Shared helpers: auto-installs missing packages, `check_internet()`. |
| `constants.py` | Shared constants: `MACOS_VERSIONS`, `MACOS_ORDER`. |
| `sample.plist` | Base OpenCore config with safe defaults. Modified by `config_plist.py`. Do not touch. |
| `build_coresync.py` | Builds **CoreSync.app** — post-install tool that copies EFI to your internal disk. No Python required. |

<br>

---

## Post-install: CoreSync.app

After macOS installs, you still need to get OpenCore onto your internal disk — otherwise you'll need the USB every time you boot. That's annoying.

**CoreSync.app** handles it for you:

- No Python or dependencies required
- macOS only
- Backs up your existing EFI before overwriting (you're welcome, again)
- Verifies the copy after installation
- Double-click to run — opens Terminal automatically

Find it on the USB or on your Desktop after install.

<br>

---

## Kexts — selected automatically

### Always included

| Kext | Why |
| --- | --- |
| | |
| **Lilu** | Required by basically everything else |
| | |
| **VirtualSMC** | Tricks macOS into thinking it's on real Apple hardware |
| | |
| **WhateverGreen** | GPU patches and iGPU framebuffer |
| | |
| **AppleALC** | Audio — headphones, mic, HDMI |
| | |
| **RestrictEvents** | CPU name and RAM display fix |
| | |
| **USBToolBox** | USB port mapping |
| | |

<br>

### Based on your hardware

| Kext | When it's included |
| --- | --- |
| **NVMeFix** | NVMe drive detected |
| **IntelMausi** | Intel ethernet |
| **RealtekRTL8111** | Realtek RTL8111/8168 ethernet |
| **AtherosE2200Ethernet** | Atheros / Killer E2200/E2400 ethernet |
| **LucyRTL8125Ethernet** | Realtek RTL8125 2.5GbE ethernet |
| **AppleIGB** | Intel I210/I211/I350 server ethernet |
| **AirportItlwm** | Intel WiFi (matched to your macOS version) |
| **itlwm** | Intel WiFi alternative — more stable, no AirDrop |
| **AirportBrcmFixup** | Broadcom WiFi |
| **IntelBluetoothFirmware** | Intel Bluetooth |
| **IntelBTPatcher** | Intel Bluetooth patcher (required alongside the above) |
| **BlueToolFixup** | Bluetooth fix (Monterey+) |
| **BrcmPatchRAM** | Broadcom Bluetooth |
| **VoodooPS2** | Laptop keyboard |
| **VoodooI2C** | I2C trackpad (modern laptops) |
| **VoodooRMI** | Synaptics trackpad via RMI (smoother than PS2) |
| **VoodooSMBus** | SMBUS driver required by VoodooRMI |
| **AlpsHID** | Alps trackpad |
| **ECEnabler** | Battery and Embedded Controller |
| **SMCBatteryManager** | Battery % in menu bar |
| **BrightnessKeys** | Brightness keys |
| **CPUFriend** | CPU power management |
| **HibernationFixup** | Sleep/wake fix (laptops) |
| **NoTouchID** | Stops TouchID login hang |
| **RadeonSensor + SMCRadeonGPU** | AMD GPU temperature monitoring |
| **CpuTscSync** | TSC sync fix (Intel desktop) |
| **AmdTscSync** | TSC sync fix (AMD) |
| **AMDRyzenCPUPowerManagement** | AMD CPU power + frequency scaling |
| **SMCAMDProcessor** | AMD CPU temps in VirtualSMC |
| **RTCMemoryFixup** | Prevents BIOS reset on reboot (Intel gen 6+) |
| **FeatureUnlock** | Unlocks AirPlay to Mac, Sidecar, Universal Control (Monterey+) |
| **CryptexFixup** | Fixes cryptex mounting on Ventura+ older CPUs |
| **GenericUSBXHCI** | XHCI driver for AMD USB controllers |
| **RealtekCardReader** | Realtek SD card reader |
| **RealtekCardReaderFriend** | Makes card reader appear native |
| **AsusSMC** | ASUS fan, backlight, battery (ASUS laptops) |
| **YogaSMC** | Lenovo fan, backlight, battery (Lenovo laptops) |

<br>

---

## Found a bug?

Open an issue. I'll look at it. No promises on how fast, but I'll look.

AutoCore is a simple project — it won't cover every hardware combo on earth, but I'll try my best to fix what I can.

<br>

---

## Disclaimer (read this, please)

AutoCore is provided as-is. It is a tool, not a miracle.

- It will not fix incompatible hardware
- It will not make AMD CPUs magically work well
- It will **not** be held responsible if you wipe your drive 🤯

**Back up your data before running anything that touches USB drives.**

You have been warned. Twice now.

<br>

---

<div align="center">

*Made with questionable amounts of caffeine and a ThinkPad that probably shouldn't be running macOS.*

</div>
