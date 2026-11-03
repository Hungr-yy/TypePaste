#!/usr/bin/env python3
"""STEPfwd TypePaste: slim Tk UI over native input adapters. No text persistence."""
from __future__ import annotations

import tkinter as tk
from tkinter import font, messagebox, ttk

from typepaste.backends import HOST_OS_OPTIONS, choose_backend, detect_host, identify_host_os
from typepaste.core import Controller, normalize_text
from typepaste.preferences import load_prefs, save_prefs

APP_TITLE = "STEPfwd TypePaste"
APP_CLASS = "STEPfwdTypePaste"
BACKGROUND = "#f5f7fb"
TEXT_COLOR = "#17243a"
MUTED = "#596779"
BLUE = "#1265a8"
GREEN = "#187c50"
RED = "#b33333"
AMBER = "#986000"


class TypePaste(tk.Tk):
    TICK_MS = 100

    def __init__(self, backend=None):
        super().__init__(className=APP_CLASS)
        self.title(APP_TITLE)
        self.configure(background=BACKGROUND)
        self.minsize(230, 465)
        self.resizable(True, True)
        self.ui_font = font.nametofont("TkDefaultFont").actual("family")
        self.mono_font = font.nametofont("TkFixedFont").actual("family")
        prefs = load_prefs()
        geometry = prefs.get("geometry", "230x465+12+155")
        if not isinstance(geometry, str) or len(geometry) > 70:
            geometry = "230x465+12+155"
        try:
            self.geometry(geometry)
        except tk.TclError:
            self.geometry("230x465+12+155")
        selected = prefs.get("host_os", HOST_OS_OPTIONS[0])
        self.host_os_var = tk.StringVar(value=selected if selected in HOST_OS_OPTIONS else HOST_OS_OPTIONS[0])
        self.host = detect_host()
        self.controller = Controller(backend or choose_backend(self.host_os_var.get(), self.host))
        self.settings_window = None
        self.pin_var = tk.BooleanVar(value=True)
        self.multiline_var = tk.BooleanVar(value=False)
        delay = prefs.get("delay_ms", 40)
        self.delay_var = tk.StringVar(value=str(delay if type(delay) is int and delay in (20, 40, 70, 120) else 40))
        self.status_var = tk.StringVar()
        self.target_var = tk.StringVar(value="Not linked")
        self.closing = False
        self._build_ui()
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Escape>", lambda _event: self.cancel())
        self.editor.bind("<Control-Return>", self._arm_key)
        if self.tk.call("tk", "windowingsystem") == "aqua":
            self.editor.bind("<Command-Return>", self._arm_key)
        self.editor.bind("<<Modified>>", self._text_changed)
        self.tick_id = self.after(self.TICK_MS, self.tick)
        caps = self.controller.backend.capabilities()
        if not caps.available:
            self.controller.message(caps.reason, "warning")
        self._render()
        self.editor.focus_set()

    def _build_ui(self) -> None:
        p = tk.Frame(self, bg=BACKGROUND, padx=9, pady=8)
        p.pack(fill="both", expand=True)

        heading = tk.Frame(p, bg=BACKGROUND)
        heading.pack(fill="x")
        tk.Label(heading, text="TYPEPASTE", fg=BLUE, bg=BACKGROUND,
                 font=(self.ui_font, 13, "bold"), anchor="w").pack(side="left")
        self.settings_button = tk.Button(
            heading, text="⚙", command=self.open_settings,
            font=(self.ui_font, 15), bg=BACKGROUND, fg=MUTED,
            activebackground="#e2ebf5", borderwidth=0, relief="flat",
            padx=4, pady=0, cursor="hand2",
        )
        self.settings_button.pack(side="right")
        tk.Label(p, text="STEPfwd • local keyboard bridge", fg=MUTED,
                 bg=BACKGROUND, font=(self.ui_font, 8), anchor="w").pack(fill="x", pady=(0, 8))

        target_row = tk.Frame(p, bg=BACKGROUND)
        target_row.pack(fill="x")
        tk.Label(target_row, text="Target", bg=BACKGROUND, fg=MUTED,
                 font=(self.ui_font, 8, "bold")).pack(side="left")
        self.target_label = tk.Label(target_row, textvariable=self.target_var,
                                     bg=BACKGROUND, fg=TEXT_COLOR,
                                     font=(self.ui_font, 8), anchor="e")
        self.target_label.pack(side="right", fill="x")

        self.link_button = tk.Button(p, text="1  Link STEPfwd Firefox", command=self.link,
                                     bg="#e2ebf5", fg=TEXT_COLOR, relief="flat",
                                     activebackground="#d3e3f4", padx=6, pady=5,
                                     font=(self.ui_font, 9, "bold"), cursor="hand2")
        self.link_button.pack(fill="x", pady=(3, 8))

        tk.Label(p, text="Text to type into the VM", bg=BACKGROUND, fg=MUTED,
                 font=(self.ui_font, 8, "bold"), anchor="w").pack(fill="x")
        editor_frame = tk.Frame(p, bg="#a9bacd", padx=1, pady=1)
        editor_frame.pack(fill="both", expand=True, pady=(3, 6))
        scrollbar = tk.Scrollbar(editor_frame, width=10)
        scrollbar.pack(side="right", fill="y")
        self.editor = tk.Text(editor_frame, wrap="word", undo=False, height=6,
                              yscrollcommand=scrollbar.set, relief="flat", borderwidth=0,
                              highlightthickness=0, background="#ffffff",
                              foreground=TEXT_COLOR, insertbackground=TEXT_COLOR,
                              font=(self.mono_font, 9), padx=6, pady=6)
        self.editor.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.editor.yview)

        row = tk.Frame(p, bg=BACKGROUND)
        row.pack(fill="x", pady=(0, 6))
        self.clip_button = tk.Button(row, text="↓ Clipboard", command=self.grab_clipboard,
                                     bg="#e2ebf5", fg=TEXT_COLOR, relief="flat",
                                     activebackground="#d3e3f4", padx=5, pady=4,
                                     cursor="hand2", font=(self.ui_font, 8))
        self.clip_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(row, text="Clear", command=self.clear_text,
                  bg="#e2ebf5", fg=TEXT_COLOR, relief="flat", padx=6, pady=4,
                  cursor="hand2", font=(self.ui_font, 8)).pack(side="right")

        options = tk.Frame(p, bg=BACKGROUND)
        options.pack(fill="x", pady=(0, 8))
        ttk.Style(self).configure("Sidecar.TCheckbutton", background=BACKGROUND,
                                  foreground=TEXT_COLOR, font=(self.ui_font, 8))
        ttk.Checkbutton(options, text="Pin", style="Sidecar.TCheckbutton",
                        variable=self.pin_var, command=self.set_pin).pack(side="left")
        ttk.Checkbutton(options, text="Multiline", style="Sidecar.TCheckbutton",
                        variable=self.multiline_var).pack(side="left", padx=(5, 0))
        tk.Label(options, text="ms", bg=BACKGROUND, fg=MUTED,
                 font=(self.ui_font, 8)).pack(side="right")
        self.delay_menu = ttk.Combobox(options, textvariable=self.delay_var,
                                       values=("20", "40", "70", "120"),
                                       width=3, state="readonly")
        self.delay_menu.pack(side="right", padx=(0, 2))

        self.arm_button = tk.Button(p, text="2  ARM PASTE → click VM", command=self.arm,
                                    bg=BLUE, fg="white", relief="flat", padx=5, pady=8,
                                    activebackground="#075286", activeforeground="white",
                                    cursor="hand2", font=(self.ui_font, 9, "bold"))
        self.arm_button.pack(fill="x")
        self.stop_button = tk.Button(p, text="Cancel / Stop  (Esc)", command=self.cancel,
                                     bg=BACKGROUND, fg=MUTED, relief="flat", padx=5, pady=4,
                                     activebackground="#e7edf4", cursor="hand2",
                                     font=(self.ui_font, 8))
        self.stop_button.pack(fill="x", pady=(2, 5))

        self.status_label = tk.Label(p, textvariable=self.status_var,
                                     fg=MUTED, bg=BACKGROUND, anchor="w",
                                     justify="left", wraplength=207,
                                     font=(self.ui_font, 8))
        self.status_label.pack(fill="x")

    def _render(self):
        controller = self.controller
        self.status_var.set(controller.status)
        colors = {"info": MUTED, "active": BLUE, "success": GREEN, "warning": AMBER, "error": RED}
        self.status_label.configure(fg=colors[controller.level])
        self.target_var.set("Click Firefox…" if controller.mode == "binding" else
                            "Firefox linked" if controller.target else "Not linked")
        caps = controller.backend.capabilities()
        busy = controller._busy()
        self.link_button.configure(state="normal" if caps.available and not busy else "disabled")
        self.arm_button.configure(state="normal" if caps.available and not busy else "disabled")
        if controller.mode in ("armed", "settling"):
            self.arm_button.configure(text="ARMED — click VM terminal", bg="#cc8322")
        elif controller.mode == "typing":
            self.arm_button.configure(text="Typing into STEPfwd…", bg=GREEN)
        else:
            self.arm_button.configure(text="2  ARM PASTE → click VM", bg=BLUE)

    def refresh_backend(self, _event=None):
        self.controller.set_backend(choose_backend(self.host_os_var.get(), self.host))
        self._render()
        if self.settings_window and self.settings_window.winfo_exists():
            caps = self.controller.backend.capabilities()
            self.backend_var.set(f"{self.controller.backend.name}\n\n{caps.reason}")
            if caps.permission_request:
                self.permission_button.pack(fill="x", pady=(0, 8), before=self.settings_footer)
            else:
                self.permission_button.pack_forget()

    def open_settings(self):
        self.controller.cancel(quiet=True)
        self._render()
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("TypePaste settings")
        window.geometry("360x380")
        window.minsize(340, 380)
        window.configure(background=BACKGROUND)
        window.transient(self)
        window.attributes("-topmost", True)
        frame = tk.Frame(window, bg=BACKGROUND, padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="⚙  Settings", bg=BACKGROUND, fg=BLUE,
                 font=(self.ui_font, 13, "bold"), anchor="w").pack(fill="x", pady=(0, 9))
        tk.Label(frame, text="Host operating system", bg=BACKGROUND, fg=TEXT_COLOR,
                 font=(self.ui_font, 9, "bold"), anchor="w").pack(fill="x")
        os_box = ttk.Combobox(frame, textvariable=self.host_os_var, values=HOST_OS_OPTIONS,
                              state="readonly", width=26)
        os_box.pack(fill="x", pady=5)
        os_box.bind("<<ComboboxSelected>>", self.refresh_backend)
        tk.Label(frame, text=f"Detected host: {self.host.label}", bg=BACKGROUND, fg=MUTED,
                 font=(self.ui_font, 8), anchor="w").pack(fill="x")
        self.backend_var = tk.StringVar()
        tk.Label(frame, textvariable=self.backend_var, bg=BACKGROUND, fg=MUTED,
                 wraplength=320, justify="left", font=(self.ui_font, 9), anchor="w").pack(fill="x", pady=12)
        self.permission_button = ttk.Button(frame, text="Allow Accessibility…", command=self.request_permission)
        if self.controller.backend.capabilities().permission_request:
            self.permission_button.pack(fill="x", pady=(0, 8))
        footer = tk.Frame(frame, bg=BACKGROUND)
        self.settings_footer = footer
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Refresh", command=self.refresh_backend).pack(side="left")
        ttk.Button(footer, text="Done", command=window.destroy).pack(side="right")
        caps = self.controller.backend.capabilities()
        self.backend_var.set(f"{self.controller.backend.name}\n\n{caps.reason}")

    def request_permission(self):
        self.controller.cancel(quiet=True)
        self.controller.backend.request_permission()
        self.refresh_backend()

    def set_pin(self):
        self.attributes("-topmost", self.pin_var.get())

    def _text_changed(self, _event=None):
        if self.editor.edit_modified():
            if self.controller.mode in ("armed", "settling"):
                self.cancel()
                self.controller.message("Text changed. Arm again when ready.", "warning")
            self.editor.edit_modified(False)

    def clear_text(self):
        if self.controller.mode != "idle" or self.controller._busy():
            self.controller.message("Cancel the transfer before clearing text.", "warning")
        else:
            self.editor.delete("1.0", "end")
            self.controller.message("Text cleared.")
        self._render()

    def grab_clipboard(self):
        if self.controller.mode != "idle" or self.controller._busy():
            self.controller.message("Cancel the transfer before replacing text.", "warning")
        else:
            try:
                value = self.clipboard_get()
            except tk.TclError:
                self.controller.message("No text available in clipboard.", "error")
            else:
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", value)
                self.controller.message(f"Loaded {len(value)} characters.", "success")
        self._render()

    def link(self):
        self.controller.begin_link()
        self._render()

    def arm(self):
        if self.controller._busy():
            self.controller.message("Stop the current transfer first.", "warning")
            self._render()
            return
        self.controller.cancel(quiet=True)
        content, error = normalize_text(self.editor.get("1.0", "end-1c"), self.multiline_var.get())
        if error:
            self.controller.message(error, "error")
        else:
            confirmed = False
            if "\n" in content or "\t" in content:
                confirmed = messagebox.askyesno(
                    "Enter and Tab can execute commands",
                    "Enter may execute commands; Tab may trigger completion or change focus.\n\n"
                    "Open a text editor in the VM first. Send this multiline/tab input?", parent=self)
                if not confirmed:
                    self._render()
                    return
            self.editor.edit_modified(False)
            self.controller.arm(content, self.multiline_var.get(), int(self.delay_var.get()), confirmed)
        self._render()

    def _arm_key(self, _event):
        self.arm()
        return "break"

    def cancel(self):
        self.controller.cancel()
        self._render()

    def tick(self):
        self.controller.tick()
        self._render()
        self.tick_id = self.after(self.TICK_MS, self.tick)

    def on_close(self):
        if self.closing:
            return
        self.closing = True
        self.controller.cancel()
        self.after_cancel(self.tick_id)
        save_prefs({"geometry": self.geometry(), "delay_ms": int(self.delay_var.get()),
                    "host_os": self.host_os_var.get()})
        self._finish_close()

    def _finish_close(self):
        if self.controller._busy():
            self.after(25, self._finish_close)
        else:
            self.destroy()


def main():
    app = TypePaste()
    app.mainloop()


if __name__ == "__main__":
    main()
