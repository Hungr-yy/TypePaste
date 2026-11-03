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
