#!/usr/bin/env bash
# Install a verified Cloudflare client for ephemeral Linux GitHub runners.
set -euo pipefail
VERSION=2026.10.0
EXPECTED=d33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl --fail --silent --show-error --location --retry 3 --max-time 90 \
  "https://github.com/cloudflare/cloudflared/releases/download/$VERSION/cloudflared-linux-amd64" \
  --output "$tmp"
printf '%s  %s\n' "$EXPECTED" "$tmp" | sha256sum --check --status
sudo install -m 0755 "$tmp" /usr/local/bin/cloudflared
cloudflared --version | grep -F "$VERSION"
echo "MMIBKR_CF_CLOUDFLARED_SHA256_VERIFIED=1"
