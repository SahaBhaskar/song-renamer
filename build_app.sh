#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_app.sh — Build Song Renamer.app + SongRenamer.dmg
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

APP_NAME="Song Renamer"
DMG_NAME="SongRenamer"
DIST_DIR="dist"
BUILD_DIR="build"

echo "━━━  Song Renamer — macOS App Builder  ━━━"
echo ""

# ── 1. Clean previous builds ────────────────────────────────────────────────
echo "▶  Cleaning previous build..."
rm -rf "$DIST_DIR" "$BUILD_DIR" "${APP_NAME}.spec.bak"

# ── 2. Build .app with PyInstaller ──────────────────────────────────────────
echo "▶  Building .app bundle (this takes a few minutes)..."
python3 -m PyInstaller song_renamer.spec --noconfirm

APP_PATH="$DIST_DIR/${APP_NAME}.app"
if [ ! -d "$APP_PATH" ]; then
    echo "✖  Build failed — .app not found in $DIST_DIR"
    exit 1
fi
echo "✔  App bundle created: $APP_PATH"

# ── 3. Remove quarantine flag (so macOS doesn't block it on first launch) ───
echo "▶  Removing quarantine flag..."
xattr -cr "$APP_PATH" 2>/dev/null || true

# ── 4. Create .dmg installer ────────────────────────────────────────────────
echo "▶  Creating DMG installer..."
DMG_PATH="$DIST_DIR/${DMG_NAME}.dmg"
TMP_DMG="$DIST_DIR/${DMG_NAME}_tmp.dmg"

# Create a temporary writable DMG
hdiutil create -size 500m -fs HFS+ -volname "$APP_NAME" "$TMP_DMG" -quiet

# Mount it
MOUNT_POINT=$(hdiutil attach "$TMP_DMG" -readwrite -noverify -quiet | \
              grep -E '^/dev/' | tail -1 | awk '{print $NF}')

# Copy app into DMG
cp -R "$APP_PATH" "$MOUNT_POINT/"

# Add a symlink to /Applications for easy drag-install
ln -s /Applications "$MOUNT_POINT/Applications"

# Unmount and convert to compressed read-only DMG
hdiutil detach "$MOUNT_POINT" -quiet
hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH" -quiet
rm "$TMP_DMG"

echo "✔  DMG created: $DMG_PATH"
echo ""
echo "━━━  Done  ━━━"
echo ""
echo "  App:  $APP_PATH"
echo "  DMG:  $DMG_PATH"
echo ""
echo "  To install: open $DMG_PATH"
echo "  Then drag 'Song Renamer' into the Applications folder."
echo ""
echo "  NOTE: If macOS blocks the app on first launch, right-click"
echo "  the app → Open → Open anyway."
