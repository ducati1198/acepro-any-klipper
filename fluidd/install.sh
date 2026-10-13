#!/usr/bin/env bash
# =========================================================================
# ACE Pro panel for Fluidd - installer
#
# Usage:
#   bash install.sh
#
# Optional environment variables:
#   FLUIDD_DIR   where to build (default: fresh clone into ./fluidd)
#   WEBROOT      where to deploy the build (default: auto-detect, see below)
#   KEEP_REPO=1  keep the cloned/built repository after deploy
#
# The script will:
#   1. check Node.js >= 18 and pnpm
#   2. copy the ACE panel sources into the Fluidd tree
#   3. patch Dashboard.vue / layout state (anchor-based, idempotent)
#   4. build Fluidd (pnpm install + pnpm run build)
#   5. back up the current webroot and deploy the new build
# =========================================================================
set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLUIDD_DIR="${FLUIDD_DIR:-$PKG_DIR/fluidd}"
WEBROOT="${WEBROOT:-}"
KEEP_REPO="${KEEP_REPO:-0}"

echo "==> Checking Node.js..."
NODE_MAJOR="$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/' || echo 0)"
if [ "${NODE_MAJOR:-0}" -lt 18 ]; then
  echo "!!! Node.js is too old ($(node -v 2>/dev/null || echo 'not found')), >= 18 is required."
  echo "    Install a current LTS from https://nodejs.org or via your package manager."
  exit 1
fi
echo "    Node $(node -v)"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "==> pnpm not found, installing..."
  npm i -g pnpm
fi
echo "    pnpm $(pnpm -v)"

# --- 1. Fluidd sources ---
if [ ! -d "$FLUIDD_DIR/.git" ]; then
  echo "==> Cloning Fluidd..."
  rm -rf "$FLUIDD_DIR"
  git clone --depth 50 https://github.com/fluidd-core/fluidd.git "$FLUIDD_DIR"
fi

# --- 2. ACE panel sources ---
echo "==> Copying ACE panel sources..."
mkdir -p "$FLUIDD_DIR/src/mixins" "$FLUIDD_DIR/src/components/widgets/ace"
cp "$PKG_DIR/src/mixins/ace.ts" "$FLUIDD_DIR/src/mixins/ace.ts"
cp "$PKG_DIR/src/components/widgets/ace/AceCard.vue" "$FLUIDD_DIR/src/components/widgets/ace/AceCard.vue"

# --- 3. Patch Dashboard.vue / layout state ---
echo "==> Patching Fluidd..."
(cd "$FLUIDD_DIR" && python3 "$PKG_DIR/apply_fluidd_ace.py")

# --- 4. Icon alias used by the card menu ---
G="$FLUIDD_DIR/src/globals.ts"
if ! grep -q "dotsVertical:" "$G"; then
  sed -i 's/^  dotsGrid: mdiDotsGrid,$/  dotsGrid: mdiDotsGrid,\n  dotsVertical: mdiDotsVertical,/' "$G"
fi

# --- 5. Build ---
echo "==> Installing dependencies (pnpm install)..."
(cd "$FLUIDD_DIR" && pnpm install)
echo "==> Building (pnpm run build)..."
(cd "$FLUIDD_DIR" && pnpm run build)

# --- 6. Deploy ---
if [ -z "$WEBROOT" ]; then
  for candidate in /usr/share/fluidd /var/www/fluidd /opt/fluidd; do
    if [ -d "$candidate" ]; then
      WEBROOT="$candidate"
      break
    fi
  done
fi

if [ -z "$WEBROOT" ]; then
  cat <<EOF
!!! Could not auto-detect the Fluidd webroot.
    Deploy manually:
      cp -r "$FLUIDD_DIR/dist/." /path/to/webroot
    or re-run with:
      WEBROOT=/path/to/webroot bash install.sh
EOF
  exit 1
fi

BACKUP="$WEBROOT.bak-ace-$(date +%Y-%m-%d-%H%M%S)"
echo "==> Deploying to $WEBROOT (backup: $BACKUP)..."
cp -r "$WEBROOT" "$BACKUP"
cp -r "$FLUIDD_DIR/dist/." "$WEBROOT/"

# Restore ownership when run through sudo
if [ -n "${SUDO_USER:-}" ]; then
  chown -R "$SUDO_USER":"$(id -gn "$SUDO_USER")" "$WEBROOT" || true
fi

if [ "$KEEP_REPO" != "1" ]; then
  echo "==> Removing build tree ($FLUIDD_DIR)..."
  rm -rf "$FLUIDD_DIR"
fi

echo ""
echo "Done! Hard-reload Fluidd in your browser: Ctrl+Shift+R"
echo "(If the card does not appear, also clear the site data / service worker"
echo " in DevTools -> Application -> Storage.)"
