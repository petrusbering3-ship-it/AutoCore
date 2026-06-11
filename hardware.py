"""AutoCore — hardware.py
Cross-platform hardware detection (macOS, Windows, Linux).
"""

import platform
import subprocess
import json
import re
import os
import glob

from lang import t

# Suppress console window pop-ups on Windows when spawning sub-processes
_NO_WINDOW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _run(cmd, shell=False):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            shell=shell, timeout=15, **_NO_WINDOW,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _ps(cmd):
    """Run a PowerShell command (Windows)."""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd])


def _cmd_exists(cmd):
    """Check whether a program exists on the system."""
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
        info["gpus"] = [g.get("sppci_model", "Unknown") for g in json.loads(raw).get("SPDisplaysDataType", [])]
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
                info["wifi"] = "Unknown"
        else:
            info["wifi"] = "No WiFi"
    except Exception:
        info["wifi"] = "Unknown"

    # Audio codec via ioreg
    audio_raw = _run(["ioreg", "-r", "-c", "IOHDACodecDevice"])
    match = re.search(r'"IOHDACodecVendorID"\s*=\s*(\d+)', audio_raw)
    info["audio_codec"] = match.group(1) if match else "Unknown"

    # Ethernet
    eth_raw = _run(["system_profiler", "SPEthernetDataType", "-json"])
    try:
        eth_data = json.loads(eth_raw).get("SPEthernetDataType", [])
        info["ethernet"] = [e.get("spethernet_chipset-id", e.get("_name", "Unknown")) for e in eth_data]
    except Exception:
        info["ethernet"] = []

    # Laptop (battery)
    batt_raw = _run(["system_profiler", "SPPowerDataType", "-json"])
    try:
        info["is_laptop"] = len(json.loads(batt_raw).get("SPPowerDataType", [])) > 0
    except Exception:
        info["is_laptop"] = False

    # Storage + NVMe
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

    # Trackpad: I2C vs PS/2 detection
    i2c_raw = _run(["ioreg", "-r", "-c", "IOHIDDevice", "-d", "3"])
    info["trackpad_i2c"] = "VoodooI2C" in i2c_raw or "SYNA" in i2c_raw or "ELAN" in i2c_raw

    i2c_lower = i2c_raw.lower()
    if "syna" in i2c_lower or "synaptics" in i2c_lower:
        info["trackpad_vendor"] = "synaptics"
    elif "alps" in i2c_lower:
        info["trackpad_vendor"] = "alps"
    elif "elan" in i2c_lower:
        info["trackpad_vendor"] = "elan"
    elif info["trackpad_i2c"]:
        info["trackpad_vendor"] = "i2c_hid"
    else:
        info["trackpad_vendor"] = "ps2"

    # System vendor
    hw_raw = _run(["system_profiler", "SPHardwareDataType"])
    info["is_vm"] = any(v in hw_raw for v in ["VMware", "VirtualBox", "Parallels", "QEMU", "Xen"])
    vendor_m = re.search(r'Manufacturer:\s*(.+)', hw_raw)
    if vendor_m:
        info["system_vendor"] = vendor_m.group(1).strip()
    elif "Apple" in hw_raw:
        info["system_vendor"] = "Apple"
    else:
        info["system_vendor"] = "Unknown"

    # Card reader detection
    usb_raw = _run(["system_profiler", "SPUSBDataType", "-json"])
    pcie_raw = _run(["system_profiler", "SPPCIDataType", "-json"])
    combined = (usb_raw + pcie_raw).lower()
    info["has_card_reader"] = any(k in combined for k in ["realtek card", "rts5", "rtl8411"])

    return info


# ─── Windows ──────────────────────────────────────────────────────────────────

# Single-shot PowerShell script: collects everything in ONE process launch.
# Replaces ~12 separate _ps() calls → scan time drops from ~8s to ~1-2s.
_WIN_SCAN_SCRIPT = r"""
$r = @{
    cpu='Unknown'; cores='?'; ram_bytes='0'; gpus=@(); wifi='No WiFi / Unknown';
    audio='Unknown'; eth=@(); battery=$null; vendor='Unknown'; bios_vendor='';
    has_nvme=$false; trackpad=@(); has_card_reader=$false; storage=@()
}
try { $p=$null; $p=Get-CimInstance Win32_Processor -Property Name,NumberOfCores -ErrorAction Stop
      $r.cpu=$p.Name; $r.cores=[string]$p.NumberOfCores } catch {}
try { $r.ram_bytes=[string](Get-CimInstance Win32_ComputerSystem -Property TotalPhysicalMemory -ErrorAction Stop).TotalPhysicalMemory } catch {}
try { $r.gpus=@(Get-CimInstance Win32_VideoController -Property Name -ErrorAction Stop | Select-Object -ExpandProperty Name) } catch {}
try { $w=netsh wlan show drivers 2>$null
      if ($w -match 'Description\s+:\s+(.+)') { $r.wifi=$Matches[1].Trim() } } catch {}
try { $r.audio=(Get-CimInstance Win32_SoundDevice -Property Name -ErrorAction Stop | Select-Object -First 1).Name } catch {}
try { $r.eth=@(Get-CimInstance Win32_NetworkAdapter -ErrorAction Stop | Where-Object {$_.NetConnectionStatus -eq 2} | Select-Object -ExpandProperty Name) } catch {}
try { $b=Get-CimInstance Win32_Battery -Property Name -ErrorAction Stop
      $r.battery=if($b){$b.Name}else{$null} } catch {}
try { $r.vendor=(Get-CimInstance Win32_ComputerSystem -Property Manufacturer -ErrorAction Stop).Manufacturer } catch {}
try { $r.bios_vendor=(Get-CimInstance Win32_BIOS -Property Manufacturer -ErrorAction Stop).Manufacturer } catch {}
try { $nvme=Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk -ErrorAction Stop | Where-Object {$_.BusType -eq 17}
      $r.has_nvme=($nvme -ne $null) } catch {}
try { $r.trackpad=@(Get-PnpDevice -ErrorAction Stop | Where-Object {$_.FriendlyName -match 'I2C|Precision.*Touchpad|Synaptics|Alps|Elan|HID.*Touchpad'} | Select-Object -ExpandProperty FriendlyName) } catch {}
try { $cr=Get-PnpDevice -ErrorAction Stop | Where-Object {$_.FriendlyName -match 'Realtek.*Card|RTS5'} | Select-Object -First 1
      $r.has_card_reader=($cr -ne $null) } catch {}
try { $r.storage=@(Get-CimInstance Win32_DiskDrive -ErrorAction Stop | ForEach-Object {
      @{name=$_.Model; ssd=(($_.MediaType -like '*SSD*') -or ($_.Model -like '*SSD*') -or ($_.Model -like '*NVMe*'))} }) } catch {}
$r | ConvertTo-Json -Depth 3
"""


def _scan_windows():
    # Run everything in a single PowerShell process — no repeated startup cost.
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_SCAN_SCRIPT],
    )

    try:
        d = json.loads(raw)
    except Exception:
        d = {}

    def _str(v):
        return str(v).strip() if v else ""

    def _list(v):
        if not v:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x]
        return [str(v).strip()] if str(v).strip() else []

    info = {}
    info["cpu"]        = _str(d.get("cpu")) or "Unknown"
    info["cpu_cores"]  = _str(d.get("cores")) or "?"
    ram = _str(d.get("ram_bytes"))
    info["ram_gb"]     = int(ram) // (1024 ** 3) if ram.isdigit() else "?"
    info["gpus"]       = _list(d.get("gpus"))
    info["wifi"]       = _str(d.get("wifi")) or "No WiFi / Unknown"
    info["audio_codec"]= _str(d.get("audio")) or "Unknown"
    info["ethernet"]   = _list(d.get("eth"))
    info["is_laptop"]  = bool(d.get("battery"))
    info["system_vendor"] = _str(d.get("vendor")) or "Unknown"
    bios_raw = _str(d.get("bios_vendor"))
    info["is_vm"] = any(v in bios_raw for v in ["VMware", "VirtualBox", "VBOX", "QEMU", "Xen", "Parallels"])
    info["has_nvme"]   = bool(d.get("has_nvme"))
    info["has_card_reader"] = bool(d.get("has_card_reader"))

    storage_raw = d.get("storage") or []
    if isinstance(storage_raw, dict):
        storage_raw = [storage_raw]
    info["storage"] = [
        {"name": s.get("name", "?"), "ssd": bool(s.get("ssd"))}
        for s in storage_raw
    ]
    # NVMe fallback: check model names if WMI query failed
    if not info["has_nvme"]:
        info["has_nvme"] = any("nvme" in s["name"].lower() for s in info["storage"])

    tp_list  = _list(d.get("trackpad"))
    tp_lower = " ".join(tp_list).lower()
    info["trackpad_i2c"] = any(k in tp_lower for k in ("i2c", "precision"))
    if "synaptics" in tp_lower:
        info["trackpad_vendor"] = "synaptics"
    elif "alps" in tp_lower:
        info["trackpad_vendor"] = "alps"
    elif "elan" in tp_lower:
        info["trackpad_vendor"] = "elan"
    elif info["trackpad_i2c"]:
        info["trackpad_vendor"] = "i2c_hid"
    else:
        info["trackpad_vendor"] = "ps2"

    return info


# ─── Linux ────────────────────────────────────────────────────────────────────

def _scan_linux():
    info = {}

    # CPU
    cpuinfo = _run("grep 'model name' /proc/cpuinfo | head -1", shell=True)
    m = re.search(r'model name\s*:\s*(.+)', cpuinfo)
    info["cpu"] = m.group(1).strip() if m else "Unknown"
    # Physical cores, not threads — the AMD kernel patches need this exact
    # number. nproc counts logical CPUs, so only use it as a fallback.
    cores_raw = _run("grep 'cpu cores' /proc/cpuinfo | head -1", shell=True)
    m = re.search(r'cpu cores\s*:\s*(\d+)', cores_raw)
    info["cpu_cores"] = m.group(1) if m else _run("nproc", shell=True)

    # RAM
    mem = _run("grep MemTotal /proc/meminfo", shell=True)
    m = re.search(r'MemTotal:\s+(\d+)', mem)
    info["ram_gb"] = int(m.group(1)) // (1024 ** 2) if m else "?"

    # GPU
    if _cmd_exists("lspci"):
        gpu_raw = _run("lspci | grep -i 'vga\\|display\\|3d'", shell=True)
        info["gpus"] = [l.split(": ", 1)[1].strip() for l in gpu_raw.splitlines() if ": " in l]
    else:
        drm = _run("ls /sys/class/drm/", shell=True)
        info["gpus"] = ["GPU found (install lspci for details)"] if drm else ["Unknown"]

    # WiFi
    if _cmd_exists("lspci"):
        wifi_raw = _run("lspci | grep -i 'network\\|wireless\\|wifi'", shell=True)
        info["wifi"] = wifi_raw.splitlines()[0].split(": ", 1)[-1].strip() if wifi_raw else "Unknown"
    else:
        ifaces = _run("ls /sys/class/net/", shell=True).split()
        wifi_iface = next((i for i in ifaces if i.startswith("w")), None)
        info["wifi"] = f"WiFi interface: {wifi_iface}" if wifi_iface else "Unknown"

    # Audio — prefer the actual HDA codec name ("Realtek ALC256") from
    # /proc/asound: config_plist matches it to the right AppleALC layout-id.
    # lspci only names the controller, which always falls back to alcid=1.
    codec_raw = _run("grep -h '^Codec:' /proc/asound/card*/codec#* 2>/dev/null | head -1", shell=True)
    m = re.search(r'Codec:\s*(.+)', codec_raw)
    if m:
        info["audio_codec"] = m.group(1).strip()
    elif _cmd_exists("lspci"):
        audio_raw = _run("lspci | grep -i 'audio\\|sound'", shell=True)
        info["audio_codec"] = audio_raw.splitlines()[0].split(": ", 1)[-1].strip() if audio_raw else "Unknown"
    else:
        asound = _run("cat /proc/asound/cards", shell=True)
        info["audio_codec"] = asound.splitlines()[0].strip() if asound else "Unknown"

    # Ethernet
    if _cmd_exists("lspci"):
        eth_raw = _run("lspci | grep -i 'ethernet'", shell=True)
        info["ethernet"] = [l.split(": ", 1)[-1].strip() for l in eth_raw.splitlines() if l]
    else:
        ifaces = _run("ls /sys/class/net/", shell=True).split()
        info["ethernet"] = [i for i in ifaces if i.startswith("e")]

    # Laptop (battery)
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

    info["has_nvme"] = len(glob.glob("/dev/nvme*")) > 0

    # Trackpad: check I2C bus and lspci for known vendors
    i2c_hid = _run("grep -ri 'i2c-hid\\|SYNA\\|ELAN\\|ALPS\\|synaptics\\|alps\\|elan' /sys/bus/i2c/devices/ 2>/dev/null", shell=True)
    lspci_tp = ""
    if _cmd_exists("lspci"):
        lspci_tp = _run("lspci | grep -i 'synaptics\\|alps\\|elan'", shell=True)
    combined_tp = (i2c_hid + lspci_tp).lower()
    info["trackpad_i2c"] = bool(i2c_hid)
    if "syna" in combined_tp or "synaptics" in combined_tp:
        info["trackpad_vendor"] = "synaptics"
    elif "alps" in combined_tp:
        info["trackpad_vendor"] = "alps"
    elif "elan" in combined_tp:
        info["trackpad_vendor"] = "elan"
    elif info["trackpad_i2c"]:
        info["trackpad_vendor"] = "i2c_hid"
    else:
        info["trackpad_vendor"] = "ps2"

    # System vendor — /sys/class/dmi/id/sys_vendor (no root needed)
    sys_vendor = _run("cat /sys/class/dmi/id/sys_vendor 2>/dev/null", shell=True)
    if not sys_vendor and _cmd_exists("dmidecode"):
        sys_vendor = _run(["dmidecode", "-s", "system-manufacturer"])
    info["system_vendor"] = sys_vendor.strip() if sys_vendor else "Unknown"

    # VM detection via DMI
    info["is_vm"] = any(v in info["system_vendor"] for v in ["VMware", "VirtualBox", "QEMU", "Xen", "Parallels"])

    # Card reader detection
    cr_raw = ""
    if _cmd_exists("lspci"):
        cr_raw = _run("lspci | grep -i 'rtl8411\\|rts5\\|card reader\\|realtek.*card'", shell=True)
    if not cr_raw:
        cr_raw = _run("ls /sys/bus/pci/drivers/rtsx* 2>/dev/null", shell=True)
    info["has_card_reader"] = bool(cr_raw)

    return info


# ─── CPU analysis ─────────────────────────────────────────────────────────────

def _cpu_details(cpu_string):
    cpu = cpu_string.lower()
    vendor = "AMD" if "amd" in cpu else "Intel"

    generation = "Unknown"
    if vendor == "Intel":
        m = re.search(r'i[3579]-(\d{4,5})', cpu)
        if m:
            num = m.group(1)
            if len(num) == 5:
                prefix = num[:2]
            elif num[:2] in ("10", "11", "12", "13", "14"):
                prefix = num[:2]
            else:
                prefix = num[0]
            gen_map = {
                "4":  "Haswell (4. gen)",
                "5":  "Broadwell (5. gen)",
                "6":  "Skylake (6. gen)",
                "7":  "Kaby Lake (7. gen)",
                "8":  "Coffee Lake (8. gen)",
                "9":  "Coffee Lake Refresh (9. gen)",
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


# ─── Compatibility check ──────────────────────────────────────────────────────

def _check_compatibility(info):
    issues = []
    warnings = []

    cpu = info.get("cpu", "").lower()
    gpus = [g.lower() for g in info.get("gpus", [])]

    for g in gpus:
        if "nvidia" in g:
            issues.append(t("compat_nvidia"))

    if re.search(r'i[3579]-1[234]\d{3}', cpu):
        warnings.append(t("compat_new_intel"))

    if "amd" in cpu and "ryzen" not in cpu:
        issues.append(t("compat_amd_old"))

    wifi = info.get("wifi", "").lower()
    if "realtek" in wifi:
        issues.append(t("compat_realtek_wifi"))
    elif "intel" in wifi:
        warnings.append(t("compat_intel_wifi"))
    elif "broadcom" in wifi or "bcm" in wifi:
        warnings.append(t("compat_broadcom_wifi"))

    compatible = t("no") if issues else (t("yes") + " (with caveats)" if warnings else t("yes"))
    return {"compatible": compatible, "issues": issues, "warnings": warnings}


# ─── Main entry ───────────────────────────────────────────────────────────────

def scan():
    os_name = platform.system()
    print(t("scan_start", os=os_name), end=" ", flush=True)

    if os_name == "Darwin":
        raw = _scan_macos()
    elif os_name == "Windows":
        raw = _scan_windows()
    elif os_name == "Linux":
        raw = _scan_linux()
    else:
        print(t("scan_unknown_os"))
        return None

    vendor, generation = _cpu_details(raw.get("cpu", ""))
    raw["os"] = os_name
    raw["cpu_vendor"] = vendor
    raw["cpu_generation"] = generation
    raw["compatibility"] = _check_compatibility(raw)

    print("✓")
    return raw


def print_summary(info, lang="EN"):
    c = info.get("compatibility", {})
    print("\n" + "=" * 52)
    print(f"  {t('hw_title')}")
    print("=" * 52)
    print(f"  CPU         : {info.get('cpu', '?')}")
    print(f"  Generation  : {info.get('cpu_generation', '?')}")
    print(f"  {t('hw_cores'):<12}: {info.get('cpu_cores', '?')}")
    print(f"  RAM         : {info.get('ram_gb', '?')} GB")
    print(f"  GPU(s)      : {', '.join(info.get('gpus', ['?']))}")
    print(f"  WiFi        : {info.get('wifi', '?')}")
    print(f"  {t('hw_audio'):<12}: {info.get('audio_codec', '?')}")
    print(f"  Ethernet    : {', '.join(info.get('ethernet', ['?']))}")
    print(f"  {t('hw_laptop'):<12}: {t('yes') if info.get('is_laptop') else t('no')}")
    print(f"  Vendor      : {info.get('system_vendor', 'Unknown')}")
    print(f"  Trackpad    : {info.get('trackpad_vendor', 'unknown')}")
    print(f"  {t('hw_macos_ok'):<12}: {c.get('compatible', '?')}")

    if c.get("issues"):
        print(f"\n  {t('hw_issues')}")
        for i in c["issues"]:
            print(f"    ✗ {i}")
    if c.get("warnings"):
        print(f"\n  {t('hw_warnings')}")
        for w in c["warnings"]:
            print(f"    ⚠ {w}")

    print("=" * 52 + "\n")


def save_report(info, path=None):
    """Save hardware report as a text file to the Desktop."""
    if path is None:
        desktop = os.path.expanduser("~/Desktop")
        path = os.path.join(desktop, "autocore_hardware.txt")
    try:
        c = info.get("compatibility", {})
        with open(path, "w", encoding="utf-8") as f:
            f.write("AutoCore — Hardware Report\n")
            f.write("=" * 44 + "\n")
            f.write(f"CPU         : {info.get('cpu', '?')}\n")
            f.write(f"Generation  : {info.get('cpu_generation', '?')}\n")
            f.write(f"Cores       : {info.get('cpu_cores', '?')}\n")
            f.write(f"RAM         : {info.get('ram_gb', '?')} GB\n")
            f.write(f"GPU(s)      : {', '.join(info.get('gpus', ['?']))}\n")
            f.write(f"WiFi        : {info.get('wifi', '?')}\n")
            f.write(f"Audio       : {info.get('audio_codec', '?')}\n")
            f.write(f"Ethernet    : {', '.join(info.get('ethernet', ['?']))}\n")
            f.write(f"Laptop      : {'Yes' if info.get('is_laptop') else 'No'}\n")
            f.write(f"Vendor      : {info.get('system_vendor', 'Unknown')}\n")
            f.write(f"Trackpad    : {info.get('trackpad_vendor', 'unknown')}\n")
            f.write(f"VM          : {'Yes' if info.get('is_vm') else 'No'}\n")
            f.write(f"macOS OK    : {c.get('compatible', '?')}\n")
            if c.get("issues"):
                f.write("\nISSUES:\n")
                for i in c["issues"]:
                    f.write(f"  ✗ {i}\n")
            if c.get("warnings"):
                f.write("\nWARNINGS:\n")
                for w in c["warnings"]:
                    f.write(f"  ⚠ {w}\n")
        return path
    except Exception:
        return None


if __name__ == "__main__":
    result = scan()
    if result:
        print_summary(result)
        save_report(result)
