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

## Suggested starting Codex task

> Read AGENTS.md and CODEX_HANDOFF.md. Refactor STEPfwd TypePaste into a cross-platform architecture with a clearly labeled gear/settings menu for Auto, Windows 11, macOS, Manjaro Linux, and Ubuntu host OS profiles. Keep the existing Manjaro/X11 behavior working, require an explicit Arm action, verify target focus, preserve multiline and no-auto-Enter safeguards, and show honest unavailable states for unimplemented OS backends. Start by implementing and testing M1, propose the minimal adapter boundary for M2–M4, then execute further milestones only with code and real test evidence. Add tests and update README for every stage.
