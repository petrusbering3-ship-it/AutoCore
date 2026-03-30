<br>
<div align="center">

# 🍎 AutoCore

### Automated OpenCore USB installer.
### Answer a few questions. Get a bootable Hackintosh USB.

**Supports macOS · Windows · Linux**
WIP!
Updates coming soon!

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

[1/6] Scanning hardware...          ✓ Intel Core i5, Intel UHD 620, Realtek ALC293
[2/6] Selecting kexts...            ✓ 14 kexts selected
[3/6] Building EFI...               ✓ OpenCore 1.0.0 downloaded
[4/6] Downloading macOS recovery... ✓ macOS Ventura
[5/6] Generating config.plist...    ✓ 14 kexts, SMBIOS: MacBookPro13,1
[6/6] Flash to USB...               ✓ Done!
```

That's it. No config files. No manual kext hunting. No crying.

<br>

---

## Requirements

- Python 3.8+
- A USB drive (4GB+ recommended)
- Admin / root privileges (needed for USB flashing)
- Compatible hardware (Intel CPU recommended — AMD is a whole other adventure)
- The ability to stay calm when things go sideways

Missing Python packages are installed automatically. You're welcome.

<br>

---

## Files

| File | What it does |
| --- | --- |
| `main.py` | The only file you need to touch. Ties everything together. |
| `hardware.py` | Scans your CPU, GPU, WiFi, ethernet, audio, NVMe, trackpad and battery. Checks macOS compatibility. Works on macOS, Windows and Linux. |
| `kexts.py` | Picks the right kexts for your hardware and macOS version. Downloads them from GitHub automatically. |
| `efi_builder.py` | Builds the full EFI folder. Downloads OpenCore (RELEASE) and grabs macOS recovery straight from Apple. |
| `config_plist.py` | Generates a complete `config.plist` based on your hardware. SMBIOS is auto-generated — no placeholders. |
| `sample.plist` | The base OpenCore config with safe defaults. Modified by `config_plist.py`. Don't touch this. |
| `usb.py` | Handles USB selection, formatting and flashing. This is the part where data loss happens if you pick the wrong drive. |
| `build_coresync.py` | Builds **CoreSync.app** — a post-install tool that copies the EFI to your internal disk. |

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
| | |
| **NVMeFix** | NVMe drive detected |
| | |
| **IntelMausi** | Intel ethernet |
| | |
| **RealtekRTL8111** | Realtek ethernet |
| | |
| **AirportItlwm** | Intel WiFi (version-specific) |
| | |
| **AirportBrcmFixup** | Broadcom WiFi |
| | |
| **IntelBluetoothFirmware** | Intel Bluetooth |
| | |
| **BlueToolFixup** | Bluetooth fix (Monterey+) |
| | |
| **BrcmPatchRAM** | Broadcom Bluetooth |
| | |
| **VoodooPS2** | Laptop keyboard |
| | |
| **VoodooI2C** | I2C trackpad |
| | |
| **ECEnabler** | Battery and Embedded Controller |
| | |
| **SMCBatteryManager** | Battery % in menu bar |
| | |
| **BrightnessKeys** | Brightness keys |
| | |
| **CPUFriend** | CPU power management |
| | |

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
