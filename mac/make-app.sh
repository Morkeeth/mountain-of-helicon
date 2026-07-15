#!/bin/bash
# Wrap the SwiftPM binary in a real .app bundle.
#
# `swift run` is enough to use the app, but a bundle gives it a proper identity
# (LSUIElement so it stays menu-bar-only, a bundle id, a name in the menu bar).
# Usage: ./make-app.sh [--release]  ->  ./Helicon.app
set -euo pipefail

cd "$(dirname "$0")"
CONFIG="debug"
[[ "${1:-}" == "--release" ]] && CONFIG="release"

echo "building ($CONFIG)…"
swift build -c "$CONFIG"

BIN="$(swift build -c "$CONFIG" --show-bin-path)/Helicon"
APP="Helicon.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Helicon"

# The brand faces travel INSIDE the app, two ways on purpose:
#  - Contents/Resources/Fonts + ATSApplicationFontsPath: the standard macOS
#    route, so the fonts exist for the process before any of our code runs.
#  - the SwiftPM resource bundle: what `swift run` uses, and what Theme.swift
#    registers from. Copying it keeps the bundled app and `swift run` identical.
# Registering twice is a no-op (already-registered is not an error), and the
# app degrades to system faces if either is missing rather than failing.
BIN_DIR="$(swift build -c "$CONFIG" --show-bin-path)"
if [[ -d "$BIN_DIR/Helicon_Helicon.bundle" ]]; then
  cp -R "$BIN_DIR/Helicon_Helicon.bundle" "$APP/Contents/Resources/"
  cp -R "$BIN_DIR/Helicon_Helicon.bundle/Fonts" "$APP/Contents/Resources/Fonts"
  echo "bundled $(ls "$APP/Contents/Resources/Fonts" | wc -l | tr -d ' ') font files"
else
  echo "warning: no resource bundle found; the app will fall back to system fonts"
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>Helicon</string>
    <key>CFBundleDisplayName</key>     <string>Mount Helicon</string>
    <key>CFBundleIdentifier</key>      <string>supply.earned.helicon</string>
    <key>CFBundleExecutable</key>      <string>Helicon</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>0.1.0</string>
    <key>LSMinimumSystemVersion</key>  <string>14.0</string>
    <!-- Fraunces / Bricolage Grotesque / IBM Plex Mono, loaded for this app
         only. Typography is the brand: without this the cockpit falls back to
         New York + SF and reads as a different product than the dashboard. -->
    <key>ATSApplicationFontsPath</key> <string>Fonts</string>
    <!-- menu-bar-first: no Dock icon until the cockpit is opened -->
    <key>LSUIElement</key>             <true/>
</dict>
PLIST
echo '</plist>' >> "$APP/Contents/Info.plist"

# Ad-hoc signature: enough to launch locally, not distributable.
codesign --force --sign - "$APP" 2>/dev/null || echo "note: ad-hoc codesign skipped"

echo "built $APP"
echo "run:  open $APP        (menu-bar sentry)"
echo "      $APP/Contents/MacOS/Helicon --queue   (open the cockpit directly)"
