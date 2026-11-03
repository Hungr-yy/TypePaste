#!/usr/bin/env bash
# Per-user installation only. Dependencies are installed separately by the user.
set -euo pipefail
APP_SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TYPEPASTE_DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPDIR="$TYPEPASTE_DATA/stepfwd-typepaste"
DESKTOPDIR="$TYPEPASTE_DATA/applications"
python3 -c 'import tkinter' || { echo 'Install Python and Tk first.' >&2; exit 1; }
command -v xdotool >/dev/null || { echo 'Install xdotool first.' >&2; exit 1; }
mkdir -p "$APPDIR/typepaste/backends" "$DESKTOPDIR"
if [[ "$APP_SOURCE" != "$APPDIR" ]]; then
    cp -- "$APP_SOURCE/stepfwd_sidecar.py" "$APPDIR/"
    cp -- "$APP_SOURCE"/typepaste/*.py "$APPDIR/typepaste/"
    cp -- "$APP_SOURCE"/typepaste/backends/*.py "$APPDIR/typepaste/backends/"
fi
chmod 755 "$APPDIR/stepfwd_sidecar.py"
python3 - "$APPDIR" "$DESKTOPDIR" <<'PY'
from pathlib import Path
import sys
appdir, desktopdir = map(Path, sys.argv[1:])
# Desktop Entry Exec quoting differs from shell quoting. Escape both layers.
def quote(value):
    value = value.replace('%', '%%')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    return '"' + value.replace('\\', '\\\\') + '"'
if any(c in str(appdir) for c in '\n\r'):
    raise SystemExit('Installation path must not contain line breaks.')
entry = '\n'.join([
    '[Desktop Entry]', 'Type=Application', 'Version=1.0', 'Name=STEPfwd TypePaste',
    'Comment=Local keyboard assistance for STEPfwd',
    'Exec=' + quote(sys.executable) + ' ' + quote(str(appdir / 'stepfwd_sidecar.py')),
    'Icon=input-keyboard', 'Terminal=false', 'Categories=Utility;',
    'StartupWMClass=STEPfwdTypePaste', '',
])
path = desktopdir / 'stepfwd-typepaste.desktop'
path.write_text(entry, encoding='utf-8')
path.chmod(0o644)
PY
echo "Installed: STEPfwd TypePaste"
echo "Launch via application menu or: python3 '$APPDIR/stepfwd_sidecar.py'"
