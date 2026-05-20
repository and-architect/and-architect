#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AND Architect – Grasshopper Plugin Build Script (Rhino 8 / macOS)
# ─────────────────────────────────────────────────────────────────────────────
#
# Prerequisites:
#   .NET 7 SDK   → https://dotnet.microsoft.com/download/dotnet/7.0
#   Rhino 8 Mac  → https://www.rhino3d.com/download/
#
# Usage:
#   chmod +x build.sh
#   ./build.sh
#
# The script builds the plugin and copies the .gha file to your
# Grasshopper Libraries folder so it loads next time you open Rhino.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_NAME="AndArchitectGH"
GHA_DEST="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper/Libraries"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AND Architect – Grasshopper Plugin Builder         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Check for .NET SDK ────────────────────────────────────────────────────────
if ! command -v dotnet &> /dev/null; then
    echo "❌  .NET SDK not found."
    echo "    Install from: https://dotnet.microsoft.com/download/dotnet/7.0"
    exit 1
fi

DOTNET_VER=$(dotnet --version)
echo "✓  .NET SDK: $DOTNET_VER"

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo "→  Building $PLUGIN_NAME …"
cd "$PLUGIN_DIR"

dotnet build "$PLUGIN_NAME.csproj" \
    --configuration Release \
    --verbosity minimal

GHA_SRC="$PLUGIN_DIR/bin/Release/net7.0/$PLUGIN_NAME.gha"

if [ ! -f "$GHA_SRC" ]; then
    # Fallback: DLL renamed manually
    DLL_SRC="$PLUGIN_DIR/bin/Release/net7.0/$PLUGIN_NAME.dll"
    if [ -f "$DLL_SRC" ]; then
        cp "$DLL_SRC" "$GHA_SRC"
        echo "✓  Renamed .dll → .gha"
    else
        echo "❌  Build output not found at $GHA_SRC"
        exit 1
    fi
fi

# ── Install ───────────────────────────────────────────────────────────────────
echo ""
echo "→  Installing to Grasshopper Libraries …"
mkdir -p "$GHA_DEST"
cp "$GHA_SRC" "$GHA_DEST/$PLUGIN_NAME.gha"
echo "✓  Installed: $GHA_DEST/$PLUGIN_NAME.gha"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Done! Restart Rhino 8 to load the plugin.         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Components in Grasshopper:"
echo "    AND Architect → 01 Setup    : AND_Room, AND_Building, AND_Orient"
echo "    AND Architect → 02 Generate : AND_Gen,  AND_Solar"
echo "    AND Architect → 03 AI       : AND_AI"
echo "    AND Architect → 04 Visualize: AND_Viz"
echo ""
