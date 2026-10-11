#!/bin/bash
# Read-only neutral controller preseal build. CommandCenter #809.
set -euo pipefail
BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
STAGE="$WORK/neutral-controller-preseal"
CF_DIR="$WORK/cf-cli"
PIN="5bf353c4475dc846159ecf369395862cbb9db759"
RAW="https://raw.githubusercontent.com/XoticHaze/research-compute-public-/$PIN/cloudflare"
ID="b33595eb85f346b0d1bf201810b4499a"
BROKER_ORIGIN="https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev"
AUTH="reference-maintenance-authority-v1"
MAINT="reference-release-maintainer-v1"
fail(){ echo "NEUTRAL_CONTROLLER_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -f "$WORK/cloudflare_neutral_account_id" && -d "$CF_DIR" ]] || fail saved_account_missing
[[ "$(tr -d '\r\n' < "$WORK/cloudflare_neutral_account_id")" == "$ID" ]] || fail account_id_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
[[ ! -e "$CF_DIR/.env" ]] || fail dotenv_override
NODE="$(find "$WORK/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
export PATH="$(dirname "$NODE"):$PATH"
export npm_config_cache="$WORK/npm-cache"
export NPM_CONFIG_CACHE="$WORK/npm-cache"
export CLOUDFLARE_ACCOUNT_ID="$ID"
umask 077
mkdir -p "$STAGE" "$WORK/npm-cache"
chmod 700 "$STAGE"
(
 cd "$CF_DIR"
 npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/account.json"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/inventory.json"
)
python3 - "$STAGE/account.json" "$STAGE/inventory.json" "$ID" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text())
x=json.loads(Path(sys.argv[2]).read_text())
if isinstance(x,dict): x=x.get('result')
assert isinstance(a,dict) and a.get('id')==sys.argv[3] and a.get('name')=='Shared Compute Neutral Authorization'
assert isinstance(x,list), 'invalid Worker search'
names={str(v.get('script_name') or '') for v in x if isinstance(v,dict)}
assert 'reference-release-broker-v1' in names, 'broker missing'
assert not names.intersection({'reference-maintenance-authority-v1','reference-release-maintainer-v1'}), 'controller present; reconcile'
print('NEUTRAL_ACCOUNT_AND_BROKER_VERIFIED=1')
print('NEUTRAL_CONTROLLER_NAMES_ABSENT=1')
PY
for role in "$AUTH" "$MAINT"; do
 mkdir -p "$STAGE/$role/src"
 for file in src/index.js wrangler.jsonc; do
  /usr/bin/curl -fLsS --retry 3 "$RAW/$role/$file" -o "$STAGE/$role/$file"
 done
done
python3 - "$STAGE" "$BROKER_ORIGIN" "$ID" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); origin=sys.argv[2]; account=sys.argv[3]
auth='reference-maintenance-authority-v1'
maint='reference-release-maintainer-v1'
ac=json.loads((root/auth/'wrangler.jsonc').read_text())
mc=json.loads((root/maint/'wrangler.jsonc').read_text())
for role,c,classname,bind in [(auth,ac,'AuthorityState','AUTHORITY_STATE'),(maint,mc,'MaintenanceLedger','MAINTENANCE_LEDGER')]:
 assert c['name']==role and c['main']=='src/index.js'
 assert c['workers_dev'] is False and c['preview_urls'] is False
 assert c['exports'][classname]['storage']=='sqlite'
 assert c['durable_objects']['bindings']==[{'name':bind,'class_name':classname}]
 source=(root/role/'src/index.js').read_text()
 assert 'function brokerOrigin(env)' in source and 'slenderiq.workers.dev' not in source
 assert 'BROKER_PUBLIC_ORIGIN' in source
 assert '["index.js", "intent.js", "ticket.js"]' in source
assert ac['vars']['AUTO_APPLY_ENABLED']=='0'
assert ac['triggers']['crons']==['*/15 * * * *']
assert ac['services']==[{'binding':'MAINTAINER','service':maint}]
assert mc['services']==[{'binding':'MAINTENANCE_AUTHORITY','service':auth}]
assert mc['secrets_store_secrets'][0]['binding']=='BROKER_EDITOR_TOKEN'
assert 'async scheduled(controller)' in (root/auth/'src/index.js').read_text()
assert 'async brokerState()' in (root/maint/'src/index.js').read_text()
for role in (auth,maint):
 isauth=role==auth
 klass='AuthorityState' if isauth else 'MaintenanceLedger'
 do='AUTHORITY_STATE' if isauth else 'MAINTENANCE_LEDGER'
 partner=maint if isauth else auth
 peer='MAINTAINER' if isauth else 'MAINTENANCE_AUTHORITY'
 bindings={
  do:'bindings.durableObject({worker:'+json.dumps(role)+',exportName:'+json.dumps(klass)+'})',
  peer:'bindings.worker({worker:'+json.dumps(partner)+'})',
  'BROKER_PUBLIC_ORIGIN':'bindings.text('+json.dumps(origin)+')'
 }
 if isauth:
  bindings['AUTO_APPLY_ENABLED']='bindings.text("0")'
  bindings['APPROVED_BROKER_SOURCE_SHA']='bindings.text("")'
 else:
  bindings['CLOUDFLARE_ACCOUNT_ID']='bindings.text('+json.dumps(account)+')'
 b=',\n'.join('      '+k+': '+v for k,v in sorted(bindings.items()))
 cron=',\n    triggers:[triggers.scheduled({schedule:"*/15 * * * *"})]' if isauth else ''
 text=('import {defineConfig,bindings,exports,triggers} from "cf/config";\n'
       'export default defineConfig({worker:{\n'
       '    name:'+json.dumps(role)+',\n'
       '    entrypoint:"./src/index.js",\n'
       '    compatibilityDate:"2026-09-27",\n'
       '    workersDev:false,\n    previewUrls:false,\n'
       '    exports:{'+klass+':exports.durableObject({storage:"sqlite"})},\n'
       '    env:{\n'+b+'\n    }'+cron+'\n'
       '}});\n')
 (root/role/'cloudflare.config.ts').write_text(text)
 (root/role/'package.json').write_text('{"private":true,"type":"module","name":"'+role+'"}\n')
print('NEUTRAL_CONTROLLER_SOURCE_CONTRACT_PASS=1')
print('NEUTRAL_CONTROLLER_CF_CONFIG_PASS=1')
print('AUTO_APPLY_ENABLED=0')
print('BROKER_EDITOR_TOKEN_BOUND=NO')
PY
for role in "$AUTH" "$MAINT"; do
 (
  cd "$STAGE/$role"
  npm install --no-audit --no-fund --save-dev cf@1.0.0-beta.14 wrangler@4.136.0 > "$STAGE/$role/install.log" 2>&1 || {
   tail -30 "$STAGE/$role/install.log" >&2; fail npm_install_failed;
  }
  ./node_modules/.bin/cf deploy --dry-run > "$STAGE/$role/dry-run.log" 2>&1 || {
   tail -60 "$STAGE/$role/dry-run.log" >&2; fail cf_dry_run_failed;
  }
 )
 echo "NEUTRAL_CONTROLLER_DRY_RUN_PASS=$role"
done
echo "CLOUDFLARE_MUTATIONS=NONE"
echo "NEXT_GATE=guarded_neutral_controller_preseal_deployment"
