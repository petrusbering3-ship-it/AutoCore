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

from utils import force_utf8_output  # noqa: E402

force_utf8_output()   # UTF-8 stdout/stderr so glyphs never crash a print


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
        try:
            _sp.run(
                [sys.executable, "-m", "pip", "install"] + missing + ["--quiet"],
                check=True,
            )
            print("✓")
        except Exception:
            print("FAILED")
            print("  Please run:  pip install " + " ".join(missing))
            sys.exit(1)


_bootstrap()

import customtkinter as ctk  # noqa: E402

from lang import set_lang  # noqa: E402
from constants import MACOS_VERSIONS, MACOS_INFO  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Palette ───────────────────────────────────────────────────────────────────
# Ported from the AutoCore "Liquid Glass" design system (tokens/colors.css).
# customtkinter can't do real backdrop-blur, so we approximate the glass look
# with the design's cool-graphite ink scale + the single system-blue accent
# ramp + Apple-vibrant semantic colors, generous radii and badge dots.

C_BG       = "#0b0d13"   # canvas-base — window background (the "aurora" base)
C_HEADER   = "#0e1016"   # ink-900     — title / footer bars
C_CARD     = "#171a24"   # ink-800     — raised glass surfaces
C_CARD_HI  = "#1f2330"   # ink-700     — hover / selected fill
C_WELL     = "#0e1016"   # ink-900     — inset log "wells"
C_BORDER   = "#2b303f"   # ink-600     — hairline strokes
C_STROKE   = "#3c4254"   # ink-500     — brighter rim

C_ACCENT   = "#0a84ff"   # accent-500  — primary system blue
C_ACCENT_2 = "#0071e3"   # accent-600  — pressed / hover
C_ACCENT_3 = "#3ea0ff"   # accent-400  — highlight text

C_SUCCESS  = "#30d158"   # vibrant green
C_WARN     = "#ff9f0a"   # vibrant orange
C_ERROR    = "#ff453b"   # vibrant red

C_TEXT     = "#d8dce5"   # ink-100     — primary text
C_MUTED    = "#828b9e"   # ink-300     — secondary text
C_FAINT    = "#5b6376"   # ink-400     — tertiary / placeholder

# Status-tag colors for the macOS picker
_TAG_COLOR = {
    "latest":      C_ACCENT,
    "recommended": C_SUCCESS,
    "stable":      C_MUTED,
    "legacy":      C_WARN,
}
_TAG_LABEL = {
    "latest":      "Latest",
    "recommended": "Recommended",
    "stable":      "Stable",
    "legacy":      "Legacy",
}


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
        self.geometry("820x620")
        self.minsize(820, 620)
        self.resizable(False, False)
        self.configure(fg_color=C_BG)

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
        self._content.pack(fill="both", expand=True, padx=28, pady=(14, 0))

        self._build_footer()
        self._show_step(0)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=C_HEADER)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Hairline under the header for a bit of depth
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=C_BORDER).pack(fill="x")

        brand = ctk.CTkFrame(hdr, fg_color="transparent")
        brand.pack(side="left", padx=20)
        ctk.CTkLabel(
            brand, text="◆", font=ctk.CTkFont(size=22, weight="bold"),
            text_color=C_ACCENT,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            brand, text="AutoCore",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        self._dots_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        self._dots_frame.pack(side="right", padx=18)

        self._dot_labels = []
        step_names = ["Welcome", "Hardware", "macOS", "Kexts", "Build", "Flash"]
        for i in range(self.N_STEPS):
            col = ctk.CTkFrame(self._dots_frame, fg_color="transparent")
            col.pack(side="left", padx=6)
            dot = ctk.CTkLabel(col, text="●", font=ctk.CTkFont(size=13),
                               text_color=C_BORDER, width=14)
            dot.pack()
            ctk.CTkLabel(col, text=step_names[i], font=ctk.CTkFont(size=9),
                         text_color=C_FAINT).pack(pady=(1, 0))
            self._dot_labels.append(dot)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=C_BORDER).pack(
            fill="x", side="bottom")
        ftr = ctk.CTkFrame(self, height=68, corner_radius=0, fg_color=C_HEADER)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)

        self._back_btn = ctk.CTkButton(
            ftr, text="← Back", width=104, height=38, corner_radius=10,
            fg_color="transparent", border_width=1, border_color=C_BORDER,
            text_color=C_MUTED, hover_color=C_CARD,
            command=self._go_back, state="disabled",
        )
        self._back_btn.pack(side="left", padx=20, pady=14)

        self._status_lbl = ctk.CTkLabel(
            ftr, text="", font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        )
        self._status_lbl.pack(side="left", padx=8)

        self._next_btn = ctk.CTkButton(
            ftr, text="Next →", width=140, height=38, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C_CARD, hover_color=C_ACCENT_2, text_color=C_FAINT,
            command=self._go_next, state="disabled",
        )
        self._next_btn.pack(side="right", padx=20, pady=14)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _update_dots(self, step: int):
        for i, lbl in enumerate(self._dot_labels):
            if i < step:
                lbl.configure(text="●", text_color=C_SUCCESS)
            elif i == step:
                lbl.configure(text="●", text_color=C_ACCENT)
            else:
                lbl.configure(text="●", text_color=C_BORDER)

    def _set_nav(self, *, back=False, next_text="Next →",
                 next_on=False, next_color=None):
        self._back_btn.configure(
            state="normal" if back else "disabled",
            text_color=C_TEXT if back else C_FAINT,
        )
        self._next_btn.configure(
            text=next_text,
            state="normal" if next_on else "disabled",
            fg_color=(next_color or C_ACCENT) if next_on else C_CARD,
            text_color="#ffffff" if next_on else C_FAINT,
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

    def _title(self, parent, text: str, sub: str = None, eyebrow: str = None):
        if eyebrow:
            ctk.CTkLabel(
                parent, text=eyebrow.upper(),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=C_ACCENT_3, anchor="w",
            ).pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).pack(fill="x", pady=(0, 2))
        if sub:
            ctk.CTkLabel(
                parent, text=sub,
                font=ctk.CTkFont(size=12), text_color=C_MUTED, anchor="w",
            ).pack(fill="x", pady=(0, 14))
        else:
            ctk.CTkFrame(parent, height=1, fg_color=C_BORDER).pack(fill="x", pady=(0, 14))

    def _badge(self, parent, text: str, tone: str = "neutral"):
        """A small pill with a colored leading dot, like the design's Badge."""
        color = {
            "accent":  C_ACCENT, "success": C_SUCCESS,
            "warning": C_WARN,   "danger":  C_ERROR, "neutral": C_MUTED,
        }.get(tone, C_MUTED)
        pill = ctk.CTkFrame(parent, fg_color=C_CARD_HI, corner_radius=999)
        ctk.CTkLabel(pill, text="●", text_color=color,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(10, 4), pady=3)
        ctk.CTkLabel(pill, text=text, text_color=C_TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 12))
        return pill

    def _log_box(self, parent, height: int = 90) -> ctk.CTkTextbox:
        tb = ctk.CTkTextbox(
            parent, height=height,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=C_WELL, text_color=C_MUTED,
            border_width=1, border_color=C_BORDER,
            corner_radius=10, state="disabled",
        )
        tb.pack(fill="x", pady=(10, 0))
        return tb

    def _poll_log(self, textbox: ctk.CTkTextbox):
        # Stop polling once the step changes and its textbox is destroyed —
        # otherwise the dead loop raises TclError and keeps draining the
        # shared queue, stealing log output from the live textbox.
        if not textbox.winfo_exists():
            return
        try:
            while True:
                chunk = self._log_q.get_nowait()
                textbox.configure(state="normal")
                textbox.insert("end", chunk)
                textbox.see("end")
                textbox.configure(state="disabled")
        except queue.Empty:
            pass
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

        # Logo mark in a rounded "glass" tile
        tile = ctk.CTkFrame(f, width=96, height=96, corner_radius=24,
                            fg_color=C_CARD, border_width=1, border_color=C_STROKE)
        tile.pack(pady=(34, 14))
        tile.pack_propagate(False)
        ctk.CTkLabel(tile, text="◆", font=ctk.CTkFont(size=46, weight="bold"),
                     text_color=C_ACCENT).pack(expand=True)

        ctk.CTkLabel(f, text="AutoCore",
                     font=ctk.CTkFont(size=42, weight="bold"),
                     text_color=C_TEXT).pack()
        ctk.CTkLabel(f, text="Your Hackintosh, assembled in minutes.",
                     font=ctk.CTkFont(size=14), text_color=C_MUTED).pack(pady=(4, 30))

        ctk.CTkLabel(f, text="LANGUAGE",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_ACCENT_3).pack(pady=(0, 8))

        lang_row = ctk.CTkFrame(f, fg_color="transparent")
        lang_row.pack()

        self._lang_en_btn = ctk.CTkButton(
            lang_row, text="English", width=156, height=40, corner_radius=10,
            font=ctk.CTkFont(size=13),
            fg_color=C_ACCENT if self._lang == "EN" else C_CARD,
            hover_color=C_ACCENT_2,
            border_width=1, border_color=C_ACCENT if self._lang == "EN" else C_BORDER,
            command=lambda: self._pick_lang("EN"),
        )
        self._lang_en_btn.pack(side="left", padx=8)

        self._lang_da_btn = ctk.CTkButton(
            lang_row, text="Dansk", width=156, height=40, corner_radius=10,
            font=ctk.CTkFont(size=13),
            fg_color=C_ACCENT if self._lang == "DA" else C_CARD,
            hover_color=C_ACCENT_2,
            border_width=1, border_color=C_ACCENT if self._lang == "DA" else C_BORDER,
            command=lambda: self._pick_lang("DA"),
        )
        self._lang_da_btn.pack(side="left", padx=8)

        ctk.CTkLabel(
            f,
            text="Requires an internet connection to download kexts and OpenCore.",
            font=ctk.CTkFont(size=11), text_color=C_FAINT,
        ).pack(pady=(26, 0))

    def _pick_lang(self, code: str):
        self._lang = code
        set_lang(code)
        self._lang_en_btn.configure(
            fg_color=C_ACCENT if code == "EN" else C_CARD,
            border_color=C_ACCENT if code == "EN" else C_BORDER)
        self._lang_da_btn.configure(
            fg_color=C_ACCENT if code == "DA" else C_CARD,
            border_color=C_ACCENT if code == "DA" else C_BORDER)

    # ══════════════════════════════════════════════════════════════════════════
    # Step 1: Hardware scan
    # ══════════════════════════════════════════════════════════════════════════

    def _step_hardware(self):
        self._set_nav(back=True, next_on=False)
        self._set_status("Scanning hardware…")

        f = self._content
        self._title(f, "Your hardware", "AutoCore scanned this machine — review it before continuing.",
                    eyebrow="Step 1 · Detect")

        results = ctk.CTkScrollableFrame(f, height=270, fg_color=C_CARD, corner_radius=16,
                                         border_width=1, border_color=C_STROKE)
        results.pack(fill="x")
        self._hw_results = results

        self._hw_spin = ctk.CTkLabel(results, text="Scanning hardware…",
                                     text_color=C_MUTED, font=ctk.CTkFont(size=13))
        self._hw_spin.pack(pady=28)

        log = self._log_box(f, height=60)
        self._poll_log(log)

        def _scan():
            import hardware
            return hardware.scan()

        def _done(hw, err):
            if hw:
                self._hw = hw
            # User may have navigated away mid-scan — the widgets are gone.
            if not self._hw_results.winfo_exists():
                return
            if err or not hw:
                self._hw_spin.configure(text=f"✗  Scan failed: {err}", text_color=C_ERROR)
                self._set_status("Scan failed", C_ERROR)
                return
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
            row = ctk.CTkFrame(self._hw_results, fg_color=C_CARD_HI, corner_radius=10)
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=f"{label}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_MUTED, width=84, anchor="w").pack(side="left", padx=(12, 0), pady=7)
            ctk.CTkLabel(row, text=str(value)[:60], text_color=C_TEXT,
                         font=ctk.CTkFont(size=12), anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text="●", text_color=C_SUCCESS,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=14)

        compat = hw.get("compatibility", {})
        for issue in compat.get("issues", []):
            card = ctk.CTkFrame(self._hw_results, fg_color="#2a1416", corner_radius=10,
                                border_width=1, border_color="#5e2327")
            card.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(card, text=f"✕  {issue}", text_color=C_ERROR,
                         font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=620).pack(padx=12, pady=6, fill="x")
        for warn in compat.get("warnings", []):
            card = ctk.CTkFrame(self._hw_results, fg_color="#2a2110", corner_radius=10,
                                border_width=1, border_color="#5e4a1f")
            card.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(card, text=f"!  {warn}", text_color=C_WARN,
                         font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=620).pack(padx=12, pady=6, fill="x")

    # ══════════════════════════════════════════════════════════════════════════
    # Step 2: macOS version
    # ══════════════════════════════════════════════════════════════════════════

    def _step_macos(self):
        self._set_nav(back=True, next_on=bool(self._macos))
        self._set_status("Choose the release to build for")

        f = self._content
        self._title(f, "Choose macOS",
                    "Newest first. The EFI is tuned to the release you pick.",
                    eyebrow="Step 2 · Target")

        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="macos")

        # Newest → oldest so the latest/recommended releases sit at the top.
        ordered = list(reversed(MACOS_VERSIONS))
        self._macos_cards = {}
        for i, ver in enumerate(ordered):
            info = MACOS_INFO.get(ver, {})
            col, row = i % 2, i // 2
            card = self._macos_card(grid, ver, info)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            self._macos_cards[ver] = card

        # Info panel for the selected version (mirrors the design's detail card)
        self._macos_info = ctk.CTkFrame(f, fg_color=C_CARD, corner_radius=14,
                                        border_width=1, border_color=C_STROKE)
        self._macos_info.pack(fill="x", pady=(12, 0))
        self._macos_info_lbl = ctk.CTkLabel(
            self._macos_info,
            text="Select a version to see details and hardware notes.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED,
            anchor="w", justify="left", wraplength=720,
        )
        self._macos_info_lbl.pack(fill="x", padx=16, pady=12)

        if self._macos:
            self._render_macos_info(self._macos)

    def _macos_card(self, parent, ver: str, info: dict):
        sel  = self._macos == ver
        tag  = info.get("tag", "stable")
        card = ctk.CTkFrame(
            parent, corner_radius=12, height=68,
            fg_color=C_CARD_HI if sel else C_CARD,
            border_width=2, border_color=C_ACCENT if sel else C_BORDER,
        )
        card.pack_propagate(False)

        # Big version number on the left
        ctk.CTkLabel(card, text=info.get("number", "?"), width=54,
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_ACCENT_3 if sel else C_MUTED).pack(side="left", padx=(14, 6))

        mid = ctk.CTkFrame(card, fg_color="transparent")
        mid.pack(side="left", fill="both", expand=True, pady=10)
        ctk.CTkLabel(mid, text=f"macOS {ver}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(mid, text=str(info.get("year", "")),
                     font=ctk.CTkFont(size=11), text_color=C_FAINT,
                     anchor="w").pack(fill="x")

        # Tag chip on the right
        chip = ctk.CTkLabel(
            card, text=_TAG_LABEL.get(tag, tag),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=_TAG_COLOR.get(tag, C_MUTED),
            fg_color=C_WELL, corner_radius=999, width=92,
        )
        chip.pack(side="right", padx=12, pady=10)

        # Make the whole card (and children) clickable
        for w in (card, mid, chip):
            w.bind("<Button-1>", lambda _e, v=ver: self._pick_macos(v))
        for child in mid.winfo_children():
            child.bind("<Button-1>", lambda _e, v=ver: self._pick_macos(v))
        return card

    def _pick_macos(self, ver: str):
        self._macos = ver
        for v, card in self._macos_cards.items():
            sel = v == ver
            card.configure(fg_color=C_CARD_HI if sel else C_CARD,
                           border_color=C_ACCENT if sel else C_BORDER)
        self._render_macos_info(ver)
        self._set_nav(back=True, next_on=True)
        self._set_status(f"Selected macOS {ver}")

    def _render_macos_info(self, ver: str):
        info = MACOS_INFO.get(ver, {})
        lines = [f"macOS {ver}  ·  version {info.get('number', '?')}  ·  {info.get('year', '')}"]
        if info.get("note"):
            lines.append(info["note"])

        # Hardware-aware hints
        if self._hw:
            import re as _re
            m   = _re.search(r"(\d+)\. gen", self._hw.get("cpu_generation", ""))
            gen = int(m.group(1)) if m else 0
            if self._hw.get("cpu_vendor") == "AMD" and ver in ("High Sierra", "Catalina"):
                lines.append("Note: AMD Ryzen runs best on Ventura or later.")
            elif gen and gen >= 12 and ver in ("High Sierra", "Catalina", "Big Sur"):
                lines.append("Note: 12th-gen+ Intel needs Ventura or later for full support.")
        self._macos_info_lbl.configure(text="\n".join(lines), text_color=C_TEXT)

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
        self._title(f, "Kexts & drivers",
                    f"AutoCore picked {n} kexts for your hardware — downloading now.",
                    eyebrow="Step 3 · Drivers")

        # Overall progress
        self._kext_bar = ctk.CTkProgressBar(f, height=10, corner_radius=999,
                                            progress_color=C_ACCENT, fg_color=C_WELL)
        self._kext_bar.pack(fill="x", pady=(0, 4))
        self._kext_bar.set(0)

        self._kext_lbl = ctk.CTkLabel(f, text="Preparing…",
                                      font=ctk.CTkFont(size=12),
                                      text_color=C_MUTED, anchor="w")
        self._kext_lbl.pack(fill="x")

        # Kext list
        scroll = ctk.CTkScrollableFrame(f, height=200, fg_color=C_CARD, corner_radius=14,
                                        border_width=1, border_color=C_STROKE)
        scroll.pack(fill="x", pady=(6, 0))

        self._kext_row_icons = {}
        for name in self._selected:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            icon = ctk.CTkLabel(row, text="○", width=18,
                                text_color=C_FAINT, font=ctk.CTkFont(size=13))
            icon.pack(side="left")
            ctk.CTkLabel(row, text=name + ".kext", text_color=C_TEXT,
                         font=ctk.CTkFont(family="Consolas", size=12),
                         anchor="w").pack(side="left", padx=6)
            self._kext_row_icons[name] = icon

        log = self._log_box(f, height=56)
        self._poll_log(log)

        os.makedirs(self._kexts_dir, exist_ok=True)

        def _download():
            return _kexts.download_kexts(
                self._selected, self._hw, self._macos, self._kexts_dir
            )

        def _done(result, err):
            if result:
                # Record results even if the user navigated away mid-download
                self._selected, self._failed = result
            if not self._kext_bar.winfo_exists():
                return
            self._kext_bar.set(1.0)
            if err:
                self._kext_lbl.configure(text=f"Error: {err}", text_color=C_ERROR)
                self._set_status("Download failed", C_ERROR)
                return
            selected, failed = result
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
        self._title(f, "Assembling EFI",
                    "Downloading OpenCore, injecting kexts and generating config.plist.",
                    eyebrow="Step 4 · Build")

        # Step checklist
        checklist = ctk.CTkFrame(f, fg_color=C_CARD, corner_radius=14,
                                 border_width=1, border_color=C_STROKE)
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
            row.pack(fill="x", padx=16, pady=6)
            icon = ctk.CTkLabel(row, text="○", width=20,
                                text_color=C_FAINT, font=ctk.CTkFont(size=14))
            icon.pack(side="left")
            ctk.CTkLabel(row, text=s, text_color=C_TEXT,
                         font=ctk.CTkFont(size=13), anchor="w").pack(side="left", padx=10)
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
            if not self._build_icons[0].winfo_exists():
                return
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
                    "Formats the drive, then writes the EFI and macOS recovery.",
                    eyebrow="Step 5 · Install")

        # Drive selector row
        sel_row = ctk.CTkFrame(f, fg_color="transparent")
        sel_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(sel_row, text="USB drive", width=90, text_color=C_MUTED,
                     font=ctk.CTkFont(size=13), anchor="w").pack(side="left")

        self._drive_var  = ctk.StringVar(value="Scanning…")
        self._drive_menu = ctk.CTkOptionMenu(
            sel_row, variable=self._drive_var,
            values=["Scanning…"], width=360, corner_radius=10,
            fg_color=C_CARD, button_color=C_CARD_HI, button_hover_color=C_ACCENT_2,
            command=self._on_drive_pick,
        )
        self._drive_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            sel_row, text="↺", width=40, corner_radius=10,
            fg_color=C_CARD, hover_color=C_CARD_HI,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(size=16),
            command=self._refresh_drives,
        ).pack(side="left")

        # Warning banner
        warn_card = ctk.CTkFrame(f, fg_color="#2a2110", corner_radius=10,
                                 border_width=1, border_color="#5e4a1f")
        warn_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            warn_card,
            text="This permanently ERASES the selected drive. "
                 "Back up any important data first.",
            text_color=C_WARN, font=ctk.CTkFont(size=12),
            wraplength=680, anchor="w",
        ).pack(padx=14, pady=8, fill="x")

        # Flash button
        self._flash_btn = ctk.CTkButton(
            f, text="Flash USB", height=48, corner_radius=12,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#c2362f", hover_color="#a32a25",
            state="disabled", command=self._confirm_flash,
        )
        self._flash_btn.pack(fill="x", pady=(0, 10))

        # Progress
        self._usb_bar = ctk.CTkProgressBar(f, height=8, corner_radius=999,
                                           progress_color=C_ACCENT, fg_color=C_WELL)
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
        import usbflash as _usb
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
        self._drive_labels = labels
        self._drive_menu.configure(values=labels)
        self._drive_var.set(labels[0])
        self._on_drive_pick(labels[0])

    def _on_drive_pick(self, label: str):
        # Match by exact label index — substring matching on the device ID
        # ("1", "2", …on Windows) can hit digits in another drive's size/name
        # and silently select (and later ERASE) the wrong disk.
        try:
            idx = self._drive_labels.index(label)
        except (AttributeError, ValueError):
            return
        d = self._safe_drives[idx]
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

    def _confirm_flash(self):
        if not self._usb_drive:
            return
        d = self._usb_drive

        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm erase")
        dialog.geometry("460x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=C_BG)
        dialog.grab_set()
        dialog.lift()

        ctk.CTkLabel(
            dialog, text="Erase this drive?",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=C_TEXT,
        ).pack(pady=(22, 4), padx=20)
        ctk.CTkLabel(
            dialog,
            text=(
                f"This will permanently erase:\n"
                f"{d['device']}  —  {d['name']}  ({d['size_gb']:.1f} GB)"
            ),
            font=ctk.CTkFont(size=13), text_color=C_MUTED,
            wraplength=400, justify="center",
        ).pack(pady=(0, 16), padx=20)

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
            btn_row, text="Cancel", width=130, height=40, corner_radius=10,
            fg_color=C_CARD, hover_color=C_CARD_HI,
            border_width=1, border_color=C_BORDER, text_color=C_TEXT,
            command=_cancel,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Erase & flash", width=180, height=40, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#c2362f", hover_color="#a32a25",
            command=_go,
        ).pack(side="left", padx=8)

    def _do_flash(self):
        drive   = self._usb_drive
        os_name = platform.system()
        out_dir = self._output_dir
        hw      = self._hw

        import usbflash as _usb

        def _flash():
            device = drive["device"]

            # 1. Format
            print(f"  → Formatting {device}…", end=" ", flush=True)
            if os_name == "Darwin":
                ok, err = _usb._format_macos(device)
            elif os_name == "Windows":
                ok, err = _usb._format_windows(device, drive["size_gb"])
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
