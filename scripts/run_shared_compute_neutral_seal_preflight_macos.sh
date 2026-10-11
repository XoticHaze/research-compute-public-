#!/bin/bash
# CommandCenter #809: neutral Secrets Store inventory, read-only.
# No store or token creation. All authenticated API calls must be exact-account GETs.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
OUT="$ROOT/neutral-seal-preflight"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
fail(){ echo "NEUTRAL_SEAL_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail neutral_session_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail saved_account_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail api_token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail api_key_override
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail api_email_override
[[ ! -e "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail pinned_node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache"
export NPM_CONFIG_CACHE="$ROOT/npm-cache"
umask 077
mkdir -p "$OUT"
chmod 700 "$OUT"
cd "$CLI"
python3 - "$OUT" "$ACCOUNT" <<'PY'
import json,subprocess,sys,urllib.parse
from pathlib import Path
out=Path(sys.argv[1]); account=sys.argv[2]
cli=['npx','--yes','cf@1.0.0-beta.14']
def call(parts):
 p=subprocess.run(cli+parts,capture_output=True,text=True,timeout=75)
 if p.returncode:
  return None,(p.stderr or p.stdout)[-350:].strip()
 try:return json.loads(p.stdout),None
 except Exception:return None,'non_json_result'
a,error=call(['accounts','get'])
if error or not isinstance(a,dict) or a.get('id')!=account or a.get('name')!='Shared Compute Neutral Authorization':
 raise SystemExit('NEUTRAL_ACCOUNT_READBACK_FAIL=1')
print('NEUTRAL_ACCOUNT_READBACK_PASS=1',flush=True)
operation=['secrets-store','stores','list']
schema,error=call(['schema']+operation)
if error:
 print('SECRETS_STORE_GET_CLI_SCHEMA_UNAVAILABLE=1',flush=True)
 print('SCHEMA_ERROR='+str(error),flush=True)
 print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
 raise SystemExit(2)
required='/accounts/{account_id}/secrets_store/stores'
if (not isinstance(schema,dict) or
 str(schema.get('httpMethod') or schema.get('method') or '').upper()!='GET' or
 str(schema.get('path') or '').lstrip('/')!=required.lstrip('/')):
 print('SECRETS_STORE_GET_CLI_SCHEMA_MISMATCH=1',flush=True)
 print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
 raise SystemExit(2)
print('SECRETS_STORE_GET_SCHEMA_PASS=1',flush=True)
target='https://api.cloudflare.com/client/v4/accounts/'+account+'/secrets_store/stores'
choice=None
for args in [[],['--account-id',account]]:
 preview,error=call(operation+args+['--dry-run'])
 if error or not isinstance(preview,dict):continue
 parsed=urllib.parse.urlsplit(str(preview.get('url') or ''))
 url=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
 if preview.get('method')=='GET' and url==target:
  choice=args
  break
if choice is None:
 print('SECRETS_STORE_GET_PREVIEW_UNRESOLVED=1',flush=True)
 print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
 raise SystemExit(2)
print('SECRETS_STORE_READ_REQUEST_PASS=1',flush=True)
node,error=call(operation+choice)
if error:
 print('SECRETS_STORE_GET_ERROR='+str(error),flush=True)
 raise SystemExit(2)
# Store metadata only. Never print secret values or bearer credentials.
(out/'neutral-store-metadata.json').write_text(json.dumps(node,indent=2)+'\n')
if isinstance(node,dict):
 if node.get('success') is False: raise SystemExit('SECRETS_STORE_GET_API_DENIED=1')
 items=node.get('result')
else:items=node
if isinstance(items,dict):items=items.get('stores')
if not isinstance(items,list):raise SystemExit('SECRETS_STORE_RESPONSE_SHAPE_UNKNOWN=1')
if len(items)>1:raise SystemExit('MULTIPLE_STORES_UNEXPECTED_IN_BETA=1')
for item in items:
 if not isinstance(item,dict):raise SystemExit('STORE_RECORD_INVALID=1')
 if item.get('account_id') and item['account_id']!=account:
  raise SystemExit('STORE_WRONG_ACCOUNT_REJECTED=1')
 if not isinstance(item.get('id'),str) or len(item['id'])!=32:
  raise SystemExit('STORE_ID_INVALID=1')
 print('NEUTRAL_STORE_NAME='+str(item.get('name') or ''),flush=True)
 print('NEUTRAL_STORE_ID='+item['id'],flush=True)
print('NEUTRAL_STORE_COUNT='+str(len(items)),flush=True)
print('SECRETS_STORE_INVENTORY_PASS=1',flush=True)
print('BROKER_EDITOR_TOKEN_CREATED=NO',flush=True)
print('BROKER_SIGNER_CREATED=NO',flush=True)
print('AUTO_APPLY_ENABLED=0',flush=True)
print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
print('NEXT_GATE='+('neutral_store_creation_guard' if not items else 'single_neutral_broker_editor_credential_guard'),flush=True)
PY
