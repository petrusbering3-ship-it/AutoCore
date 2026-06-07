"""
AutoCore — gui.py
Wizard-style GUI entry point.  Run directly or via the compiled .exe.
"""

import os
import sys
import queue
import threading
import tempfile
import platform
import time
import subprocess as _sp


# ── Bootstrap required packages before any imports ────────────────────────────
def _bootstrap():
    missing = []
    for pkg in ("customtkinter", "requests"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"  [AutoCore] Installing: {', '.join(missing)}...", end=" ", flush=True)
        _sp.run(
            [sys.executable, "-m", "pip", "install"] + missing + ["--quiet"],
            check=True,
        )
        print("✓")


_bootstrap()

import customtkinter as ctk  # noqa: E402

from lang import set_lang  # noqa: E402
from constants import MACOS_VERSIONS  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Palette ───────────────────────────────────────────────────────────────────

C_ACCENT  = "#3b82f6"   # blue-500
C_SUCCESS = "#22c55e"   # green-500
C_WARN    = "#f59e0b"   # amber-500
C_ERROR   = "#ef4444"   # red-500
C_MUTED   = "#64748b"   # slate-500
C_CARD    = "#1e293b"   # slate-800
C_HEADER  = "#0f172a"   # slate-900


# ── stdout → queue bridge ─────────────────────────────────────────────────────

class _LogCapture:
    """Redirect print() to a thread-safe queue so the GUI can display it."""

    def __init__(self, q: queue.Queue):
        self._q    = q
        self._real = sys.__stdout__

    def write(self, text: str):
        if text:
            self._q.put(text)
        if self._real:
            try:
                self._real.write(text)
            except Exception:
                pass

    def flush(self):
        if self._real:
            try:
                self._real.flush()
            except Exception:
                pass

    def fileno(self):
        return 1


# ── Main application ──────────────────────────────────────────────────────────

class AutoCoreApp(ctk.CTk):
    N_STEPS = 6

    def __init__(self):
        super().__init__()
        self.title("AutoCore")
        self.geometry("760x570")
        self.resizable(False, False)

        # ── Shared state ──────────────────────────────────────────────────────
        self._hw          = None
        self._macos       = None
        self._selected    = []
        self._failed      = []
        self._output_dir  = os.path.join(tempfile.gettempdir(), "autocore_build")
        self._kexts_dir   = os.path.join(self._output_dir, "_kexts")
        self._build_res   = None
        self._config_path = None
        self._usb_drive   = None
        self._safe_drives = []
        self._lang        = "EN"
        self._step        = 0

        # ── Log capture ───────────────────────────────────────────────────────
        self._log_q = queue.Queue()
        sys.stdout  = _LogCapture(self._log_q)

        # ── Layout ────────────────────────────────────────────────────────────
        self._build_header()

        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=24, pady=(10, 0))

        self._build_footer()
        self._show_step(0)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=C_HEADER)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="  ⬛  AutoCore",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=16)

        self._dots_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        self._dots_frame.pack(side="right", padx=16)

        self._dot_labels = []
        step_names = ["Welcome", "Hardware", "macOS", "Kexts", "Build", "Flash"]
        for i in range(self.N_STEPS):
            col = ctk.CTkFrame(self._dots_frame, fg_color="transparent")
            col.pack(side="left", padx=4)
            dot = ctk.CTkLabel(col, text="○", font=ctk.CTkFont(size=16),
                               text_color=C_MUTED, width=16)
            dot.pack()
            ctk.CTkLabel(col, text=step_names[i], font=ctk.CTkFont(size=9),
                         text_color=C_MUTED).pack()
            self._dot_labels.append(dot)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ftr = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color=C_HEADER)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)

        self._back_btn = ctk.CTkButton(
            ftr, text="← Back", width=100,
            fg_color="transparent", border_width=1, border_color=C_MUTED,
            text_color=C_MUTED, hover_color=C_CARD,
            command=self._go_back, state="disabled",
        )
        self._back_btn.pack(side="left", padx=16, pady=10)

        self._status_lbl = ctk.CTkLabel(
            ftr, text="", font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        )
        self._status_lbl.pack(side="left", padx=8)

        self._next_btn = ctk.CTkButton(
            ftr, text="Next →", width=130,
            fg_color="#334155", hover_color="#2563eb",
            command=self._go_next, state="disabled",
        )
        self._next_btn.pack(side="right", padx=16, pady=10)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _update_dots(self, step: int):
        for i, lbl in enumerate(self._dot_labels):
            if i < step:
                lbl.configure(text="●", text_color=C_SUCCESS)
            elif i == step:
                lbl.configure(text="●", text_color=C_ACCENT)
            else:
                lbl.configure(text="○", text_color=C_MUTED)

    def _set_nav(self, *, back=False, next_text="Next →",
                 next_on=False, next_color=None):
        self._back_btn.configure(
            state="normal" if back else "disabled",
            text_color="white" if back else C_MUTED,
        )
        self._next_btn.configure(
            text=next_text,
            state="normal" if next_on else "disabled",
            fg_color=(next_color or C_ACCENT) if next_on else "#334155",
        )

    def _set_status(self, msg: str, color: str = None):
        self._status_lbl.configure(text=msg, text_color=color or C_MUTED)

    def _go_next(self):
        self._show_step(self._step + 1)

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _show_step(self, n: int):
        self._step = n
        self._update_dots(n)
        for w in self._content.winfo_children():
            w.destroy()
        [
            self._step_welcome,
            self._step_hardware,
            self._step_macos,
            self._step_kexts,
            self._step_build,
            self._step_usb,
        ][n]()

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _title(self, parent, text: str, sub: str = None):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 2))
        if sub:
            ctk.CTkLabel(
                parent, text=sub,
                font=ctk.CTkFont(size=12), text_color=C_MUTED, anchor="w",
            ).pack(fill="x", pady=(0, 10))
        else:
            ctk.CTkFrame(parent, height=1, fg_color="#334155").pack(fill="x", pady=(0, 10))

    def _log_box(self, parent, height: int = 90) -> ctk.CTkTextbox:
        tb = ctk.CTkTextbox(
            parent, height=height,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0f172a", text_color="#94a3b8",
            corner_radius=6, state="disabled",
        )
        tb.pack(fill="x", pady=(8, 0))
        return tb

    def _poll_log(self, textbox: ctk.CTkTextbox):
        try:
            while True:
                chunk = self._log_q.get_nowait()
                textbox.configure(state="normal")
                textbox.insert("end", chunk)
                textbox.see("end")
                textbox.configure(state="disabled")
        except queue.Empty:
            pass
        # Re-schedule only while we're still on the same step's textbox
        self.after(80, lambda: self._poll_log(textbox))

    def _run_thread(self, fn, on_done, *args, **kwargs):
        """Run fn(*args, **kwargs) in background; call on_done(result, err) on main thread."""
        def _inner():
            try:
                r = fn(*args, **kwargs)
                self.after(0, lambda res=r: on_done(res, None))
            except Exception as e:
                self.after(0, lambda err=e: on_done(None, err))
        threading.Thread(target=_inner, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    # Step 0: Welcome
    # ══════════════════════════════════════════════════════════════════════════

    def _step_welcome(self):
        self._set_nav(next_text="Get Started →", next_on=True, next_color=C_ACCENT)
        self._set_status("")

        f = self._content
        ctk.CTkLabel(f, text="🍎", font=ctk.CTkFont(size=72)).pack(pady=(20, 0))
        ctk.CTkLabel(f, text="AutoCore",
                     font=ctk.CTkFont(size=40, weight="bold")).pack()
        ctk.CTkLabel(f, text="Hackintosh USB Builder  •  v1.3",
                     font=ctk.CTkFont(size=14), text_color=C_MUTED).pack(pady=(4, 28))

        ctk.CTkLabel(f, text="Language / Sprog",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(0, 8))

        lang_row = ctk.CTkFrame(f, fg_color="transparent")
        lang_row.pack()

        self._lang_en_btn = ctk.CTkButton(
            lang_row, text="🇬🇧  English", width=150, height=38,
            fg_color=C_ACCENT if self._lang == "EN" else "transparent",
            border_width=1, border_color=C_ACCENT,
            command=lambda: self._pick_lang("EN"),
        )
        self._lang_en_btn.pack(side="left", padx=8)

        self._lang_da_btn = ctk.CTkButton(
            lang_row, text="🇩🇰  Dansk", width=150, height=38,
            fg_color=C_ACCENT if self._lang == "DA" else "transparent",
            border_width=1, border_color=C_ACCENT,
            command=lambda: self._pick_lang("DA"),
        )
        self._lang_da_btn.pack(side="left", padx=8)

        ctk.CTkLabel(
            f,
            text="⚠  Requires an internet connection to download kexts and OpenCore",
            font=ctk.CTkFont(size=11), text_color=C_MUTED,
        ).pack(pady=(24, 0))

    def _pick_lang(self, code: str):
        self._lang = code
        set_lang(code)
        self._lang_en_btn.configure(fg_color=C_ACCENT if code == "EN" else "transparent")
        self._lang_da_btn.configure(fg_color=C_ACCENT if code == "DA" else "transparent")

    # ══════════════════════════════════════════════════════════════════════════
    # Step 1: Hardware scan
    # ══════════════════════════════════════════════════════════════════════════

    def _step_hardware(self):
        self._set_nav(back=True, next_on=False)
        self._set_status("Scanning hardware…")

        f = self._content
        self._title(f, "Hardware Scan", "Detecting your system configuration")

        results = ctk.CTkScrollableFrame(f, height=240, fg_color=C_CARD, corner_radius=8)
        results.pack(fill="x")
        self._hw_results = results

        self._hw_spin = ctk.CTkLabel(results, text="⠙  Scanning…",
                                     text_color=C_MUTED, font=ctk.CTkFont(size=13))
        self._hw_spin.pack(pady=24)

        log = self._log_box(f, height=60)
        self._poll_log(log)

        def _scan():
            import hardware
            return hardware.scan()

        def _done(hw, err):
            if err or not hw:
                self._hw_spin.configure(text=f"✗  Scan failed: {err}", text_color=C_ERROR)
                self._set_status("Scan failed", C_ERROR)
                return
            self._hw = hw
            self._render_hw_cards(hw)
            self._set_status("Hardware detected", C_SUCCESS)
            self._set_nav(back=True, next_on=True)

        self._run_thread(_scan, _done)

    def _render_hw_cards(self, hw: dict):
        self._hw_spin.destroy()

        fields = [
            ("CPU",      hw.get("cpu", "?")),
            ("Gen",      hw.get("cpu_generation", "?")),
            ("RAM",      f"{hw.get('ram_gb', '?')} GB"),
            ("GPU",      ", ".join(hw.get("gpus", ["?"])[:2])),
            ("WiFi",     hw.get("wifi", "?")),
            ("Ethernet", ", ".join(hw.get("ethernet", ["?"])[:2])),
            ("Type",     "Laptop" if hw.get("is_laptop") else "Desktop"),
            ("Vendor",   hw.get("system_vendor", "?")),
        ]

        for label, value in fields:
            row = ctk.CTkFrame(self._hw_results, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=f"{label}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=C_MUTED, width=70, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=str(value)[:60],
                         font=ctk.CTkFont(size=12), anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text="✓", text_color=C_SUCCESS,
                         font=ctk.CTkFont(size=12)).pack(side="right", padx=12)

        compat = hw.get("compatibility", {})
        for issue in compat.get("issues", []):
            card = ctk.CTkFrame(self._hw_results, fg_color="#450a0a", corner_radius=4)
            card.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(card, text=f"✗  {issue}", text_color=C_ERROR,
                         font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=600).pack(padx=10, pady=4, fill="x")
        for warn in compat.get("warnings", []):
            card = ctk.CTkFrame(self._hw_results, fg_color="#431407", corner_radius=4)
            card.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(card, text=f"⚠  {warn}", text_color=C_WARN,
                         font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=600).pack(padx=10, pady=4, fill="x")

    # ══════════════════════════════════════════════════════════════════════════
    # Step 2: macOS version
    # ══════════════════════════════════════════════════════════════════════════

    def _step_macos(self):
        self._set_nav(back=True, next_on=bool(self._macos))
        self._set_status("Choose a macOS version to install")

        f = self._content
        self._title(f, "Select macOS Version")

        ICONS = {
            "Big Sur": "🏔", "Monterey": "🌊",
            "Ventura": "🌁", "Sonoma": "🍇", "Sequoia": "🌲",
        }

        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(pady=(4, 12))

        self._macos_btns = {}
        for i, ver in enumerate(MACOS_VERSIONS):
            col, row = i % 3, i // 3
            btn = ctk.CTkButton(
                grid,
                text=f"{ICONS.get(ver, '🍎')}\n{ver}",
                width=216, height=84,
                font=ctk.CTkFont(size=14),
                fg_color=C_ACCENT if self._macos == ver else C_CARD,
                hover_color="#2563eb",
                border_width=2,
                border_color=C_ACCENT if self._macos == ver else "#334155",
                corner_radius=10,
                command=lambda v=ver: self._pick_macos(v),
            )
            btn.grid(row=row, column=col, padx=6, pady=6)
            self._macos_btns[ver] = btn

        # Hardware-aware hints
        if self._hw:
            import re as _re
            m = _re.search(r"(\d+)\. gen", self._hw.get("cpu_generation", ""))
            gen = int(m.group(1)) if m else 0
            hints = []
            if gen >= 12:
                hints.append("⚠  Gen 12+ Intel: Ventura or later recommended")
            if self._hw.get("cpu_vendor") == "AMD":
                hints.append("⚠  AMD Ryzen: Ventura recommended for best compatibility")
            for hint in hints:
                ctk.CTkLabel(f, text=hint, text_color=C_WARN,
                             font=ctk.CTkFont(size=12), anchor="w").pack(fill="x")

    def _pick_macos(self, ver: str):
        self._macos = ver
        for v, btn in self._macos_btns.items():
            sel = v == ver
            btn.configure(fg_color=C_ACCENT if sel else C_CARD,
                          border_color=C_ACCENT if sel else "#334155")
        self._set_nav(back=True, next_on=True)
        self._set_status(f"Selected: {ver}")

    # ══════════════════════════════════════════════════════════════════════════
    # Step 3: Kext download
    # ══════════════════════════════════════════════════════════════════════════

    def _step_kexts(self):
        import kexts as _kexts

        self._selected = _kexts.select_kexts(self._hw, self._macos)
        n = len(self._selected)

        self._set_nav(back=True, next_on=False)
        self._set_status(f"Downloading {n} kexts…")

        f = self._content
        self._title(f, "Kexts", f"Downloading {n} kexts selected for your hardware")

        # Overall progress
        self._kext_bar = ctk.CTkProgressBar(f, height=10)
        self._kext_bar.pack(fill="x", pady=(0, 4))
        self._kext_bar.set(0)

        self._kext_lbl = ctk.CTkLabel(f, text="Preparing…",
                                      font=ctk.CTkFont(size=12),
                                      text_color=C_MUTED, anchor="w")
        self._kext_lbl.pack(fill="x")

        # Kext list
        scroll = ctk.CTkScrollableFrame(f, height=200, fg_color=C_CARD, corner_radius=8)
        scroll.pack(fill="x", pady=(6, 0))

        self._kext_row_icons = {}
        for name in self._selected:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            icon = ctk.CTkLabel(row, text="○", width=18,
                                text_color=C_MUTED, font=ctk.CTkFont(size=13))
            icon.pack(side="left")
            ctk.CTkLabel(row, text=name + ".kext",
                         font=ctk.CTkFont(size=12), anchor="w").pack(side="left", padx=6)
            self._kext_row_icons[name] = icon

        log = self._log_box(f, height=56)
        self._poll_log(log)

        os.makedirs(self._kexts_dir, exist_ok=True)

        def _download():
            return _kexts.download_kexts(
                self._selected, self._hw, self._macos, self._kexts_dir
            )

        def _done(result, err):
            self._kext_bar.set(1.0)
            if err:
                self._kext_lbl.configure(text=f"Error: {err}", text_color=C_ERROR)
                self._set_status("Download failed", C_ERROR)
                return
            selected, failed = result
            self._selected = selected
            self._failed   = failed
            for name, icon in self._kext_row_icons.items():
                icon.configure(
                    text="✗" if name in failed else "✓",
                    text_color=C_ERROR if name in failed else C_SUCCESS,
                )
            if failed:
                self._kext_lbl.configure(
                    text=f"Done — {len(failed)} manual download(s) required  (see log)",
                    text_color=C_WARN,
                )
                self._set_status(f"{len(selected)} kexts ready, {len(failed)} manual", C_WARN)
            else:
                self._kext_lbl.configure(
                    text=f"All {len(selected)} kexts ready ✓", text_color=C_SUCCESS,
                )
                self._set_status(f"All {len(selected)} kexts downloaded", C_SUCCESS)
            self._set_nav(back=True, next_on=True)

        self._run_thread(_download, _done)
        self._watch_kexts()

    def _watch_kexts(self):
        """Animate progress bar and row icons while download runs."""
        if self._step != 3:
            return
        try:
            done = sum(
                1 for d in os.listdir(self._kexts_dir)
                if d.endswith(".kext") and os.path.isdir(os.path.join(self._kexts_dir, d))
            )
            total = max(len(self._selected), 1)
            self._kext_bar.set(min(done / total, 0.97))
            self._kext_lbl.configure(text=f"Downloading… {done}/{total} kexts")

            for name, icon in self._kext_row_icons.items():
                if os.path.isdir(os.path.join(self._kexts_dir, name + ".kext")):
                    if icon.cget("text") in ("○", "↓"):
                        icon.configure(text="✓", text_color=C_SUCCESS)
                elif icon.cget("text") == "○":
                    icon.configure(text="↓", text_color=C_ACCENT)
        except Exception:
            pass
        self.after(350, self._watch_kexts)

    # ══════════════════════════════════════════════════════════════════════════
    # Step 4: Build EFI
    # ══════════════════════════════════════════════════════════════════════════

    def _step_build(self):
        self._set_nav(back=True, next_on=False)
        self._set_status("Building EFI…")

        f = self._content
        self._title(f, "Build EFI", "Downloading OpenCore, generating config.plist")

        # Step checklist
        checklist = ctk.CTkFrame(f, fg_color=C_CARD, corner_radius=8)
        checklist.pack(fill="x")

        steps = [
            "Download OpenCore",
            "Copy SSDTs to EFI/OC/ACPI",
            "Move kexts → EFI/OC/Kexts",
            "Generate config.plist",
            "Download macOS recovery",
        ]
        self._build_icons = []
        for s in steps:
            row = ctk.CTkFrame(checklist, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=5)
            icon = ctk.CTkLabel(row, text="○", width=20,
                                text_color=C_MUTED, font=ctk.CTkFont(size=14))
            icon.pack(side="left")
            ctk.CTkLabel(row, text=s, font=ctk.CTkFont(size=13),
                         anchor="w").pack(side="left", padx=10)
            self._build_icons.append(icon)

        log = self._log_box(f, height=156)
        self._poll_log(log)
        self._build_log = log

        os.makedirs(self._output_dir, exist_ok=True)

        def _build():
            import efi_builder
            return efi_builder.build(
                self._macos, self._kexts_dir, self._output_dir, hardware=self._hw,
            )

        def _done(res, err):
            if err or not res or not res.get("ok"):
                msg = str(err) if err else "Build failed"
                for icon in self._build_icons:
                    if icon.cget("text") == "↓":
                        icon.configure(text="✗", text_color=C_ERROR)
                self._set_status(msg, C_ERROR)
                return

            self._build_res = res
            # Mark first 3 steps done (OpenCore/SSDTs/kexts done by efi_builder)
            for icon in self._build_icons[:3]:
                icon.configure(text="✓", text_color=C_SUCCESS)

            # config.plist (runs on main thread — fast, no blocking I/O)
            try:
                import config_plist
                self._config_path = config_plist.generate(
                    self._hw, self._selected, self._macos, self._output_dir,
                    ssdts=res.get("ssdts", []),
                    opencanopy=res.get("opencanopy", False),
                )
                self._build_icons[3].configure(text="✓", text_color=C_SUCCESS)
            except Exception as e:
                self._build_icons[3].configure(text="✗", text_color=C_ERROR)
                print(f"\n  ! config.plist generation failed: {e}")

            # Recovery download is part of efi_builder.build; mark done
            self._build_icons[4].configure(text="✓", text_color=C_SUCCESS)

            self._set_status("EFI built successfully", C_SUCCESS)
            self._set_nav(back=True, next_on=True)

        self._run_thread(_build, _done)
        self._watch_build()

    def _watch_build(self):
        """Advance checklist icons by matching log keywords."""
        if self._step != 4:
            return
        try:
            text = self._build_log.get("1.0", "end").lower()
            markers = [
                ("opencore", 0),
                ("ssdt", 1),
                ("kexts copied", 2),
                ("config.plist", 3),
                ("recovery", 4),
            ]
            for keyword, idx in markers:
                icon = self._build_icons[idx]
                if keyword in text and icon.cget("text") == "○":
                    icon.configure(text="↓", text_color=C_ACCENT)
        except Exception:
            pass
        self.after(600, self._watch_build)

    # ══════════════════════════════════════════════════════════════════════════
    # Step 5: Flash USB
    # ══════════════════════════════════════════════════════════════════════════

    def _step_usb(self):
        self._set_nav(back=True, next_on=False, next_text="Finish ✓")
        self._set_status("Select a USB drive")

        f = self._content
        self._title(f, "Flash to USB",
                    "Formats the drive and writes EFI + macOS recovery")

        # Drive selector row
        sel_row = ctk.CTkFrame(f, fg_color="transparent")
        sel_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(sel_row, text="USB Drive:", width=90,
                     font=ctk.CTkFont(size=13), anchor="w").pack(side="left")

        self._drive_var  = ctk.StringVar(value="Scanning…")
        self._drive_menu = ctk.CTkOptionMenu(
            sel_row, variable=self._drive_var,
            values=["Scanning…"], width=360,
            command=self._on_drive_pick,
        )
        self._drive_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            sel_row, text="↺", width=36,
            fg_color="transparent", border_width=1, border_color=C_MUTED,
            font=ctk.CTkFont(size=16),
            command=self._refresh_drives,
        ).pack(side="left")

        # Warning banner
        warn_card = ctk.CTkFrame(f, fg_color="#431407", corner_radius=6)
        warn_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            warn_card,
            text="⚠  This will permanently ERASE the selected drive. "
                 "Back up any important data first.",
            text_color=C_WARN, font=ctk.CTkFont(size=12),
            wraplength=680, anchor="w",
        ).pack(padx=14, pady=8, fill="x")

        # Flash button
        self._flash_btn = ctk.CTkButton(
            f, text="▶  Flash USB", height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#b91c1c", hover_color="#991b1b",
            state="disabled", command=self._confirm_flash,
        )
        self._flash_btn.pack(fill="x", pady=(0, 10))

        # Progress
        self._usb_bar = ctk.CTkProgressBar(f, height=8)
        self._usb_bar.pack(fill="x")
        self._usb_bar.set(0)

        self._usb_prog_lbl = ctk.CTkLabel(
            f, text="", font=ctk.CTkFont(size=12),
            text_color=C_MUTED, anchor="w",
        )
        self._usb_prog_lbl.pack(fill="x")

        log = self._log_box(f, height=80)
        self._poll_log(log)

        self._refresh_drives()

    def _refresh_drives(self):
        import usb as _usb
        drives = _usb.list_drives()
        safe   = [d for d in drives if 4 <= d["size_gb"] <= 512]
        self._safe_drives = safe

        if not safe:
            self._drive_menu.configure(values=["No USB drives found"])
            self._drive_var.set("No USB drives found")
            self._flash_btn.configure(state="disabled")
            self._set_status("No USB drives found — plug one in and refresh", C_WARN)
            return

        labels = [
            f"{d['device']}  ·  {d['name']}  ·  {d['size_gb']:.1f} GB"
            for d in safe
        ]
        self._drive_menu.configure(values=labels)
        self._drive_var.set(labels[0])
        self._on_drive_pick(labels[0])

    def _on_drive_pick(self, label: str):
        for d in self._safe_drives:
            if d["device"] in label:
                self._usb_drive = d
                self._flash_btn.configure(state="normal")
                if d["size_gb"] < 16:
                    self._set_status(
                        f"⚠  {d['size_gb']:.1f} GB — 16 GB recommended", C_WARN
                    )
                else:
                    self._set_status(
                        f"Ready to flash {d['device']}  ({d['name']})"
                    )
                return

    def _confirm_flash(self):
        if not self._usb_drive:
            return
        d = self._usb_drive

        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm erase")
        dialog.geometry("440x210")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()

        ctk.CTkLabel(
            dialog,
            text=(
                f"⚠  This will PERMANENTLY ERASE:\n\n"
                f"     {d['device']}  —  {d['name']}  ({d['size_gb']:.1f} GB)\n\n"
                "Continue?"
            ),
            font=ctk.CTkFont(size=13), wraplength=400,
        ).pack(pady=20, padx=20)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=4)

        def _cancel():
            dialog.destroy()

        def _go():
            dialog.destroy()
            self._flash_btn.configure(state="disabled")
            self._set_nav(back=False, next_on=False)
            self._do_flash()

        ctk.CTkButton(
            btn_row, text="Cancel", width=120,
            fg_color="transparent", border_width=1, border_color=C_MUTED,
            command=_cancel,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Yes — Erase & Flash", width=180,
            fg_color="#b91c1c", hover_color="#991b1b",
            command=_go,
        ).pack(side="left", padx=8)

    def _do_flash(self):
        drive   = self._usb_drive
        os_name = platform.system()
        out_dir = self._output_dir
        hw      = self._hw

        import usb as _usb

        def _flash():
            device = drive["device"]

            # 1. Format
            print(f"  → Formatting {device}…", end=" ", flush=True)
            if os_name == "Darwin":
                ok, err = _usb._format_macos(device)
            elif os_name == "Windows":
                ok, err = _usb._format_windows(device)
            else:
                ok, err = _usb._format_linux(device)
            if not ok:
                raise RuntimeError(f"Format failed: {err}")
            print("✓")

            # 2. Mount
            if os_name == "Darwin":
                mount = _usb._mount_macos(device)
            elif os_name == "Windows":
                mount = _usb._mount_windows(device)
            else:
                mount = _usb._mount_linux(device)
            if not mount or not os.path.exists(mount):
                raise RuntimeError("Could not mount drive after formatting")

            # 3. Copy EFI
            efi_src = os.path.join(out_dir, "EFI")
            if os.path.exists(efi_src):
                _usb._copy_with_progress(
                    efi_src, os.path.join(mount, "EFI"), "EFI"
                )

            # 4. Copy recovery
            rec_src = os.path.join(out_dir, "com.apple.recovery.boot")
            if os.path.exists(rec_src):
                _usb._copy_with_progress(
                    rec_src,
                    os.path.join(mount, "com.apple.recovery.boot"),
                    "macOS recovery",
                )

            # 5. Write NEXT_STEPS.md
            _usb._write_next_steps(mount, hardware=hw)

            # 6. Eject
            print("  → Ejecting…", end=" ", flush=True)
            if os_name == "Darwin":
                _usb._eject_macos(device)
            elif os_name == "Windows":
                _usb._eject_windows(device)
            else:
                _usb._eject_linux(device, mount)
            print("✓")
            return True

        def _done(result, err):
            self._usb_bar.set(1.0)
            if err:
                self._usb_prog_lbl.configure(
                    text=f"Failed: {err}", text_color=C_ERROR,
                )
                self._set_status(f"Flash failed: {err}", C_ERROR)
                self._flash_btn.configure(state="normal")
                self._set_nav(back=True, next_on=False)
                return
            self._usb_prog_lbl.configure(
                text="✓  USB is ready — safely remove and boot from it!",
                text_color=C_SUCCESS,
            )
            self._set_status("Done! USB ready.", C_SUCCESS)
            self._set_nav(back=False, next_text="✓  Done", next_on=True,
                          next_color=C_SUCCESS)

        def _animate():
            if self._step == 5:
                cur = self._usb_bar.get()
                if cur < 0.90:
                    self._usb_bar.set(cur + 0.018)
                    self._usb_prog_lbl.configure(
                        text=f"Flashing…  {int((cur + 0.018) * 100)}%",
                        text_color=C_MUTED,
                    )
                self.after(300, _animate)

        _animate()
        self._run_thread(_flash, _done)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = AutoCoreApp()
    app.mainloop()


if __name__ == "__main__":
    main()
