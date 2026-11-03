# STEPfwd TypePaste

A small, always-on-top keyboard companion for instructor-approved STEPfwd labs. Paste text into the sidecar, link Firefox, arm, and click inside the VM. The slim UI follows the included [PNG reference](stepfwd-typepaste-v0.2-preview.png).

**v0.3 is a cross-platform preview, not a validated production release.** Native backends and packages exist; the real STEPfwd acceptance matrix still needs to be completed. This is an unofficial local utility, with no STEPfwd API, guest changes, telemetry, or network access in the application.

## What has actually been tested

| Host | Implementation | Evidence | STEPfwd status |
| --- | --- | --- | --- |
| Manjaro X11 | `xdotool` / XTEST, exact window + PID + class | Local unit/UI tests and real XTEST into disposable Tk widgets on Xvfb | User's direct `xdotool` command worked on 2026-11-01; complete sidecar workflow still untested |
| Ubuntu X11 | Same Linux adapter | CI workflow includes unit/UI/Xvfb integration checks; see the actual run result | No physical Ubuntu/STEPfwd validation |
| Windows 11 | Native `SendInput`, foreground HWND + PID + Firefox process | Simulated API tests; native build/UI CI uses Windows Server, **not Windows 11** | Experimental; no Windows 11/STEPfwd validation |
| macOS | Quartz + Accessibility focused-window identity | Simulated API tests; native macOS build/UI CI | Experimental; no physical Mac/STEPfwd validation |
| Linux Wayland, including XWayland | Disabled | Tests verify refusal even when `DISPLAY` is set | Global focus cannot be verified reliably with this adapter |

CI success establishes the checks it ran, not browser-console compatibility. Windows Unicode `VK_PACKET` and macOS Unicode events can be ignored by remote consoles that only use physical keycodes. Validate a harmless sample in STEPfwd before relying on these backends. Host/guest keyboard layouts and Unicode coverage also need real testing.

## Install and run

Download a package from a successful **Test and package** GitHub Actions run. These are unsigned preview artifacts, not signed/notarized releases.

- **Windows 11:** extract the Windows ZIP and run `TypePaste.exe` as your normal user. Keep Firefox at normal privilege too. No administrator or UAC bypass is used.
- **macOS:** extract the macOS ZIP, move `TypePaste.app` to Applications, and open it. In the gear menu, click **Allow Accessibility…**, grant access in System Settings → Privacy & Security → Accessibility, then **Refresh**. The app never requests Screen Recording. Unsigned previews may be blocked by Gatekeeper; use macOS's normal per-app approval only for a build you trust. Do not disable Gatekeeper. Distributing a production release still requires Developer ID signing and notarization.
- **Manjaro:** install dependencies with `sudo pacman -S --needed python tk xdotool`, extract the Linux archive, and run `./install.sh`.
- **Ubuntu:** install dependencies with `sudo apt install python3 python3-tk xdotool`, extract the Linux archive, and run `./install.sh`.

Linux installation is per user and requires no root. Dependency installation is a separate, explicit system-administration step. Log into an **X11** session. The launcher appears as **STEPfwd TypePaste**; the app can also run from source:

```bash
python3 stepfwd_sidecar.py
```

Source runs need Python 3.10+ and Tk. macOS additionally needs the pinned bridges in `requirements-macos.txt`, installed in a virtual environment. Windows and Linux have no Python runtime dependencies beyond the standard library; Linux needs the external `xdotool` command.

## Use

1. Click **1 Link STEPfwd Firefox**, then click the Firefox window containing STEPfwd. Linking times out after 45 seconds.
2. Paste text into the sidecar or click **Clipboard**. The clipboard is read only when you request it.
3. Click **2 ARM PASTE → click VM**, or press Ctrl+Enter in the editor (Command+Enter also works on macOS).
4. Click **directly inside the guest terminal/editor** within 35 seconds. Typing begins after the linked window holds focus for 220 ms.
5. Use **Cancel / Stop**, or Escape while the sidecar is focused, to stop. Losing the linked window's focus stops at the next backend check. Check for partial input before trying again.

40 ms is the default minimum interval; choose 70 or 120 for slower consoles. Backend overhead may make typing slower than the selected interval. Keep modifier keys released while typing. Text stays in the sidecar for repeated use; **Clear** removes it. Opening Settings cancels an active transfer. Changing the host profile or clicking Refresh also discards the target link.

The **gear** chooses the native **host** OS, not the guest Kali OS. Auto is recommended. An incorrect manual override disables Link and Arm and explains why. The settings panel shows backend availability and permission requirements.

## Input safety and limitations

- Explicit Arm is required for every transfer. The backend checks linked window identity before **each character**. Window/application matching never depends on a title substring.
- This is a best-effort guard, not atomic routing: focus can change between inspection and OS event delivery. One in-flight character/key pair can still arrive after a change or cancellation. No desktop automation can promise that window focus alone identifies the guest terminal.
- A different tab, Firefox's address bar, a browser popup, or a different guest field inside the same linked window may be indistinguishable. Always click the actual VM input area and keep that tab selected.
- No final Enter is added; trailing CR/LF are stripped. Embedded newlines and tabs are blocked by default. **Multiline** opt-in plus a per-transfer confirmation is required for either. Enter can execute commands and Tab can trigger completion or move focus: use a guest text editor.
- NUL, Escape, Backspace, other control characters, invalid surrogates and alternate Unicode line separators are rejected. Text is limited to 20,000 characters.
- Stop is not a global hotkey. Escape only works in the sidecar; clicking Stop also moves focus away from Firefox. Cancellation cannot undo input already sent.
- No clipboard text, target IDs, histories or permission choices are persisted. Only geometry, host profile and typing delay are saved. Multiline always starts disabled.
- Preferences: Linux `$XDG_CONFIG_HOME/stepfwd-typepaste/preferences.json` (default `~/.config`); Windows `%LOCALAPPDATA%/stepfwd-typepaste/preferences.json`; macOS `~/Library/Application Support/stepfwd-typepaste/preferences.json`.

Wayland is intentionally unavailable: `ydotool`/`uinput` can inject keys but do not establish trustworthy foreground-window identity, and the RemoteDesktop portal requires a separate consent/session design. This version does not request device permissions, start privileged daemons, or quietly fall back to XWayland.

## Fullscreen and two monitors

Drag the roughly 230-pixel sidecar into STEPfwd's white margin. **Pin** requests always-on-top; fullscreen stacking is controlled by the desktop. On KDE, create a KWin window rule matching only `STEPfwdTypePaste` or the exact title and try **Keep Above**. If your KWin version exposes a **Layer → Overlay** rule, it may help. Otherwise maximize Firefox without F11, keep TypePaste on the other monitor, or leave fullscreen to arm it. Other desktops and macOS fullscreen Spaces may require the same alternatives.

## Tests and builds

The test-first history includes failing contract commits followed by implementations. Native API tests use fakes and emit no real input. UI tests use a fake backend. X11 integration tests require explicit opt-in and verify they are on Xvfb before touching focus metadata.

```bash
python3 -m unittest -v test_core.py test_native.py
python3 -m py_compile stepfwd_sidecar.py
TYPEPASTE_REQUIRE_GUI=1 TYPEPASTE_X11_TEST=1 xvfb-run -a python3 -m unittest -v test_ui.py test_x11_integration.py
```

Build on the destination operating system:

```bash
# Manjaro / Ubuntu: source bundle, no Python build dependencies
./scripts/build-linux.sh

# macOS: installs pinned build dependencies in .venv
./scripts/build-macos.sh
```

On Windows with Python 3.12 installed, run `scripts/build-windows.ps1` from PowerShell. It creates `.venv` and runs the tests before packaging. Outputs go to `dist/`. The Linux bundle uses the host's Python/Tk/xdotool to avoid incompatible bundled glibc versions across distros. GitHub Actions runs unit tests, GUI smoke checks and native packaging on Ubuntu, Windows Server and macOS; Linux also runs Xvfb integration tests. It uploads artifacts without publishing a public release.

## Architecture and release gate

- `stepfwd_sidecar.py`: compact Tk UI; no native keyboard or focus code.
- `typepaste/core.py`: explicit link/arm/settle/type lifecycle, timeouts, generation-safe cancellation and worker isolation.
- `typepaste/backends/`: typed target/capability records and separate Linux, Windows and macOS adapters.
- `typepaste/preferences.py`: atomic, allowlisted preference writes.

Before claiming production support, complete [the real-machine acceptance checklist](CODEX_HANDOFF.md), validate packaged launches on the destination hardware and STEPfwd, and sign/notarize native releases. Never claim CI fakes or Xvfb prove the remote VM accepted text.

Implementation references: [Microsoft SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput), [Apple Accessibility trust](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions), [PyObjC ApplicationServices](https://pyobjc.readthedocs.io/en/latest/apinotes/ApplicationServices.html), [PyInstaller native builds](https://pyinstaller.org/en/stable/), [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html).
