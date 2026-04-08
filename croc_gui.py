#!/usr/bin/env python3
"""
CrocDrop — A beautiful GUI for croc file transfers.
Sender uses this GUI. Receiver just does: croc <secret-key>
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import sys
import platform
import re
import shutil
import urllib.request
import tempfile
import json

# ── Theme ──────────────────────────────────────────────────────────────────────
BG        = "#0d0f14"
SURFACE   = "#161b25"
SURFACE2  = "#1e2636"
ACCENT    = "#00e5ff"
ACCENT2   = "#7b5cff"
TEXT      = "#e8edf5"
MUTED     = "#5a6a85"
SUCCESS   = "#00e676"
ERROR     = "#ff5252"
WARNING   = "#ffab40"

FONT_MONO = ("JetBrains Mono", 10) if shutil.which("fc-list") else ("Courier", 10)
FONT_HEAD = ("Helvetica Neue", 22, "bold")
FONT_SUB  = ("Helvetica Neue", 11)
FONT_BODY = ("Helvetica Neue", 10)
FONT_CODE = ("Courier New", 11, "bold")

# ── Croc installer ─────────────────────────────────────────────────────────────
def is_croc_installed():
    return shutil.which("croc") is not None

def install_croc_linux():
    """Install croc on Linux/macOS using the official install script."""
    try:
        script_url = "https://getcroc.schollz.com"
        result = subprocess.run(
            ["curl", "-sL", script_url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False, "Failed to download install script"
        # Write and execute
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(result.stdout)
            fname = f.name
        os.chmod(fname, 0o755)
        res = subprocess.run(["bash", fname], capture_output=True, text=True, timeout=120)
        os.unlink(fname)
        return res.returncode == 0, res.stderr or res.stdout
    except Exception as e:
        return False, str(e)

def install_croc_windows():
    """Install croc on Windows using scoop or direct download."""
    # Try scoop first
    if shutil.which("scoop"):
        res = subprocess.run(["scoop", "install", "croc"], capture_output=True, text=True, timeout=120)
        return res.returncode == 0, res.stderr or res.stdout
    # Try winget
    if shutil.which("winget"):
        res = subprocess.run(["winget", "install", "schollz.croc"], capture_output=True, text=True, timeout=120)
        return res.returncode == 0, res.stderr or res.stdout
    return False, "Please install croc manually: https://github.com/schollz/croc/releases"

# ── Main App ───────────────────────────────────────────────────────────────────
class CrocDropApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CrocDrop")
        self.geometry("720x600")
        self.minsize(640, 520)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._send_process = None
        self._selected_file = tk.StringVar()
        self._secret_key    = tk.StringVar()
        self._status_text   = tk.StringVar(value="Ready to send a file.")
        self._progress_val  = tk.DoubleVar(value=0)

        self._build_ui()
        self._check_croc()

    # ── UI ──────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ─ Header bar ─
        header = tk.Frame(self, bg=SURFACE, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        logo_frame = tk.Frame(header, bg=SURFACE)
        logo_frame.pack(side="left", padx=24, fill="y")

        tk.Label(logo_frame, text="🐊", font=("Helvetica", 22),
                 bg=SURFACE, fg=ACCENT).pack(side="left", padx=(0,8), pady=16)
        tk.Label(logo_frame, text="CrocDrop", font=("Helvetica Neue", 18, "bold"),
                 bg=SURFACE, fg=TEXT).pack(side="left", pady=16)

        tk.Label(header, text="peer-to-peer · encrypted · instant",
                 font=FONT_BODY, bg=SURFACE, fg=MUTED).pack(side="right", padx=24)

        # ─ Croc status banner ─
        self._croc_banner = tk.Frame(self, bg=WARNING, height=30)
        self._croc_banner.pack(fill="x")
        self._croc_banner.pack_propagate(False)
        self._croc_banner_lbl = tk.Label(
            self._croc_banner,
            text="⏳  Checking for croc...",
            font=FONT_BODY, bg=WARNING, fg="#1a1a1a"
        )
        self._croc_banner_lbl.pack(pady=5)

        # ─ Main content ─
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=32, pady=20)

        # ─ File picker section ─
        self._section_label(body, "01  SELECT FILE TO SEND")

        pick_row = tk.Frame(body, bg=BG)
        pick_row.pack(fill="x", pady=(6,0))

        self._file_entry = tk.Entry(
            pick_row,
            textvariable=self._selected_file,
            font=FONT_CODE,
            bg=SURFACE2, fg=ACCENT, insertbackground=ACCENT,
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground=MUTED,
            highlightcolor=ACCENT
        )
        self._file_entry.pack(side="left", fill="x", expand=True, ipady=10, ipadx=12)

        self._browse_btn = self._make_btn(
            pick_row, "  Browse…", self._browse_file,
            bg=SURFACE2, fg=TEXT, hover_bg=SURFACE
        )
        self._browse_btn.pack(side="left", padx=(8,0), ipady=10, ipadx=16)

        # Drop hint
        tk.Label(body, text="or drag & drop a file into the field above",
                 font=("Helvetica", 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(4,16))

        # ─ Secret key section ─
        self._section_label(body, "02  SET A SECRET KEY  (share this with receiver)")

        key_row = tk.Frame(body, bg=BG)
        key_row.pack(fill="x", pady=(6,0))

        self._key_entry = tk.Entry(
            key_row,
            textvariable=self._secret_key,
            font=FONT_CODE,
            bg=SURFACE2, fg=ACCENT2, insertbackground=ACCENT2,
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground=MUTED,
            highlightcolor=ACCENT2,
            width=24
        )
        self._key_entry.pack(side="left", ipady=10, ipadx=12)

        self._gen_btn = self._make_btn(
            key_row, "⚡ Generate", self._gen_key,
            bg=SURFACE2, fg=TEXT, hover_bg=SURFACE
        )
        self._gen_btn.pack(side="left", padx=(8,0), ipady=10, ipadx=14)

        tk.Label(body, text='leave blank to let croc auto-generate a key',
                 font=("Helvetica", 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(4,20))

        # ─ Receiver command ─
        rcv_frame = tk.Frame(body, bg=SURFACE, bd=0)
        rcv_frame.pack(fill="x", pady=(0,20))
        rcv_inner = tk.Frame(rcv_frame, bg=SURFACE)
        rcv_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(rcv_inner, text="RECEIVER RUNS:",
                 font=("Helvetica", 8, "bold"), bg=SURFACE, fg=MUTED).pack(anchor="w")
        self._rcv_cmd_lbl = tk.Label(
            rcv_inner,
            text="croc <your-secret-key>",
            font=FONT_CODE, bg=SURFACE, fg=SUCCESS
        )
        self._rcv_cmd_lbl.pack(anchor="w", pady=(4,0))

        self._secret_key.trace_add("write", self._update_rcv_cmd)

        # ─ Send button ─
        self._send_btn = self._make_btn(
            body, "  SEND FILE  🚀", self._send_file,
            bg=ACCENT, fg="#000000", hover_bg="#00b8d4",
            font=("Helvetica Neue", 13, "bold")
        )
        self._send_btn.pack(fill="x", ipady=14)

        # ─ Progress ─
        self._progress = ttk.Progressbar(
            body, variable=self._progress_val, maximum=100,
            mode="indeterminate"
        )
        self._progress.pack(fill="x", pady=(12,0))

        # ─ Log / status ─
        log_frame = tk.Frame(body, bg=SURFACE, bd=0)
        log_frame.pack(fill="both", expand=True, pady=(14,0))

        tk.Label(log_frame, text="LOG", font=("Helvetica", 8, "bold"),
                 bg=SURFACE, fg=MUTED).pack(anchor="w", padx=12, pady=(8,0))

        self._log = tk.Text(
            log_frame,
            bg=SURFACE, fg=TEXT,
            font=("Courier New", 9),
            relief="flat", bd=0,
            wrap="word",
            height=5,
            state="disabled",
            highlightthickness=0
        )
        self._log.pack(fill="both", expand=True, padx=12, pady=(4,12))

        sb = tk.Scrollbar(log_frame, command=self._log.yview, bg=SURFACE,
                          troughcolor=SURFACE, relief="flat")
        self._log.config(yscrollcommand=sb.set)

    def _section_label(self, parent, text):
        tk.Label(parent, text=text,
                 font=("Helvetica Neue", 9, "bold"),
                 bg=BG, fg=MUTED, anchor="w").pack(fill="x")

    def _make_btn(self, parent, text, cmd, bg=SURFACE2, fg=TEXT,
                  hover_bg=None, font=None):
        if font is None:
            font = FONT_SUB
        btn = tk.Label(parent, text=text, font=font,
                       bg=bg, fg=fg, cursor="hand2",
                       relief="flat", bd=0)
        btn.bind("<Button-1>", lambda e: cmd())
        if hover_bg:
            btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
            btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    # ── Logic ───────────────────────────────────────────────────────────────────
    def _check_croc(self):
        def task():
            if is_croc_installed():
                self.after(0, self._croc_ok)
            else:
                self.after(0, lambda: self._log_line("croc not found — installing…", WARNING))
                ok, msg = (install_croc_windows() if platform.system() == "Windows"
                           else install_croc_linux())
                if ok or is_croc_installed():
                    self.after(0, self._croc_ok)
                else:
                    self.after(0, lambda: self._croc_fail(msg))
        threading.Thread(target=task, daemon=True).start()

    def _croc_ok(self):
        self._croc_banner.config(bg=SUCCESS)
        self._croc_banner_lbl.config(bg=SUCCESS,
            text="✓  croc is installed and ready", fg="#001a00")
        self._log_line("croc ready.", SUCCESS)

    def _croc_fail(self, msg):
        self._croc_banner.config(bg=ERROR)
        self._croc_banner_lbl.config(bg=ERROR,
            text=f"✗  croc not found — {msg[:80]}", fg="white")
        self._log_line(f"croc install failed: {msg}", ERROR)

    def _browse_file(self):
        path = filedialog.askopenfilename(title="Select file to send")
        if path:
            self._selected_file.set(path)
            self._log_line(f"Selected: {os.path.basename(path)}", ACCENT)

    def _gen_key(self):
        import random, string
        words = ["swift", "amber", "delta", "neon", "croc", "nova",
                 "blaze", "lunar", "cyber", "drop", "pixel", "echo"]
        key = "-".join(random.choices(words, k=3)) + "-" + \
              "".join(random.choices(string.digits, k=4))
        self._secret_key.set(key)

    def _update_rcv_cmd(self, *_):
        k = self._secret_key.get().strip()
        cmd = f"croc {k}" if k else "croc <your-secret-key>"
        self._rcv_cmd_lbl.config(text=cmd)

    def _log_line(self, msg, color=TEXT):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _send_file(self):
        path = self._selected_file.get().strip()
        key  = self._secret_key.get().strip()

        if not path:
            messagebox.showwarning("No file", "Please select a file to send first.")
            return
        if not os.path.exists(path):
            messagebox.showerror("Not found", f"File not found:\n{path}")
            return
        if not is_croc_installed():
            messagebox.showerror("croc missing", "croc is not installed yet. Please wait.")
            return

        cmd = ["croc", "send"]
        if key:
            cmd += ["--code", key]
        cmd.append(path)

        self._log_line(f"$ {' '.join(cmd)}", MUTED)
        self._send_btn.config(bg=MUTED, text="  Sending…")
        self._progress.config(mode="indeterminate")
        self._progress.start(12)

        def run():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                self._send_process = proc
                for line in proc.stdout:
                    line = line.rstrip()
                    # Detect the code line
                    m = re.search(r'Code is: (.+)', line)
                    if m:
                        code = m.group(1).strip()
                        self.after(0, lambda c=code: self._on_code_known(c))
                    self.after(0, lambda l=line: self._log_line(l))
                proc.wait()
                ok = proc.returncode == 0
                self.after(0, lambda: self._on_send_done(ok))
            except Exception as ex:
                self.after(0, lambda: self._log_line(str(ex), ERROR))
                self.after(0, lambda: self._on_send_done(False))

        threading.Thread(target=run, daemon=True).start()

    def _on_code_known(self, code):
        self._secret_key.set(code)
        self._rcv_cmd_lbl.config(text=f"croc {code}")
        self._log_line(f"✓ Code: {code}", SUCCESS)

    def _on_send_done(self, ok):
        self._progress.stop()
        self._progress_val.set(100 if ok else 0)
        if ok:
            self._send_btn.config(bg=SUCCESS, fg="#000", text="  ✓ File Sent!")
            self._log_line("Transfer complete.", SUCCESS)
        else:
            self._send_btn.config(bg=ERROR, fg="white", text="  ✗ Failed — retry?")
            self._log_line("Transfer failed or cancelled.", ERROR)
        # Reset button after 4s
        self.after(4000, lambda: self._send_btn.config(
            bg=ACCENT, fg="#000", text="  SEND FILE  🚀"))


# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Style ttk progressbar
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Horizontal.TProgressbar",
                    background=ACCENT, troughcolor=SURFACE2,
                    bordercolor=SURFACE2, lightcolor=ACCENT, darkcolor=ACCENT)

    app = CrocDropApp()
    app.mainloop()
