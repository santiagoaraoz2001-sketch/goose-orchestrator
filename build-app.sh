#!/bin/bash
# Build Goose Orchestrator — creates the browser app + macOS .app launcher
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Step 1: Python dependencies ==="
uv sync

echo "=== Step 2: Frontend build ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Step 3: Create macOS .app bundle ==="
APP_NAME="Goose Orchestrator.app"
APP_DIR="dist/$APP_NAME"

rm -rf "dist/$APP_NAME"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cp macos/Info.plist "$APP_DIR/Contents/"
cp macos/launch "$APP_DIR/Contents/MacOS/launch"
chmod +x "$APP_DIR/Contents/MacOS/launch"

# Generate a simple .icns from an SVG-rendered PNG (creates a basic icon)
# If icon.icns exists in macos/, use it; otherwise generate a placeholder
if [ -f macos/icon.icns ]; then
    cp macos/icon.icns "$APP_DIR/Contents/Resources/icon.icns"
else
    echo "  (No icon.icns found, generating placeholder)"
    ICONSET_DIR="/tmp/goose-orchestrator-icon.iconset"
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"

    # Create a simple icon using sips from a colored square
    python3 -c "
import struct, zlib
def png(w, h, r, g, b):
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''
    for y in range(h):
        raw += b'\x00' + bytes([r, g, b, 255]) * w
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
for s in [16, 32, 64, 128, 256, 512, 1024]:
    with open(f'$ICONSET_DIR/icon_{s}x{s}.png', 'wb') as f:
        f.write(png(s, s, 47, 252, 200))
"
    iconutil -c icns "$ICONSET_DIR" -o "$APP_DIR/Contents/Resources/icon.icns" 2>/dev/null || true
    rm -rf "$ICONSET_DIR"
fi

echo "=== Step 4: Create release archive ==="
cd dist
tar -czf "goose-orchestrator-macos.tar.gz" "$APP_NAME"
cd ..

echo ""
echo "✓ Build complete!"
echo "  App:     dist/$APP_NAME"
echo "  Archive: dist/goose-orchestrator-macos.tar.gz"
echo ""
echo "To install: drag 'Goose Orchestrator.app' to /Applications"
echo "Or run: cp -r \"dist/$APP_NAME\" /Applications/"
