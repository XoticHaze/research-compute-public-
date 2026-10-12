#!/bin/bash
# Read-only account-bound Worker ID and token permission-group discovery.
# No token creation, no secrets, no token list, no Cloudflare writes.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
fail(){ echo "NEUTRAL_EDITOR_MAPPING_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail account_workspace_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail account_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail key_override
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail email_override
[[ ! -f "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
cd "$CLI"
python3 - "$ACCOUNT" <<'PY'
import json,re,subprocess,sys,urllib.parse
account=sys.argv[1]
cli=['npx','--yes','cf@1.0.0-beta.14']
def cf(args):
 try:p=subprocess.run(cli+args,capture_output=True,text=True,timeout=90)
 except Exception:return None,'CLI_SPAWN_OR_TIMEOUT'
 if p.returncode:
  raw=(p.stderr or '')+' '+(p.stdout or '')
  found=re.search(r'(?i)\b(?:HTTP\s+)?(401|403|404|429|500|502|503)\b',raw)
  return None,'HTTP_'+found.group(1) if found else 'CLI_NONZERO'
 try:return json.loads(p.stdout),None
 except ValueError:return None,'NOT_JSON'
def validated_get(op,path):
 s,error=cf(['schema']+op)
 if error or not isinstance(s,dict) or str(s.get('httpMethod')).upper()!='GET' or str(s.get('path'))!=path:
  return 'GET_SCHEMA_MISMATCH'
 p,error=cf(op+['--dry-run'])
 if error or not isinstance(p,dict):return 'GET_DRYRUN_INVALID'
 u=urllib.parse.urlsplit(str(p.get('url') or ''))
 clean=urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,'',''))
 expect='https://api.cloudflare.com/client/v4'+path.replace('{account_id}',account)
 if p.get('method')!='GET' or clean!=expect:return 'GET_TARGET_MISMATCH'
 return None
def array(node):
 x=node.get('result') if isinstance(node,dict) else node
 if isinstance(x,dict):
  for k in ('items','workers','permission_groups','data','result'):
   if isinstance(x.get(k),list):return x[k]
 return x if isinstance(x,list) else None
print('ACCOUNT_ID_MATCHED_LOCAL=1',flush=True)
who,error=cf(['accounts','get'])
if error or not isinstance(who,dict) or who.get('id')!=account or who.get('name')!='Shared Compute Neutral Authorization':
 print('NEUTRAL_REMOTE_ACCOUNT_READBACK=FAILED',flush=True)
 raise SystemExit(2)
print('NEUTRAL_REMOTE_ACCOUNT_READBACK=PASS',flush=True)
worker_op=['workers','list']
stage=validated_get(worker_op,'/accounts/{account_id}/workers/workers')
if stage:
 print('WORKERS_LIST_GET='+stage,flush=True)
else:
 result,error=cf(worker_op)
 if error:print('WORKERS_LIST_GET='+error,flush=True)
 else:
  rows=array(result)
  if not isinstance(rows,list):
   print('WORKERS_LIST_SHAPE=UNKNOWN',flush=True)
  else:
   matches=[x for x in rows if isinstance(x,dict) and
            (x.get('name')=='reference-release-broker-v1' or x.get('script_name')=='reference-release-broker-v1')]
   print('BROKER_WORKER_MATCH_COUNT='+str(len(matches)),flush=True)
   if len(matches)==1:
    candidate=str(matches[0].get('id') or matches[0].get('worker_id') or '')
    if re.fullmatch(r'[0-9a-f]{32}',candidate):
     print('BROKER_IMMUTABLE_WORKER_ID_CANDIDATE='+candidate,flush=True)
    else:
     print('BROKER_IMMUTABLE_WORKER_ID_CANDIDATE=NOT_PRESENT_AS_HEX32',flush=True)
group_op=['accounts','tokens','permission-groups','list']
stage=validated_get(group_op,'/accounts/{account_id}/tokens/permission_groups')
if stage:
 print('EDITOR_GROUP_LIST_GET='+stage,flush=True)
else:
 result,error=cf(group_op)
 if error:print('EDITOR_GROUP_LIST_GET='+error,flush=True)
 else:
  rows=array(result)
  if not isinstance(rows,list):print('EDITOR_PERMISSION_GROUP_RESPONSE_SHAPE=UNKNOWN',flush=True)
  else:
   matches=[x for x in rows if isinstance(x,dict) and
            'worker' in str(x.get('name') or '').lower() and
            'editor' in str(x.get('name') or '').lower() and x.get('is_selectable') is True]
   print('SELECTABLE_WORKERS_EDITOR_GROUP_CANDIDATE_COUNT='+str(len(matches)),flush=True)
   if len(matches)==1 and re.fullmatch(r'[0-9a-f]{32}',str(matches[0].get('id') or '')):
    print('WORKERS_EDITOR_PERMISSION_GROUP_ID_CANDIDATE='+matches[0]['id'],flush=True)
    print('WORKERS_EDITOR_GROUP_SCOPE_NAMES='+','.join(map(str,matches[0].get('scopes') or [])),flush=True)
   else:print('WORKERS_EDITOR_PERMISSION_GROUP_ID_CANDIDATE=UNRESOLVED',flush=True)
print('TOKEN_CREATION=NOT_ATTEMPTED',flush=True)
print('OAUTH_SCOPE_CHANGE=NONE',flush=True)
print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
print('NEXT_GATE=confirm_exact_worker_resource_and_role_before_any_credential_create',flush=True)
PY
