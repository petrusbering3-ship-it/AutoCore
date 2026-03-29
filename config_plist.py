"""
AutoCore — config_plist.py
Genererer EFI/OC/config.plist ved at modificere sample.plist med hardware-specifikke indstillinger.
Platform Info (serial, MLB, UUID, ROM) genereres automatisk med macserial.
"""

import os
import re
import sys
import subprocess
import platform
import plistlib
import random
import uuid as _uuid_mod

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAMPLE = os.path.join(SCRIPT_DIR, "sample.plist")


# ─── Auto-installer requests ──────────────────────────────────────────────────

def _ensure_deps():
    try:
        import requests
        return requests
    except ImportError:
        print("  [AutoCore] Installerer manglende pakke: requests...", end=" ", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "requests", "--quiet"],
            check=True
        )
        print("✓")
        import requests
        return requests

requests = _ensure_deps()


# ─── SMBIOS tabel ─────────────────────────────────────────────────────────────

SMBIOS_TABLE = {
    ("4",  True):  "MacBookPro11,4",
    ("4",  False): "iMac15,1",
    ("5",  True):  "MacBookPro12,1",
    ("5",  False): "iMac16,2",
    ("6",  True):  "MacBookPro13,1",
    ("6",  False): "iMac17,1",
    ("7",  True):  "MacBookPro14,1",
    ("7",  False): "iMac18,3",
    ("8",  True):  "MacBookPro15,2",
    ("8",  False): "iMac19,1",
    ("9",  True):  "MacBookPro15,2",
    ("9",  False): "iMac19,1",
    ("10", True):  "MacBookPro16,2",
    ("10", False): "iMac20,1",
    ("11", True):  "MacBookPro18,3",
    ("11", False): "iMacPro1,1",
    ("12", True):  "MacBookPro18,3",
    ("12", False): "MacPro7,1",
    ("13", True):  "MacBookPro18,3",
    ("13", False): "MacPro7,1",
    ("14", True):  "MacBookPro18,3",
    ("14", False): "MacPro7,1",
}

# ─── iGPU platform IDs ────────────────────────────────────────────────────────

IGPU_PLATFORM_ID = {
    ("4",  True):  bytes([0x03, 0x00, 0x26, 0x0d]),  # Haswell laptop
    ("4",  False): bytes([0x03, 0x00, 0x22, 0x0d]),  # Haswell desktop
    ("5",  True):  bytes([0x06, 0x00, 0x26, 0x16]),  # Broadwell laptop
    ("5",  False): bytes([0x07, 0x00, 0x22, 0x16]),  # Broadwell desktop
    ("6",  True):  bytes([0x00, 0x00, 0x16, 0x19]),  # Skylake laptop HD 520
    ("6",  False): bytes([0x00, 0x00, 0x12, 0x19]),  # Skylake desktop HD 530
    ("7",  True):  bytes([0x00, 0x00, 0x16, 0x59]),  # Kaby Lake laptop HD 620
    ("7",  False): bytes([0x03, 0x00, 0x12, 0x59]),  # Kaby Lake desktop HD 630
    ("8",  True):  bytes([0x09, 0x00, 0xa5, 0x3e]),  # Coffee Lake laptop UHD 620
    ("8",  False): bytes([0x07, 0x00, 0x9b, 0x3e]),  # Coffee Lake desktop UHD 630
    ("9",  True):  bytes([0x09, 0x00, 0xa5, 0x3e]),  # Coffee Lake Refresh laptop
    ("9",  False): bytes([0x07, 0x00, 0x9b, 0x3e]),  # Coffee Lake Refresh desktop
    ("10", True):  bytes([0x09, 0x00, 0xa5, 0x3e]),  # Comet Lake laptop
    ("10", False): bytes([0x07, 0x00, 0x9b, 0x3e]),  # Comet Lake desktop
    ("11", True):  bytes([0x02, 0x00, 0x9a, 0x8a]),  # Tiger Lake laptop Iris Xe
    ("11", False): bytes([0x03, 0x00, 0xc8, 0x9b]),  # Rocket Lake desktop
    ("12", True):  bytes([0x02, 0x00, 0xfb, 0x89]),  # Alder Lake laptop
    ("12", False): bytes([0x00, 0x00, 0x6e, 0x9a]),  # Alder Lake desktop
    ("13", True):  bytes([0x02, 0x00, 0xfb, 0x89]),  # Raptor Lake laptop
    ("13", False): bytes([0x00, 0x00, 0x6e, 0x9a]),  # Raptor Lake desktop
    ("14", True):  bytes([0x02, 0x00, 0xfb, 0x89]),  # Raptor Lake Refresh laptop
    ("14", False): bytes([0x00, 0x00, 0x6e, 0x9a]),  # Raptor Lake Refresh desktop
}

# ─── Kext metadata ────────────────────────────────────────────────────────────

KEXT_META = {
    "Lilu":                   ("Lilu.kext",                   "Contents/MacOS/Lilu",                   "", ""),
    "VirtualSMC":             ("VirtualSMC.kext",             "Contents/MacOS/VirtualSMC",             "", ""),
    "SMCProcessor":           ("SMCProcessor.kext",           "Contents/MacOS/SMCProcessor",           "", ""),
    "SMCSuperIO":             ("SMCSuperIO.kext",             "Contents/MacOS/SMCSuperIO",             "", ""),
    "WhateverGreen":          ("WhateverGreen.kext",          "Contents/MacOS/WhateverGreen",          "", ""),
    "AppleALC":               ("AppleALC.kext",               "Contents/MacOS/AppleALC",               "", ""),
    "RestrictEvents":         ("RestrictEvents.kext",         "Contents/MacOS/RestrictEvents",         "", ""),
    "NVMeFix":                ("NVMeFix.kext",                "Contents/MacOS/NVMeFix",                "", ""),
    "CPUFriend":              ("CPUFriend.kext",              "Contents/MacOS/CPUFriend",              "", ""),
    "IntelMausi":             ("IntelMausi.kext",             "Contents/MacOS/IntelMausi",             "", ""),
    "RealtekRTL8111":         ("RealtekRTL8111.kext",         "Contents/MacOS/RealtekRTL8111",         "", ""),
    "AirportItlwm":           ("AirportItlwm.kext",           "Contents/MacOS/AirportItlwm",           "", ""),
    "AirportBrcmFixup":       ("AirportBrcmFixup.kext",       "Contents/MacOS/AirportBrcmFixup",       "", ""),
    "IntelBluetoothFirmware": ("IntelBluetoothFirmware.kext", "Contents/MacOS/IntelBluetoothFirmware", "", ""),
    "IntelBTPatcher":         ("IntelBTPatcher.kext",         "Contents/MacOS/IntelBTPatcher",         "", ""),
    "BlueToolFixup":          ("BlueToolFixup.kext",          "Contents/MacOS/BlueToolFixup",          "21.0.0", ""),
    "BrcmPatchRAM3":          ("BrcmPatchRAM3.kext",          "Contents/MacOS/BrcmPatchRAM3",          "", ""),
    "BrcmFirmwareData":       ("BrcmFirmwareData.kext",       "",                                      "", ""),
    "BrcmBluetoothInjector":  ("BrcmBluetoothInjector.kext",  "",                                      "", "20.99.99"),
    "VoodooPS2Controller":    ("VoodooPS2Controller.kext",    "Contents/MacOS/VoodooPS2Controller",    "", ""),
    "VoodooI2C":              ("VoodooI2C.kext",              "Contents/MacOS/VoodooI2C",              "", ""),
    "VoodooI2CHID":           ("VoodooI2CHID.kext",           "Contents/MacOS/VoodooI2CHID",           "", ""),
    "ECEnabler":              ("ECEnabler.kext",              "Contents/MacOS/ECEnabler",              "", ""),
    "SMCBatteryManager":      ("SMCBatteryManager.kext",      "Contents/MacOS/SMCBatteryManager",      "", ""),
    "BrightnessKeys":         ("BrightnessKeys.kext",         "Contents/MacOS/BrightnessKeys",         "", ""),
    "USBToolBox":             ("USBToolBox.kext",             "Contents/MacOS/USBToolBox",             "", ""),
}

KEXT_ORDER = [
    "Lilu", "VirtualSMC", "SMCProcessor", "SMCSuperIO",
    "WhateverGreen", "AppleALC", "RestrictEvents", "NVMeFix", "CPUFriend",
    "IntelMausi", "RealtekRTL8111",
    "AirportItlwm", "AirportBrcmFixup",
    "IntelBluetoothFirmware", "IntelBTPatcher", "BlueToolFixup",
    "BrcmPatchRAM3", "BrcmFirmwareData", "BrcmBluetoothInjector",
    "VoodooPS2Controller", "VoodooI2C", "VoodooI2CHID",
    "ECEnabler", "SMCBatteryManager", "BrightnessKeys",
    "USBToolBox",
]

KEXT_EXPAND = {
    "VirtualSMC":             ["VirtualSMC", "SMCProcessor", "SMCSuperIO"],
    "IntelBluetoothFirmware": ["IntelBluetoothFirmware", "IntelBTPatcher"],
    "BrcmPatchRAM":           ["BrcmPatchRAM3", "BrcmFirmwareData", "BrcmBluetoothInjector"],
    "VoodooI2C":              ["VoodooI2C", "VoodooI2CHID"],
}


# ─── macserial ────────────────────────────────────────────────────────────────

_MACSERIAL_REPO = "acidanthera/macserial"

# Keyword til at finde det rigtige asset i release
_MACSERIAL_ASSET_KEY = {
    "Darwin":  "mac",
    "Windows": "win",
}

# Model → 4-char serienummer suffix (fra macserial's model database)
_SERIAL_SUFFIXES = {
    "MacBookPro11,4": "DRJM",
    "MacBookPro12,1": "DV35",
    "MacBookPro13,1": "GH7H",
    "MacBookPro14,1": "HB21",
    "MacBookPro15,2": "LVDN",
    "MacBookPro16,2": "THCD",
    "MacBookPro16,3": "THCA",
    "MacBookPro18,3": "T6QP",
    "iMac15,1":       "DHJQ",
    "iMac16,2":       "DHKP",
    "iMac17,1":       "DHQ8",
    "iMac18,3":       "J9JN",
    "iMac19,1":       "JCMH",
    "iMac20,1":       "JDQ4",
    "iMacPro1,1":     "J09P",
    "MacPro7,1":      "LKCH",
}

# Gyldige tegn i Apple serienumre (ingen I, O for at undgå forveksling)
_SERIAL_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"

# Halvår-bogstaver for 2019–2022 (S/T=2019, V/W=2020, X/Y=2021, Z/C=2022)
_YEAR_CHARS = "STVWXYZ"


def _download_macserial(tools_dir):
    """
    Downloader macserial fra acidanthera/macserial releases.
    Returnerer stien til binary, eller None (Linux / fejl) → Python-fallback.
    Gemmer binary til genbrug ved efterfølgende kørsler.
    """
    import zipfile, io

    os_name = platform.system()
    asset_key = _MACSERIAL_ASSET_KEY.get(os_name)
    if not asset_key:
        return None  # Linux: ingen pre-bygget binary

    os.makedirs(tools_dir, exist_ok=True)
    fname = "macserial.exe" if os_name == "Windows" else "macserial"
    dest = os.path.join(tools_dir, fname)

    if os.path.exists(dest) and os.path.getsize(dest) > 10_000:
        return dest  # Brug cached version

    try:
        # Hent seneste release
        api_url = f"https://api.github.com/repos/{_MACSERIAL_REPO}/releases/latest"
        r = requests.get(api_url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        assets = r.json().get("assets", [])

        asset = next((a for a in assets if asset_key in a["name"] and a["name"].endswith(".zip")), None)
        if not asset:
            return None

        # Download og udpak zip
        r2 = requests.get(asset["browser_download_url"], timeout=30)
        r2.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(r2.content)) as z:
            # Find binary i zip (macserial eller macserial.exe)
            binary_entry = next((e for e in z.namelist() if e == fname or e.endswith("/" + fname)), None)
            if not binary_entry:
                return None
            with z.open(binary_entry) as src, open(dest, "wb") as dst:
                dst.write(src.read())

        if os_name != "Windows":
            os.chmod(dest, 0o755)
        return dest

    except Exception as e:
        print(f"\n    ! macserial download fejlede: {e}")
        return None


def _run_macserial(binary, model):
    """
    Kører: macserial -n 1 -m <model>
    Output format: '  ModelName | SerialNumber | MLB'
    Returnerer (serial, mlb) eller (None, None) ved fejl.
    """
    try:
        result = subprocess.run(
            [binary, "-n", "1", "-m", model],
            capture_output=True, text=True, timeout=10
        )
        # Output format: 'Serial | MLB'
        for line in result.stdout.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and len(parts[0]) == 12:
                return parts[0], parts[1]
    except Exception as e:
        print(f"\n    ! macserial fejlede: {e}")
    return None, None


def _generate_serial_fallback(model):
    """
    Python-fallback til Linux og når macserial ikke kan køres.
    Genererer et korrekt formateret (men ikke Apple-registreret) serienummer.

    Format: LL + Y + W + UUU + MMMM = 12 tegn
      LL   = fabrikskode (C02)
      Y    = halvår-bogstav
      W    = ugebogstav (1-9, A-T)
      UUU  = unik produktionsnummer (3 tegn)
      MMMM = model-suffix (4 tegn)
    """
    factory = "C02"
    year    = random.choice(_YEAR_CHARS)
    week    = random.choice("123456789ABCDEFGHJKLMNPQRST")
    unique  = "".join(random.choices(_SERIAL_CHARS, k=3))
    suffix  = _SERIAL_SUFFIXES.get(model, "XXXX")

    serial = factory + year + week + unique + suffix  # 12 tegn

    # MLB: 17 tegn — C02 + Y + W + 9 tilfældige + suffix[:3]
    mlb_pad = "".join(random.choices(_SERIAL_CHARS, k=9))
    mlb = factory + year + week + mlb_pad + suffix[:3]  # 17 tegn

    return serial, mlb


def _get_rom_bytes():
    """
    Returnerer 6-byte ROM (MAC-adresse).
    Forsøger at bruge systemets rigtige MAC; falder tilbage til tilfældig lokal-admin adresse.
    """
    node = _uuid_mod.getnode()
    # uuid.getnode() sætter multicast-bit hvis den ikke kan finde en rigtig MAC
    if node & (1 << 40):
        rom = bytes([random.randint(0, 255) for _ in range(6)])
        # Sæt locally administered bit, ryd multicast bit
        rom = bytes([rom[0] & 0xFE | 0x02]) + rom[1:]
    else:
        rom = node.to_bytes(6, "big")
    return rom


def _generate_platform_info(smbios_model, tools_dir):
    """
    Genererer komplet Platform Info til OpenCore.
    Bruger macserial hvis tilgængeligt, ellers Python-fallback.

    Returnerer dict med: serial, mlb, system_uuid, rom, used_macserial
    """
    binary = _download_macserial(tools_dir)

    if binary:
        serial, mlb = _run_macserial(binary, smbios_model)
        used_macserial = serial is not None
    else:
        serial, mlb = None, None
        used_macserial = False

    if not serial:
        serial, mlb = _generate_serial_fallback(smbios_model)

    system_uuid = str(_uuid_mod.uuid4()).upper()
    rom = _get_rom_bytes()

    return {
        "serial":         serial,
        "mlb":            mlb,
        "system_uuid":    system_uuid,
        "rom":            rom,
        "used_macserial": used_macserial,
    }


# ─── Hjælpefunktioner ─────────────────────────────────────────────────────────

def _get_gen_prefix(hardware):
    gen_str = hardware.get("cpu_generation", "")
    m = re.search(r'(\d+)\. gen', gen_str)
    return m.group(1) if m else "8"


def _is_ice_lake(cpu_str):
    return bool(re.search(r'i[3579]-10\d{2}[Gg]\d', cpu_str or ""))


def _get_smbios(hardware):
    gen = _get_gen_prefix(hardware)
    is_laptop = hardware.get("is_laptop", False)
    vendor = hardware.get("cpu_vendor", "Intel")

    if vendor == "AMD":
        return "iMacPro1,1"

    if gen == "10" and is_laptop and _is_ice_lake(hardware.get("cpu", "")):
        return "MacBookPro16,3"

    return SMBIOS_TABLE.get((gen, is_laptop), "iMac20,1")


def _get_igpu_platform_id(hardware):
    vendor = hardware.get("cpu_vendor", "Intel")
    if vendor != "Intel":
        return None

    gpus = [g.lower() for g in hardware.get("gpus", [])]
    has_igpu = any("intel" in g for g in gpus) or not gpus
    if not has_igpu:
        return None

    gen = _get_gen_prefix(hardware)
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


def _build_kext_entries(selected_names):
    expanded = set(_expand_kexts(selected_names))
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


def _get_kernel_quirks(hardware):
    gen = _get_gen_prefix(hardware)
    vendor = hardware.get("cpu_vendor", "Intel")
    quirks = {}

    if vendor == "AMD":
        quirks["AppleXcpmCfgLock"] = False
        quirks["AppleXcpmExtraMsrs"] = False
        quirks["DisableIoMapper"] = True
        return quirks

    gen_num = int(gen) if gen.isdigit() else 8
    if gen_num >= 12:
        quirks["ProvideCurrentCpuInfo"] = True
    if gen_num <= 4:
        quirks["AppleCpuPmCfgLock"] = True

    return quirks


def _get_boot_args(hardware):
    args = ["-v", "keepsyms=1", "debug=0x100"]
    gen = _get_gen_prefix(hardware)
    gen_num = int(gen) if gen.isdigit() else 8

    if gen_num >= 12:
        args.append("revpatch=sbvmm,cpuname")

    gpus = [g.lower() for g in hardware.get("gpus", [])]
    if any("nvidia" in g or "gtx" in g or "rtx" in g for g in gpus):
        args.append("-wegnoegpu")

    return " ".join(args)


# ─── Hoved-funktion ───────────────────────────────────────────────────────────

def generate(hardware, selected_kexts, macos_version, efi_dir, sample_path=None):
    """
    Genererer EFI/OC/config.plist ved at modificere sample.plist.

    hardware       : dict fra hardware.py scan()
    selected_kexts : liste af kext-navne fra kexts.py select_kexts()
    macos_version  : "Ventura" / "Sonoma" / "Sequoia"
    efi_dir        : rod-mappe for EFI (config.plist lægges i efi_dir/EFI/OC/)
    sample_path    : sti til sample.plist (default: samme mappe som dette script)
    """
    print("[5/6] Genererer config.plist...")

    # ── Indlæs sample.plist ──────────────────────────────────────────────────
    sample = sample_path or DEFAULT_SAMPLE
    if not os.path.exists(sample):
        print(f"  FEJL — sample.plist ikke fundet: {sample}")
        return None

    with open(sample, "rb") as f:
        config = plistlib.load(f)

    # ── SMBIOS model ─────────────────────────────────────────────────────────
    smbios_model = _get_smbios(hardware)
    config["PlatformInfo"]["Generic"]["SystemProductName"] = smbios_model

    # ── Platform Info (serial, MLB, UUID, ROM) ───────────────────────────────
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

    # ── DeviceProperties (iGPU) ──────────────────────────────────────────────
    igpu_props = _get_igpu_platform_id(hardware)
    if igpu_props:
        config["DeviceProperties"]["Add"]["PciRoot(0x0)/Pci(0x2,0x0)"] = igpu_props

    # ── Kernel.Add (kexts i korrekt rækkefølge) ──────────────────────────────
    config["Kernel"]["Add"] = _build_kext_entries(selected_kexts)

    # ── Kernel.Quirks ────────────────────────────────────────────────────────
    for key, val in _get_kernel_quirks(hardware).items():
        config["Kernel"]["Quirks"][key] = val

    # ── Boot args ────────────────────────────────────────────────────────────
    config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = \
        _get_boot_args(hardware)

    # ── Skriv config.plist ───────────────────────────────────────────────────
    out_dir = os.path.join(efi_dir, "EFI", "OC")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "config.plist")

    with open(out_path, "wb") as f:
        plistlib.dump(config, f, fmt=plistlib.FMT_XML, sort_keys=False)

    kext_count = len(config["Kernel"]["Add"])
    print(f"  ✓ config.plist klar — {kext_count} kexts")

    _print_warnings(hardware, smbios_model, pi["used_macserial"])
    return out_path


def _print_warnings(hardware, smbios_model, used_macserial):
    gen = _get_gen_prefix(hardware)
    gen_num = int(gen) if gen.isdigit() else 8

    print()
    print("  ┌─ NÆSTE SKRIDT ────────────────────────────────────────────────")
    print("  │")

    if not used_macserial:
        print("  │  ⚠  Serial genereret med Python-fallback (Linux)")
        print("  │     Til iMessage/iCloud: kør GenSMBIOS manuelt og opdater")
        print("  │     config.plist → PlatformInfo → Generic")
        print("  │")

    if gen_num >= 12:
        print("  │  Tilføj SSDT-PLUG-ALT.aml til EFI/OC/ACPI/ og ACPI → Add")
    elif gen_num >= 6:
        print("  │  Tilføj SSDT-PLUG.aml + SSDT-EC.aml til EFI/OC/ACPI/ og ACPI → Add")

    if hardware.get("is_laptop"):
        print("  │  Laptop: Tilføj SSDT-PNLF.aml for backlight-kontrol")

    print("  │")
    print("  │  Tjek Apple dækning for din serial (bør vise 'ugyldig'):")
    print("  │  https://checkcoverage.apple.com")
    print("  │")
    print("  └───────────────────────────────────────────────────────────────")
    print()


# ─── Print oversigt ──────────────────────────────────────────────────────────

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
    dp    = config.get("DeviceProperties", {}).get("Add", {})

    serial = pi.get("SystemSerialNumber", "?")
    serial_display = serial[:3] + "XXXXXXX" + serial[-2:] if len(serial) == 12 else serial

    print("\n" + "=" * 52)
    print("  CONFIG.PLIST — OVERSIGT")
    print("=" * 52)
    print(f"  SMBIOS      : {pi.get('SystemProductName', '?')}")
    print(f"  Serial      : {serial_display}")
    print(f"  MLB         : {pi.get('MLB', '?')[:6]}...")
    print(f"  UUID        : {pi.get('SystemUUID', '?')[:8]}...")
    print(f"  Boot args   : {args}")
    print(f"  Kexts       : {len(kexts)}")
    if dp:
        print(f"  DevProps    : {', '.join(dp.keys())}")
    print(f"  Sti         : {config_path}")
    print("=" * 52 + "\n")


# ─── Standalone test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_hw = {
        "cpu": "Intel Core i5-6200U",
        "cpu_vendor": "Intel",
        "cpu_generation": "Skylake (6. gen)",
        "is_laptop": True,
        "gpus": ["Intel HD Graphics 520"],
        "has_nvme": False,
        "wifi": "Intel (itlwm)",
        "ethernet": ["Intel I219V"],
        "trackpad_i2c": True,
    }
    test_kexts = [
        "Lilu", "VirtualSMC", "WhateverGreen", "AppleALC", "RestrictEvents",
        "IntelMausi", "AirportItlwm", "IntelBluetoothFirmware", "BlueToolFixup",
        "VoodooPS2Controller", "VoodooI2C", "ECEnabler", "SMCBatteryManager",
        "BrightnessKeys", "USBToolBox",
    ]
    out = generate(test_hw, test_kexts, "Sonoma", "/tmp/autocore_test")
    if out:
        print_summary(out, test_hw, test_kexts)
