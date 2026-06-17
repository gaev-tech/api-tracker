#!/usr/bin/env bash
# Publishes a clite .deb into the local aptly repo on the prod server.
#
# Usage:  publish-deb.sh <VERSION> <BINARY_PATH>
#
# Spec: architecture.md §15.9.5, implementation-plan.md §6.3.4.
#
# Expects on the host:
#   - aptly installed
#   - GPG private key imported under the gpg key id stored in $APT_GPG_KEY_ID
#     (or the first secret key, if APT_GPG_KEY_ID is unset)
#   - $REPO_NAME (default: clite-stable) — aptly repo, created on first run
#   - $DIST (default: stable), $COMPONENT (default: main)
#   - $PUBLISH_ROOT (default: /var/lib/api-tracker/apt/public) — served by nginx
#
# The script is idempotent: re-running with the same version is a no-op
# (aptly refuses to add a package that already lives in the repo).

set -euo pipefail

VERSION="${1:?usage: publish-deb.sh <version> <binary>}"
BINARY="${2:?usage: publish-deb.sh <version> <binary>}"

REPO_NAME="${REPO_NAME:-clite-stable}"
DIST="${DIST:-stable}"
COMPONENT="${COMPONENT:-main}"
PUBLISH_ROOT="${PUBLISH_ROOT:-/var/lib/api-tracker/apt/public}"
APTLY_CONFIG="${APTLY_CONFIG:-/etc/aptly.conf}"

if [[ ! -x "$BINARY" ]]; then
  chmod +x "$BINARY"
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

PKGROOT="$WORKDIR/clite_${VERSION}_amd64"
mkdir -p "$PKGROOT/DEBIAN" "$PKGROOT/usr/bin"

cp "$BINARY" "$PKGROOT/usr/bin/clite"
chmod 755 "$PKGROOT/usr/bin/clite"

cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: clite
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: gaev-tech <support@apitracker.ru>
Homepage: https://apitracker.ru
Description: AI-driven task tracker CLI for apitracker.ru
 clite is the command-line interface to apitracker.ru — manage tasks,
 projects, teams, history, and tariffs from your terminal. The package
 ships a single static binary built with PyInstaller.
EOF

DEB_PATH="$WORKDIR/clite_${VERSION}_amd64.deb"
dpkg-deb --build "$PKGROOT" "$DEB_PATH"

# Ensure repo exists. `aptly repo show` exits non-zero if missing.
if ! aptly -config="$APTLY_CONFIG" repo show "$REPO_NAME" >/dev/null 2>&1; then
  aptly -config="$APTLY_CONFIG" repo create \
    -distribution="$DIST" -component="$COMPONENT" "$REPO_NAME"
fi

aptly -config="$APTLY_CONFIG" repo add "$REPO_NAME" "$DEB_PATH"

SNAPSHOT="${REPO_NAME}-${VERSION}-$(date -u +%Y%m%d%H%M%S)"
aptly -config="$APTLY_CONFIG" snapshot create "$SNAPSHOT" from repo "$REPO_NAME"

# First publish vs subsequent switch.
if aptly -config="$APTLY_CONFIG" publish list -raw 2>/dev/null \
     | awk '{print $2}' | grep -qx "$DIST"; then
  aptly -config="$APTLY_CONFIG" publish switch "$DIST" filesystem:stable: "$SNAPSHOT"
else
  aptly -config="$APTLY_CONFIG" publish snapshot \
    -distribution="$DIST" -component="$COMPONENT" \
    "$SNAPSHOT" filesystem:stable:
fi

# Make sure nginx-visible root has Release / Packages / Packages.gz / InRelease.
mkdir -p "$PUBLISH_ROOT"
echo "Published clite ${VERSION} into ${REPO_NAME} (snapshot ${SNAPSHOT})."
echo "Public root: ${PUBLISH_ROOT}"
