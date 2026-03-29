import platform
import subprocess
import json
import re
import os
import glob


def _run(cmd, shell=False):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=15)
        return result.stdout.strip()
    except Exception:
        return ""


def _ps(cmd):
    """Kør PowerShell kommando (Windows)"""
    return _run(["powershell", "-NoProfile", "-Command", cmd])


def _cmd_exists(cmd):
    """Tjek om et program findes på systemet"""
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


# ─── macOS ────────────────────────────────────────────────────────────────────

def _scan_macos():
    info = {}

    info["cpu"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    info["cpu_cores"] = _run(["sysctl", "-n", "hw.physicalcpu"])

    ram_bytes = _run(["sysctl", "-n", "hw.memsize"])
    info["ram_gb"] = int(ram_bytes) // (1024 ** 3) if ram_bytes.isdigit() else "?"

    # GPU
    raw = _run(["system_profiler", "SPDisplaysDataType", "-json"])
    try:
        info["gpus"] = [g.get("sppci_model", "Ukendt") for g in json.loads(raw).get("SPDisplaysDataType", [])]
    except Exception:
        info["gpus"] = []

    # WiFi
    wifi_sp = _run(["system_profiler", "SPAirPortDataType", "-json"])
    try:
        wifi_data = json.loads(wifi_sp)
        interfaces = wifi_data.get("SPAirPortDataType", [{}])[0].get("spairport_airport_interfaces", [])
        if interfaces:
            iface = interfaces[0]
            card_type = iface.get("spairport_wireless_card_type", "")
            firmware = iface.get("spairport_wireless_firmware_version", "")
            vendor_map = {"0x8086": "Intel", "0x14e4": "Broadcom", "0x168c": "Atheros"}
            vendor = next((v for k, v in vendor_map.items() if k in card_type), "")
            if vendor and firmware:
                info["wifi"] = f"{vendor} ({firmware.split()[0]})"
            elif vendor:
                info["wifi"] = vendor
            elif card_type:
                info["wifi"] = card_type
            else:
                info["wifi"] = "Ukendt"
        else:
            info["wifi"] = "Ingen WiFi"
    except Exception:
        info["wifi"] = "Ukendt"

    # Audio codec via ioreg
    audio_raw = _run(["ioreg", "-r", "-c", "IOHDACodecDevice"])
    match = re.search(r'"IOHDACodecVendorID"\s*=\s*(\d+)', audio_raw)
    info["audio_codec"] = match.group(1) if match else "Ukendt"

    # Ethernet
    eth_raw = _run(["system_profiler", "SPEthernetDataType", "-json"])
    try:
        eth_data = json.loads(eth_raw).get("SPEthernetDataType", [])
        info["ethernet"] = [e.get("spethernet_chipset-id", e.get("_name", "Ukendt")) for e in eth_data]
    except Exception:
        info["ethernet"] = []

    # Laptop (batteri)
    batt_raw = _run(["system_profiler", "SPPowerDataType", "-json"])
    try:
        info["is_laptop"] = len(json.loads(batt_raw).get("SPPowerDataType", [])) > 0
    except Exception:
        info["is_laptop"] = False

    # Storage + NVMe detection
    storage_raw = _run(["system_profiler", "SPStorageDataType", "-json"])
    try:
        drives = json.loads(storage_raw).get("SPStorageDataType", [])
        info["storage"] = [{"name": d.get("_name", "?"), "ssd": d.get("spstorage_solid_state", "No") == "Yes"} for d in drives]
    except Exception:
        info["storage"] = []

    nvme_raw = _run(["system_profiler", "SPNVMeDataType", "-json"])
    try:
        info["has_nvme"] = len(json.loads(nvme_raw).get("SPNVMeDataType", [])) > 0
    except Exception:
        info["has_nvme"] = False

    # Trackpad type — I2C (moderne) vs PS/2 (ældre)
    i2c_raw = _run(["ioreg", "-r", "-c", "IOHIDDevice", "-d", "3"])
    info["trackpad_i2c"] = "VoodooI2C" in i2c_raw or "SYNA" in i2c_raw or "ELAN" in i2c_raw

    return info


# ─── Windows ──────────────────────────────────────────────────────────────────

def _scan_windows():
    info = {}

    # CPU — PowerShell først (virker på Win10+11), wmic som fallback
    cpu = _ps("(Get-CimInstance Win32_Processor).Name")
    if not cpu:
        raw = _run('wmic cpu get Name /value', shell=True)
        m = re.search(r'Name=(.+)', raw)
        cpu = m.group(1).strip() if m else "Ukendt"
    info["cpu"] = cpu

    cores = _ps("(Get-CimInstance Win32_Processor).NumberOfCores")
    info["cpu_cores"] = cores if cores else "?"

    # RAM
    ram = _ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
    if not ram:
        raw = _run('wmic ComputerSystem get TotalPhysicalMemory /value', shell=True)
        m = re.search(r'TotalPhysicalMemory=(\d+)', raw)
        ram = m.group(1) if m else "0"
    info["ram_gb"] = int(ram) // (1024 ** 3) if ram.isdigit() else "?"

    # GPU
    gpus = _ps("(Get-CimInstance Win32_VideoController).Name")
    if not gpus:
        raw = _run('wmic path win32_VideoController get Name /value', shell=True)
        gpus = "\n".join(re.findall(r'Name=(.+)', raw))
    info["gpus"] = [g.strip() for g in gpus.splitlines() if g.strip()]

    # WiFi — netsh virker på alle Windows versioner
    wifi_raw = _run('netsh wlan show drivers', shell=True)
    m = re.search(r'Description\s+:\s+(.+)', wifi_raw)
    info["wifi"] = m.group(1).strip() if m else "Ingen WiFi / Ukendt"

    # Audio
    audio = _ps("(Get-CimInstance Win32_SoundDevice).Name")
    if not audio:
        raw = _run('wmic sounddev get Name /value', shell=True)
        audio = "\n".join(re.findall(r'Name=(.+)', raw))
    info["audio_codec"] = ", ".join([a.strip() for a in audio.splitlines() if a.strip()])

    # Ethernet
    eth = _ps("(Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.NetConnectionStatus -eq 2}).Name")
    if not eth:
        raw = _run('wmic nic where "NetConnectionStatus=2" get Name /value', shell=True)
        eth = "\n".join(re.findall(r'Name=(.+)', raw))
    info["ethernet"] = [n.strip() for n in eth.splitlines() if n.strip()]

    # Laptop (batteri)
    batt = _ps("(Get-CimInstance Win32_Battery).Name")
    info["is_laptop"] = bool(batt and batt.strip())

    # Storage + NVMe
    storage_raw = _ps("Get-CimInstance Win32_DiskDrive | Select-Object Model,MediaType | ConvertTo-Json")
    try:
        drives_raw = json.loads(storage_raw)
        if isinstance(drives_raw, dict):
            drives_raw = [drives_raw]
        info["storage"] = [
            {"name": d.get("Model", "?"), "ssd": "SSD" in (d.get("MediaType") or "")}
            for d in drives_raw
        ]
    except Exception:
        info["storage"] = []

    nvme_raw = _ps("Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk | Where-Object {$_.BusType -eq 17} | Select-Object FriendlyName | ConvertTo-Json")
    try:
        info["has_nvme"] = bool(json.loads(nvme_raw))
    except Exception:
        # Fallback: tjek model navne
        info["has_nvme"] = any("nvme" in d["name"].lower() for d in info.get("storage", []))

    # Trackpad type
    i2c_raw = _ps("Get-PnpDevice | Where-Object {$_.FriendlyName -match 'I2C|HID|Precision'} | Select-Object FriendlyName | ConvertTo-Json")
    info["trackpad_i2c"] = bool(i2c_raw and ("I2C" in i2c_raw or "Precision" in i2c_raw))

    return info


# ─── Linux ────────────────────────────────────────────────────────────────────

def _scan_linux():
    info = {}

    # CPU — /proc/cpuinfo er altid tilgængelig
    cpuinfo = _run("grep 'model name' /proc/cpuinfo | head -1", shell=True)
    m = re.search(r'model name\s*:\s*(.+)', cpuinfo)
    info["cpu"] = m.group(1).strip() if m else "Ukendt"
    info["cpu_cores"] = _run("nproc", shell=True)

    # RAM — /proc/meminfo er altid tilgængelig
    mem = _run("grep MemTotal /proc/meminfo", shell=True)
    m = re.search(r'MemTotal:\s+(\d+)', mem)
    info["ram_gb"] = int(m.group(1)) // (1024 ** 2) if m else "?"

    # GPU — lspci, fallback til /sys
    if _cmd_exists("lspci"):
        gpu_raw = _run("lspci | grep -i 'vga\\|display\\|3d'", shell=True)
        info["gpus"] = [l.split(": ", 1)[1].strip() for l in gpu_raw.splitlines() if ": " in l]
    else:
        # Fallback: læs fra /sys/class/drm
        drm = _run("ls /sys/class/drm/", shell=True)
        info["gpus"] = ["GPU fundet (installer lspci for detaljer)"] if drm else ["Ukendt"]

    # WiFi — lspci, fallback til /sys/class/net
    if _cmd_exists("lspci"):
        wifi_raw = _run("lspci | grep -i 'network\\|wireless\\|wifi'", shell=True)
        info["wifi"] = wifi_raw.splitlines()[0].split(": ", 1)[-1].strip() if wifi_raw else "Ukendt"
    else:
        # Fallback: kig på netværksinterfaces
        ifaces = _run("ls /sys/class/net/", shell=True).split()
        wifi_iface = next((i for i in ifaces if i.startswith("w")), None)
        info["wifi"] = f"WiFi interface: {wifi_iface}" if wifi_iface else "Ukendt"

    # Audio — lspci, fallback til /proc/asound
    if _cmd_exists("lspci"):
        audio_raw = _run("lspci | grep -i 'audio\\|sound'", shell=True)
        info["audio_codec"] = audio_raw.splitlines()[0].split(": ", 1)[-1].strip() if audio_raw else "Ukendt"
    else:
        asound = _run("cat /proc/asound/cards", shell=True)
        info["audio_codec"] = asound.splitlines()[0].strip() if asound else "Ukendt"

    # Ethernet — lspci, fallback til /sys/class/net
    if _cmd_exists("lspci"):
        eth_raw = _run("lspci | grep -i 'ethernet'", shell=True)
        info["ethernet"] = [l.split(": ", 1)[-1].strip() for l in eth_raw.splitlines() if l]
    else:
        ifaces = _run("ls /sys/class/net/", shell=True).split()
        info["ethernet"] = [i for i in ifaces if i.startswith("e")]

    # Laptop (batteri) — /sys er altid tilgængelig
    info["is_laptop"] = (
        os.path.exists("/sys/class/power_supply/BAT0") or
        os.path.exists("/sys/class/power_supply/BAT1")
    )

    # Storage + NVMe
    try:
        storage_raw = _run("lsblk -d -o NAME,MODEL,ROTA --json", shell=True)
        devices = json.loads(storage_raw).get("blockdevices", [])
        info["storage"] = [{"name": d.get("model", d.get("name", "?")), "ssd": d.get("rota") == "0"} for d in devices]
    except Exception:
        blocks = _run("ls /sys/block/", shell=True).split()
        info["storage"] = [{"name": b, "ssd": False} for b in blocks if not b.startswith("loop")]

    # NVMe: tjek om /dev/nvme* eksisterer
    info["has_nvme"] = len(glob.glob("/dev/nvme*")) > 0

    # Trackpad type: tjek I2C bus for HID enheder
    i2c_devices = _run("ls /sys/bus/i2c/devices/ 2>/dev/null", shell=True)
    i2c_hid = _run("grep -r 'i2c-hid\\|SYNA\\|ELAN\\|ALPS' /sys/bus/i2c/devices/ 2>/dev/null", shell=True)
    info["trackpad_i2c"] = bool(i2c_hid)

    return info


# ─── CPU analyse ──────────────────────────────────────────────────────────────

def _cpu_details(cpu_string):
    cpu = cpu_string.lower()
    vendor = "AMD" if "amd" in cpu else "Intel"

    generation = "Ukendt"
    if vendor == "Intel":
        m = re.search(r'i[3579]-(\d{4,5})', cpu)
        if m:
            num = m.group(1)
            # 5-cifret (f.eks. 10900) → første 2 cifre er generation
            # 4-cifret startende med 10/11/12/13/14 → første 2 cifre
            # 4-cifret startende med 4-9 → første ciffer
            if len(num) == 5:
                prefix = num[:2]
            elif num[:2] in ("10", "11", "12", "13", "14"):
                prefix = num[:2]
            else:
                prefix = num[0]
            gen_map = {
                "4": "Haswell (4. gen)",
                "5": "Broadwell (5. gen)",
                "6": "Skylake (6. gen)",
                "7": "Kaby Lake (7. gen)",
                "8": "Coffee Lake (8. gen)",
                "9": "Coffee Lake Refresh (9. gen)",
                "10": "Comet/Ice Lake (10. gen)",
                "11": "Rocket/Tiger Lake (11. gen)",
                "12": "Alder Lake (12. gen)",
                "13": "Raptor Lake (13. gen)",
                "14": "Raptor Lake Refresh (14. gen)",
            }
            generation = gen_map.get(prefix, f"Intel {prefix}. gen")
    elif vendor == "AMD":
        m = re.search(r'ryzen\s+\d+\s+(\d)', cpu)
        generation = f"Ryzen Gen {m.group(1)}" if m else "AMD Ryzen"

    return vendor, generation


# ─── Kompatibilitetstjek ──────────────────────────────────────────────────────

def _check_compatibility(info):
    issues = []
    warnings = []

    cpu = info.get("cpu", "").lower()
    gpus = [g.lower() for g in info.get("gpus", [])]

    # NVIDIA GPU — kun støttet til High Sierra
    for g in gpus:
        if "nvidia" in g:
            issues.append("NVIDIA GPU — kun macOS op til High Sierra (10.13)")

    # Intel 12./13./14. gen — kræver ekstra patches
    if re.search(r'i[3579]-1[234]\d{3}', cpu):
        warnings.append("12./13./14. gen Intel — kræver ekstra ACPI/Booter patches")

    # AMD CPU
    if "amd" in cpu and "ryzen" not in cpu:
        issues.append("Ældre AMD CPU — meget begrænset macOS support")

    # WiFi
    wifi = info.get("wifi", "").lower()
    if "realtek" in wifi:
        issues.append("Realtek WiFi — ikke supporteret, kræver USB WiFi eller korterstatning")
    elif "intel" in wifi:
        warnings.append("Intel WiFi — virker med itlwm/AirportItlwm kext")
    elif "broadcom" in wifi or "bcm" in wifi:
        warnings.append("Broadcom WiFi — tjek om kortmodellen er på kompatibilitetslisten")

    compatible = "Nej" if issues else ("Med forbehold" if warnings else "Ja")
    return {"compatible": compatible, "issues": issues, "warnings": warnings}


# ─── Hoved-funktion ───────────────────────────────────────────────────────────

def scan():
    os_name = platform.system()
    print(f"[1/6] Scanner hardware ({os_name})...", end=" ", flush=True)

    if os_name == "Darwin":
        raw = _scan_macos()
    elif os_name == "Windows":
        raw = _scan_windows()
    elif os_name == "Linux":
        raw = _scan_linux()
    else:
        print("FEJL — ukendt OS")
        return None

    vendor, generation = _cpu_details(raw.get("cpu", ""))
    raw["os"] = os_name
    raw["cpu_vendor"] = vendor
    raw["cpu_generation"] = generation
    raw["compatibility"] = _check_compatibility(raw)

    print("✓")
    return raw


def print_summary(info):
    c = info.get("compatibility", {})
    print("\n" + "=" * 52)
    print("  HARDWARE OVERSIGT")
    print("=" * 52)
    print(f"  CPU         : {info.get('cpu', '?')}")
    print(f"  Generation  : {info.get('cpu_generation', '?')}")
    print(f"  Kerner      : {info.get('cpu_cores', '?')}")
    print(f"  RAM         : {info.get('ram_gb', '?')} GB")
    print(f"  GPU(er)     : {', '.join(info.get('gpus', ['?']))}")
    print(f"  WiFi        : {info.get('wifi', '?')}")
    print(f"  Lyd (codec) : {info.get('audio_codec', '?')}")
    print(f"  Ethernet    : {', '.join(info.get('ethernet', ['?']))}")
    print(f"  Laptop      : {'Ja' if info.get('is_laptop') else 'Nej'}")
    print(f"  macOS OK    : {c.get('compatible', '?')}")

    if c.get("issues"):
        print("\n  PROBLEMER:")
        for i in c["issues"]:
            print(f"    x {i}")
    if c.get("warnings"):
        print("\n  ADVARSLER:")
        for w in c["warnings"]:
            print(f"    ! {w}")

    print("=" * 52 + "\n")


if __name__ == "__main__":
    result = scan()
    if result:
        print_summary(result)
