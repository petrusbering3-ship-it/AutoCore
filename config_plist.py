"""
AutoCore — config_plist.py
Generates EFI/OC/config.plist by modifying sample.plist with hardware-specific settings.
Platform Info (serial, MLB, UUID, ROM) is generated automatically via macserial.
"""

import os
import re
import sys
import subprocess
import platform
import plistlib
import random
import uuid as _uuid_mod

from lang import t
from utils import _ensure_deps

requests = _ensure_deps()

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAMPLE = os.path.join(SCRIPT_DIR, "sample.plist")


# ─── SMBIOS table ─────────────────────────────────────────────────────────────

SMBIOS_TABLE = {
    ("4",  True):  "MacBookPro11,4",  ("4",  False): "iMac15,1",
    ("5",  True):  "MacBookPro12,1",  ("5",  False): "iMac16,2",
    ("6",  True):  "MacBookPro13,1",  ("6",  False): "iMac17,1",
    ("7",  True):  "MacBookPro14,1",  ("7",  False): "iMac18,3",
    ("8",  True):  "MacBookPro15,2",  ("8",  False): "iMac19,1",
    ("9",  True):  "MacBookPro15,2",  ("9",  False): "iMac19,1",
    ("10", True):  "MacBookPro16,2",  ("10", False): "iMac20,1",
    ("11", True):  "MacBookPro18,3",  ("11", False): "iMacPro1,1",
    ("12", True):  "MacBookPro18,3",  ("12", False): "MacPro7,1",
    ("13", True):  "MacBookPro18,3",  ("13", False): "MacPro7,1",
    ("14", True):  "MacBookPro18,3",  ("14", False): "MacPro7,1",
}

# ─── iGPU platform IDs ────────────────────────────────────────────────────────

IGPU_PLATFORM_ID = {
    ("4",  True):  bytes([0x03, 0x00, 0x26, 0x0d]),
    ("4",  False): bytes([0x03, 0x00, 0x22, 0x0d]),
    ("5",  True):  bytes([0x06, 0x00, 0x26, 0x16]),
    ("5",  False): bytes([0x07, 0x00, 0x22, 0x16]),
    ("6",  True):  bytes([0x00, 0x00, 0x16, 0x19]),
    ("6",  False): bytes([0x00, 0x00, 0x12, 0x19]),
    ("7",  True):  bytes([0x00, 0x00, 0x16, 0x59]),
    ("7",  False): bytes([0x03, 0x00, 0x12, 0x59]),
    ("8",  True):  bytes([0x09, 0x00, 0xa5, 0x3e]),
    ("8",  False): bytes([0x07, 0x00, 0x9b, 0x3e]),
    ("9",  True):  bytes([0x09, 0x00, 0xa5, 0x3e]),
    ("9",  False): bytes([0x07, 0x00, 0x9b, 0x3e]),
    ("10", True):  bytes([0x09, 0x00, 0xa5, 0x3e]),
    ("10", False): bytes([0x07, 0x00, 0x9b, 0x3e]),
    ("11", True):  bytes([0x02, 0x00, 0x9a, 0x8a]),
    ("11", False): bytes([0x03, 0x00, 0xc8, 0x9b]),
    ("12", True):  bytes([0x02, 0x00, 0xfb, 0x89]),
    ("12", False): bytes([0x00, 0x00, 0x6e, 0x9a]),
    ("13", True):  bytes([0x02, 0x00, 0xfb, 0x89]),
    ("13", False): bytes([0x00, 0x00, 0x6e, 0x9a]),
    ("14", True):  bytes([0x02, 0x00, 0xfb, 0x89]),
    ("14", False): bytes([0x00, 0x00, 0x6e, 0x9a]),
}

# ─── Audio codec → AppleALC layout ID ────────────────────────────────────────

CODEC_LAYOUT_MAP = {
    0x10EC0221: ("ALC221",  11), 0x10EC0225: ("ALC225",  28),
    0x10EC0230: ("ALC230",   3), 0x10EC0233: ("ALC233",   3),
    0x10EC0235: ("ALC235",  11), 0x10EC0245: ("ALC245",  15),
    0x10EC0255: ("ALC255",  66), 0x10EC0256: ("ALC256",  69),
    0x10EC0257: ("ALC257",  11), 0x10EC0269: ("ALC269",   1),
    0x10EC0270: ("ALC270",  15), 0x10EC0272: ("ALC272",   3),
    0x10EC0274: ("ALC274",  21), 0x10EC0280: ("ALC280",  14),
    0x10EC0282: ("ALC282",   3), 0x10EC0283: ("ALC283",  11),
    0x10EC0285: ("ALC285",  71), 0x10EC0286: ("ALC286",   3),
    0x10EC0289: ("ALC289",  87), 0x10EC0290: ("ALC290",   3),
    0x10EC0292: ("ALC292",  12), 0x10EC0293: ("ALC293",   3),
    0x10EC0295: ("ALC295",  15), 0x10EC0298: ("ALC298",  28),
    0x10EC0299: ("ALC299",  72), 0x10EC0300: ("ALC300",  99),
    0x10EC0623: ("ALC623",  13), 0x10EC0671: ("ALC671",  11),
    0x10EC0700: ("ALC700",  75), 0x10EC0892: ("ALC892",   1),
    0x10EC0897: ("ALC897",  13), 0x10EC1150: ("ALC1150",  1),
    0x10EC1220: ("ALC1220",  1),
    0x111D76D1: ("IDT92HD71",  3), 0x111D7605: ("IDT92HD75B", 3),
    0x14F15069: ("CX20585",    3), 0x14F15098: ("CX20598",    3),
    0x1106E721: ("VT1802",     3),
}


def _get_audio_layout(audio_codec_str):
    try:
        codec_id = int(audio_codec_str)
        entry = CODEC_LAYOUT_MAP.get(codec_id)
        if entry:
            return entry[0], entry[1]
        masked = codec_id & 0xFFFFFF00
        for key, val in CODEC_LAYOUT_MAP.items():
            if (key & 0xFFFFFF00) == masked:
                return val[0], val[1]
    except (ValueError, TypeError):
        pass
    return "Unknown", 1


# ─── Kext metadata ────────────────────────────────────────────────────────────

KEXT_META = {
    "Lilu":                         ("Lilu.kext",                         "Contents/MacOS/Lilu",                         "", ""),
    "VirtualSMC":                   ("VirtualSMC.kext",                   "Contents/MacOS/VirtualSMC",                   "", ""),
    "SMCProcessor":                 ("SMCProcessor.kext",                 "Contents/MacOS/SMCProcessor",                 "", ""),
    "SMCSuperIO":                   ("SMCSuperIO.kext",                   "Contents/MacOS/SMCSuperIO",                   "", ""),
    "WhateverGreen":                ("WhateverGreen.kext",                "Contents/MacOS/WhateverGreen",                "", ""),
    "AppleALC":                     ("AppleALC.kext",                     "Contents/MacOS/AppleALC",                     "", ""),
    "RestrictEvents":               ("RestrictEvents.kext",               "Contents/MacOS/RestrictEvents",               "", ""),
    "NVMeFix":                      ("NVMeFix.kext",                      "Contents/MacOS/NVMeFix",                      "", ""),
    "CPUFriend":                    ("CPUFriend.kext",                    "Contents/MacOS/CPUFriend",                    "", ""),
    "CpuTscSync":                   ("CpuTscSync.kext",                   "Contents/MacOS/CpuTscSync",                   "", ""),
    "AmdTscSync":                   ("AmdTscSync.kext",                   "Contents/MacOS/AmdTscSync",                   "", ""),
    "AMDRyzenCPUPowerManagement":   ("AMDRyzenCPUPowerManagement.kext",   "Contents/MacOS/AMDRyzenCPUPowerManagement",   "", ""),
    "SMCAMDProcessor":              ("SMCAMDProcessor.kext",              "Contents/MacOS/SMCAMDProcessor",              "", ""),
    "IntelMausi":                   ("IntelMausi.kext",                   "Contents/MacOS/IntelMausi",                   "", ""),
    "RealtekRTL8111":               ("RealtekRTL8111.kext",               "Contents/MacOS/RealtekRTL8111",               "", ""),
    "AtherosE2200Ethernet":         ("AtherosE2200Ethernet.kext",         "Contents/MacOS/AtherosE2200Ethernet",         "", ""),
    "LucyRTL8125Ethernet":          ("LucyRTL8125Ethernet.kext",          "Contents/MacOS/LucyRTL8125Ethernet",          "", ""),
    "AppleIGB":                     ("AppleIGB.kext",                     "Contents/MacOS/AppleIGB",                     "", ""),
    "AirportItlwm":                 ("AirportItlwm.kext",                 "Contents/MacOS/AirportItlwm",                 "", ""),
    "itlwm":                        ("itlwm.kext",                        "Contents/MacOS/itlwm",                        "", ""),
    "AirportBrcmFixup":             ("AirportBrcmFixup.kext",             "Contents/MacOS/AirportBrcmFixup",             "", ""),
    "IntelBluetoothFirmware":       ("IntelBluetoothFirmware.kext",       "Contents/MacOS/IntelBluetoothFirmware",       "", ""),
    "IntelBTPatcher":               ("IntelBTPatcher.kext",               "Contents/MacOS/IntelBTPatcher",               "", ""),
    "BlueToolFixup":                ("BlueToolFixup.kext",                "Contents/MacOS/BlueToolFixup",                "21.0.0", ""),
    "BrcmPatchRAM3":                ("BrcmPatchRAM3.kext",                "Contents/MacOS/BrcmPatchRAM3",                "", ""),
    "BrcmFirmwareData":             ("BrcmFirmwareData.kext",             "",                                            "", ""),
    "BrcmBluetoothInjector":        ("BrcmBluetoothInjector.kext",        "",                                            "", "20.99.99"),
    "VoodooPS2Controller":          ("VoodooPS2Controller.kext",          "Contents/MacOS/VoodooPS2Controller",          "", ""),
    "VoodooI2C":                    ("VoodooI2C.kext",                    "Contents/MacOS/VoodooI2C",                    "", ""),
    "VoodooI2CHID":                 ("VoodooI2CHID.kext",                 "Contents/MacOS/VoodooI2CHID",                 "", ""),
    "VoodooRMI":                    ("VoodooRMI.kext",                    "Contents/MacOS/VoodooRMI",                    "", ""),
    "VoodooSMBus":                  ("VoodooSMBus.kext",                  "Contents/MacOS/VoodooSMBus",                  "", ""),
    "AlpsHID":                      ("AlpsHID.kext",                      "Contents/MacOS/AlpsHID",                      "", ""),
    "ECEnabler":                    ("ECEnabler.kext",                    "Contents/MacOS/ECEnabler",                    "", ""),
    "SMCBatteryManager":            ("SMCBatteryManager.kext",            "Contents/MacOS/SMCBatteryManager",            "", ""),
    "BrightnessKeys":               ("BrightnessKeys.kext",               "Contents/MacOS/BrightnessKeys",               "", ""),
    "HibernationFixup":             ("HibernationFixup.kext",             "Contents/MacOS/HibernationFixup",             "", ""),
    "NoTouchID":                    ("NoTouchID.kext",                    "Contents/MacOS/NoTouchID",                    "", ""),
    "RadeonSensor":                 ("RadeonSensor.kext",                 "Contents/MacOS/RadeonSensor",                 "", ""),
    "SMCRadeonGPU":                 ("SMCRadeonGPU.kext",                 "Contents/MacOS/SMCRadeonGPU",                 "", ""),
    "RTCMemoryFixup":               ("RTCMemoryFixup.kext",               "Contents/MacOS/RTCMemoryFixup",               "", ""),
    "FeatureUnlock":                ("FeatureUnlock.kext",                "Contents/MacOS/FeatureUnlock",                "", ""),
    "CryptexFixup":                 ("CryptexFixup.kext",                 "Contents/MacOS/CryptexFixup",                 "", ""),
    "GenericUSBXHCI":               ("GenericUSBXHCI.kext",               "Contents/MacOS/GenericUSBXHCI",               "", ""),
    "RealtekCardReader":            ("RealtekCardReader.kext",            "Contents/MacOS/RealtekCardReader",            "", ""),
    "RealtekCardReaderFriend":      ("RealtekCardReaderFriend.kext",      "Contents/MacOS/RealtekCardReaderFriend",      "", ""),
    "AsusSMC":                      ("AsusSMC.kext",                      "Contents/MacOS/AsusSMC",                      "", ""),
    "YogaSMC":                      ("YogaSMC.kext",                      "Contents/MacOS/YogaSMC",                      "", ""),
    "USBToolBox":                   ("USBToolBox.kext",                   "Contents/MacOS/USBToolBox",                   "", ""),
    "UTBMap":                       ("UTBMap.kext",                       "",                                            "", ""),
}

KEXT_ORDER = [
    "Lilu", "VirtualSMC", "SMCProcessor", "SMCSuperIO",
    "WhateverGreen", "AppleALC", "RestrictEvents", "NVMeFix",
    "CPUFriend", "CpuTscSync", "AmdTscSync",
    "AMDRyzenCPUPowerManagement", "SMCAMDProcessor",
    "RTCMemoryFixup", "FeatureUnlock", "CryptexFixup",
    "RadeonSensor", "SMCRadeonGPU",
    "IntelMausi", "RealtekRTL8111", "AtherosE2200Ethernet",
    "LucyRTL8125Ethernet", "AppleIGB",
    "AirportItlwm", "itlwm", "AirportBrcmFixup",
    "IntelBluetoothFirmware", "IntelBTPatcher", "BlueToolFixup",
    "BrcmPatchRAM3", "BrcmFirmwareData", "BrcmBluetoothInjector",
    "VoodooPS2Controller", "VoodooI2C", "VoodooI2CHID",
    "VoodooRMI", "VoodooSMBus", "AlpsHID",
    "ECEnabler", "SMCBatteryManager", "BrightnessKeys",
    "HibernationFixup", "NoTouchID",
    "GenericUSBXHCI", "USBToolBox", "UTBMap",
    "RealtekCardReader", "RealtekCardReaderFriend",
    "AsusSMC", "YogaSMC",
]

KEXT_EXPAND = {
    "VirtualSMC":   ["VirtualSMC", "SMCProcessor", "SMCSuperIO"],
    "BrcmPatchRAM": ["BrcmPatchRAM3", "BrcmFirmwareData", "BrcmBluetoothInjector"],
    "VoodooI2C":    ["VoodooI2C", "VoodooI2CHID"],
}


# ─── macserial ────────────────────────────────────────────────────────────────

_MACSERIAL_REPO = "acidanthera/macserial"
_MACSERIAL_ASSET_KEY = {"Darwin": "mac", "Windows": "win"}

_SERIAL_SUFFIXES = {
    "MacBookPro11,4": "DRJM", "MacBookPro12,1": "DV35", "MacBookPro13,1": "GH7H",
    "MacBookPro14,1": "HB21", "MacBookPro15,2": "LVDN", "MacBookPro16,2": "THCD",
    "MacBookPro16,3": "THCA", "MacBookPro18,3": "T6QP", "iMac15,1": "DHJQ",
    "iMac16,2": "DHKP", "iMac17,1": "DHQ8", "iMac18,3": "J9JN",
    "iMac19,1": "JCMH", "iMac20,1": "JDQ4", "iMacPro1,1": "J09P",
    "MacPro7,1": "LKCH",
}

_SERIAL_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
_YEAR_CHARS   = "STVWXYZ"


def _download_macserial(tools_dir):
    import zipfile, io
    os_name   = platform.system()
    asset_key = _MACSERIAL_ASSET_KEY.get(os_name)
    if not asset_key:
        print(t("macserial_unavail"))
        return None

    os.makedirs(tools_dir, exist_ok=True)
    fname = "macserial.exe" if os_name == "Windows" else "macserial"
    dest  = os.path.join(tools_dir, fname)

    if os.path.exists(dest) and os.path.getsize(dest) > 10_000:
        return dest

    try:
        api_url = f"https://api.github.com/repos/{_MACSERIAL_REPO}/releases/latest"
        r = requests.get(api_url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        assets = r.json().get("assets", [])
        asset  = next((a for a in assets if asset_key in a["name"] and a["name"].endswith(".zip")), None)
        if not asset:
            return None
        r2 = requests.get(asset["browser_download_url"], timeout=30)
        r2.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r2.content)) as z:
            binary_entry = next((e for e in z.namelist() if e == fname or e.endswith("/" + fname)), None)
            if not binary_entry:
                return None
            with z.open(binary_entry) as src, open(dest, "wb") as dst:
                dst.write(src.read())
        if os_name != "Windows":
            os.chmod(dest, 0o755)
        return dest
    except Exception as e:
        print(f"\n    ! macserial download failed: {e}")
        return None


def _run_macserial(binary, model):
    try:
        result = subprocess.run(
            [binary, "-n", "1", "-m", model],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and len(parts[0]) == 12:
                return parts[0], parts[1]
    except Exception as e:
        print(f"\n    ! macserial failed: {e}")
    return None, None


def _generate_serial_fallback(model):
    factory = "C02"
    year    = random.choice(_YEAR_CHARS)
    week    = random.choice("123456789ABCDEFGHJKLMNPQRST")
    unique  = "".join(random.choices(_SERIAL_CHARS, k=3))
    suffix  = _SERIAL_SUFFIXES.get(model, "XXXX")
    serial  = factory + year + week + unique + suffix
    mlb_pad = "".join(random.choices(_SERIAL_CHARS, k=9))
    mlb     = factory + year + week + mlb_pad + suffix[:3]
    return serial, mlb


def _get_rom_bytes():
    node = _uuid_mod.getnode()
    if node & (1 << 40):
        rom = bytes([random.randint(0, 255) for _ in range(6)])
        rom = bytes([rom[0] & 0xFE | 0x02]) + rom[1:]
    else:
        rom = node.to_bytes(6, "big")
    return rom


def _generate_platform_info(smbios_model, tools_dir):
    binary = _download_macserial(tools_dir)
    if binary:
        serial, mlb    = _run_macserial(binary, smbios_model)
        used_macserial = serial is not None
    else:
        serial, mlb    = None, None
        used_macserial = False
    if not serial:
        serial, mlb = _generate_serial_fallback(smbios_model)
    return {
        "serial":         serial,
        "mlb":            mlb,
        "system_uuid":    str(_uuid_mod.uuid4()).upper(),
        "rom":            _get_rom_bytes(),
        "used_macserial": used_macserial,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_gen_prefix(hardware):
    gen_str = hardware.get("cpu_generation", "")
    m = re.search(r'(\d+)\. gen', gen_str)
    return m.group(1) if m else "8"


def _is_ice_lake(cpu_str):
    return bool(re.search(r'i[3579]-10\d{2}[Gg]\d', cpu_str or ""))


def _get_smbios(hardware):
    gen       = _get_gen_prefix(hardware)
    is_laptop = hardware.get("is_laptop", False)
    vendor    = hardware.get("cpu_vendor", "Intel")
    if vendor == "AMD":
        return "iMacPro1,1"
    if gen == "10" and is_laptop and _is_ice_lake(hardware.get("cpu", "")):
        return "MacBookPro16,3"
    return SMBIOS_TABLE.get((gen, is_laptop), "iMac20,1")


def _get_igpu_platform_id(hardware):
    vendor = hardware.get("cpu_vendor", "Intel")
    if vendor != "Intel":
        return None
    gpus     = [g.lower() for g in hardware.get("gpus", [])]
    has_igpu = any("intel" in g for g in gpus) or not gpus
    if not has_igpu:
        return None
    gen       = _get_gen_prefix(hardware)
    is_laptop = hardware.get("is_laptop", False)
    if gen == "10" and is_laptop and _is_ice_lake(hardware.get("cpu", "")):
        platform_id = bytes([0x00, 0x00, 0x52, 0x8a])
    else:
        platform_id = IGPU_PLATFORM_ID.get((gen, is_laptop))
    if not platform_id:
        return None
    props = {"AAPL,ig-platform-id": platform_id}
    if is_laptop:
        props["framebuffer-patch-enable"] = bytes([0x01, 0x00, 0x00, 0x00])
    return props


def _expand_kexts(selected_names):
    expanded = []
    seen = set()
    for name in selected_names:
        for sub in KEXT_EXPAND.get(name, [name]):
            if sub not in seen:
                expanded.append(sub)
                seen.add(sub)
    return expanded


def _build_kext_entries(selected_names, kexts_dir=None):
    expanded = set(_expand_kexts(selected_names))
    if kexts_dir and os.path.isdir(os.path.join(kexts_dir, "UTBMap.kext")):
        expanded.add("UTBMap")
    entries = []
    for name in KEXT_ORDER:
        if name not in expanded:
            continue
        meta = KEXT_META.get(name)
        if not meta:
            continue
        bundle, executable, min_kernel, max_kernel = meta
        entries.append({
            "Arch":           "x86_64",
            "BundlePath":     bundle,
            "Comment":        "",
            "Enabled":        True,
            "ExecutablePath": executable,
            "MaxKernel":      max_kernel,
            "MinKernel":      min_kernel,
            "PlistPath":      "Contents/Info.plist",
        })
    return entries


def _get_kernel_quirks(hardware, macos_version="Sonoma"):
    from constants import MACOS_ORDER
    gen     = _get_gen_prefix(hardware)
    vendor  = hardware.get("cpu_vendor", "Intel")
    gen_num = int(gen) if gen.isdigit() else 8
    quirks  = {}

    if vendor == "AMD":
        quirks["AppleXcpmCfgLock"]   = False
        quirks["AppleXcpmExtraMsrs"] = False
        quirks["DisableIoMapper"]    = True
        return quirks

    quirks["AppleXcpmCfgLock"]    = True
    quirks["DisableIoMapper"]     = True
    quirks["ReleaseUsbOwnership"] = True

    # XhciPortLimit: True for Big Sur and below, False for Monterey+
    macos_idx     = MACOS_ORDER.index(macos_version) if macos_version in MACOS_ORDER else 3
    monterey_idx  = MACOS_ORDER.index("Monterey")
    quirks["XhciPortLimit"] = (macos_idx < monterey_idx)

    if gen_num >= 12:
        quirks["ProvideCurrentCpuInfo"] = True
    if gen_num <= 4:
        quirks["AppleCpuPmCfgLock"] = True

    return quirks


def _get_boot_args(hardware, audio_layout=None):
    args    = ["-v", "keepsyms=1", "debug=0x100"]
    gen     = _get_gen_prefix(hardware)
    gen_num = int(gen) if gen.isdigit() else 8

    if gen_num >= 12:
        args.append("revpatch=sbvmm,cpuname")

    is_laptop = hardware.get("is_laptop", False)
    gpus      = [g.lower() for g in hardware.get("gpus", [])]
    # Only add -wegnoegpu on desktops — on laptops it breaks iGPU display output
    if not is_laptop and any("nvidia" in g or "gtx" in g or "rtx" in g for g in gpus):
        args.append("-wegnoegpu")

    layout = audio_layout if audio_layout else 1
    args.append(f"alcid={layout}")
    return " ".join(args)


def _add_ssdt_entries(config, ssdt_files):
    if not ssdt_files:
        return
    existing       = config.get("ACPI", {}).get("Add", [])
    existing_paths = {e.get("Path", "") for e in existing}
    for ssdt in ssdt_files:
        if ssdt not in existing_paths:
            existing.append({"Comment": "", "Enabled": True, "Path": ssdt})
    config.setdefault("ACPI", {})["Add"] = existing


def _get_acpi_patches(hardware):
    patches   = []
    is_laptop = hardware.get("is_laptop", False)
    gen_str   = hardware.get("cpu_generation", "")
    m         = re.search(r'(\d+)\. gen', gen_str)
    gen       = int(m.group(1)) if m else 8
    if is_laptop and gen >= 5:
        patches.append({
            "Base": "", "BaseSkip": 0, "Comment": "_OSI to XOSI",
            "Count": 0, "Enabled": True,
            "Find": bytes.fromhex("5F4F5349"), "Limit": 0,
            "Mask": bytes(4), "OemTableId": bytes(8),
            "Replace": bytes.fromhex("584F5349"), "ReplaceMask": bytes(4),
            "Skip": 0, "TableLength": 0, "TableSignature": bytes(4),
        })
    return patches


def _configure_opencanopy(config, opencanopy_available):
    if not opencanopy_available:
        return
    try:
        config.setdefault("Misc", {}).setdefault("Boot", {})["PickerMode"] = "External"
        config["Misc"]["Boot"]["ShowPicker"] = True
    except Exception:
        pass


def _ensure_opencanopy_driver(config):
    try:
        drivers = config.setdefault("UEFI", {}).setdefault("Drivers", [])
        paths   = {d.get("Path", "") if isinstance(d, dict) else d for d in drivers}
        if "OpenCanopy.efi" not in paths:
            drivers.append({
                "Arguments": "", "Comment": "", "Enabled": True,
                "LoadEarly": False, "Path": "OpenCanopy.efi",
            })
    except Exception:
        pass


# ─── Main generate function ───────────────────────────────────────────────────

def generate(hardware, selected_kexts, macos_version, efi_dir, sample_path=None,
             ssdts=None, opencanopy=False):
    print(t("plist_generating"))

    # Fix sample.plist path — use absolute path from script location
    sample = sample_path or DEFAULT_SAMPLE
    if not os.path.exists(sample):
        print(t("plist_not_found", path=sample))
        return None

    with open(sample, "rb") as f:
        config = plistlib.load(f)

    # ── SMBIOS model ─────────────────────────────────────────────────────────
    smbios_model = _get_smbios(hardware)
    config["PlatformInfo"]["Generic"]["SystemProductName"] = smbios_model

    # ── Platform Info ────────────────────────────────────────────────────────
    tools_dir = os.path.join(efi_dir, "_tools")
    print(f"  → Platform Info ({smbios_model})...", end=" ", flush=True)
    pi = _generate_platform_info(smbios_model, tools_dir)

    config["PlatformInfo"]["Generic"]["SystemSerialNumber"] = pi["serial"]
    config["PlatformInfo"]["Generic"]["MLB"]                = pi["mlb"]
    config["PlatformInfo"]["Generic"]["SystemUUID"]         = pi["system_uuid"]
    config["PlatformInfo"]["Generic"]["ROM"]                = pi["rom"]

    src = "macserial" if pi["used_macserial"] else "Python-fallback"
    print(f"✓ ({src})")
    print(f"    Serial : {pi['serial']}")
    print(f"    MLB    : {pi['mlb']}")
    print(f"    UUID   : {pi['system_uuid']}")

    # ── Audio layout-id ──────────────────────────────────────────────────────
    codec_str             = hardware.get("audio_codec", "Unknown")
    codec_name, audio_layout = _get_audio_layout(codec_str)
    if codec_name != "Unknown":
        print(f"    Audio  : {codec_name} → alcid={audio_layout}")
    else:
        print(f"    Audio  : codec {codec_str} — using alcid=1 (fallback)")

    # ── DeviceProperties (iGPU) ──────────────────────────────────────────────
    igpu_props = _get_igpu_platform_id(hardware)
    if igpu_props:
        config.setdefault("DeviceProperties", {}).setdefault("Add", {}) \
            ["PciRoot(0x0)/Pci(0x2,0x0)"] = igpu_props

    # ── ACPI.Add (SSDTs) ─────────────────────────────────────────────────────
    if ssdts:
        _add_ssdt_entries(config, ssdts)

    # ── ACPI.Patch (renames) ─────────────────────────────────────────────────
    acpi_patches = _get_acpi_patches(hardware)
    if acpi_patches:
        existing_patches   = config.setdefault("ACPI", {}).setdefault("Patch", [])
        existing_comments  = {p.get("Comment", "") for p in existing_patches}
        for patch in acpi_patches:
            if patch["Comment"] not in existing_comments:
                existing_patches.append(patch)
        print(f"    ACPI   : {len(acpi_patches)} rename patch(es) added")

    # ── Kernel.Add (kexts in correct order) ──────────────────────────────────
    kexts_dir = os.path.join(efi_dir, "_kexts")
    config.setdefault("Kernel", {})["Add"] = _build_kext_entries(selected_kexts, kexts_dir)

    # ── Kernel.Quirks ────────────────────────────────────────────────────────
    quirks = config.setdefault("Kernel", {}).setdefault("Quirks", {})
    for key, val in _get_kernel_quirks(hardware, macos_version).items():
        quirks[key] = val

    # ── Boot args ────────────────────────────────────────────────────────────
    _nvram_key = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
    config.setdefault("NVRAM", {}).setdefault("Add", {}).setdefault(_nvram_key, {})["boot-args"] = \
        _get_boot_args(hardware, audio_layout)

    # ── OpenCanopy ───────────────────────────────────────────────────────────
    if opencanopy:
        _configure_opencanopy(config, opencanopy)
        _ensure_opencanopy_driver(config)

    # ── Write config.plist ───────────────────────────────────────────────────
    out_dir  = os.path.join(efi_dir, "EFI", "OC")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "config.plist")

    with open(out_path, "wb") as f:
        plistlib.dump(config, f, fmt=plistlib.FMT_XML, sort_keys=False)

    kext_count = len(config["Kernel"]["Add"])
    print(f"  ✓ config.plist ready — {kext_count} kexts")

    _print_warnings(hardware, smbios_model, pi["used_macserial"])
    return out_path


def _print_warnings(hardware, smbios_model, used_macserial):
    gen     = _get_gen_prefix(hardware)
    gen_num = int(gen) if gen.isdigit() else 8

    print()
    print(f"  ┌─ {t('plist_next_steps')} ──────────────────────────────────────────")
    print("  │")

    if not used_macserial:
        print(f"  │  ⚠  {t('plist_serial_fallback')}")
        print(f"  │     {t('plist_serial_tip')}")
        print(f"  │     {t('plist_serial_tip2')}")
        print("  │")

    if gen_num >= 12:
        print(f"  │  {t('plist_ssdt_info_12')}")
    elif gen_num >= 6:
        print(f"  │  {t('plist_ssdt_info_6')}")

    print("  │")
    print(f"  │  {t('plist_coverage_tip')}")
    print("  │  https://checkcoverage.apple.com")
    print("  │")
    print("  └───────────────────────────────────────────────────────────────")
    print()


# ─── Print summary ────────────────────────────────────────────────────────────

def print_summary(config_path, hardware, selected_kexts):
    if not config_path or not os.path.exists(config_path):
        return
    with open(config_path, "rb") as f:
        config = plistlib.load(f)

    pi    = config.get("PlatformInfo", {}).get("Generic", {})
    kexts = config.get("Kernel", {}).get("Add", [])
    args  = config.get("NVRAM", {}).get("Add", {}).get(
        "7C436110-AB2A-4BBB-A880-FE41995C9F82", {}
    ).get("boot-args", "")
    dp   = config.get("DeviceProperties", {}).get("Add", {})
    acpi = config.get("ACPI", {}).get("Add", [])

    serial = pi.get("SystemSerialNumber", "?")
    # Mask serial regardless of length
    if len(serial) >= 4:
        serial_display = serial[:3] + "X" * (len(serial) - 5) + serial[-2:]
    else:
        serial_display = "????"

    print("\n" + "=" * 52)
    print(f"  {t('plist_title')}")
    print("=" * 52)
    print(f"  SMBIOS      : {pi.get('SystemProductName', '?')}")
    print(f"  Serial      : {serial_display}")
    print(f"  MLB         : {pi.get('MLB', '?')[:6]}...")
    print(f"  UUID        : {pi.get('SystemUUID', '?')[:8]}...")
    print(f"  Boot args   : {args}")
    print(f"  {t('plist_kexts_lbl'):<12}: {len(kexts)}")
    if acpi:
        print(f"  SSDTs       : {', '.join(e.get('Path','') for e in acpi)}")
    if dp:
        print(f"  DevProps    : {', '.join(dp.keys())}")
    print(f"  {t('plist_path_lbl'):<12}: {config_path}")
    print("=" * 52 + "\n")


# ─── Standalone test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_hw = {
        "cpu": "Intel Core i5-6200U", "cpu_vendor": "Intel",
        "cpu_generation": "Skylake (6. gen)", "is_laptop": True,
        "gpus": ["Intel HD Graphics 520"], "has_nvme": False,
        "wifi": "Intel (itlwm)", "ethernet": ["Intel I219V"],
        "trackpad_i2c": True, "audio_codec": "283902611",
    }
    test_kexts = [
        "Lilu", "VirtualSMC", "WhateverGreen", "AppleALC", "RestrictEvents",
        "IntelMausi", "AirportItlwm", "IntelBluetoothFirmware", "IntelBTPatcher",
        "BlueToolFixup", "VoodooPS2", "VoodooI2C", "ECEnabler",
        "SMCBatteryManager", "BrightnessKeys", "USBToolBox",
    ]
    out = generate(test_hw, test_kexts, "Sonoma", "/tmp/autocore_test",
                   ssdts=["SSDT-EC-USBX-LAPTOP.aml", "SSDT-PNLF.aml"])
    if out:
        print_summary(out, test_hw, test_kexts)
