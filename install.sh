#!/usr/bin/env bash
set -euo pipefail

APPDIR="$HOME/.local/share/stepfwd-typepaste"
DESKTOPDIR="$HOME/.local/share/applications"
mkdir -p "$APPDIR" "$DESKTOPDIR"
cp -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/stepfwd_sidecar.py" "$APPDIR/stepfwd_sidecar.py"
chmod 755 "$APPDIR/stepfwd_sidecar.py"
cat > "$DESKTOPDIR/stepfwd-typepaste.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=STEPfwd TypePaste
Comment=Sidecar clipboard-to-keystrokes bridge for STEPfwd console
Exec=python3 $APPDIR/stepfwd_sidecar.py
Icon=input-keyboard
Terminal=false
Categories=Utility;
StartupWMClass=STEPfwdTypePaste
EOF
chmod 644 "$DESKTOPDIR/stepfwd-typepaste.desktop"
echo "Installed: STEPfwd TypePaste"
echo "Launch via application menu or: python3 '$APPDIR/stepfwd_sidecar.py'"
