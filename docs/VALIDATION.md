# v0.3 validation record — 2026-11-03

Code revision: `081c7345fdc3aceb4fecaddd7f524ae766551d94`.

[Successful native CI run](https://github.com/Hungr-yy/TypePaste/actions/runs/41594413130). All three jobs passed. Later documentation-only commits do not change the tested application code.

| Environment | Checks actually completed | Limits |
| --- | --- | --- |
| Local Manjaro, Python 3.14.7, isolated Xvfb/Tk | Core safety and simulated API tests; UI/settings checks; real xdotool/XTEST input, case/punctuation/accent preservation, no appended Enter, focus-loss stop and cancellation; entry-point compilation; temporary per-user installation including a path with spaces; desktop-file validation | No real STEPfwd sidecar session, fullscreen or physical monitor testing |
| Ubuntu 24.04 x64 CI, Python 3.12 | Core/API/UI tests; real xdotool/XTEST integration on Xvfb; compilation and Linux source-bundle creation | Virtual display and disposable Tk target, not STEPfwd or an Ubuntu workstation |
| Windows Server 2022 x64 CI, Python 3.12 | Core/API/UI tests; actual Win32 binding load/ABI smoke check; compilation and PyInstaller executable build | Not Windows 11; no native keyboard injection or STEPfwd session tested |
| macOS 14 ARM64 CI, Python 3.12 | Core/API/UI tests; actual PyObjC bridge load and Unicode event creation without posting; compilation and PyInstaller app build | No permission grant, native keyboard posting, physical Mac or STEPfwd session tested |

There are 54 test methods across the four suites. Local/Ubuntu Linux runs execute 52 and skip the two native Windows/macOS smoke checks. Windows and macOS each execute their own native smoke check, skip the other OS check, and do not run the X11-only integration suite. CI fails if a required GUI display is unavailable.

## Produced and downloaded packages

- `TypePaste-0.3.0-windows-amd64.zip`: portable `TypePaste.exe` and README.
- `TypePaste-0.3.0-darwin-arm64.zip`: `TypePaste.app` with preserved bundle layout.
- `TypePaste-0.3.0-linux-x86_64.tar.gz`: Python source, installer, tests, build scripts and documentation. Runtime uses the destination Linux Python/Tk/xdotool.

All three artifacts were downloaded from the successful run. ZIP integrity was checked, expected executable/app entries were verified, and the Linux archive's runtime modules and installer were verified. Local copies are in `dist/packages/`, with `SHA256SUMS`. Build artifacts are not committed to Git.

Windows and macOS packages remain unsigned previews; macOS Intel and Windows ARM64 packages were not built. A macOS ARM64 package does not establish Intel compatibility. No signed/notarized production release has been published.

## Failures caught before completion

Test-first safety contracts caught stale cancellation status. Real X11 tests caught a Unicode timing issue at zero xdotool delay. Ubuntu CI caught the unsupported `getwindowclassname` command in its older xdotool, then exposed Tk test-fixture finalization on a worker thread; both were fixed. Additional regression tests cover safe in-flight key-pair completion and refreshing the macOS Accessibility button after a host-profile change.

The user-provided proof remains the successful direct xdotool command into STEPfwd on Manjaro on 2026-11-01. No additional end-to-end STEPfwd success is claimed. Follow the remaining real-machine checklist in [CODEX_HANDOFF.md](../CODEX_HANDOFF.md) before marking any new host as validated production support.

## v0.3.1 immediate-start update — 2026-11-03

Application revision `1a4c93116341dd2ff9360b69d679ca9434c7643d` passed [all three native CI jobs](https://github.com/Hungr-yy/TypePaste/actions/runs/41599654857). Windows x64, macOS ARM64 and Linux x64 packages were rebuilt as v0.3.1.

The 220 ms focus-settle timer was removed. An armed transfer now starts on the next successful linked-focus observation, without waiting for a countdown. The trigger still uses focus, not a physical mouse hook: Alt+Tab into the linked window also counts. The 35-second unused-Arm expiry and per-character delay remain; the UI labels the latter `ms/key`.

Test-first regressions verify that no clock advancement is needed to start, other windows cannot trigger typing, and focus arriving at expiry sends nothing. Core/API tests and GUI smoke checks passed locally; the complete platform-appropriate checks passed in CI. There are now 55 test methods across the four suites. The physical-machine and STEPfwd limitations above remain unchanged.


## v0.4 KDE Wayland preview — 2026-11-03

Local checks on Manjaro, Python 3.14.7, PyGObject 3.56.3 and KWin 6.7.4:

- 65 core/native/Wayland unit tests: 63 passed, two native-only Windows/macOS smoke checks skipped on Linux.
- Nine Tk UI tests passed on Xvfb; all three existing real xdotool/XTEST integration tests passed.
- Three real Gio/D-Bus transport tests passed against a fake portal on an isolated session bus. This validates protocol encoding, early signals, denial, cancellation, revocation and paired key calls without injecting input.
- Two read-only tests passed on the actual KDE Wayland desktop: fresh focus snapshots and cleanup, and refusal after deliberately unloading only the test's own helper. No window titles, clipboard or screen contents were read.
- Python compilation passed. The Linux bundle contains every Wayland runtime module and the validation docs. A temporary per-user installation with spaces in its path passed content checks. The existing per-user TypePaste installation was then updated and its installed Wayland modules verified against the source.

**Not tested:** real KDE permission approval, actual Wayland keyboard delivery, native Wayland or XWayland Firefox/STEPfwd, physical Ubuntu, Windows 11 or macOS. The only confirmed STEPfwd input remains the user's original direct xdotool command. Keep this release labeled a preview.

[The v0.4 native CI run](https://github.com/Hungr-yy/TypePaste/actions/runs/41690688094) passed all three jobs for application revision `8045185`: Ubuntu 24.04 x64, Windows Server 2022 x64, and macOS 14 ARM64. Linux also passed the real Gio/fake-portal transport suite using its system Python/PyGObject. All platform-appropriate unit and UI checks passed, followed by native packaging. Windows Server is not Windows 11 hardware testing; macOS event creation still does not post keyboard input.

The three v0.4.0 packages were downloaded into ignored `dist/packages-0.4.0/`. ZIP integrity, Windows PE and macOS Mach-O presence, and Linux backend contents were checked. SHA-256 hashes are in that directory's `SHA256SUMS`. Later documentation-only commits do not change this tested application revision.
