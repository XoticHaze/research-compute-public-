#!/usr/bin/env bash
# Bind a single approved SSH forwarded port to Cloudflare Access.
# Never starts/restarts IBKR or handles the account password.
set -euo pipefail
test -n "${MMIBKR_CF_SSH_HOSTNAME:-}"
test -n "${MMIBKR_CF_GATEWAY_TUNNEL_TOKEN:-}"
state="${RUNNER_TEMP:?}/mmibkr-cf-ssh-host"
python scripts/mmibkr_cf_ssh_transport_v1.py gateway --state-dir "$state"
sudo apt-get -qq update >/dev/null
sudo apt-get install -y -qq openssh-server >/dev/null
sudo mkdir -p /run/sshd
sudo /usr/sbin/sshd -t -f "$state/sshd_config"
sudo /usr/sbin/sshd -f "$state/sshd_config"
test "$(ss -lnt | awk '$4=="127.0.0.1:2222"{print $4}' | wc -l)" -eq 1
# Named tunnel must be configured upstream: hostname SSH -> localhost:2222,
# Access app Service Auth policy. Token passed through environment only.
TUNNEL_TOKEN="$MMIBKR_CF_GATEWAY_TUNNEL_TOKEN" \
  nohup cloudflared tunnel --no-autoupdate run \
    > "$state/cloudflared.log" 2>&1 &
echo "$!" > "$state/cloudflared.pid"
sleep 5
kill -0 "$(cat "$state/cloudflared.pid")"
echo "MMIBKR_CF_GATEWAY_SSH_LISTENER_LOOPBACK_ONLY=1"
echo "MMIBKR_CF_TUNNEL_CONNECTOR_PROCESS_RUNNING=1"
echo "MMIBKR_CF_ACCESS_AUTHENTICATION=NOT_YET_VERIFIED"
