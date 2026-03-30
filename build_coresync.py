"""
AutoCore — build_coresync.py
Bygger CoreSync.app: et standalone macOS-program (ingen Python krævet)
der kopierer OpenCore EFI fra USB til den interne disk efter macOS-installation.
"""

import os
import shutil
import stat


# ─── CoreSync shell script ────────────────────────────────────────────────────

_CORESYNC_SCRIPT = r"""#!/usr/bin/env bash
# CoreSync — OpenCore Post-Install EFI Installer
# Kopierer OpenCore EFI fra AutoCore USB til din interne disk.
# Kræver ingen installation — bare dobbeltklik.

# ── Hvis ikke i terminal, åbn Terminal og kør igen ───────────────────────────
if [ ! -t 1 ]; then
    SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    osascript -e "
        tell application \"Terminal\"
            activate
            do script \"clear; '$SELF'\"
        end tell"
    exit 0
fi

# ── Farver ────────────────────────────────────────────────────────────────────
B='\033[1m'; G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; N='\033[0m'

clear
printf "\n"
printf "  ${B}╔══════════════════════════════════════════════════╗${N}\n"
printf "  ${B}║   CoreSync — OpenCore EFI Installer             ║${N}\n"
printf "  ${B}║   Kopierer OpenCore fra USB til din harddisk    ║${N}\n"
printf "  ${B}╚══════════════════════════════════════════════════╝${N}\n"
printf "\n"

# ── Find AutoCore USB ─────────────────────────────────────────────────────────
printf "  Søger efter AutoCore USB...\n"
USB_MOUNT=""

for vol in /Volumes/*/; do
    if [ -f "${vol}EFI/OC/config.plist" ] && [ -f "${vol}EFI/OC/OpenCore.efi" ]; then
        USB_MOUNT="${vol%/}"
        break
    fi
done

if [ -z "$USB_MOUNT" ]; then
    printf "\n  ${R}✗ Ingen AutoCore USB fundet!${N}\n"
    printf "  Tilslut USB'en med EFI/OC/config.plist og prøv igen.\n\n"
    read -rp "  Tryk Enter for at afslutte..." _; exit 1
fi

printf "  ${G}✓${N} USB fundet: ${B}$USB_MOUNT${N}\n"

# Tæl filer på USB som reference
USB_FILE_COUNT=$(find "$USB_MOUNT/EFI" -type f 2>/dev/null | wc -l | tr -d ' ')
printf "  → $USB_FILE_COUNT filer i EFI-mappen\n\n"

# ── Liste interne diske ───────────────────────────────────────────────────────
printf "  ${B}Tilgængelige interne diske:${N}\n\n"

DISKS=()
LABELS=()
IDX=1

while IFS= read -r line; do
    if [[ "$line" =~ ^(/dev/disk[0-9]+)[[:space:]] ]]; then
        DISK="${BASH_REMATCH[1]}"
        INFO=$(diskutil info "$DISK" 2>/dev/null)
        SIZE=$(echo "$INFO" | awk -F': ' '/Disk Size/{gsub(/ *\([^)]*\)/,"",$2); gsub(/^ +| +$/,"",$2); print $2}' | head -1)
        MODEL=$(echo "$INFO" | awk -F': ' '/Device \/ Media Name/{gsub(/^ +| +$/,"",$2); print $2}' | head -1)
        [ -z "$MODEL" ] && MODEL="Ukendt disk"
        [ -z "$SIZE" ]  && SIZE="?"
        printf "    [${IDX}] ${B}$DISK${N}  $MODEL  ($SIZE)\n"
        DISKS+=("$DISK")
        LABELS+=("$MODEL")
        ((IDX++))
    fi
done < <(diskutil list internal physical 2>/dev/null)

if [ ${#DISKS[@]} -eq 0 ]; then
    printf "\n  ${R}✗ Ingen interne diske fundet.${N}\n\n"
    read -rp "  Tryk Enter for at afslutte..." _; exit 1
fi

printf "\n"
while true; do
    read -rp "  Vælg disk [1-${#DISKS[@]}]: " CHOICE
    if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#DISKS[@]}" ]; then
        break
    fi
    printf "  Ugyldigt valg.\n"
done

TARGET_DISK="${DISKS[$((CHOICE-1))]}"
TARGET_LABEL="${LABELS[$((CHOICE-1))]}"
printf "\n  Valgt: ${B}$TARGET_DISK${N} ($TARGET_LABEL)\n\n"

# ── Find EFI-partition ────────────────────────────────────────────────────────
printf "  Søger efter EFI-partition på $TARGET_DISK...\n"

EFI_PART=$(diskutil list "$TARGET_DISK" 2>/dev/null \
    | awk '/EFI/{print $NF}' | head -1)

if [ -z "$EFI_PART" ]; then
    printf "\n  ${R}✗ Ingen EFI-partition fundet på $TARGET_DISK.${N}\n"
    printf "  Disken bruger muligvis MBR i stedet for GPT.\n\n"
    read -rp "  Tryk Enter for at afslutte..." _; exit 1
fi

printf "  ${G}✓${N} EFI-partition: ${B}/dev/$EFI_PART${N}\n\n"

# ── Bekræftelse ───────────────────────────────────────────────────────────────
printf "  ${B}┌─ OVERSIGT ─────────────────────────────────────────────────┐${N}\n"
printf "  ${B}│${N}  Kilde (USB)  : $USB_MOUNT                \n"
printf "  ${B}│${N}  Mål          : /dev/$EFI_PART  på  $TARGET_DISK       \n"
printf "  ${B}│${N}  Backup       : Eksisterende EFI gemmes på Skrivebordet \n"
printf "  ${B}└────────────────────────────────────────────────────────────┘${N}\n\n"

read -rp "  Skriv 'JA' for at installere OpenCore på $TARGET_DISK: " CONFIRM
if [ "$CONFIRM" != "JA" ]; then
    printf "\n  Annulleret.\n\n"; exit 0
fi
printf "\n"

# ── Monter EFI ────────────────────────────────────────────────────────────────
printf "  → Monterer EFI-partition..."
MOUNT_OUT=$(diskutil mount "/dev/$EFI_PART" 2>&1)
if [ $? -ne 0 ]; then
    printf " ${R}FEJL${N}\n  ! $MOUNT_OUT\n\n"
    read -rp "  Tryk Enter for at afslutte..." _; exit 1
fi

EFI_MOUNT=$(printf '%s' "$MOUNT_OUT" | grep -oE '/Volumes/[^ ]+' | head -1)
[ -z "$EFI_MOUNT" ] && EFI_MOUNT="/Volumes/EFI"
printf " ${G}✓${N} ($EFI_MOUNT)\n"

# ── Backup eksisterende EFI ───────────────────────────────────────────────────
if [ -d "$EFI_MOUNT/EFI" ]; then
    BACKUP="$HOME/Desktop/EFI_backup_$(date +%Y%m%d_%H%M%S)"
    printf "  → Sikkerhedskopierer eksisterende EFI..."
    if cp -r "$EFI_MOUNT/EFI" "$BACKUP" 2>/dev/null; then
        printf " ${G}✓${N}\n  → Gemt: ~/Desktop/$(basename "$BACKUP")\n"
    else
        printf " ${Y}!${N} (advarsel: backup fejlede — fortsætter)\n"
    fi
fi

# ── Kopier EFI ────────────────────────────────────────────────────────────────
printf "  → Kopierer EFI fra USB til disk..."
rm -rf "$EFI_MOUNT/EFI" 2>/dev/null
cp -r "$USB_MOUNT/EFI" "$EFI_MOUNT/" 2>/dev/null
COPY_RC=$?

if [ $COPY_RC -ne 0 ]; then
    printf " ${R}FEJL${N} (exit $COPY_RC)\n"
    diskutil unmount "$EFI_MOUNT" &>/dev/null
    printf "\n  Mulig årsag: manglende tilladelser. Prøv at køre fra Terminal:\n"
    printf "  sudo cp -r \"$USB_MOUNT/EFI\" \"$EFI_MOUNT/\"\n\n"
    read -rp "  Tryk Enter for at afslutte..." _; exit 1
fi
printf " ${G}✓${N}\n"

# ── Verificering ──────────────────────────────────────────────────────────────
printf "  → Verificerer...\n"
ERRORS=0
WARNINGS=0

# Fil-tælling
DST_COUNT=$(find "$EFI_MOUNT/EFI" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$USB_FILE_COUNT" -ne "$DST_COUNT" ]; then
    printf "  ${Y}!${N} Fil-mismatch: USB=$USB_FILE_COUNT kopieret=$DST_COUNT\n"
    ((WARNINGS++))
fi

# Kritiske filer
declare -a CRITICAL=(
    "EFI/BOOT/BOOTx64.efi"
    "EFI/OC/OpenCore.efi"
    "EFI/OC/config.plist"
)
for F in "${CRITICAL[@]}"; do
    if [ ! -f "$EFI_MOUNT/$F" ]; then
        printf "  ${R}✗ Mangler: $F${N}\n"
        ((ERRORS++))
    else
        printf "  ${G}✓${N} $F\n"
    fi
done

# Kexts mappe
KEXT_COUNT=$(find "$EFI_MOUNT/EFI/OC/Kexts" -name "*.kext" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
printf "  ${G}✓${N} EFI/OC/Kexts — $KEXT_COUNT kexts\n"

# ── Afmonter ──────────────────────────────────────────────────────────────────
printf "  → Afmonterer EFI-partition..."
diskutil unmount "$EFI_MOUNT" &>/dev/null
printf " ${G}✓${N}\n\n"

# ── Resultat ──────────────────────────────────────────────────────────────────
if [ "$ERRORS" -eq 0 ]; then
    printf "  ${G}${B}╔══════════════════════════════════════════════════╗${N}\n"
    printf "  ${G}${B}║  ✓  CoreSync fuldført uden fejl!                ║${N}\n"
    printf "  ${G}${B}╚══════════════════════════════════════════════════╝${N}\n\n"
    printf "  OpenCore er installeret på ${B}$TARGET_DISK${N}.\n\n"
    printf "  ${B}Hvad sker der nu:${N}\n"
    printf "  1. Fjern USB-drevet\n"
    printf "  2. Genstart computeren\n"
    printf "  3. Gå ind i BIOS/UEFI og sæt ${B}$TARGET_DISK${N} som første boot-enhed\n"
    printf "  4. Computeren starter direkte i OpenCore fra nu af\n"
else
    printf "  ${Y}${B}╔══════════════════════════════════════════════════╗${N}\n"
    printf "  ${Y}${B}║  ⚠  CoreSync fuldført med $ERRORS fejl           ║${N}\n"
    printf "  ${Y}${B}╚══════════════════════════════════════════════════╝${N}\n\n"
    printf "  Tjek fejlene ovenfor. EFI-backup er på Skrivebordet.\n"
fi

printf "\n"
read -rp "  Tryk Enter for at afslutte..."
printf "\n"
"""

# ─── Info.plist ───────────────────────────────────────────────────────────────

_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>CoreSync</string>
    <key>CFBundleIdentifier</key>
    <string>com.autocore.coresync</string>
    <key>CFBundleName</key>
    <string>CoreSync</string>
    <key>CFBundleDisplayName</key>
    <string>CoreSync</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
"""


# ─── Builder ──────────────────────────────────────────────────────────────────

def build(output_dir):
    """
    Bygger CoreSync.app i output_dir.
    Kopierer også til Skrivebordet hvis muligt.
    Returnerer stien til .app eller None ved fejl.
    """
    import platform
    if platform.system() != "Darwin":
        return None  # Kun macOS

    app_dir   = os.path.join(output_dir, "CoreSync.app")
    macos_dir = os.path.join(app_dir, "Contents", "MacOS")
    res_dir   = os.path.join(app_dir, "Contents", "Resources")

    try:
        os.makedirs(macos_dir, exist_ok=True)
        os.makedirs(res_dir,   exist_ok=True)

        # Skriv shell script
        script_path = os.path.join(macos_dir, "CoreSync")
        with open(script_path, "w") as f:
            f.write(_CORESYNC_SCRIPT)
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Skriv Info.plist
        with open(os.path.join(app_dir, "Contents", "Info.plist"), "w") as f:
            f.write(_INFO_PLIST)

        # Kopier til Skrivebord
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "CoreSync.app")
        if os.path.exists(desktop):
            shutil.rmtree(desktop)
        shutil.copytree(app_dir, desktop)

        return app_dir if os.path.exists(app_dir) else None

    except Exception as e:
        print(f"  ! CoreSync.app build fejlede: {e}")
        return None
