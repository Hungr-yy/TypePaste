# STEPfwd TypePaste — instructions for coding agents

## Product and user journey

This repository is an unofficial, locally running, permission-respecting desktop utility for an instructor-authorized CERT STEPfwd lab. STEPfwd's browser-hosted Kali terminal accepts synthetic keystrokes (validated by a successful manual `xdotool type --clearmodifiers --delay 40 "STEPfwd test 123"` test on Manjaro). Native clipboard integration is absent.

The user copies text from another monitor, pastes it into a narrow, always-on-top companion window sitting in STEPfwd's white margin, arms a paste, clicks the VM terminal, and the companion types text into the browser console. It must never paste into a random background window. The project should ultimately run on Windows 11, macOS, Manjaro Linux, and Ubuntu **hosts**, independently of the guest OS running inside STEPfwd.

## Current state

- `stepfwd_sidecar.py` is the slim Tk UI; `typepaste/core.py` owns transfer safety and `typepaste/backends/` contains separate native adapters. Linux X11 remains xdotool-based. Wayland/XWayland sessions fail closed.
- Gear/settings validates Auto/Windows 11/macOS/Manjaro Linux/Ubuntu. Windows SendInput and macOS Quartz/Accessibility implementations are experimental until real STEPfwd testing; never claim build or fake-API tests establish hardware compatibility.
- Test-driven development: add a failing regression test before changing behavior. `test_core.py`, `test_native.py`, `test_ui.py` and opt-in `test_x11_integration.py` cover safety, native API contracts, UI and isolated XTEST.
- `install.sh` installs the Linux launcher and modules. `scripts/` and GitHub Actions build native preview packages. `README.md` distinguishes actual validation from simulation.
- `CODEX_HANDOFF.md` is the detailed engineering specification and acceptance checklist. Read it before modifying code.

## Engineering principles

1. Separate the **native host** from STEPfwd's **guest OS**. The gear OS selector configures the host-specific input/backend. Default to Auto detection, allow manual override only with validation, and show capabilities and reasons when unavailable.
2. Build adapters behind an interface such as `get_active_target`, `link_target`, `send_keystrokes`, `abort`, `capabilities`. Keep Tkinter UI free of OS-specific code. Avoid a rewrite unless it materially improves the UX.
3. Backend targets: Linux X11 (`xdotool`, preserve working behavior); Linux Wayland (evaluate permitted `ydotool`/portal solutions and focus-detection constraints); Windows 11 (native `SendInput` or reviewed input library plus native foreground-window detection); macOS (Quartz/Accessibility plus native foreground application/window detection). Do not claim untested platforms work.
4. Critical invariants: explicit arm; focus verification on linked target where APIs allow; no automatic final Enter; multiline/tab disabled by default; user-confirmation for multiline; cancel or stop mid-transfer; no clipboard persistence/logging, network calls, or elevation; clear status/error messages.
5. A feature that requires accessibility/input-monitoring or `/dev/uinput` permissions must request only documented permission. Do not silently disable OS security mechanisms or require root to run the application.
6. Support true/fullscreen as best effort; always-on-top is not guaranteed above fullscreen browser windows. Provide KDE KWin guidance and reasonable alternatives.
7. Preserve the 230-ish pixel slim sidecar and practical keyboard- and mouse-based workflow. Gear icon should remain accessible. Optimize for use across two monitors and fast repeated pastes.
8. Add tests for target matching, OS detection, adapter choice, failures, Unicode, mixed case, shell metacharacters, line endings, tab/Enter safety, and stop behavior. Keep the Linux prototype continuously runnable.
9. Build deliverables: Windows `.exe`, macOS `.app`, and Linux bundles or scripted installation. Document what was tested on real hardware vs simulated in CI.
10. Keep it authorized and transparent: application is for instructor-approved input assistance only; do not implement hypervisor access, stealth, privilege escalation, or bypasses of server-side controls.

## Development workflow

- Run `python3 -m unittest -v test_core.py` and `python3 -m py_compile stepfwd_sidecar.py` after code changes.
- Prefer standard-library Python where possible. Document and pin added dependencies only when needed.
- Update `README.md`, `CODEX_HANDOFF.md`, and tests whenever support status changes.
- Before making a major architectural change, summarize the migration plan and acceptance criteria in the task discussion.
- Do not commit secrets, clipboard contents, authentication artifacts, or personal STEPfwd screenshots.
