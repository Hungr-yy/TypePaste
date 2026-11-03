# TypePaste — Codex development handoff

## Objective

Turn a Manjaro/X11 proof of concept into a polished and genuinely cross-platform desktop app that helps authorized students enter copied text into a browser-hosted virtual-machine console that does not have clipboard integration. This utility uses locally simulated keyboard input. STEPfwd itself and its VMs must remain unmodified.

### Demonstrated proof of concept

On 2026-11-01 the user successfully entered `STEPfwd test 123` into Kali within STEPfwd using:

```bash
sleep 3
xdotool type --clearmodifiers --delay 40 "STEPfwd test 123"
```

A screenshot visibly showed the text in the Kali terminal. The input mechanism works in the user's Manjaro browser session. Note: this only establishes a direct `xdotool` proof of concept, not end-to-end verification of this UI or other operating systems.

## Required experience

1. A compact, resizable, always-visible TypePaste sidecar sits in the unused left white margin of STEPfwd. It must remain usable while the user switches between Firefox, the VM console, and a second monitor. A KDE KWin fullscreen overlay rule may be required, with fallback to a maximized (non-F11) browser.
2. Sidecar has a text area, **Clipboard** action, **Link target**, **Arm Paste**, **Cancel/Stop**, typing-speed control, multiline switch, and a **gear icon** to open Settings.
3. The Settings dialog contains **Host operating system:** Auto (recommended), Windows 11, macOS, Manjaro Linux, Ubuntu. Auto selects the correct local operating system; an override must be validated against the actual host rather than blindly changing labels.
4. After explicit arming, focus changes to the linked STEPfwd Firefox window, and the software types into the currently focused VM console without a fixed three-second timeout. If focus is lost, it should stop where technically possible.
5. Respect privacy: keep clipboard contents in memory, never write them to disk, never send them over network, and never type without a user-initiated Arm action.

## OS backend design (host, not guest)

| Host | Key injection | Focus verification | Permissions / issues |
|---|---|---|---|
| Manjaro Linux | Existing `xdotool`/XTEST on X11; research Wayland-compatible authorized backend | `xdotool getactivewindow` on X11 | Native Wayland can prevent global focus inspection; XWayland may only expose X11 windows |
| Ubuntu | Same X11 adapter; separate Wayland strategy as permitted | X11 as above; design fallback when unavailable | Session-type detection required; `DISPLAY` alone may point to XWayland |
| Windows 11 | Windows API `SendInput` or trusted wrapper, preserving text and special characters | `GetForegroundWindow`, process/window title/handle | Respect UIPI/integrity boundaries; no UAC bypass |
| macOS | Quartz keyboard events (e.g. `CGEventKeyboardSetUnicodeString`) or documented accessibility APIs | `NSWorkspace`/Quartz accessible app/window | Document and request Accessibility permission explicitly; no silent screen/accessibility capture |

The UI layer should depend on a typed adapter interface, not conditional branches scattered throughout UI code. Nonfunctional backends must be visibly disabled. Never fake capability in order to make the settings dropdown look complete. GUI frameworks can remain Tkinter for v1; evaluate a later migration to PySide6/Tauri only with a good reason.

## Development milestones / acceptance criteria

**M1 — Working Linux app + gear UI (already partly done).** Confirm gear opens settings, remembers chosen host profile, defaults to Auto, and prevents selecting Windows/macOS on Linux from invoking `xdotool`. Preserve focus linking, arming and safety behavior. Add core tests; document how to configure KWin fullscreen layering.

**M2 — Two Linux distros.** Test an X11 Manjaro session and Ubuntu X11. Decide on a practical Wayland backend with explicit limitations or provide a clear unsupported message, especially for native Wayland Firefox. Test virtual-console focus and keyboard layout across local and guest environments. Package Linux launchers.

**M3 — Windows 11.** Implement native host focus and keystrokes, guard against incorrect target windows and elevated privileges, validate ASCII, punctuation, keyboard layout and Unicode, then package a portable executable.

**M4 — macOS.** Implement Quartz/Accessibility backend, show an onboarding explanation for Accessibility permissions, verify focus/typing/cancel, then package and document app signing or unsigned application limitations.

**M5 — Regression & polish.** Automated unit tests; UI smoke tests; cross-platform CI where feasible; real-machine manual test matrix; release documentation, screenshots with any personal details removed, and instructions for limitations. Provide deterministic error messages and no unhandled exceptions for uninstalled backends.

## Safety acceptance tests

- No paste before *Arm* or after timeout.
- No paste into an unlinked window and (when technically detectable) stop on focus loss.
- Never automatically send Enter after a single-line payload.
- Reject multiline/tabs by default; explicit opt-in with warning for multiline.
- No persistent user clipboard content, plaintext histories, analytics, or remote calls. OS access permissions, if required, should be requested transparently and not repeatedly spammed.
- Give the user an accessible Cancel/Stop action, clearly document that interruption may leave partial input.
- Test quote/pipes/backslashes and other shell metacharacters without changing them.
- Clearly state permissions required on macOS, Linux Wayland, and Windows.

## Constraints and known unknowns

- We don't know STEPfwd's internal hypervisor/console technology; do not assume VMware or VNC.
- We cannot remotely inspect or alter the CMU-hosted VM. The app is local input assistance only.
- Browser tab/window focus does not guarantee the DOM canvas or guest terminal is focused. A user click directly in the VM is still required; report the limitation.
- Existing v0.2 UI is not yet functionally tested on the user's Manjaro machine. Only the one-shot xdotool command is confirmed to work.
- Physical testing on Windows 11/macOS/Ubuntu is needed before claiming support.

## v0.3 implementation update — 2026-11-03

The slim Tk reference UI is retained. Native code lives in separate adapters; the controller owns link/arm/settle/type state and runs transfers outside Tk. The Windows adapter uses SendInput UTF-16 events, exact HWND/PID and Firefox executable checks. The macOS adapter uses Quartz Unicode events and Accessibility focused-window identity via CFEqual, with an explicit permission button. Native libraries are loaded only on their own host.

Linux still uses xdotool/XTEST with payloads on stdin. Focus is checked per character. A real isolated Xvfb test exposed dropped Unicode with xdotool's zero delay; a 20 ms internal delay fixes the tested accented character and is retained. Requested speed is a minimum interval including backend time. No physical STEPfwd validation has been added by these tests.

Wayland/XWayland sessions now fail closed. DISPLAY alone is not enough to verify focus when native Wayland applications are present. A future consent-based portal adapter must solve focus identity before enabling input; do not enable ydotool as an unchecked fallback.

Safety improvements: exact window/process/application matching, control-character rejection, confirmation for tabs as well as newlines, cancellation on Settings, profile changes unlink targets, stale worker results cannot override new UI state, and a new transfer cannot start while a cancelled worker is still running. Only allowlisted preferences persist. Focus checks and event delivery are not atomic: document residual in-flight input risk.

Tests are in test_core.py, test_native.py, test_ui.py and test_x11_integration.py. The Git history records test-first contract commits. The GitHub Actions workflow builds destination-native artifacts. Windows Server CI is not Windows 11 testing. Automated macOS UI/build checks do not establish STEPfwd input compatibility. Read the actual CI run results before reporting success.

## Remaining real-machine release gate

Record host version, CPU architecture, X11/Wayland session, browser version, local/guest keyboard layouts, package identifier, and result for each run. Do not record actual clipboard content, credentials or personal screenshots.

For **each** of Manjaro X11, Ubuntu X11, Windows 11 and macOS:

- [ ] Launch the packaged app on a clean user account; verify settings, gear, fonts, DPI and multi-monitor positioning.
- [ ] Link the actual STEPfwd Firefox window and send a harmless `STEPfwd test 123` sample.
- [ ] Verify mixed case, quotes, pipes, backslashes, shell metacharacters, accented text, non-Latin text and supplementary-plane Unicode. Record unsupported characters/console behavior honestly.
- [ ] Confirm no typing before Arm, after timeout, after Cancel, or when another Firefox window is foreground.
- [ ] Confirm focus loss and Stop halt a long transfer; inspect partial input and repeat promptly to catch stale-worker races.
- [ ] Check trailing newline removal, multiline/tab confirmation and modifier-key behavior in a guest editor.
- [ ] Check browser tabs/address bar limitations and fullscreen fallback, including macOS Spaces/KDE rules.
- [ ] Windows: test ordinary versus elevated Firefox; failure must never suggest elevation or bypass. Verify VK_PACKET reaches the remote console.
- [ ] macOS: test Accessibility denied, granted, revoked and app relocation; verify the focused AX window is available and Unicode events reach the console. No Screen Recording request.
- [ ] Verify cancellation/clean shutdown from a packaged build and that preferences contain no payload data.

Release signing/notarization and real-machine validation remain required. v0.3 must remain labeled a preview until those gates pass.
