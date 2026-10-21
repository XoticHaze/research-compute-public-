#!/usr/bin/env bash
# Headless Cloudflare Access -> pinned OpenSSH host -> localhost-only 4001.
set -euo pipefail
state="${RUNNER_TEMP:?}/mmibkr-cf-ssh-reader"
python scripts/mmibkr_cf_ssh_transport_v1.py reader --state-dir "$state"
host="${MMIBKR_CF_SSH_HOSTNAME:?}"
# cloudflared Access receives its service-token pair from environment; no
# token is printed or embedded into argv, GitHub logs, or SSH configuration.
timeout --signal=TERM --kill-after=5 95 \
  ssh -F "$state/ssh_config" -f -N \
    -L 127.0.0.1:14001:127.0.0.1:4001 "$host"
# SSH's ExitOnForwardFailure proves local bind only; caller must perform
# a separate application-level round trip before saying transport works.
test "$(ss -lnt | awk '$4=="127.0.0.1:14001"{print $4}' | wc -l)" -eq 1
echo "MMIBKR_CF_SSH_PINNED_HOST_HANDSHAKE=PASS"
echo "MMIBKR_CF_SSH_LOCAL_FORWARD_LOOPBACK_ONLY=1"
echo "MMIBKR_CF_TUNNEL_BROKER_APP_HANDSHAKE=NOT_YET_TESTED"
