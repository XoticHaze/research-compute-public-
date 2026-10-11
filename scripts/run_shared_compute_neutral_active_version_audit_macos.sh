#!/bin/bash
# CommandCenter #809. Read-only attestation of deployed neutral controller versions.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
OUT="$ROOT/neutral-active-version-audit"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
fail(){ echo "NEUTRAL_ACTIVE_VERSION_AUDIT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" && -f "$ROOT/cloudflare_neutral_account_id" ]] || fail saved_account_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail wrong_account_id
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_email
[[ ! -e "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
umask 077
mkdir -p "$OUT"
chmod 700 "$OUT"
cd "$CLI"
python3 - "$OUT" "$ACCOUNT" <<'PY'
import json,subprocess,sys,urllib.parse,re
from pathlib import Path
out=Path(sys.argv[1]); account=sys.argv[2]
base='https://api.cloudflare.com/client/v4/accounts/'+account
roles=['reference-maintenance-authority-v1','reference-release-maintainer-v1']
def invoke(parts):
 p=subprocess.run(['npx','--yes','cf@1.0.0-beta.14']+parts,capture_output=True,text=True,timeout=75)
 if p.returncode: return None,p.stderr.strip()[-350:]
 try:return json.loads(p.stdout),None
 except Exception:return None,'non_json_stdout'
a,error=invoke(['accounts','get'])
if error or not isinstance(a,dict) or a.get('id')!=account or a.get('name')!='Shared Compute Neutral Authorization':
 raise SystemExit('NEUTRAL_ACCOUNT_READBACK_FAIL=1')
print('NEUTRAL_ACCOUNT_READBACK_PASS=1',flush=True)
def checked_read(cmd,role,suffix,extra):
 target=base+suffix
 candidates=[
  ['--worker',role]+extra,
  ['--script-name',role]+extra,
  ['--worker-id',role]+extra,
  [role]+extra,
 ]
 preview_paths=[]
 chosen=None
 for args in candidates:
  preview,err=invoke(cmd+args+['--dry-run'])
  if err or not isinstance(preview,dict):continue
  method=str(preview.get('method') or '').upper()
  link=str(preview.get('url') or '')
  parsed=urllib.parse.urlsplit(link)
  actual=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
  if method=='GET' and actual==target:
   chosen=args;break
  preview_paths.append((method,parsed.path))
 if chosen is None:
  print('READ_PREVIEW_UNRESOLVED='+role+'_'+cmd[-1],flush=True)
  print('EXPECTED_PATH='+suffix,flush=True)
  print('NONMATCHING_REQUESTS='+repr(preview_paths[:4]),flush=True)
  raise SystemExit('NEUTRAL_GET_COMMAND_BINDING_UNRESOLVED=1')
 print('NEUTRAL_GET_REQUEST_PREVIEW_PASS='+role+'_'+cmd[-1],flush=True)
 data,error=invoke(cmd+chosen)
 if error:raise SystemExit('NEUTRAL_GET_FAILED='+role+'_'+cmd[-1]+': '+str(error))
 (out/(role+'-'+cmd[-1]+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 if isinstance(data,dict) and data.get('success') is True and 'result' in data:
  return data['result']
 return data
def require(ok,tag,role):
 print(tag+'='+('PASS' if ok else 'FAIL'),flush=True)
 if not ok:raise SystemExit('REMOTE_ACTIVE_BINDING_CHECK_FAILED='+role)
for role in roles:
 deployments=checked_read(['workers','deployments','list'],role,
  '/workers/scripts/'+role+'/deployments',[])
 if isinstance(deployments,dict):deployments=deployments.get('deployments')
 if not isinstance(deployments,list) or not deployments:
  raise SystemExit('ACTIVE_DEPLOYMENT_SHAPE_INVALID='+role)
 current=deployments[0]
 active=current.get('versions') if isinstance(current,dict) else None
 if not isinstance(active,list) or len(active)!=1 or float(active[0].get('percentage') or -1)!=100:
  raise SystemExit('ACTIVE_DEPLOYMENT_NOT_SINGLE_100_PERCENT='+role)
 version=str(active[0].get('version_id') or '')
 if not re.fullmatch(r'[A-Za-z0-9-]{36}',version):
  raise SystemExit('ACTIVE_VERSION_ID_INVALID='+role)
 print('ACTIVE_DEPLOYMENT_READBACK_PASS='+role,flush=True)
 detail=checked_read(['workers','versions','get'],role,
  '/workers/workers/'+role+'/versions/'+version,['--version-id',version])
 if not isinstance(detail,dict):
  raise SystemExit('DEPLOYED_VERSION_SHAPE_INVALID='+role)
 if str(detail.get('id') or '')!=version:
  raise SystemExit('DEPLOYED_VERSION_ID_MISMATCH='+role)
 rows=detail.get('bindings')
 if rows is None:rows=(detail.get('resources') or {}).get('bindings')
 if not isinstance(rows,list):
  print('DEPLOYED_VERSION_TOP_KEYS='+repr(sorted(detail.keys())),flush=True)
  raise SystemExit('BINDINGS_NOT_IN_VERSION_RESPONSE='+role)
 b={str(x.get('name')):x for x in rows if isinstance(x,dict) and x.get('name')}
 print('REMOTE_BINDING_NAMES_'+role+'='+','.join(sorted(b)),flush=True)
 require('BROKER_EDITOR_TOKEN' not in b,'BROKER_EDITOR_ABSENT_'+role,role)
 require('BROKER_SIGNING_PRIVATE_JWK' not in b,'BROKER_SIGNER_ABSENT_'+role,role)
 origin=b.get('BROKER_PUBLIC_ORIGIN') or {}
 require(origin.get('type') in ('plain_text','text') and
  (origin.get('text') or origin.get('value'))=='https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev',
  'NEUTRAL_BROKER_ORIGIN_'+role,role)
 if role==roles[0]:
  peer='MAINTAINER';partner=roles[1];dobind='AUTHORITY_STATE';klass='AuthorityState'
 else:
  peer='MAINTENANCE_AUTHORITY';partner=roles[0];dobind='MAINTENANCE_LEDGER';klass='MaintenanceLedger'
 p=b.get(peer) or {}
 require(p.get('type')=='service' and (p.get('service') or p.get('service_name'))==partner,
  'SERVICE_TARGET_'+role,role)
 d=b.get(dobind) or {}
 require(d.get('type') in ('durable_object_namespace','durable_object') and
  d.get('class_name')==klass,'DURABLE_OBJECT_CLASS_'+role,role)
 if role==roles[0]:
  flag=b.get('AUTO_APPLY_ENABLED') or {}
  require((flag.get('text') or flag.get('value'))=='0','AUTO_APPLY_DISABLED',role)
 else:
  aid=b.get('CLOUDFLARE_ACCOUNT_ID') or {}
  require((aid.get('text') or aid.get('value'))==account,'MAINTAINER_ACCOUNT_BOUND',role)
 print('REMOTE_ACTIVE_VERSION_BINDINGS_PASS='+role,flush=True)
print('REMOTE_ACTIVE_VERSION_BINDINGS_AUDIT_PASS=1',flush=True)
print('REMOTE_WORKERS_DEV_AND_CRON=AUDIT_STILL_PENDING',flush=True)
print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
print('NEXT_GATE=remote_ingress_cron_evidence_then_isolated_secret_provisioning',flush=True)
PY
