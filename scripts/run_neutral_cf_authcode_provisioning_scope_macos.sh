#!/bin/bash
# One controlled alternate OAuth grant check for the neutral account.
# AUTHORIZATION-CODE FLOW, not device flow. No Cloudflare API token created.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
CLI="$ROOT/cf-cli"
fail(){ echo "NEUTRAL_AUTHCODE_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail no_neutral_cli
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail wrong_saved_account
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_api_email
[[ ! -f "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail no_portable_node
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
cd "$CLI"
echo "OAUTH_FLOW=AUTHORIZATION_CODE_NOT_DEVICE"
echo "REQUESTED_SCOPES=EXACT_FIVE_NARROW_SCOPE_KEYS"
echo "NEUTRAL_ACCOUNT_BOUND=1"
echo "ACCOUNT_API_TOKEN_CREATE_POST=NOT_ATTEMPTED"
echo "CLOUDFLARE_WORKER_MUTATIONS=NONE"
echo "BEGIN_ONE_BROWSER_CONSENT=1"
# --no-device enables PKCE authorization-code consent flow (local callback);
# --no-browser prints URL without opening a browser. Keep terminal open.
# Never paste callback URLs, authorization codes, or OAuth credential JSON.
if ! npx --yes cf@1.0.0-beta.14 auth login \
 --force --no-device --no-browser \
 --scopes user:read account:read account_api_tokens:create workers:write workers_scripts:write; then
 echo "AUTHORIZATION_CODE_LOGIN=FAILED_NO_TOKEN_CREATION"
 echo "NEXT_GATE=LOCAL_CALLBACK_OR_OAUTH_ISSUANCE_DIAGNOSTIC"
 exit 2
fi
python3 - "$ACCOUNT" <<'PY'
import json,subprocess,sys
account=sys.argv[1]
cli=['npx','--yes','cf@1.0.0-beta.14']
def load(args):
 p=subprocess.run(cli+args,capture_output=True,text=True,timeout=90)
 if p.returncode:return None
 try:return json.loads(p.stdout)
 except ValueError:return None
who=load(['auth','whoami'])
acct=load(['accounts','get'])
ok=(isinstance(who,dict) and who.get('authenticated') is True
    and who.get('tokenValid') is True)
bound=(isinstance(acct,dict) and acct.get('id')==account
       and acct.get('name')=='Shared Compute Neutral Authorization')
scopes=set(who.get('scopes') or []) if ok else set()
needed={'user:read','account:read','account_api_tokens:create',
        'workers:write','workers_scripts:write'}
issued=needed.issubset(scopes)
print('OAUTH_AUTHENTICATED='+str(ok).upper(),flush=True)
print('NEUTRAL_ACCOUNT_READBACK='+('PASS' if bound else 'FAIL'),flush=True)
print('ACCOUNT_API_TOKEN_CREATE_SCOPE_ISSUED='+('YES' if issued else 'NO'),flush=True)
print('ACCOUNT_API_TOKEN_CREATE_POST=NOT_ATTEMPTED',flush=True)
print('CLOUDFLARE_API_MUTATIONS=NONE',flush=True)
print('NEXT_GATE='+('BROKER_EDITOR_POLICY_AND_SECURE_ENROLLMENT' if issued and bound else 'CLOUDFLARE_OAUTH_ISSUER_GRANT_MISMATCH'),flush=True)
if not (ok and bound and issued):raise SystemExit(2)
PY
