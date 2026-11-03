#!/usr/bin/env python3
"""STEPfwd TypePaste — local clipboard-to-keystrokes sidecar (Linux X11 backend).

This v0.2 UI lets you select Windows 11, macOS, Manjaro Linux, or Ubuntu
as a future backend target. Only Linux X11/XWayland is implemented today;
other platforms are shown as unavailable, rather than pretending to work.
No clipboard contents are saved to disk or transmitted over the network.
"""

from __future__ import annotations

import json
import os
import platform
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

APP_TITLE = "STEPfwd TypePaste"
APP_CLASS = "STEPfwdTypePaste"
PREF_FILE = Path.home() / ".config" / "stepfwd-typepaste" / "preferences.json"
BACKGROUND = "#f5f7fb"
TEXT_COLOR = "#17243a"
MUTED = "#596779"
BLUE = "#1265a8"
GREEN = "#187c50"
RED = "#b33333"
AMBER = "#986000"

HOST_OS_OPTIONS = (
    "Auto (recommended)",
    "Windows 11",
    "macOS",
    "Manjaro Linux",
    "Ubuntu",
)


def identify_host_os(system_name: str, distro_id: str = "", distro_like: str = "") -> str:
    """Classify the *host*, not the operating system inside STEPfwd."""
    if system_name == "Windows":
        return "Windows 11"  # Windows-family profile; exact Windows version not inferred.
    if system_name == "Darwin":
        return "macOS"
    if system_name == "Linux":
        distros = {distro_id.lower(), *distro_like.lower().split()}
        if "manjaro" in distros:
            return "Manjaro Linux"
        if "ubuntu" in distros:
            return "Ubuntu"
        return "Linux (other)"
    return f"Other ({system_name})"


def detect_host_os() -> str:
    system_name = platform.system()
    distro_id = ""
    distro_like = ""
    if system_name == "Linux":
        try:
            contents = Path("/etc/os-release").read_text(encoding="utf-8")
            for line in contents.splitlines():
                if line.startswith("ID="):
                    distro_id = line[3:].strip().strip('"')
                if line.startswith("ID_LIKE="):
                    distro_like = line[8:].strip().strip('"')
        except OSError:
            pass
    return identify_host_os(system_name, distro_id, distro_like)


def linux_backend_status(selected: str, detected: str, has_xdotool: bool,
                         display: str | None, session: str) -> tuple[bool, str]:
    """Return an explicit support verdict before enabling input injection."""
    resolved = detected if selected == HOST_OS_OPTIONS[0] else selected
    if selected != HOST_OS_OPTIONS[0] and resolved != detected:
        return False, f"{resolved} selected; this host is {detected}. Choose Auto."
    if resolved in ("Windows 11", "macOS"):
        return False, f"{resolved} backend is planned, not implemented in this version."
    if not resolved.startswith(("Manjaro", "Ubuntu", "Linux")):
        return False, f"Unsupported host: {resolved}."
    if not has_xdotool:
        return False, "Install xdotool to enable Linux keyboard injection."
    if not display:
        return False, "No X11 DISPLAY found; native Wayland support is planned."
    if session == "wayland":
        return True, "Experimental: XWayland only. Native Wayland Firefox may not link."
    return True, "Ready: Linux X11 + xdotool keyboard backend."


def xdotool(*arguments: str, timeout: float = 1.2) -> str | None:
    """Run read-only xdotool subcommands; return None on failure."""
    try:
        completed = subprocess.run(
            ["xdotool", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode:
        return None
    return completed.stdout.strip()


def active_window() -> tuple[str, str] | None:
    """Return active X11 window ID and WM_CLASS, or None."""
    window_id = xdotool("getactivewindow")
    if not window_id:
        return None
    window_class = xdotool("getwindowclass", window_id)
    if window_class is None:
        return None
    return window_id, window_class.lower()


def load_prefs() -> dict:
    try:
        data = json.loads(PREF_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def normalize_text(text: str, allow_multiline: bool) -> tuple[str | None, str | None]:
    """Remove trailing line endings, reject dangerous keyboard control keys by default."""
    text = text.replace("\r\n", "\n").rstrip("\r\n")
    if not text:
        return None, "Paste some text first."
    if "\x00" in text:
        return None, "NUL characters cannot be typed."
    if not allow_multiline and ("\n" in text or "\r" in text or "\t" in text):
        return None, "Multiple lines/tabs blocked. Enable 'Multiline' only in an editor."
    # CR is unambiguously an Enter in terminal input, including in multiline mode.
    if "\r" in text:
        return None, "Carriage returns are blocked; use normal line feeds."
    return text, None


class TypePaste(tk.Tk):
    TICK_MS = 100
    ARM_TIMEOUT = 35.0
    FOCUS_SETTLE = 0.22

    def __init__(self) -> None:
        super().__init__(className=APP_CLASS)
        self.title(APP_TITLE)
        self.configure(background=BACKGROUND)
        self.minsize(214, 375)
        self.resizable(True, True)

        prefs = load_prefs()
        saved_geometry = prefs.get("geometry", "230x465+12+155")
        if not isinstance(saved_geometry, str) or len(saved_geometry) > 70:
            saved_geometry = "230x465+12+155"
        try:
            self.geometry(saved_geometry)
        except tk.TclError:
            self.geometry("230x465+12+155")

        saved_host = prefs.get("host_os", HOST_OS_OPTIONS[0])
        if saved_host not in HOST_OS_OPTIONS:
            saved_host = HOST_OS_OPTIONS[0]
        self.host_os_var = tk.StringVar(value=saved_host)
        self.detected_host = detect_host_os()
        self.settings_window: tk.Toplevel | None = None
        self.pin_var = tk.BooleanVar(value=True)
        self.multiline_var = tk.BooleanVar(value=False)
        initial_delay = prefs.get("delay_ms", 40)
        if not isinstance(initial_delay, int) or initial_delay not in (20, 40, 70, 120):
            initial_delay = 40
        self.delay_var = tk.StringVar(value=str(initial_delay))
        self.status_var = tk.StringVar(value="Link to your STEPfwd Firefox first.")
        self.target_var = tk.StringVar(value="Not linked")
        self.mode = "idle"  # idle | binding | armed | settling | typing
        self.target_window_id: str | None = None
        self.current_target_id: str | None = None
        self.deadline = 0.0
        self.settle_until = 0.0
        self.pending_text = ""
        self.proc: subprocess.Popen | None = None
        self.completed: queue.Queue = queue.Queue()

        self._build_ui()
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Escape>", lambda _event: self.cancel())
        self.editor.bind("<Control-Return>", self._arm_key)
        self.after(self.TICK_MS, self.tick)
        ready, info = self.backend_ready()
        if not ready:
            self.set_status(info, AMBER)
        self.after(150, lambda: self.editor.focus_set())

    def _build_ui(self) -> None:
        p = tk.Frame(self, bg=BACKGROUND, padx=9, pady=8)
        p.pack(fill="both", expand=True)

        heading = tk.Frame(p, bg=BACKGROUND)
        heading.pack(fill="x")
        tk.Label(heading, text="TYPEPASTE", fg=BLUE, bg=BACKGROUND,
                 font=("DejaVu Sans", 13, "bold"), anchor="w").pack(side="left")
        self.settings_button = tk.Button(
            heading, text="⚙", command=self.open_settings,
            font=("DejaVu Sans", 15), bg=BACKGROUND, fg=MUTED,
            activebackground="#e2ebf5", borderwidth=0, relief="flat",
            padx=4, pady=0, cursor="hand2",
        )
        self.settings_button.pack(side="right")
        tk.Label(p, text="STEPfwd • local keyboard bridge", fg=MUTED,
                 bg=BACKGROUND, font=("DejaVu Sans", 8), anchor="w").pack(fill="x", pady=(0, 8))

        target_row = tk.Frame(p, bg=BACKGROUND)
        target_row.pack(fill="x")
        tk.Label(target_row, text="Target", bg=BACKGROUND, fg=MUTED,
                 font=("DejaVu Sans", 8, "bold")).pack(side="left")
        self.target_label = tk.Label(target_row, textvariable=self.target_var,
                                     bg=BACKGROUND, fg=TEXT_COLOR,
                                     font=("DejaVu Sans", 8), anchor="e")
        self.target_label.pack(side="right", fill="x")

        self.link_button = tk.Button(p, text="1  Link STEPfwd Firefox", command=self.link,
                                     bg="#e2ebf5", fg=TEXT_COLOR, relief="flat",
                                     activebackground="#d3e3f4", padx=6, pady=5,
                                     font=("DejaVu Sans", 9, "bold"), cursor="hand2")
        self.link_button.pack(fill="x", pady=(3, 8))

        tk.Label(p, text="Text to type into the VM", bg=BACKGROUND, fg=MUTED,
                 font=("DejaVu Sans", 8, "bold"), anchor="w").pack(fill="x")
        editor_frame = tk.Frame(p, bg="#a9bacd", padx=1, pady=1)
        editor_frame.pack(fill="both", expand=True, pady=(3, 6))
        scrollbar = tk.Scrollbar(editor_frame, width=10)
        scrollbar.pack(side="right", fill="y")
        self.editor = tk.Text(editor_frame, wrap="word", undo=True, height=6,
                              yscrollcommand=scrollbar.set, relief="flat", borderwidth=0,
                              highlightthickness=0, background="#ffffff",
                              foreground=TEXT_COLOR, insertbackground=TEXT_COLOR,
                              font=("DejaVu Sans Mono", 9), padx=6, pady=6)
        self.editor.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.editor.yview)

        row = tk.Frame(p, bg=BACKGROUND)
        row.pack(fill="x", pady=(0, 6))
        self.clip_button = tk.Button(row, text="↓ Clipboard", command=self.grab_clipboard,
                                     bg="#e2ebf5", fg=TEXT_COLOR, relief="flat",
                                     activebackground="#d3e3f4", padx=5, pady=4,
                                     cursor="hand2", font=("DejaVu Sans", 8))
        self.clip_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(row, text="Clear", command=self.clear_text,
                  bg="#e2ebf5", fg=TEXT_COLOR, relief="flat", padx=6, pady=4,
                  cursor="hand2", font=("DejaVu Sans", 8)).pack(side="right")

        options = tk.Frame(p, bg=BACKGROUND)
        options.pack(fill="x", pady=(0, 8))
        ttk.Style(self).configure("Sidecar.TCheckbutton", background=BACKGROUND,
                                  foreground=TEXT_COLOR, font=("DejaVu Sans", 8))
        ttk.Checkbutton(options, text="Pin", style="Sidecar.TCheckbutton",
                        variable=self.pin_var, command=self.set_pin).pack(side="left")
        ttk.Checkbutton(options, text="Multiline", style="Sidecar.TCheckbutton",
                        variable=self.multiline_var).pack(side="left", padx=(5, 0))
        tk.Label(options, text="ms", bg=BACKGROUND, fg=MUTED,
                 font=("DejaVu Sans", 8)).pack(side="right")
        self.delay_menu = ttk.Combobox(options, textvariable=self.delay_var,
                                       values=("20", "40", "70", "120"),
                                       width=3, state="readonly")
        self.delay_menu.pack(side="right", padx=(0, 2))

        self.arm_button = tk.Button(p, text="2  ARM PASTE → click VM", command=self.arm,
                                    bg=BLUE, fg="white", relief="flat", padx=5, pady=8,
                                    activebackground="#075286", activeforeground="white",
                                    cursor="hand2", font=("DejaVu Sans", 9, "bold"))
        self.arm_button.pack(fill="x")
        self.stop_button = tk.Button(p, text="Cancel / Stop  (Esc)", command=self.cancel,
                                     bg=BACKGROUND, fg=MUTED, relief="flat", padx=5, pady=4,
                                     activebackground="#e7edf4", cursor="hand2",
                                     font=("DejaVu Sans", 8))
        self.stop_button.pack(fill="x", pady=(2, 5))

        self.status_label = tk.Label(p, textvariable=self.status_var,
                                     fg=MUTED, bg=BACKGROUND, anchor="w",
                                     justify="left", wraplength=207,
                                     font=("DejaVu Sans", 8))
        self.status_label.pack(fill="x")

    def backend_ready(self) -> tuple[bool, str]:
        return linux_backend_status(
            self.host_os_var.get(), self.detected_host,
            bool(shutil.which("xdotool")), os.environ.get("DISPLAY"),
            os.environ.get("XDG_SESSION_TYPE", "").lower(),
        )

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return
        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("TypePaste settings")
        window.geometry("340x253")
        window.minsize(310, 230)
        window.resizable(True, True)
        window.configure(background=BACKGROUND)
        window.transient(self)
        window.attributes("-topmost", True)
        frame = tk.Frame(window, bg=BACKGROUND, padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="⚙  Settings", bg=BACKGROUND, fg=BLUE,
                 font=("DejaVu Sans", 13, "bold"), anchor="w").pack(fill="x", pady=(0, 9))
        tk.Label(frame, text="Host operating system", bg=BACKGROUND, fg=TEXT_COLOR,
                 font=("DejaVu Sans", 9, "bold"), anchor="w").pack(fill="x")
        os_box = ttk.Combobox(frame, textvariable=self.host_os_var,
                              values=HOST_OS_OPTIONS, state="readonly", width=26)
        os_box.pack(fill="x", pady=(5, 5))
        tk.Label(frame, text=f"Detected host: {self.detected_host}", bg=BACKGROUND,
                 fg=MUTED, font=("DejaVu Sans", 8), anchor="w").pack(fill="x")
        backend_var = tk.StringVar()
        backend_label = tk.Label(frame, textvariable=backend_var, bg=BACKGROUND,
                                  fg=MUTED, wraplength=290, justify="left",
                                  font=("DejaVu Sans", 9), anchor="w")
        backend_label.pack(fill="x", pady=(13, 8))

        def refresh_backend(_event: tk.Event | None = None) -> None:
            if _event is not None and self.mode in ("binding", "armed", "settling"):
                self.cancel()  # Never keep a paste armed while switching host profiles.
            ok, info = self.backend_ready()
            backend_var.set(info)
            backend_label.configure(fg=GREEN if ok else AMBER)
            if self.mode not in ("typing", "settling"):
                self.set_status(info, GREEN if ok else AMBER)

        os_box.bind("<<ComboboxSelected>>", refresh_backend)
        refresh_backend()
        tk.Button(frame, text="Done", command=window.destroy, bg=BLUE,
                  fg="white", activebackground="#075286", relief="flat",
                  padx=12, pady=5, cursor="hand2").pack(side="bottom", anchor="e")

    def set_status(self, message: str, color: str = MUTED) -> None:
        self.status_var.set(message)
        self.status_label.configure(fg=color)

    def set_pin(self) -> None:
        self.attributes("-topmost", self.pin_var.get())

    def clear_text(self) -> None:
        if self.mode in ("armed", "settling", "typing"):
            self.set_status("Cancel the transfer before clearing text.", AMBER)
            return
        self.editor.delete("1.0", "end")
        self.set_status("Text cleared.")

    def grab_clipboard(self) -> None:
        if self.mode in ("armed", "settling", "typing"):
            self.set_status("Cancel the transfer before replacing text.", AMBER)
            return
        try:
            value = self.clipboard_get()
        except tk.TclError:
            self.set_status("No text available in clipboard.", RED)
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", value)
        self.set_status(f"Loaded {len(value)} characters from clipboard.", GREEN)

    def link(self) -> None:
        ready, reason = self.backend_ready()
        if not ready:
            self.set_status(reason, RED)
            return
        if self.mode == "typing" or (self.proc is not None and self.proc.poll() is None):
            self.set_status("Stop the current typing operation first.", AMBER)
            return
        self.mode = "binding"
        self.target_window_id = None
        self.target_var.set("Click Firefox…")
        self.deadline = time.monotonic() + 45.0
        self.set_status("Now click inside the STEPfwd Firefox window.", BLUE)

    def arm(self) -> None:
        ready, reason = self.backend_ready()
        if not ready:
            self.set_status(reason, RED)
            return
        if self.mode == "typing" or (self.proc is not None and self.proc.poll() is None):
            self.set_status("Previous typing operation is still finishing.", AMBER)
            return
        if self.target_window_id is None:
            self.set_status("Link STEPfwd's Firefox window first.", RED)
            return
        content = self.editor.get("1.0", "end-1c")
        content, error = normalize_text(content, self.multiline_var.get())
        if error:
            self.set_status(error, RED)
            return
        assert content is not None
        if len(content) > 20000:
            self.set_status("Limit: 20,000 characters per transfer.", RED)
            return
        if "\n" in content:
            yes = messagebox.askyesno(
                "Multiline typing can execute commands",
                "Embedded Enter keys may execute commands in a shell.\n\n"
                "Only continue if the guest has a suitable editor open. Send multiline text?",
                parent=self,
            )
            if not yes:
                self.set_status("Multiline transfer cancelled.")
                return
        self.pending_text = content
        self.mode = "armed"
        self.deadline = time.monotonic() + self.ARM_TIMEOUT
        self.arm_button.configure(text="ARMED — click Kali terminal", bg="#cc8322")
        self.set_status("Click inside the linked Firefox VM (35s timeout).", AMBER)

    def _arm_key(self, _event: tk.Event) -> str:
        self.arm()
        return "break"

    def cancel(self) -> None:
        if self.mode == "typing" and self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
            self.set_status("Typing interrupted. Check the VM for partial input.", AMBER)
        elif self.mode in ("armed", "binding", "settling"):
            self.set_status("Transfer cancelled.")
        self.pending_text = ""
        self.mode = "idle"
        self._reset_arm_button()
        self.target_var.set("Firefox linked" if self.target_window_id else "Not linked")

    def _reset_arm_button(self) -> None:
        self.arm_button.configure(text="2  ARM PASTE → click VM", bg=BLUE)

    def _start_typing(self) -> None:
        ready, reason = self.backend_ready()
        if not ready:
            self.cancel()
            self.set_status(reason, RED)
            return
        self.mode = "typing"
        self.current_target_id = self.target_window_id
        self.arm_button.configure(text="Typing into STEPfwd…", bg=GREEN)
        delay = int(self.delay_var.get())
        payload = self.pending_text.encode("utf-8")
        try:
            self.proc = subprocess.Popen(
                ["xdotool", "type", "--clearmodifiers", "--delay", str(delay), "--file", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            self.mode = "idle"
            self._reset_arm_button()
            self.set_status(f"Couldn't start xdotool: {exc}", RED)
            return
        self.set_status(f"Typing {len(self.pending_text)} chars at {delay}ms/key…", GREEN)
        process = self.proc
        thread = threading.Thread(target=self._feed_process, args=(process, payload), daemon=True)
        thread.start()

    def _feed_process(self, process: subprocess.Popen, payload: bytes) -> None:
        try:
            _stdout, stderr = process.communicate(input=payload)
            result = (process, process.returncode, stderr.decode("utf-8", errors="replace"))
        except (OSError, ValueError) as exc:
            result = (process, -1, str(exc))
        self.completed.put(result)

    def _drain_results(self) -> None:
        while True:
            try:
                proc, code, error = self.completed.get_nowait()
            except queue.Empty:
                break
            if proc is not self.proc:
                continue
            if self.mode == "typing":
                if code == 0:
                    self.set_status(f"Sent {len(self.pending_text)} characters. Ready again.", GREEN)
                else:
                    self.set_status(f"Typing stopped (exit {code}): {error[:100]}", RED)
                self.mode = "idle"
                self.pending_text = ""
                self._reset_arm_button()
            self.proc = None

    def tick(self) -> None:
        self._drain_results()
        now = time.monotonic()
        if self.mode in ("binding", "armed", "settling", "typing"):
            current = active_window()
            if self.mode == "binding":
                if current and "firefox" in current[1]:
                    self.target_window_id = current[0]
                    self.target_var.set("Firefox linked")
                    self.mode = "idle"
                    self.set_status("Linked! Paste text, arm, then click Kali.", GREEN)
                elif now > self.deadline:
                    self.mode = "idle"
                    self.target_var.set("Not linked")
                    self.set_status("Link timed out. Try again.", RED)
            elif self.mode in ("armed", "settling"):
                if now > self.deadline:
                    self.cancel()
                    self.set_status("Arming timed out. Nothing was typed.", AMBER)
                elif current and current[0] == self.target_window_id:
                    if self.mode == "armed":
                        self.mode = "settling"
                        self.settle_until = now + self.FOCUS_SETTLE
                    elif now >= self.settle_until:
                        self._start_typing()
                else:
                    self.mode = "armed"  # Restart settling if focus moves elsewhere.
            elif self.mode == "typing" and self.proc and self.proc.poll() is None:
                if not current or current[0] != self.current_target_id:
                    # Best-effort emergency stop. Some characters may already have been typed.
                    self.cancel()
        self.after(self.TICK_MS, self.tick)

    def on_close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        try:
            PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
            PREF_FILE.write_text(json.dumps({
                "geometry": self.geometry(), "delay_ms": int(self.delay_var.get()),
                "host_os": self.host_os_var.get(),
            }, indent=2), encoding="utf-8")
            os.chmod(PREF_FILE, 0o600)
        except (OSError, ValueError):
            pass
        self.destroy()


def main() -> None:
    app = TypePaste()
    app.mainloop()


if __name__ == "__main__":
    main()
