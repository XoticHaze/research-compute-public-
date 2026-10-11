#!/bin/bash
# CommandCenter #809: create the ONLY store in the isolated neutral account.
# Guarded one-time mutation. No API tokens, Worker deployment, or secrets.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
OUT="$ROOT/neutral-seal-store-create"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
STORE_NAME="shared-compute-neutral-authorization"
fail(){ echo "NEUTRAL_STORE_CREATE_FAIL=$1" >&2; exit 2; }
[[ "$(printenv CONFIRM_NEUTRAL_STORE_CREATE || true)" == "YES" ]] || fail explicit_consent_missing
[[ -f "$ROOT/cloudflare_neutral_account_id" && -d "$CLI" ]] || fail neutral_session_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail saved_account_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail api_token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail global_key_override
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail global_email_override
[[ ! -e "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache"
export NPM_CONFIG_CACHE="$ROOT/npm-cache"
umask 077
mkdir -p "$OUT"
chmod 700 "$OUT"
cd "$CLI"
python3 - "$OUT" "$ACCOUNT" "$STORE_NAME" <<'PY'
import json,subprocess,sys,urllib.parse,re
from pathlib import Path
out=Path(sys.argv[1]); account=sys.argv[2]; store_name=sys.argv[3]
cli=['npx','--yes','cf@1.0.0-beta.14']
url='https://api.cloudflare.com/client/v4/accounts/'+account+'/secrets_store/stores'
def cf(args):
 p=subprocess.run(cli+args,text=True,capture_output=True,timeout=90)
 if p.returncode:
  return None,(p.stderr or p.stdout)[-450:].strip()
 try: return json.loads(p.stdout),None
 except Exception: return None,'invalid_json_output'
def check_schema(args,method,path):
 schema,error=cf(['schema']+args)
 if error or not isinstance(schema,dict):
  raise SystemExit('SCHEMA_UNAVAILABLE_'+args[-1]+': '+str(error))
 got_method=str(schema.get('httpMethod') or schema.get('method') or '').upper()
 got_path=str(schema.get('path') or '')
 if got_method!=method or got_path.lstrip('/')!=path.lstrip('/'):
  raise SystemExit('SCHEMA_WRONG_ROUTE_'+args[-1])
 print('STORE_'+method+'_SCHEMA_PASS=1',flush=True)
def find_preview(command,variants,method,target,body_name=None):
 for args in variants:
  preview,error=cf(command+args+['--dry-run'])
  if error or not isinstance(preview,dict):continue
  uri=urllib.parse.urlsplit(str(preview.get('url') or ''))
  clean=urllib.parse.urlunsplit((uri.scheme,uri.netloc,uri.path,'',''))
  if str(preview.get('method') or '').upper()!=method or clean!=target:continue
  if body_name is not None:
   body=preview.get('body')
   if body is None and isinstance(preview.get('request'),dict):
    body=preview['request'].get('body')
   if isinstance(body,str):
    try:body=json.loads(body)
    except Exception:continue
   if not isinstance(body,dict) or body.get('name')!=body_name:continue
  return args
 raise SystemExit('PREVIEW_UNRESOLVED_'+command[-1]+' (no write performed)')
account_info,error=cf(['accounts','get'])
if error or not isinstance(account_info,dict) or account_info.get('id')!=account or account_info.get('name')!='Shared Compute Neutral Authorization':
 raise SystemExit('NEUTRAL_ACCOUNT_READBACK_FAIL=1')
print('NEUTRAL_ACCOUNT_READBACK_PASS=1',flush=True)
list_cmd=['secrets-store','stores','list']
create_cmd=['secrets-store','stores','create']
path='/accounts/{account_id}/secrets_store/stores'
check_schema(list_cmd,'GET',path)
check_schema(create_cmd,'POST',path)
list_args=find_preview(list_cmd,[[],['--account-id',account]],'GET',url)
print('NEUTRAL_STORE_LIST_REQUEST_PASS=1',flush=True)
def list_stores():
 raw,error=cf(list_cmd+list_args)
 if error:raise SystemExit('NEUTRAL_STORE_LIST_FAILED: '+str(error))
 if isinstance(raw,dict) and raw.get('success') is False:
  raise SystemExit('NEUTRAL_STORE_LIST_API_DENIED=1')
 rows=raw.get('result') if isinstance(raw,dict) else raw
 if isinstance(rows,dict):rows=rows.get('stores')
 if not isinstance(rows,list):raise SystemExit('NEUTRAL_STORE_LIST_SHAPE_INVALID=1')
 return rows
existing=list_stores()
if existing:
 print('NEUTRAL_STORE_COUNT='+str(len(existing)),flush=True)
 print('STORE_CREATE_NOT_PERFORMED=existing_store_requires_reconciliation',flush=True)
 raise SystemExit(2)
print('NEUTRAL_STORE_COUNT_BEFORE=0',flush=True)
# Mutation target and body must BOTH match a preview exactly.
create_args=find_preview(create_cmd,
 [['--name',store_name],['--name='+store_name],[store_name]],
 'POST',url,body_name=store_name)
print('NEUTRAL_STORE_CREATE_REQUEST_DRY_RUN_PASS=1',flush=True)
# This is the sole guarded mutation. The write-only store starts empty.
print('NEUTRAL_STORE_CREATION_BEGIN=1',flush=True)
result,error=cf(create_cmd+create_args)
if error or (isinstance(result,dict) and result.get('success') is False):
 print('STORE_CREATION_RESULT_UNCERTAIN_OR_FAILED=1',flush=True)
 print('STORE_CREATION_ERROR='+str(error or 'api_error'),flush=True)
 print('NEXT_GATE=read_only_store_reconciliation',flush=True)
 raise SystemExit(2)
if isinstance(result,dict) and result.get('success') is True:result=result.get('result')
if not isinstance(result,dict) or result.get('name')!=store_name or not re.fullmatch(r'[0-9a-f]{32}',str(result.get('id') or '')):
 print('STORE_CREATE_RESPONSE_SHAPE_UNEXPECTED=1',flush=True)
 print('NEXT_GATE=read_only_store_reconciliation',flush=True)
 raise SystemExit(2)
if result.get('account_id') and result['account_id']!=account:
 raise SystemExit('STORE_CREATED_IN_WRONG_ACCOUNT_PROOF_FAILED=1')
print('NEUTRAL_STORE_CREATE_RESPONSE_PASS=1',flush=True)
after=list_stores()
if len(after)!=1 or after[0].get('id')!=result['id'] or after[0].get('name')!=store_name:
 print('NEUTRAL_STORE_READBACK_MISMATCH=1',flush=True)
 print('NEXT_GATE=read_only_store_reconciliation',flush=True)
 raise SystemExit(2)
receipt={'account_id':account,'store_id':result['id'],'store_name':store_name,'secrets_created':0}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(out/'receipt.json').chmod(0o600)
print('NEUTRAL_STORE_ID='+result['id'],flush=True)
print('NEUTRAL_STORE_COUNT_AFTER=1',flush=True)
print('NEUTRAL_STORE_REMOTE_READBACK_PASS=1',flush=True)
print('BROKER_EDITOR_TOKEN_CREATED=NO',flush=True)
print('BROKER_SIGNER_CREATED=NO',flush=True)
print('AUTO_APPLY_ENABLED=0',flush=True)
print('CLOUDFLARE_MUTATIONS=ONE_NEW_NEUTRAL_SECRETS_STORE',flush=True)
print('NEXT_GATE=broker_specific_editor_credential_scope_preflight',flush=True)
PY
