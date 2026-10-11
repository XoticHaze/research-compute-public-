#!/bin/bash
# Read-only post-deploy reconciliation for neutral preseal broker.
# CommandCenter #809. No Cloudflare mutation; no credential printing.
set -euo pipefail
BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
CF_DIR="$WORK/cf-cli"
STAGE="$WORK/neutral-broker-cf-deploy"
EXPECTED_ID="b33595eb85f346b0d1bf201810b4499a"
ORIGIN="https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev"
fail(){ echo "NEUTRAL_BROKER_READBACK_FAIL=$1" >&2; exit 2; }
NODE="$(find "$WORK/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_runtime_missing
export PATH="$(dirname "$NODE"):$PATH"
export npm_config_cache="$WORK/npm-cache"
export NPM_CONFIG_CACHE="$WORK/npm-cache"
[[ -d "$CF_DIR" && -f "$WORK/cloudflare_neutral_account_id" ]] || fail saved_account_missing
ACTUAL="$(tr -d '\r\n' < "$WORK/cloudflare_neutral_account_id")"
[[ "$ACTUAL" == "$EXPECTED_ID" ]] || fail wrong_account_id
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
export CLOUDFLARE_ACCOUNT_ID="$ACTUAL"
umask 077
mkdir -p "$STAGE"
(
 cd "$CF_DIR"
 npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/reconcile-account.json"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/reconcile-search.json"
)
readback_fail=0
python3 - "$STAGE/reconcile-account.json" "$STAGE/reconcile-search.json" "$EXPECTED_ID" <<'PY' || readback_fail=1
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text())
x=json.loads(Path(sys.argv[2]).read_text())
if not isinstance(a,dict) or a.get('id')!=sys.argv[3] or a.get('name')!='Shared Compute Neutral Authorization':
 raise SystemExit('NEUTRAL_ACCOUNT_READBACK_MISMATCH=1')
if isinstance(x,dict): x=x.get('result')
if not isinstance(x,list): raise SystemExit('NEUTRAL_WORKER_SEARCH_INVALID_SHAPE=1')
names=sorted(set(str(row.get('script_name') or row.get('name') or '') for row in x if isinstance(row,dict)))
found='reference-release-broker-v1' in names
print('NEUTRAL_ACCOUNT_READBACK_PASS=1')
print('NEUTRAL_WORKER_SEARCH_COUNT='+str(len(x)))
print('NEUTRAL_SEARCHED_SCRIPT_NAMES='+','.join(n for n in names if n and n.startswith('reference-')))
print('NEUTRAL_BROKER_REMOTE_READBACK_PASS='+str(int(found)))
if not found:
 print('NEXT_CHECK=inspect_cf_deploy_log_without_redeploying')
 raise SystemExit(3)
PY

# No authenticated requests to the public worker.
probe(){
  local label="$1" method="$2" path="$3" expected="$4" response code
  response="$STAGE/reconcile-$label.json"
  if [[ "$method" == "POST" ]]; then
    code="$(/usr/bin/curl --silent --show-error --max-time 25 --connect-timeout 10 \
      --output "$response" --write-out '%{http_code}' --header 'content-type: application/json' \
      --data '{}' "$ORIGIN$path")" || {
      echo "NEUTRAL_$label"_"NETWORK_ERROR=1"; return 1;
    }
  else
    code="$(/usr/bin/curl --silent --show-error --max-time 25 --connect-timeout 10 \
      --output "$response" --write-out '%{http_code}' "$ORIGIN$path")" || {
      echo "NEUTRAL_$label"_"NETWORK_ERROR=1"; return 1;
    }
  fi
  echo "NEUTRAL_$label"_"HTTP=$code"
  if [[ "$code" == "$expected" ]]; then
    echo "NEUTRAL_$label"_"PASS=1"
  else
    echo "NEUTRAL_$label"_"PASS=0"
    return 1
  fi
}
failures=0
probe HEALTH GET /healthz 200 || failures=$((failures+1))
probe PUBLIC_KEY_PRESEAL GET /v1/public-key 503 || failures=$((failures+1))
probe RELEASE_PRESEAL POST /v1/release 503 || failures=$((failures+1))
echo "READBACK_HTTP_FAILURE_COUNT=$failures"
echo "CLOUDFLARE_MUTATIONS=NONE"
if [[ "$failures" -gt 0 || "$readback_fail" -gt 0 ]]; then
  echo "NEXT_GATE=investigate_readback_before_any_new_deployment"
  exit 2
fi
echo "BROKER_SIGNER_SEALED=NO"
echo "NEXT_GATE=isolated_maintenance_control_plane_bootstrap"
