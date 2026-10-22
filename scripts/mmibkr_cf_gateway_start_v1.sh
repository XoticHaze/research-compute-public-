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
if ! kill -0 "$(cat "$state/cloudflared.pid")" 2>/dev/null; then
  # The raw cloudflared log may include tenant or token details. Report only
  # fixed categories and a digest; never send raw stderr to public CI logs.
  python - "$state/cloudflared.log" <<'PY'
import hashlib
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
raw = path.read_bytes() if path.exists() else b""
text = raw.decode("utf-8", "replace").lower()
rules = (
    ("INVALID_TUNNEL_TOKEN", r"(?:invalid|malformed|parse|decode)[^\\n]{0,120}(?:tunnel )?token|token[^\\n]{0,120}(?:invalid|malformed|parse|decode)"),
    ("TUNNEL_TOKEN_MISSING", r"(?:token[^\\n]{0,100}(?:missing|not set|required)|(?:missing|required)[^\\n]{0,100}token)"),
    ("TUNNEL_NOT_FOUND", r"tunnel[^\\n]{0,100}(?:not found|does not exist|unknown tunnel)"),
    ("TUNNEL_AUTH_REJECTED", r"unauthoriz|forbidden|authentication failed|permission denied"),
    ("CLIENT_COMMAND_REJECTED", r"incorrect usage|flag provided but not defined|unknown flag|cannot find tunnel"),
    ("NETWORK_CONNECTIVITY", r"no such host|failed to (?:dial|connect)|network is unreachable|context deadline exceeded|i/o timeout|lookup[^\\n]{0,100}failed"),
    ("TUNNEL_REGISTRATION_REJECTED", r"failed to register|registering tunnel[^\\n]{0,100}fail"),
)
category = next((name for name, pattern in rules if re.search(pattern, text)), "UNCLASSIFIED")
print("MMIBKR_CF_TUNNEL_STARTUP_FAILURE=" + category)
print("MMIBKR_CF_TUNNEL_LOG_SHA256=" + hashlib.sha256(raw).hexdigest())
PY
  echo "MMIBKR_CF_TUNNEL_PROCESS_EXITED=1"
  exit 46
fi
echo "MMIBKR_CF_GATEWAY_SSH_LISTENER_LOOPBACK_ONLY=1"
echo "MMIBKR_CF_TUNNEL_CONNECTOR_PROCESS_RUNNING=1"
echo "MMIBKR_CF_ACCESS_AUTHENTICATION=NOT_YET_VERIFIED"
