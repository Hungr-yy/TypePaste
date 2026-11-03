# STEPfwd TypePaste v0.2 — Codex-ready prototype

A narrow, always-on-top desktop companion window for typing local text into CMU CERT STEPfwd's browser-hosted Kali console using synthetic **keyboard input**, not clipboard integration. Useful for an authorized lab with no guest clipboard. Developed as a local proof of concept; not an official CMU/CERT tool.

## Platform support and settings

Click the **⚙ gear icon** at the top-right of the sidecar. In Settings, choose **Auto (recommended)** or one of **Windows 11, macOS, Manjaro Linux, Ubuntu** as the *host OS* profile. The Kali OS inside STEPfwd is a guest, and does **not** determine the selected profile. The selector remembers your choice and prevents sending keystrokes if it does not match the detected host.

**Important:** this is a roadmap-ready selector, not a cross-platform release. The current backend is **Linux X11 using xdotool**, tested in a simulated environment and based on the user's successful manual command on Manjaro. On Wayland, it may work only if Firefox is running through XWayland. **Windows and macOS are not implemented** and the UI will honestly report that they are unavailable. Ubuntu with an X11 session uses the same Linux backend but has not been validated on an actual Ubuntu machine. Refer to `AGENTS.md` and `CODEX_HANDOFF.md` for a developer handoff and acceptance criteria.

## Install on Manjaro

```bash
sudo pacman -S --needed python tk xdotool
unzip stepfwd-typepaste.zip
cd stepfwd-typepaste
./install.sh
```

Launch **STEPfwd TypePaste** from the application menu, or directly:

```bash
python3 ~/.local/share/stepfwd-typepaste/stepfwd_sidecar.py
```

If you do not want to install it, run `python3 stepfwd_sidecar.py` directly in the extracted folder.

## Use

1. Open STEPfwd in **Firefox** and open Kali's terminal. Drag the sidecar into the **white left margin** (default window position is at X=12, Y=155, width=230px, matching the 1728px screenshot; drag it if the display differs).
2. Click **1 Link STEPfwd Firefox** on the sidecar, then click anywhere **inside the Firefox STEPfwd window**. The sidecar should report **Firefox linked**. This remembers the Firefox window ID to avoid typing into other browser windows. Re-link if you restart Firefox or move STEPfwd to a different Firefox window.
3. Copy text from the other monitor. Paste it into the sidecar using Ctrl+V, or click **↓ Clipboard**.
4. Click **2 ARM PASTE → click VM**. It is now armed for up to 35 seconds.
5. Click **directly inside the Kali terminal or editor** in STEPfwd. After a 220ms focus-settle interval, xdotool starts typing the text into the VM. The sidecar stays open and retains the text so you can reuse it. No fixed 3-second countdown.
6. Press **Esc** while the sidecar is focused, or **Cancel / Stop**, to cancel/interrupt an operation. Losing Firefox focus mid-transfer also interrupts it as a best-effort guard. Partial input may already have been sent.

Ctrl+Enter in the sidecar editor also arms the transfer. The **40 ms per key** default is intentionally conservative (matching the command that worked in STEPfwd). If characters are missed, increase to 70 or 120ms.

### Multiline safety

Embedded newlines and tab characters are blocked by default. Typing an Enter or Tab in a shell is **not the same** as pasting: it can execute commands or trigger completion. To type a script, first open a text editor in the VM (such as `nano`), enable **Multiline**, and accept the confirmation. Do not arm multiline text at a shell prompt unless you explicitly intend to execute it. Trailing newlines are removed so pasting a copied one-liner does not automatically run it.

The sidecar does not log or save transferred text. It only saves window geometry and typing speed under `~/.config/stepfwd-typepaste/preferences.json`. It never uploads the text anywhere.

### Always visible in Firefox fullscreen on KDE

The sidecar uses Tk's `-topmost` flag (the **Pin** checkbox) by default, which works above ordinary windows. **True fullscreen is compositor-dependent**; KWin can place fullscreen Firefox above ordinary topmost windows. If the sidecar disappears behind Firefox in F11:

1. While the sidecar is visible, right-click its window title bar → **More Actions** → **Configure Special Window Settings** (or visit **System Settings → Window Management → Window Rules**).
2. Add a rule matching only **STEPfwd TypePaste** by its window title; do not match every Python or Tkinter window.
3. Add **Layer**, choose **Overlay**, with **Force**. Add **Keep Above Other Windows**, if available, and set to **Yes**. Apply the rule, then retry Firefox F11.
4. If your Plasma version has no **Layer** rule or still hides the sidecar, use Firefox maximized but **not F11 fullscreen**. This makes the white margins visible without losing the sidecar.

This KWin `Layer → Overlay` mechanism has been recommended by KWin maintainers for keeping picture-in-picture windows visible above fullscreen windows. It may depend on your Plasma build.

Reference: https://www.mail-archive.com/kde-bugs-dist@kde.org/msg896612.html

### Troubleshooting

- **The link action never detects Firefox:** Run `xdotool getactivewindow getwindowclass` in a **local terminal while Firefox is active**. It should print `firefox`. Firefox may be running as a native Wayland window or your session may not allow X11 introspection.
- **`xdotool type` worked manually, but the sidecar does not:** Confirm the Firefox window ID is linked, click *inside the Kali console* rather than on the surrounding white area, and keep focus there until typing finishes. Re-link after Firefox restarts.
- **Characters are missing:** Increase the typing speed delay to 70 or 120ms. Note: larger delay means *slower* typing.
- **The app can't start:** `echo $XDG_SESSION_TYPE` should normally report `x11`; this program depends on `xdotool` and access to Firefox through X11/XWayland. `echo $DISPLAY` should return something.
- **Clipboard is empty:** Ensure the copied item is text (not a file or image) and use Ctrl+V in the editor as an alternative.
- **A permission prompt appears:** X11 `xdotool` normally does not require root. If Plasma or another tool requests permission, inspect the exact prompt instead of granting blanket admin privileges; do not run this app with `sudo`.

## Architecture and extra-credit findings

`Text in host memory → xdotool XTEST key events → Firefox STEPfwd console → Kali's focused terminal/editor`.

The app watches the active X11 window ID, requires an explicit target binding, and only types when that exact target Firefox window regains focus. It deliberately uses no API calls, VMware agent, hypervisor access, or direct access to STEPfwd internals. This demonstrates that blocking native clipboard integration does not inherently block text injection by simulated keystrokes. The simulation's success with your Kali terminal is established by your screenshot; the sidecar's behavior needs real-world validation on your machine.

**Scope:** use only where your instructor/lab explicitly permits input automation. The application does not attempt privilege escalation or unauthorized access.

## Handoff to Codex

The repository contains `AGENTS.md` (instructions Codex automatically reads) and `CODEX_HANDOFF.md` (detailed milestones). Extract the archive, then launch Codex CLI in the extracted folder and request it to read those two files before beginning. For a ready-to-paste task prompt, see the end of `CODEX_HANDOFF.md`.

```bash
# Install the Codex CLI first, if it is not installed:
npm install -g @openai/codex

cd ~/Downloads/stepfwd-typepaste
python3 -m unittest -v test_core.py
codex
```

The CLI prompts you to sign in to ChatGPT. No GitHub upload is required for local Codex CLI. Git checkpoints are recommended before larger changes.
