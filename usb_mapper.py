"""
AutoCore — usb_mapper.py
Automatisk USB port-mapper via IORegistry (macOS).

Læser alle USB-porte fra IORegistry uden at brugeren skal sætte noget i.
Genererer UTBMap.kext som USBToolBox.kext bruger til permanent port-mapping.
Tilføjer UTBMap til EFI/OC/Kexts/ og config.plist Kernel.Add automatisk.

Connector typer (UsbConnector):
  0   = USB 2.0 Type-A (ekstern)
  3   = USB 3.x Type-A (ekstern)
  8   = USB-C med switch (USB2+USB3)
  9   = USB 2.0 companion (intern del af USB3-port)
  10  = USB-C kun USB3
  255 = Intern (Bluetooth, fingerprint, webcam)
"""

import os
import platform
import plistlib
import shutil
import subprocess
import struct


def _run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        return result.stdout
    except Exception:
        return b""


def _scan_ports_macos():
    """
    Læs USB-porte fra IORegistry via ioreg.
    Returnerer dict: port_name → {connector, port_data, location, controller}
    """
    raw = _run(["ioreg", "-r", "-c", "AppleUSBXHCIPort", "-a", "-d", "4"])
    if not raw:
        return {}

    try:
        entries = plistlib.loads(raw)
    except Exception:
        return {}

    ports = {}
    for entry in entries:
        name = entry.get("IORegistryEntryName", "")
        if not name:
            continue

        # UsbConnector fortæller port-typen
        connector = entry.get("UsbConnector", entry.get("PortType", -1))
        port_data = entry.get("port", b"\x00\x00\x00\x00")
        location  = entry.get("locationID", 0)

        # Få controller-navn fra parent-chain (til multi-controller systemer)
        controller = entry.get("IOParentRegistryEntryName", "XHC")

        if isinstance(port_data, bytes) and len(port_data) >= 4:
            port_index = struct.unpack_from("<I", port_data[:4])[0]
        else:
            port_index = 0

        ports[name] = {
            "connector":   connector,
            "port_data":   port_data if isinstance(port_data, bytes) else bytes(4),
            "location":    location,
            "controller":  controller,
            "port_index":  port_index,
        }

    return ports


def _guess_connector(port_name, port_index):
    """
    Gæt connector-type ud fra port-navn og indeks.
    HS = High Speed (USB 2.0), SS = SuperSpeed (USB 3.x)
    USR = intern, PR = intern.
    """
    name_upper = port_name.upper()

    if "SS" in name_upper:
        return 3      # USB 3.x Type-A ekstern
    if "HS" in name_upper:
        # HS01-HS14: ekstern. Interne porte har typisk højere numre.
        if port_index > 12:
            return 255    # Sandsynligvis intern (BT, webcam)
        return 0          # USB 2.0 Type-A ekstern
    if "PR" in name_upper or "USR" in name_upper:
        return 255    # Intern
    # Ukendt — sæt som USB 2.0 ekstern
    return 0


def _port_type_label(connector):
    labels = {
        0:   "USB 2.0 A",
        3:   "USB 3.x A",
        8:   "USB-C (m/switch)",
        9:   "USB 2.0 (companion)",
        10:  "USB-C",
        255: "Intern",
    }
    return labels.get(connector, f"Ukendt ({connector})")


def _generate_utbmap_kext(ports, smbios_model, kext_dir):
    """
    Generer UTBMap.kext/Contents/Info.plist.
    Følger USBToolBox's format (UTBMapVersion 2).
    """
    contents_dir = os.path.join(kext_dir, "UTBMap.kext", "Contents")
    os.makedirs(contents_dir, exist_ok=True)

    port_entries = {}
    for name, info in ports.items():
        connector = info["connector"]
        if connector == -1:
            connector = _guess_connector(name, info["port_index"])

        port_data = info["port_data"]
        if not isinstance(port_data, bytes) or len(port_data) < 4:
            port_data = struct.pack("<I", info["port_index"])

        port_entries[name] = {
            "UsbConnector": connector,
            "port":         port_data,
        }

    info_plist = {
        "CFBundleIdentifier":        "com.dhinakg.USBToolBox.Map",
        "CFBundleName":              "UTBMap",
        "CFBundlePackageType":       "KEXT",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion":           "1.1.0",
        "IOKitPersonalities": {
            "UTBMap": {
                "IOClass":       "USBToolBox",
                "IOProviderClass": "IOPCIDevice",
                "UTBMapVersion": 2,
                "model":         smbios_model,
                "Ports":         port_entries,
            }
        },
        "OSBundleRequired": "Root",
    }

    plist_path = os.path.join(contents_dir, "Info.plist")
    with open(plist_path, "wb") as f:
        plistlib.dump(info_plist, f, fmt=plistlib.FMT_XML)

    return os.path.join(kext_dir, "UTBMap.kext")


def _copy_kext_to_efi(kext_path, output_dir):
    """Kopier UTBMap.kext til EFI/OC/Kexts/."""
    dst = os.path.join(output_dir, "EFI", "OC", "Kexts", "UTBMap.kext")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(kext_path, dst)


def _add_utbmap_to_config(config_path):
    """Tilføj UTBMap.kext entry til Kernel.Add i config.plist."""
    if not config_path or not os.path.exists(config_path):
        return

    with open(config_path, "rb") as f:
        config = plistlib.load(f)

    kernel_add = config.get("Kernel", {}).get("Add", [])

    # Tjek om UTBMap allerede er der
    if any(e.get("BundlePath") == "UTBMap.kext" for e in kernel_add):
        return

    # Find USBToolBox position og sæt UTBMap efter det
    insert_after = len(kernel_add)
    for i, entry in enumerate(kernel_add):
        if entry.get("BundlePath") == "USBToolBox.kext":
            insert_after = i + 1
            break

    utbmap_entry = {
        "Arch":           "x86_64",
        "BundlePath":     "UTBMap.kext",
        "Comment":        "AutoCore USB Map",
        "Enabled":        True,
        "ExecutablePath": "",
        "MaxKernel":      "",
        "MinKernel":      "",
        "PlistPath":      "Contents/Info.plist",
    }

    kernel_add.insert(insert_after, utbmap_entry)
    config.setdefault("Kernel", {})["Add"] = kernel_add

    with open(config_path, "wb") as f:
        plistlib.dump(config, f, fmt=plistlib.FMT_XML, sort_keys=False)


def _print_port_table(ports):
    """Vis en pæn tabel over alle fundne porte."""
    print()
    print("  USB PORTE — AUTOCORE MAP")
    print("  " + "-" * 48)
    print(f"  {'Port':<8} {'Type':<20} {'Indeks':>7}  {'Connector':>5}")
    print("  " + "-" * 48)
    for name in sorted(ports.keys()):
        info = ports[name]
        connector = info["connector"]
        if connector == -1:
            connector = _guess_connector(name, info["port_index"])
            label = _port_type_label(connector) + " *"
        else:
            label = _port_type_label(connector)
        print(f"  {name:<8} {label:<20} {info['port_index']:>7}  {connector:>5}")
    print("  " + "-" * 48)
    print("  * = Gættet ud fra port-navn (ingen enheder detekteret)")
    print()


def run(smbios_model, kexts_dir, output_dir, config_path):
    """
    Hoved-funktion — kaldes fra main.py.
    Kører kun på macOS.
    """
    if platform.system() != "Darwin":
        return

    print("  → Automatisk USB-mapping via IORegistry...", end=" ", flush=True)

    ports = _scan_ports_macos()
    if not ports:
        print("FEJL — ingen USB porte fundet i IORegistry")
        return

    print(f"✓ ({len(ports)} porte)")

    # macOS-grænse: max 15 porte per controller
    if len(ports) > 15:
        # Sorter: SS porte, HS porte, interne sidst. Behold de første 15.
        def port_priority(item):
            name, info = item
            conn = info["connector"]
            if conn in (3, 8, 10):  return 0   # SS / USB-C
            if conn == 0:           return 1   # HS ekstern
            if conn == 9:           return 2   # Companion
            if conn == 255:         return 3   # Intern
            return 2
        sorted_ports = sorted(ports.items(), key=port_priority)
        ports = dict(sorted_ports[:15])
        print(f"  ⚠  Begrænset til 15 porte (macOS limit). {len(ports)} porte behold.")

    # Vis tabel
    _print_port_table(ports)

    # Generer UTBMap.kext
    kext_path = _generate_utbmap_kext(ports, smbios_model, kexts_dir)

    # Kopier til EFI
    _copy_kext_to_efi(kext_path, output_dir)

    # Tilføj til config.plist
    _add_utbmap_to_config(config_path)

    ambiguous = [
        name for name, info in ports.items()
        if info["connector"] == -1
    ]
    if ambiguous:
        print(f"  ⚠  {len(ambiguous)} porte med ukendt type — gættet ud fra navn")
        print(f"     Stik en USB-enhed i hver port og kør USBToolBox for præcis mapping")

    print(f"  ✓ UTBMap.kext genereret og tilføjet til EFI ({len(ports)} porte)")


if __name__ == "__main__":
    # Test
    if platform.system() == "Darwin":
        ports = _scan_ports_macos()
        print(f"Fandt {len(ports)} USB porte:")
        for name, info in sorted(ports.items()):
            c = info["connector"]
            if c == -1:
                c = _guess_connector(name, info["port_index"])
            print(f"  {name:<8} → {_port_type_label(c)}")
    else:
        print("USB-mapping kræver macOS (IORegistry)")
