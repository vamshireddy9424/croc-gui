#!/usr/bin/env python3
"""
CrocDrop — GUI for croc file transfers.
Fixes: file path display, transfer complete timing, secret key copy button.
New:   WhatsApp/Telegram share, tar bundling for large files (cross-platform).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import platform
import re
import shutil
import tempfile
import tarfile
import urllib.parse
import webbrowser
import random
import string

# ── Theme ──────────────────────────────────────────────────────────────────────
BG       = "#0d0f14"
SURFACE  = "#161b25"
SURF2    = "#1e2636"
SURF3    = "#252d3d"
ACCENT   = "#00e5ff"
ACCENT2  = "#7b5cff"
TEXT     = "#e8edf5"
MUTED    = "#5a6a85"
SUCCESS  = "#00e676"
ERROR    = "#ff5252"
WARN     = "#ffab40"
WA_GREEN = "#25D366"
TG_BLUE  = "#229ED9"

F_CODE  = ("Courier New", 11, "bold")
F_BODY  = ("Helvetica", 10)
F_SMALL = ("Helvetica", 8)
F_BIG   = ("Helvetica", 13, "bold")

# ── croc helpers ──────────────────────────────────────────────────────────────
def is_croc_installed():
    return shutil.which("croc") is not None

def install_croc():
    sys_ = platform.system()
    try:
        if sys_ == "Windows":
            for mgr, cmd in [
                ("winget", ["winget","install","schollz.croc","-e","--silent"]),
                ("scoop",  ["scoop","install","croc"])
            ]:
                if shutil.which(mgr):
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                    if r.returncode == 0:
                        return True, ""
            return False, "Install croc from https://github.com/schollz/croc/releases"
        else:
            if sys_ == "Darwin" and shutil.which("brew"):
                r = subprocess.run(["brew","install","croc"],
                                   capture_output=True, text=True, timeout=180)
                if r.returncode == 0:
                    return True, ""
            r = subprocess.run(["curl","-sL","https://getcroc.schollz.com"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return False, "Could not reach getcroc.schollz.com"
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
                f.write(r.stdout)
                fname = f.name
            os.chmod(fname, 0o755)
            r2 = subprocess.run(["bash", fname], capture_output=True, text=True, timeout=180)
            os.unlink(fname)
            return r2.returncode == 0 or is_croc_installed(), r2.stderr
    except Exception as e:
        return False, str(e)

# ── File size helpers ──────────────────────────────────────────────────────────
def get_file_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for dirpath, _, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except Exception:
                pass
    return total

def format_size(b):
    for unit in ["B","KB","MB","GB","TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"

# ── Tar bundler (no compression = no data loss, just packaging) ───────────────
def bundle_to_tar(src_path, progress_cb=None):
    """
    Pack src_path into a .tar archive using Python's built-in tarfile module.
    Works on Windows, macOS, Linux. No compression (tarfile.open mode='w')
    so there is zero data or quality loss.
    Returns (tar_path, tmp_dir_to_cleanup).
    """
    base    = os.path.basename(src_path.rstrip("/\\"))
    tmp_dir = tempfile.mkdtemp(prefix="crocdrop_")
    out     = os.path.join(tmp_dir, base + ".tar")

    with tarfile.open(out, "w") as tar:
        tar.add(src_path, arcname=base)
        if progress_cb:
            progress_cb(1, 1)

    return out, tmp_dir


# ── Main App ───────────────────────────────────────────────────────────────────
class CrocDropApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CrocDrop")
        self.geometry("760x700")
        self.minsize(680, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._send_proc          = None
        self._tmp_dir            = None
        self._receiver_connected = False
        self._room_ready = False

        self._sel_file    = tk.StringVar()
        self._secret      = tk.StringVar()
        self._do_compress = tk.BooleanVar(value=False)
        self._socks5      = tk.StringVar()
        self._http_proxy  = tk.StringVar()

        self._sel_file.trace_add("write", self._on_file_changed)
        self._secret.trace_add("write",   self._update_rcv_cmd)

        self._build_ui()
        self._check_croc()

    # ──────────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ──────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._style_ttk()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=SURFACE, height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🐊", font=("Helvetica",20),
                 bg=SURFACE, fg=ACCENT).pack(side="left", padx=(20,6))
        tk.Label(hdr, text="CrocDrop", font=("Helvetica",17,"bold"),
                 bg=SURFACE, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="peer-to-peer · end-to-end encrypted",
                 font=F_SMALL, bg=SURFACE, fg=MUTED).pack(side="right", padx=20)

        # ── Status banner ─────────────────────────────────────────────────────
        self._banner_frm = tk.Frame(self, bg=WARN, height=26)
        self._banner_frm.pack(fill="x")
        self._banner_frm.pack_propagate(False)
        self._banner_lbl = tk.Label(self._banner_frm,
                                    text="⏳  Checking for croc…",
                                    font=F_SMALL, bg=WARN, fg="#1a1a1a")
        self._banner_lbl.pack(pady=4)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=14)

        # ══════════════════════════════════════════════════════════════
        # 01  FILE PICKER
        # ══════════════════════════════════════════════════════════════
        self._sec(body, "01  SELECT FILE OR FOLDER TO SEND")

        pick_row = tk.Frame(body, bg=BG)
        pick_row.pack(fill="x", pady=(4,0))

        # READ-ONLY entry — updated via StringVar
        self._file_entry = tk.Entry(
            pick_row, textvariable=self._sel_file,
            font=F_CODE, bg=SURF2, fg=ACCENT,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=MUTED,
            highlightcolor=ACCENT,
            state="readonly"
        )
        self._file_entry.pack(side="left", fill="x", expand=True, ipady=9, ipadx=10)

        self._btn(pick_row, "📂  Browse", self._browse,
                  bg=SURF2, fg=TEXT, hbg=SURF3
                  ).pack(side="left", padx=(6,0), ipady=9, ipadx=14)

        self._file_info = tk.Label(body, text="", font=F_SMALL, bg=BG, fg=MUTED, anchor="w")
        self._file_info.pack(fill="x", pady=(3,0))

        # ── Compression toggle ────────────────────────────────────────────────
        comp_row = tk.Frame(body, bg=BG)
        comp_row.pack(fill="x", pady=(8,10))

        self._comp_cb = tk.Checkbutton(
            comp_row,
            text="📦  Bundle into .tar before sending  (no data loss — recommended for files ≥ 1 GB)",
            variable=self._do_compress,
            font=F_BODY, bg=BG, fg=TEXT,
            activebackground=BG, activeforeground=TEXT,
            selectcolor=SURF2,
            command=self._on_compress_toggle
        )
        self._comp_cb.pack(side="left")

        self._comp_note = tk.Label(comp_row, text="", font=F_SMALL, bg=BG, fg=MUTED)
        self._comp_note.pack(side="left", padx=(8,0))

        # ══════════════════════════════════════════════════════════════
        # 02  SECRET KEY
        # ══════════════════════════════════════════════════════════════
        self._sec(body, "02  SET A SECRET KEY")

        key_row = tk.Frame(body, bg=BG)
        key_row.pack(fill="x", pady=(4,0))

        self._key_entry = tk.Entry(
            key_row, textvariable=self._secret,
            font=F_CODE, bg=SURF2, fg=ACCENT2,
            insertbackground=ACCENT2, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=MUTED,
            highlightcolor=ACCENT2, width=28
        )
        self._key_entry.pack(side="left", ipady=9, ipadx=10)

        self._btn(key_row, "⚡ Generate", self._gen_key,
                  bg=SURF2, fg=TEXT, hbg=SURF3
                  ).pack(side="left", padx=(6,0), ipady=9, ipadx=12)

        self._copy_key_btn = self._btn(key_row, "📋 Copy Key", self._copy_key,
                                       bg=SURF2, fg=TEXT, hbg=SURF3)
        self._copy_key_btn.pack(side="left", padx=(6,0), ipady=9, ipadx=12)

        tk.Label(body,
                 text="Leave blank — croc will auto-generate a key and show it after you press Send",
                 font=F_SMALL, bg=BG, fg=MUTED).pack(anchor="w", pady=(3,0))

        # ══════════════════════════════════════════════════════════════
        # 03  SHARE
        # ══════════════════════════════════════════════════════════════
        self._sec(body, "03  SHARE WITH RECEIVER", top=12)

        rcv_outer = tk.Frame(body, bg=SURF2)
        rcv_outer.pack(fill="x", pady=(4,0))

        rcv_inner = tk.Frame(rcv_outer, bg=SURF2)
        rcv_inner.pack(fill="x", padx=14, pady=10)

        tk.Label(rcv_inner, text="RECEIVER RUNS THIS COMMAND:",
                 font=("Helvetica",8,"bold"), bg=SURF2, fg=MUTED).pack(anchor="w")

        self._rcv_cmd_lbl = tk.Label(rcv_inner, text="croc <your-secret-key>",
                                     font=F_CODE, bg=SURF2, fg=SUCCESS)
        self._rcv_cmd_lbl.pack(anchor="w", pady=(4,2))

        # Status: tells user when it's safe to share
        self._share_status = tk.Label(rcv_inner,
            text="⚠  Press SEND first — share the code only after status shows READY",
            font=("Helvetica",8,"bold"), bg=SURF2, fg=WARN)
        self._share_status.pack(anchor="w", pady=(0,6))

        share_row = tk.Frame(rcv_inner, bg=SURF2)
        share_row.pack(fill="x")

        self._copy_cmd_btn = self._btn(share_row, "📋 Copy Command", self._copy_cmd,
                                       bg=SURF3, fg=MUTED, hbg=SURFACE)
        self._copy_cmd_btn.pack(side="left", ipady=7, ipadx=12)

        self._wa_btn = self._btn(share_row, "  WhatsApp", self._share_whatsapp,
                                 bg="#1a4a2e", fg="#5a8a6a", hbg="#1a4a2e",
                                 font=("Helvetica",10,"bold"))
        self._wa_btn.pack(side="left", padx=(8,0), ipady=7, ipadx=14)

        self._tg_btn = self._btn(share_row, "  Telegram", self._share_telegram,
                                 bg="#0d2a3d", fg="#3a6a8a", hbg="#0d2a3d",
                                 font=("Helvetica",10,"bold"))
        self._tg_btn.pack(side="left", padx=(8,0), ipady=7, ipadx=14)

        # ══════════════════════════════════════════════════════════════
        # 04  PROXY (optional, collapsible)
        # ══════════════════════════════════════════════════════════════
        self._proxy_visible = tk.BooleanVar(value=False)
        proxy_toggle = self._btn(body, "⚙  Proxy settings  ▸", self._toggle_proxy,
                                 bg=BG, fg=MUTED, hbg=BG,
                                 font=("Helvetica", 8, "bold"))
        proxy_toggle.pack(anchor="w", pady=(10, 0))
        self._proxy_toggle_btn = proxy_toggle

        self._proxy_frame = tk.Frame(body, bg=SURF2)
        # Not packed yet — shown on toggle

        proxy_inner = tk.Frame(self._proxy_frame, bg=SURF2)
        proxy_inner.pack(fill="x", padx=14, pady=10)

        # SOCKS5
        row_s = tk.Frame(proxy_inner, bg=SURF2)
        row_s.pack(fill="x", pady=(0, 6))
        tk.Label(row_s, text="SOCKS5 proxy:", font=F_SMALL,
                 bg=SURF2, fg=MUTED, width=14, anchor="w").pack(side="left")
        tk.Entry(row_s, textvariable=self._socks5,
                 font=F_CODE, bg=SURF3, fg=ACCENT,
                 insertbackground=ACCENT, relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=MUTED,
                 highlightcolor=ACCENT, width=32
                 ).pack(side="left", ipady=6, ipadx=8)
        tk.Label(row_s, text="  e.g. socks5://127.0.0.1:1080",
                 font=F_SMALL, bg=SURF2, fg=MUTED).pack(side="left")

        # HTTP proxy
        row_h = tk.Frame(proxy_inner, bg=SURF2)
        row_h.pack(fill="x")
        tk.Label(row_h, text="HTTP proxy:", font=F_SMALL,
                 bg=SURF2, fg=MUTED, width=14, anchor="w").pack(side="left")
        tk.Entry(row_h, textvariable=self._http_proxy,
                 font=F_CODE, bg=SURF3, fg=ACCENT,
                 insertbackground=ACCENT, relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=MUTED,
                 highlightcolor=ACCENT, width=32
                 ).pack(side="left", ipady=6, ipadx=8)
        tk.Label(row_h, text="  e.g. http://127.0.0.1:8080",
                 font=F_SMALL, bg=SURF2, fg=MUTED).pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # SEND BUTTON + PROGRESS
        # ══════════════════════════════════════════════════════════════
        self._send_btn = self._btn(body, "  SEND FILE  🚀", self._send,
                                   bg=ACCENT, fg="#000", hbg="#00b8d4",
                                   font=("Helvetica",13,"bold"))
        self._send_btn.pack(fill="x", ipady=13, pady=(14,0))

        self._prog = ttk.Progressbar(body, maximum=100, mode="indeterminate")
        self._prog.pack(fill="x", pady=(6,0))

        self._prog_lbl = tk.Label(body, text="", font=F_SMALL, bg=BG, fg=MUTED, anchor="w")
        self._prog_lbl.pack(fill="x")

        # ══════════════════════════════════════════════════════════════
        # LOG
        # ══════════════════════════════════════════════════════════════
        log_frm = tk.Frame(body, bg=SURFACE)
        log_frm.pack(fill="both", expand=True, pady=(10,0))

        log_hdr = tk.Frame(log_frm, bg=SURFACE)
        log_hdr.pack(fill="x", padx=12, pady=(6,0))
        tk.Label(log_hdr, text="LOG", font=("Helvetica",8,"bold"),
                 bg=SURFACE, fg=MUTED).pack(side="left")
        self._btn(log_hdr, "clear", self._clear_log,
                  bg=SURFACE, fg=MUTED, hbg=SURF2,
                  font=("Helvetica",8)).pack(side="right")

        self._log_txt = tk.Text(
            log_frm, bg=SURFACE, fg=TEXT,
            font=("Courier New", 9), relief="flat", bd=0,
            wrap="word", height=6, state="disabled",
            highlightthickness=0
        )
        self._log_txt.tag_config("ok",   foreground=SUCCESS)
        self._log_txt.tag_config("err",  foreground=ERROR)
        self._log_txt.tag_config("warn", foreground=WARN)
        self._log_txt.tag_config("dim",  foreground=MUTED)
        self._log_txt.tag_config("info", foreground=ACCENT)

        sb = tk.Scrollbar(log_frm, command=self._log_txt.yview,
                          bg=SURFACE, troughcolor=SURFACE, relief="flat", width=8)
        sb.pack(side="right", fill="y", padx=(0,4), pady=4)
        self._log_txt.config(yscrollcommand=sb.set)
        self._log_txt.pack(fill="both", expand=True, padx=12, pady=(4,8))

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style()
        try: s.theme_use("clam")
        except Exception: pass
        s.configure("Horizontal.TProgressbar",
                    background=ACCENT, troughcolor=SURF2,
                    bordercolor=SURF2, lightcolor=ACCENT, darkcolor=ACCENT)

    def _sec(self, parent, text, top=0):
        tk.Label(parent, text=text, font=("Helvetica",8,"bold"),
                 bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(top, 0))

    def _btn(self, parent, text, cmd, bg=SURF2, fg=TEXT, hbg=None, font=None):
        if font is None:
            font = F_BODY
        w = tk.Label(parent, text=text, font=font,
                     bg=bg, fg=fg, cursor="hand2", relief="flat", bd=0)
        w.bind("<Button-1>", lambda e: cmd())
        if hbg:
            w.bind("<Enter>", lambda e: w.config(bg=hbg))
            w.bind("<Leave>", lambda e: w.config(bg=bg))
        return w

    def _log(self, msg, tag=""):
        def _do():
            self._log_txt.config(state="normal")
            self._log_txt.insert("end", msg + "\n", tag)
            self._log_txt.see("end")
            self._log_txt.config(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log_txt.config(state="normal")
        self._log_txt.delete("1.0", "end")
        self._log_txt.config(state="disabled")

    def _flash(self, widget, temp_text, duration=1400):
        orig = widget.cget("text")
        widget.config(text=temp_text, fg=SUCCESS)
        self.after(duration, lambda: widget.config(text=orig, fg=TEXT))

    def _clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    # ── croc install ──────────────────────────────────────────────────────────
    def _check_croc(self):
        def task():
            if is_croc_installed():
                self.after(0, self._croc_ok)
            else:
                self._log("croc not found — installing…", "warn")
                ok, msg = install_croc()
                if ok or is_croc_installed():
                    self.after(0, self._croc_ok)
                else:
                    self.after(0, lambda: self._croc_fail(msg))
        threading.Thread(target=task, daemon=True).start()

    def _croc_ok(self):
        self._banner_frm.config(bg=SUCCESS)
        self._banner_lbl.config(bg=SUCCESS,
                                text="✓  croc is installed and ready", fg="#001a00")
        self._log("croc ready ✓", "ok")

    def _croc_fail(self, msg):
        self._banner_frm.config(bg=ERROR)
        self._banner_lbl.config(bg=ERROR,
                                text=f"✗  croc not found — {msg[:80]}", fg="white")
        self._log(f"croc install failed: {msg}", "err")

    # ── File browse ───────────────────────────────────────────────────────────
    def _browse(self):
        choice = messagebox.askquestion(
            "What to send?",
            "Click YES to pick a File\nClick NO to pick a Folder",
            icon="question"
        )
        path = (filedialog.askopenfilename(title="Select file to send")
                if choice == "yes"
                else filedialog.askdirectory(title="Select folder to send"))
        if path:
            # Must temporarily enable readonly entry to update it
            self._file_entry.config(state="normal")
            self._sel_file.set(path)
            self._file_entry.config(state="readonly")

    def _on_file_changed(self, *_):
        path = self._sel_file.get().strip()
        if not path or not os.path.exists(path):
            self._file_info.config(text="")
            return
        size  = get_file_size(path)
        kind  = "folder" if os.path.isdir(path) else "file"
        name  = os.path.basename(path)
        info  = f"{name}  ·  {kind}  ·  {format_size(size)}"
        self._file_info.config(text=info, fg=ACCENT)
        self._log(f"Selected: {info}", "info")

        # Auto-suggest bundling for large files
        if size >= 1 * 1024**3:
            self._do_compress.set(True)
            self._comp_note.config(
                text=f"⚠ Large file ({format_size(size)}) — .tar bundling auto-enabled",
                fg=WARN
            )
        else:
            self._comp_note.config(text="")

    def _toggle_proxy(self):
        if self._proxy_visible.get():
            self._proxy_frame.pack_forget()
            self._proxy_visible.set(False)
            self._proxy_toggle_btn.config(text="⚙  Proxy settings  ▸")
        else:
            self._proxy_frame.pack(fill="x", before=self._send_btn)
            self._proxy_visible.set(True)
            self._proxy_toggle_btn.config(text="⚙  Proxy settings  ▾")

    def _on_compress_toggle(self):
        if self._do_compress.get():
            self._comp_note.config(
                text="Files will be packaged into a .tar archive (no data loss)", fg=MUTED)
        else:
            self._comp_note.config(text="")

    # ── Key helpers ───────────────────────────────────────────────────────────
    def _gen_key(self):
        words = ["swift","amber","delta","neon","nova",
                 "blaze","lunar","cyber","pixel","echo",
                 "storm","flash","solar","spike","frost",
                 "tiger","river","stone","cloud","flame"]
        # croc expects: number-word-word-word  (e.g. 3-correct-horse-battery)
        num = random.randint(1, 9)
        key = f"{num}-" + "-".join(random.choices(words, k=3))
        self._secret.set(key)
        self._log(f"Key set: {key}  — press Send, then share once status shows READY", "info")

    def _copy_key(self):
        key = self._secret.get().strip()
        if not key:
            messagebox.showwarning("No key", "Generate or enter a secret key first.")
            return
        self._clipboard(key)
        self._flash(self._copy_key_btn, "✅ Key Copied!")
        self._log(f"Copied key: {key}", "ok")

    def _update_rcv_cmd(self, *_):
        k = self._secret.get().strip()
        if k:
            # On Linux/macOS croc expects the secret as env var to avoid
            # leaking it in process list. This is the correct receive command.
            cmd = f'CROC_SECRET="{k}" croc'
        else:
            cmd = 'CROC_SECRET="<your-secret-key>" croc'
        self._rcv_cmd_lbl.config(text=cmd)

    # ── Share helpers ─────────────────────────────────────────────────────────
    def _build_share_msg(self):
        key = self._secret.get().strip()
        if not key:
            return None
        fname = (os.path.basename(self._sel_file.get().strip())
                 if self._sel_file.get().strip() else "a file")
        return (f"📦 CrocDrop File Transfer\n\n"
                f"Someone is sending you: {fname}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Step 1 — Install croc (one-time):\n"
                f"  Linux/Mac:  curl https://getcroc.schollz.com | bash\n"
                f"  Windows:    winget install schollz.croc\n\n"
                f"Step 2 — In your terminal, run:\n\n"
                f'  CROC_SECRET="{key}" croc\n\n'
                f"⚠ Only run this AFTER the sender says they are ready!\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 End-to-end encrypted transfer via croc.")

    def _share_whatsapp(self):
        msg = self._build_share_msg()
        if not msg:
            messagebox.showwarning("No key", "Generate a secret key first.")
            return
        webbrowser.open("https://wa.me/?text=" + urllib.parse.quote(msg))
        self._log("WhatsApp share opened in browser", "ok")

    def _share_telegram(self):
        msg = self._build_share_msg()
        if not msg:
            messagebox.showwarning("No key", "Generate a secret key first.")
            return
        webbrowser.open("https://t.me/share/url?url=&text=" + urllib.parse.quote(msg))
        self._log("Telegram share opened in browser", "ok")

    def _copy_cmd(self):
        k = self._secret.get().strip()
        if not k:
            messagebox.showwarning("No key", "Generate a key first.")
            return
        cmd = f'CROC_SECRET="{k}" croc'
        self._clipboard(cmd)
        self._flash(self._copy_cmd_btn, "✅ Copied!")
        self._log(f"Copied receiver command: {cmd}", "ok")

    # ── SEND ──────────────────────────────────────────────────────────────────
    def _send(self):
        path = self._sel_file.get().strip()
        key  = self._secret.get().strip()

        if not path:
            messagebox.showwarning("No file", "Please select a file or folder first.")
            return
        if not os.path.exists(path):
            messagebox.showerror("Not found", f"Path not found:\n{path}")
            return
        if not is_croc_installed():
            messagebox.showerror("croc missing",
                                 "croc is not installed yet.\nWait for the green banner.")
            return

        # Lock the send button and share buttons until room is ready
        self._send_btn.config(bg=MUTED, text="  Preparing…", cursor="watch")
        self._send_btn.unbind("<Button-1>")
        self._receiver_connected = False
        self._room_ready = False
        self._lock_share()

        if self._do_compress.get():
            self._prog.config(mode="indeterminate")
            self._prog.start(10)
            self._prog_lbl.config(text="Bundling into .tar (no data loss)…")
            self._log("Bundling files into .tar archive…", "warn")

            def compress_then_send():
                try:
                    tar_path, tmp_dir = bundle_to_tar(path)
                    self._tmp_dir = tmp_dir
                    sz = format_size(os.path.getsize(tar_path))
                    self.after(0, lambda: self._log(
                        f"Bundle ready: {os.path.basename(tar_path)} ({sz})", "ok"))
                    self.after(0, lambda: self._prog_lbl.config(
                        text="Bundle ready — starting transfer…"))
                    self.after(0, lambda: self._run_croc(tar_path, key))
                except Exception as e:
                    self.after(0, lambda: self._log(f"Bundle failed: {e}", "err"))
                    self.after(0, self._reset_send_btn)

            threading.Thread(target=compress_then_send, daemon=True).start()
        else:
            self._run_croc(path, key)

    def _run_croc(self, send_path, key):
        self._prog.stop()
        self._prog.config(mode="indeterminate")
        self._prog.start(10)
        self._prog_lbl.config(text="Waiting for receiver to connect…")
        self._send_btn.config(text="  Waiting for receiver… 🟡")

        # On macOS/Linux, croc v10+ requires the secret as CROC_SECRET env var.
        # Passing --code as a CLI arg causes croc to exit silently on macOS.
        IS_WIN = platform.system() == "Windows"

        cmd_args = ["croc", "send", "--no-local"]
        socks5 = self._socks5.get().strip()
        http_p = self._http_proxy.get().strip()
        if socks5:
            cmd_args += ["--socks5", socks5]
        if http_p:
            cmd_args += ["--connect", http_p]
        cmd_args.append(send_path)

        # Pass secret: env var on Unix, --code flag on Windows
        send_env = os.environ.copy()
        if key:
            if IS_WIN:
                # Windows classic mode still uses --code flag
                cmd_args.insert(2, key)
                cmd_args.insert(2, "--code")
            else:
                send_env["CROC_SECRET"] = key

        self._log(f"$ {' '.join(cmd_args)}", "dim")
        if key and not IS_WIN:
            self._log(f'  env: CROC_SECRET="{key}"', "dim")

        # Unlock share after 30s if croc doesn't echo "Code is:" (pre-set key)
        if key:
            self.after(30000, lambda: self._unlock_share(key) if not self._room_ready else None)

        import datetime
        debug_log = os.path.expanduser("~/crocdrop_debug.log")

        def run():
            try:
                with open(debug_log, "a") as dbg:
                    dbg.write(f"\n\n=== {datetime.datetime.now()} ===\n")
                    dbg.write(f"CMD: {' '.join(cmd_args)}\n")
                    if key and not IS_WIN:
                        dbg.write(f'CROC_SECRET="{key}"\n')

                proc = subprocess.Popen(
                    cmd_args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env=send_env,
                )
                self._send_proc = proc

                for raw in proc.stdout:
                    # Write raw line to debug log before any processing
                    with open(debug_log, "a") as dbg:
                        dbg.write(f"RAW: {repr(raw)}\n")

                    line = re.sub(
                        r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b.',
                        "", raw.replace("\r\n", "\n").replace("\r", "\n")
                    )
                    for part in line.split("\n"):
                        part = part.strip()
                        if part:
                            self.after(0, lambda l=part: self._handle_croc_line(l))

                proc.wait()
                with open(debug_log, "a") as dbg:
                    dbg.write(f"EXIT CODE: {proc.returncode}\n")

                self.after(0, lambda: self._on_done(proc.returncode))

            except Exception as ex:
                with open(debug_log, "a") as dbg:
                    dbg.write(f"EXCEPTION: {ex}\n")
                self.after(0, lambda: self._log(f"Launch error: {ex}", "err"))
                self.after(0, lambda: self._on_done(-99))

        threading.Thread(target=run, daemon=True).start()

    def _handle_croc_line(self, line):
        low = line.lower()

        # ── croc printed the code = relay room is NOW open, safe to share ──
        # Matches both: "Code is: X-word-word" and "On the other computer run"
        m = re.search(r'[Cc]ode is[:\s]+(\S+)', line)
        if m:
            code = m.group(1).strip()
            self._secret.set(code)
            self._room_ready = True
            self._unlock_share(code)
            return

        # Also unlock on "On the other computer" line (croc prints this right after)
        if "on the other computer" in low or "croc " in low and self._secret.get().strip():
            if not self._room_ready:
                self._room_ready = True
                self._unlock_share(self._secret.get().strip())

        # ── Receiver connected ──
        if any(x in low for x in ["connected","peer","sending","starting"]):
            if self._room_ready and not self._receiver_connected:
                self._receiver_connected = True
                self._send_btn.config(text="  Transferring… 📡")
                self._prog_lbl.config(text="Receiver connected — sending…")
                self._log("Receiver connected ✓", "ok")

        # ── Progress % ──
        pct = re.search(r'(\d{1,3}(?:\.\d+)?)\s*%', line)
        if pct:
            val = float(pct.group(1))
            if self._prog["mode"] != "determinate":
                self._prog.stop()
                self._prog.config(mode="determinate")
            self._prog["value"] = val
            self._prog_lbl.config(text=line.strip())

        # Filter noisy/sensitive lines before logging
        skip_patterns = [
            "croc_secret",          # never show secret in log
            "croc send ",           # croc echoes its own command — redundant
            "on the other computer",# shown in UI already
            "classic mode",         # implementation detail, not useful
        ]
        if not any(p in low for p in skip_patterns):
            tag = "warn" if "error" in low or "fail" in low else "dim"
            self._log(line, tag)

    def _on_done(self, returncode):
        self._prog.stop()
        self._prog.config(mode="determinate")

        if returncode == 0:
            self._prog["value"] = 100
            self._send_btn.config(bg=SUCCESS, fg="#000", text="  ✓ Transfer Complete!")
            self._prog_lbl.config(text="File delivered successfully.")
            self._log("✓ Transfer complete!", "ok")
        else:
            self._prog["value"] = 0
            if not self._receiver_connected:
                hint = "Receiver never connected — make sure they ran: croc <key>"
            else:
                hint = "Transfer interrupted or failed."
            self._send_btn.config(bg=ERROR, fg="white", text=f"  ✗ Failed")
            self._prog_lbl.config(text=hint)
            self._log(f"✗ {hint}  (exit {returncode})", "err")

        # Cleanup temp bundle
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir)
            except Exception:
                pass
            self._tmp_dir = None

        self.after(5000, self._reset_send_btn)

    def _unlock_share(self, code):
        """Called once croc has registered the room — now safe to share."""
        self._clipboard(code)
        self._share_status.config(
            text="✅  READY — receiver can now run the command below",
            fg=SUCCESS, bg="#0a2a1a"
        )
        self._share_status.master.config(bg="#0a2a1a")  # rcv_inner bg
        # Activate share buttons
        for w, bg, hbg in [
            (self._copy_cmd_btn, "#1e2636", "#252d3d"),
            (self._wa_btn,       "#25D366", "#1da851"),
            (self._tg_btn,       "#229ED9", "#1a85b8"),
        ]:
            w.config(bg=bg, fg="white", cursor="hand2")
            w.bind("<Enter>", lambda e, b=hbg, ww=w: ww.config(bg=b))
            w.bind("<Leave>", lambda e, b=bg,  ww=w: ww.config(bg=b))
        self._copy_key_btn.config(fg=TEXT)
        self._clipboard(code)
        self._flash(self._copy_key_btn, "✅ Key Copied!")
        self._log(f'✅ READY — share: CROC_SECRET="{code}" croc', "ok")
        self._prog_lbl.config(text="Relay room open — waiting for receiver…")

    def _lock_share(self):
        """Reset share buttons to locked/dim state."""
        self._room_ready = False
        self._share_status.config(
            text="⚠  Press SEND first — share the code only after status shows READY",
            fg=WARN, bg=SURF2
        )
        self._share_status.master.config(bg=SURF2)
        for w, bg, fg in [
            (self._copy_cmd_btn, "#1e2636", MUTED),
            (self._wa_btn,       "#1a4a2e", "#5a8a6a"),
            (self._tg_btn,       "#0d2a3d", "#3a6a8a"),
        ]:
            w.config(bg=bg, fg=fg, cursor="arrow")
            w.unbind("<Enter>")
            w.unbind("<Leave>")

    def _reset_send_btn(self):
        self._send_btn.config(bg=ACCENT, fg="#000",
                              text="  SEND FILE  🚀", cursor="hand2")
        self._send_btn.bind("<Button-1>", lambda e: self._send())
        self._prog_lbl.config(text="")
        self._lock_share()


# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = CrocDropApp()
    app.mainloop()
