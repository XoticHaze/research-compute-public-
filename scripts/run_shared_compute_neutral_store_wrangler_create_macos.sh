#!/bin/bash
# CommandCenter #809: create exactly one neutral account Secrets Store.
# Official Wrangler remote store create (cf beta API command missing).
# Reuses current Wrangler OAuth if present. Never creates API tokens.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
STAGE="$ROOT/neutral-store-wrangler-create"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
NAME="shared-compute-neutral-authorization"
fail(){ echo "NEUTRAL_STORE_WRANGLER_FAIL=$1" >&2; exit 2; }
[[ "$(printenv CONFIRM_NEUTRAL_STORE_CREATE || true)" == "YES" ]] || fail explicit_consent_required
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail neutral_session_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail saved_account_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_email
[[ ! -e "$CLI/.env" ]] || fail cli_dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
WRANGLER="$ROOT/neutral-controller-preseal/reference-maintenance-authority-v1/node_modules/.bin/wrangler"
[[ -x "$WRANGLER" ]] || fail pinned_wrangler_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
umask 077
mkdir -p "$STAGE"
chmod 700 "$STAGE"
[[ ! -e "$STAGE/.env" && ! -e "$STAGE/.dev.vars" && ! -e "$STAGE/wrangler.jsonc" ]] || fail unsafe_stage_configuration
# Isolated directory deliberately has no wrangler Worker config.
cd "$STAGE"
python3 - "$CLI" "$ACCOUNT" "$NAME" "$WRANGLER" "$STAGE" <<'PY'
import json,os,re,subprocess,sys
from pathlib import Path
cli_dir=Path(sys.argv[1]); account=sys.argv[2]; name=sys.argv[3]
wrangler=sys.argv[4]; stage=Path(sys.argv[5])
cli=['npx','--yes','cf@1.0.0-beta.14']
def cf(args):
 p=subprocess.run(cli+args,capture_output=True,text=True,cwd=str(cli_dir),timeout=90)
 if p.returncode:
  raise SystemExit('CF_ACCOUNT_READ_FAIL: '+(p.stderr or p.stdout)[-300:].strip())
 try:return json.loads(p.stdout)
 except Exception:raise SystemExit('CF_JSON_RESPONSE_INVALID=1')
a=cf(['accounts','get'])
assert isinstance(a,dict) and a.get('id')==account and a.get('name')=='Shared Compute Neutral Authorization','wrong Cloudflare account'
print('NEUTRAL_ACCOUNT_READBACK_PASS=1',flush=True)
schema=cf(['schema','secrets-store','stores','list'])
assert schema.get('httpMethod')=='GET' and schema.get('path')=='/accounts/{account_id}/secrets_store/stores','GET inventory schema mismatch'
def inventory():
 rows=cf(['secrets-store','stores','list'])
 if isinstance(rows,dict):rows=rows.get('result')
 if isinstance(rows,dict):rows=rows.get('stores')
 assert isinstance(rows,list),'unexpected store listing shape'
 return rows
before=inventory()
print('NEUTRAL_STORE_COUNT_BEFORE='+str(len(before)),flush=True)
if before:
 print('STORE_CREATE_NOT_PERFORMED=existing_store_reconciliation_required',flush=True)
 raise SystemExit(2)
version=subprocess.run([wrangler,'--version'],capture_output=True,text=True,cwd=str(stage),timeout=60)
if version.returncode or '4.136.0' not in (version.stdout+version.stderr):
 raise SystemExit('PINNED_WRANGLER_VERSION_MISMATCH=1')
help_=subprocess.run([wrangler,'secrets-store','store','create','--help'],capture_output=True,text=True,cwd=str(stage),timeout=60)
if help_.returncode or '--remote' not in (help_.stdout+help_.stderr):
 raise SystemExit('WRANGLER_REMOTE_STORE_CREATE_UNAVAILABLE=1')
print('WRANGLER_STORE_CREATE_CONTRACT_PASS=1',flush=True)
# User has explicitly approved this single account-local mutation. Wrangler
# may require its own OAuth login; cf and wrangler do not share auth sessions.
cmd=[wrangler,'secrets-store','store','create',name,'--remote']
print('NEUTRAL_STORE_REMOTE_CREATION_BEGIN=1',flush=True)
created=subprocess.run(cmd,capture_output=True,text=True,cwd=str(stage),timeout=180)
(stage/'wrangler-store-create.log').write_text(created.stdout+'\n'+created.stderr)
(stage/'wrangler-store-create.log').chmod(0o600)
if created.returncode:
 print('WRANGLER_STORE_CREATE_RETURN_CODE='+str(created.returncode),flush=True)
 print('NEXT_GATE=read_only_neutral_store_reconciliation',flush=True)
 # Avoid uploading logs. They can include account information or diagnostics.
 raise SystemExit(2)
print('WRANGLER_STORE_CREATE_COMMAND_PASS=1',flush=True)
after=inventory()
if len(after)!=1 or not isinstance(after[0],dict) or after[0].get('name')!=name:
 print('NEUTRAL_STORE_REMOTE_READBACK_FAILED=1',flush=True)
 print('NEXT_GATE=read_only_neutral_store_reconciliation',flush=True)
 raise SystemExit(2)
store=after[0]
assert re.fullmatch(r'[0-9a-f]{32}',str(store.get('id') or '')),'store ID invalid'
if store.get('account_id') and store['account_id']!=account:
 raise SystemExit('STORE_ACCOUNT_READBACK_MISMATCH=1')
receipt={'account_id':account,'store_id':store['id'],'store_name':name,'token_created':False,'signer_created':False}
(stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(stage/'receipt.json').chmod(0o600)
print('NEUTRAL_STORE_COUNT_AFTER=1',flush=True)
print('NEUTRAL_STORE_REMOTE_READBACK_PASS=1',flush=True)
print('NEUTRAL_STORE_ID='+store['id'],flush=True)
print('BROKER_EDITOR_TOKEN_CREATED=NO',flush=True)
print('BROKER_SIGNER_CREATED=NO',flush=True)
print('CLOUDFLARE_MUTATIONS=ONE_NEW_NEUTRAL_SECRETS_STORE',flush=True)
print('NEXT_GATE=broker_scoped_maintenance_editor_token',flush=True)
PY
