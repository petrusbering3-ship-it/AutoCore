## AutoCore v2.2

A bug-squash + capability release. **Download `AutoCore.exe` below and run it — no setup needed.**

### Critical fixes
- **macOS builds no longer crash** at the USB port-mapping step (a wrong import slipped in during the v2.0 file rename).
- **The GUI can no longer erase the wrong USB drive** — on Windows, numeric drive IDs could match digits in another drive's label. The picker now matches your selection exactly.
- **USB sticks over 32 GB now format correctly on Windows** (diskpart refuses FAT32 above 32 GB — AutoCore now creates a 32 GB partition on larger sticks).

### AMD CPUs can now boot 🎉
- AutoCore now fetches the **AMD-OSX (AMD_Vanilla) kernel patches** at build time, injects your exact physical core count, and merges them into config.plist — previously AMD configs shipped without them and could never boot.
- Adds the required `DummyPowerManagement` and `ProvideCurrentCpuInfo` quirks for AMD automatically.

### Smarter audio
- Audio layout detection now works from **codec names** ("Realtek ALC256"), not just numeric IDs — so builds made from Windows/Linux get the right `alcid` instead of falling back to `alcid=1`.
- Linux reads the real HDA codec from `/proc/asound`.

### GUI catches up with the CLI (macOS)
- Backs up any existing EFI on the USB before erasing it
- Builds and copies **CoreSync.app** to the USB
- Auto-maps USB ports (UTBMap.kext)
- Validates the final config with **ocvalidate**

### Reliability & polish
- Log boxes in the GUI no longer lose output between wizard steps; clicking Back mid-operation no longer throws errors.
- A GitHub rate-limit response is no longer misreported as "no internet".
- NoTouchID (Intel-only) is no longer installed on AMD laptops.
- Friendlier errors when package auto-install fails; crash-proof logging; `--version` now reports the real version (was stuck at 1.0.0).

---
Not affiliated with Apple Inc.
