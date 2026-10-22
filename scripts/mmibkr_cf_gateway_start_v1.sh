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
import base64
import hashlib
import json
import os
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
raw = path.read_bytes() if path.exists() else b""
text = raw.decode("utf-8", "replace").lower()

# Cloudflare remotely-managed tunnel credentials are opaque to this runner.
# Report only whether the supplied value is a bare encoded JSON token,
# never the token contents, private keys, domain, account or IDs.
token = os.environ.get("MMIBKR_CF_GATEWAY_TUNNEL_TOKEN", "").strip()
if not token:
    shape = "EMPTY"
else:
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        obj = json.loads(decoded)
        shape = ("EXPECTED_FIELDS" if isinstance(obj, dict)
                 and all(isinstance(obj.get(k), str) and obj[k] for k in ("a", "t", "s"))
                 else "DECODED_UNEXPECTED_FIELDS")
    except (ValueError, UnicodeError):
        shape = "NOT_BASE64_JSON"

rules = (
    ("MISSING_ORIGIN_CERT", r"origin certificate|origincert|cert\.pem|certificate path"),
    ("CREDENTIALS_FILE_UNAVAILABLE", r"credentials file|credentials-file|tunnel credentials not found"),
    ("INVALID_TUNNEL_TOKEN", r"(?:invalid|malformed|parse|decode)[^\n]{0,120}(?:tunnel )?token|token[^\n]{0,120}(?:invalid|malformed|parse|decode)|invalid character|illegal base64"),
    ("TUNNEL_TOKEN_MISSING", r"(?:token[^\n]{0,100}(?:missing|not set|required)|(?:missing|required)[^\n]{0,100}token)"),
    ("TUNNEL_NOT_FOUND", r"tunnel[^\n]{0,100}(?:not found|does not exist|unknown tunnel)"),
    ("TUNNEL_AUTH_REJECTED", r"unauthoriz|forbidden|authentication failed|permission denied|invalid credentials"),
    ("CLIENT_COMMAND_REJECTED", r"incorrect usage|flag provided but not defined|unknown flag|cannot find tunnel"),
    ("NETWORK_CONNECTIVITY", r"no such host|failed to (?:dial|connect)|network is unreachable|context deadline exceeded|i/o timeout|lookup[^\n]{0,100}failed"),
    ("TUNNEL_REGISTRATION_REJECTED", r"failed to register|registering tunnel[^\n]{0,100}fail"),
)
category = next((name for name, pattern in rules if re.search(pattern, text)), "UNCLASSIFIED")

# Restricted word vocabulary conveys error semantics without logging raw text
# or exposing any secret, domain, URL, account, tunnel ID or cloudflared args.
safe_words = set((
    "token tunnel credentials certificate origin config configuration"
    " missing required invalid malformed parse parsing decode base64 json"
    " failed failure error fatal unable unknown unavailable expired"
    " login permission forbidden unauthorized authentication authorization"
    " file flag flags usage argument provided expected cannot could"
    " find found connection connect register registration network"
    " cloudflared tunnelid secret empty corrupt value service"
    " timeout dial server edge lookup context"
).split())
error_lines = [line for line in text.splitlines()
               if re.search(r"\b(err|error|fatal|fail|invalid|missing|unable|unknown)\b", line)]
for index, line in enumerate(error_lines[-3:]):
    words = [word for word in re.findall(r"[a-z]{3,}", line)
             if word in safe_words]
    print(f"MMIBKR_CF_TUNNEL_ERROR_VOCAB_{index}=" + ",".join(words[:18]))
print("MMIBKR_CF_TUNNEL_TOKEN_SHAPE=" + shape)
print("MMIBKR_CF_TUNNEL_STARTUP_FAILURE=" + category)
print("MMIBKR_CF_TUNNEL_LOG_BYTES=" + str(len(raw)))
print("MMIBKR_CF_TUNNEL_LOG_SHA256=" + hashlib.sha256(raw).hexdigest())
PY  echo "MMIBKR_CF_TUNNEL_PROCESS_EXITED=1"
  exit 46
fi
echo "MMIBKR_CF_GATEWAY_SSH_LISTENER_LOOPBACK_ONLY=1"
echo "MMIBKR_CF_TUNNEL_CONNECTOR_PROCESS_RUNNING=1"
echo "MMIBKR_CF_ACCESS_AUTHENTICATION=NOT_YET_VERIFIED"
