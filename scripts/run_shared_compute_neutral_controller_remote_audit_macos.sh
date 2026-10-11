#!/bin/bash
# CommandCenter #809. Remote settings audit only: no mutation or secrets output.
set -euo pipefail
BASE="/Users/cr0nix/Documents/pfSense/tmp"
CF="$BASE/cf-cli"
STAGE="$BASE/neutral-controller-remote-audit"
ID="b33595eb85f346b0d1bf201810b4499a"
fail(){ echo "NEUTRAL_CONTROLLER_AUDIT_FAIL=$1" >&2; exit 2; }
[[ -d "$CF" && -f "$BASE/cloudflare_neutral_account_id" ]] || fail bootstrap_missing
[[ "$(tr -d '\r\n' < "$BASE/cloudflare_neutral_account_id")" == "$ID" ]] || fail account_id_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_global_key
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_email
[[ ! -e "$CF/.env" ]] || fail dotenv_override
NODE="$(find "$BASE/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail portable_node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ID"
export npm_config_cache="$BASE/npm-cache"
export NPM_CONFIG_CACHE="$BASE/npm-cache"
umask 077
mkdir -p "$STAGE"
chmod 700 "$STAGE"
cd "$CF"
npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/account.json"
npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/search.json"
python3 - "$STAGE" "$ID" <<'PY'
import json,subprocess,sys,shlex
from pathlib import Path
root=Path(sys.argv[1])
account_id=sys.argv[2]
a=json.loads((root/'account.json').read_text())
v=json.loads((root/'search.json').read_text())
if isinstance(v,dict):v=v.get('result')
assert isinstance(a,dict) and a.get('id')==account_id and a.get('name')=='Shared Compute Neutral Authorization','wrong neutral account'
assert isinstance(v,list),'inventory malformed'
names={x.get('script_name') for x in v if isinstance(x,dict)}
broker='reference-release-broker-v1'
auth='reference-maintenance-authority-v1'
maint='reference-release-maintainer-v1'
assert {broker,auth,maint}.issubset(names),'all three Workers not present'
print('NEUTRAL_ACCOUNT_AND_THREE_WORKERS_PASS=1',flush=True)
prefix=['npx','--yes','cf@1.0.0-beta.14']
def cf(args):
 p=subprocess.run(prefix+args,capture_output=True,text=True,timeout=75,check=False)
 if p.returncode:
  raise RuntimeError('cf read command failed: '+' '.join(args)+': '+p.stderr[-700:])
 try:return json.loads(p.stdout)
 except Exception as e:raise RuntimeError('non-JSON cf output: '+' '.join(args)+': '+str(e))
methods={
 'settings':('/accounts/{account_id}/workers/scripts/{script_name}/settings','get Worker script and version settings bindings'),
 'subdomain':('/accounts/{account_id}/workers/scripts/{script_name}/subdomain','get Worker script subdomain settings'),
 'schedules':('/accounts/{account_id}/workers/scripts/{script_name}/schedules','get Worker script schedules cron triggers')
}
commands={}
for key,(expected,description) in methods.items():
 matches=cf(['cli','search',description])
 assert isinstance(matches,list), 'cf cli search returned invalid shape'
 found=None
 for match in matches:
  if not isinstance(match,dict):continue
  candidate=match.get('command')
  if not isinstance(candidate,str):continue
  parts=shlex.split(candidate)
  if parts and parts[0]=='cf':parts=parts[1:]
  if not parts or any(x.startswith('-') for x in parts):continue
  try:
   meta=cf(['schema']+parts)
  except Exception:
   continue
  method=str(meta.get('httpMethod') or meta.get('http_method') or '').upper()
  path=str(meta.get('path') or '')
  if method=='GET' and path.lstrip('/')==expected.lstrip('/'):
   found=parts
   break
 assert found, 'read-only cf command not discovered for '+key+'; use cf cli search and cf schema, do not create tokens'
 commands[key]=found
 print('NEUTRAL_READ_COMMAND_SCHEMA_PASS='+key,flush=True)
def get(key,role):
 args=commands[key]+['--script-name',role]
 obj=cf(args)
 if isinstance(obj,dict) and obj.get('success') is True and 'result' in obj:
  obj=obj['result']
 assert isinstance(obj,dict),key+' readback shape invalid'
 # Retain protected local evidence, never print raw setting values or secrets.
 (root/(key+'-'+role+'.json')).write_text(json.dumps(obj,indent=2)+'\n')
 return obj
records={role:get('settings',role) for role in (auth,maint)}
def require(ok,label):
 print(label+'='+('PASS' if ok else 'FAIL'),flush=True)
 if not ok:raise AssertionError(label)
expected_origin='https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev'
for role,item in records.items():
 rows=item.get('bindings')
 require(isinstance(rows,list),'BINDING_SHAPE_'+role)
 b={x.get('name'):x for x in rows if isinstance(x,dict) and x.get('name')}
 print('REMOTE_BINDING_NAMES_'+role+'='+','.join(sorted(b)),flush=True)
 require('BROKER_EDITOR_TOKEN' not in b,'BROKER_EDITOR_ABSENT_'+role)
 require('BROKER_SIGNING_PRIVATE_JWK' not in b,'BROKER_SIGNER_ABSENT_'+role)
 bind=b.get('BROKER_PUBLIC_ORIGIN',{})
 require(bind.get('type') in ('plain_text','text') and (bind.get('text') or bind.get('value'))==expected_origin,'NEUTRAL_BROKER_ORIGIN_'+role)
 if role==auth:
  peer='MAINTAINER'; target=maint; do='AUTHORITY_STATE'; classname='AuthorityState'
 else:
  peer='MAINTENANCE_AUTHORITY'; target=auth; do='MAINTENANCE_LEDGER'; classname='MaintenanceLedger'
 p=b.get(peer,{})
 require(p.get('type')=='service' and p.get('service')==target,'PRIVATE_SERVICE_'+role)
 d=b.get(do,{})
 require(d.get('type') in ('durable_object_namespace','durable_object') and d.get('class_name')==classname,'DURABLE_OBJECT_BINDING_'+role)
 exports=item.get('exports')
 if isinstance(exports,dict) and classname in exports:
  require(exports[classname].get('storage')=='sqlite','SQLITE_EXPORT_'+role)
 else:
  print('SQLITE_EXPORT_'+role+'=NOT_RETURNED_BY_SETTINGS',flush=True)
 if role==auth:
  auto=b.get('AUTO_APPLY_ENABLED',{})
  require(auto.get('type') in ('plain_text','text') and (auto.get('text') or auto.get('value'))=='0','AUTO_APPLY_DISABLED')
 else:
  aid=b.get('CLOUDFLARE_ACCOUNT_ID',{})
  require(aid.get('type') in ('plain_text','text') and (aid.get('text') or aid.get('value'))==account_id,'MAINTAINER_TARGET_ACCOUNT')
for role in (broker,auth,maint):
 sub=get('subdomain',role)
 desired=role==broker
 require(sub.get('enabled') is desired,'WORKERS_DEV_EXPOSURE_'+role)
 require(sub.get('previews_enabled') is False,'PREVIEW_URLS_DISABLED_'+role)
for role in (auth,maint):
 cron=get('schedules',role)
 data=cron.get('schedules')
 require(isinstance(data,list),'CRON_SHAPE_'+role)
 rules=[x.get('cron') for x in data if isinstance(x,dict)]
 require(rules==(['*/15 * * * *'] if role==auth else []),'CRON_POLICY_'+role)
print('NEUTRAL_CONTROLLER_REMOTE_BINDINGS_AUDIT_PASS=1',flush=True)
print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
print('BROKER_EDITOR_TOKEN_PROVISIONED=NO',flush=True)
print('NEXT_GATE=isolated_maintenance_secret_store_and_broker_signer_provisioning',flush=True)
PY
