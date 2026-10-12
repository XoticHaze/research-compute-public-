#!/bin/bash
# Neutral authorization account: broker token-provisioning capability audit.
# READ ONLY. Uses the existing cf OAuth session. Never invokes token creation.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
fail(){ echo "NEUTRAL_TOKEN_AUDIT_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail neutral_oauth_workspace_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail saved_neutral_account_id_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token_rejected
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_global_key_rejected
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_email_rejected
[[ ! -e "$CLI/.env" ]] || fail cli_dotenv_rejected
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail pinned_node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
cd "$CLI"
python3 - "$ACCOUNT" <<'PY'
import json,subprocess,sys,urllib.parse
account=sys.argv[1]
cli=['npx','--yes','cf@1.0.0-beta.14']
def call(args):
 try:
  p=subprocess.run(cli+args,capture_output=True,text=True,timeout=90)
 except Exception:
  return None,'command_exception'
 if p.returncode:
  return None,'cli_exit_nonzero'
 try:
  return json.loads(p.stdout),None
 except Exception:
  return None,'non_json_response'
def schema(command,expected_method,expected_path):
 data,error=call(['schema']+command)
 if error or not isinstance(data,dict):
  return False
 method=str(data.get('httpMethod') or data.get('method') or '').upper()
 path=str(data.get('path') or '').lstrip('/')
 return method==expected_method and path==expected_path.lstrip('/')
def preview_matches(command,target):
 # Never perform POST, even in preview mode.
 for extras in [[],['--account-id',account]]:
  data,error=call(command+extras+['--dry-run'])
  if error or not isinstance(data,dict):
   continue
  url=urllib.parse.urlsplit(str(data.get('url') or ''))
  normalized=urllib.parse.urlunsplit((url.scheme,url.netloc,url.path,'',''))
  if str(data.get('method') or '').upper()=='GET' and normalized==target:
   return extras
 return None
try:
 info,error=call(['accounts','get'])
 if error or not isinstance(info,dict) or info.get('id')!=account or info.get('name')!='Shared Compute Neutral Authorization':
  print('NEUTRAL_ACCOUNT_READBACK_FAIL=1',flush=True)
  raise SystemExit(2)
 print('NEUTRAL_ACCOUNT_READBACK_PASS=1',flush=True)
 endpoint='/accounts/{account_id}/tokens'
 ls=['accounts','tokens','list']
 create=['accounts','tokens','create']
 ls_ok=schema(ls,'GET',endpoint)
 create_ok=schema(create,'POST',endpoint)
 print('NEUTRAL_TOKEN_LIST_GET_SCHEMA='+('PASS' if ls_ok else 'UNAVAILABLE'),flush=True)
 print('NEUTRAL_TOKEN_CREATE_POST_SCHEMA='+('PRESENT_OFFLINE_ONLY' if create_ok else 'UNAVAILABLE'),flush=True)
 # A recognized POST schema documents an operation but proves NO write authority.
 print('TOKEN_CREATE_AUTHORIZATION=UNPROVEN_NO_POST',flush=True)
 if not ls_ok:
  print('TOKEN_LIST_STAGE=CLI_SCHEMA_MISSING',flush=True)
  raise SystemExit(2)
 target='https://api.cloudflare.com/client/v4/accounts/'+account+'/tokens'
 extras=preview_matches(ls,target)
 if extras is None:
  print('TOKEN_LIST_STAGE=EXACT_ACCOUNT_GET_PREVIEW_UNRESOLVED',flush=True)
  raise SystemExit(2)
 print('TOKEN_LIST_EXACT_ACCOUNT_GET_PREVIEW_PASS=1',flush=True)
 data,error=call(ls+extras)
 if error:
  print('TOKEN_LIST_STAGE=GET_API_NOT_ACCESSIBLE_OR_CLI_FAILED',flush=True)
  print('TOKEN_CREATION_PERMISSION=NOT_ESTABLISHED',flush=True)
  raise SystemExit(2)
 if isinstance(data,dict) and data.get('success') is False:
  print('TOKEN_LIST_STAGE=GET_API_DENIED',flush=True)
  print('TOKEN_CREATION_PERMISSION=NOT_ESTABLISHED',flush=True)
  raise SystemExit(2)
 tokens=data.get('result') if isinstance(data,dict) else data
 if isinstance(tokens,dict):
  tokens=tokens.get('tokens')
 if not isinstance(tokens,list):
  print('TOKEN_LIST_STAGE=UNEXPECTED_RESPONSE_SHAPE',flush=True)
  raise SystemExit(2)
 # Names only: never print token values, IDs, creators, policies or bearer material.
 count_editor=sum(isinstance(t,dict) and t.get('name')=='Reference Release Broker Editor' for t in tokens)
 count_provisioner=sum(isinstance(t,dict) and 'provision' in str(t.get('name') or '').lower() for t in tokens)
 print('NEUTRAL_TOKEN_LIST_READ_PASS=1',flush=True)
 print('NEUTRAL_TOKEN_LIST_VISIBLE_COUNT='+str(len(tokens)),flush=True)
 print('BROKER_EDITOR_NAMED_TOKEN_VISIBLE_COUNT='+str(count_editor),flush=True)
 print('PROVISIONER_NAMED_TOKEN_VISIBLE_COUNT='+str(count_provisioner),flush=True)
 if isinstance(data,dict):
  meta=data.get('result_info')
  if isinstance(meta,dict) and isinstance(meta.get('total_count'),int):
   print('NEUTRAL_TOKEN_TOTAL_COUNT='+str(meta['total_count']),flush=True)
 print('TOKEN_LIST_READ_PROVES_WRITE=NO',flush=True)
 print('NEXT_GATE=inspect_existing_provisioner_authority_and_neutral_write_scope',flush=True)
finally:
 print('BROKER_EDITOR_TOKEN_CREATED=NO',flush=True)
 print('BROKER_SIGNER_CREATED=NO',flush=True)
 print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
PY
