#!/bin/bash
# CommandCenter #809. New-account preseal controller deployment, zero new tokens.
set -euo pipefail
BASE="/Users/cr0nix/Documents/pfSense/tmp"
STAGE="$BASE/neutral-controller-preseal"
CLI="$BASE/cf-cli"
ACCOUNT="b33595eb85f346b0d1bf201810b4499a"
AUTH="reference-maintenance-authority-v1"
MAINT="reference-release-maintainer-v1"
ORIGIN="https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev"
fail(){ echo "NEUTRAL_CONTROLLER_DEPLOY_FAIL=$1" >&2; exit 2; }
[[ "$(printenv CONFIRM_NEUTRAL_CONTROLLER_DEPLOY || true)" == YES ]] || fail consent_missing
[[ -f "$BASE/cloudflare_neutral_account_id" ]] || fail saved_id_missing
[[ "$(tr -d '\r\n' < "$BASE/cloudflare_neutral_account_id")" == "$ACCOUNT" ]] || fail wrong_account
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail key_override
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail email_override
[[ ! -e "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$BASE/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -x "$NODE" ]] || fail node_not_found
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT"
export npm_config_cache="$BASE/npm-cache"
export NPM_CONFIG_CACHE="$BASE/npm-cache"
umask 077
for role in "$AUTH" "$MAINT"; do
 [[ -s "$STAGE/$role/dry-run.log" && -x "$STAGE/$role/node_modules/.bin/cf" ]] || fail missing_successful_staged_preflight
 [[ ! -e "$STAGE/$role/.env" ]] || fail dotenv_in_stage
done
(
 cd "$CLI"
 npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/account-at-deploy.json"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/inventory-at-deploy.json"
)
python3 - "$STAGE" "$ACCOUNT" "$ORIGIN" <<'PY'
import json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]); account=sys.argv[2]; origin=sys.argv[3]
a=json.loads((root/'account-at-deploy.json').read_text())
v=json.loads((root/'inventory-at-deploy.json').read_text())
if isinstance(v,dict):v=v.get('result')
assert a.get('id')==account and a.get('name')=='Shared Compute Neutral Authorization'
assert isinstance(v,list)
names={str(x.get('script_name') or '') for x in v if isinstance(x,dict)}
assert 'reference-release-broker-v1' in names
assert not names.intersection({'reference-maintenance-authority-v1','reference-release-maintainer-v1'}),'controller already exists, do not overwrite'
expected={
'reference-maintenance-authority-v1':('793f173213ee90d877d10ae4ae9951a30066ceb8','e27b150da4bf0f637a8e1d4cf2c0d2208007ea44'),
'reference-release-maintainer-v1':('33e1582534c7769ade4da2e9c118c983a74cb180','0edebd2cc40fdf6fd1db6a7a2f34a218d3f222c9')
}
for role,(src,conf) in expected.items():
 for relative,sha in [('src/index.js',src),('wrangler.jsonc',conf)]:
  digest=subprocess.check_output(['git','hash-object',str(root/role/relative)],text=True).strip()
  assert digest==sha,'staged source hash mismatch: '+role+'/'+relative
c={role:(root/role/'cloudflare.config.ts').read_text() for role in expected}
for name,text in c.items():
 assert 'workersDev:false' in text and 'previewUrls:false' in text
 assert origin in text and 'slenderiq.workers.dev' not in text
 assert 'BROKER_EDITOR_TOKEN' not in text and '95f8a1ba7b0a48d29a574790245fcd55' not in text
 assert 'bindings.durableObject(' in text and 'exports.durableObject(' in text
a=c['reference-maintenance-authority-v1']
m=c['reference-release-maintainer-v1']
needle=',\n      MAINTAINER: bindings.worker({worker:"reference-release-maintainer-v1"})'
assert a.count(needle)==1,'could not safely break circular binding'
assert 'AUTO_APPLY_ENABLED: bindings.text("0")' in a
assert 'triggers.scheduled({schedule:"*/15 * * * *"})' in a
assert 'MAINTENANCE_AUTHORITY: bindings.worker({worker:"reference-maintenance-authority-v1"})' in m
assert 'CLOUDFLARE_ACCOUNT_ID: bindings.text('+json.dumps(account)+')' in m
(root/'reference-maintenance-authority-v1'/'cloudflare.bootstrap.config.ts').write_text(a.replace(needle,''))
(root/'reference-maintenance-authority-v1'/'cloudflare.linked.config.ts').write_text(a)
print('NEUTRAL_CONTROLLER_EXACT_SOURCE_AND_ACCOUNT_PASS=1')
print('NEUTRAL_CONTROLLER_NO_EDITOR_OR_OLD_STORE_PASS=1')
print('NEUTRAL_CONTROLLER_AUTO_APPLY_OFF_PASS=1')
PY
cp "$STAGE/$AUTH/cloudflare.bootstrap.config.ts" "$STAGE/$AUTH/cloudflare.config.ts"
(
 cd "$STAGE/$AUTH"
 ./node_modules/.bin/cf deploy --dry-run > "$STAGE/$AUTH/bootstrap-dry-run.log" 2>&1 || {
   tail -50 "$STAGE/$AUTH/bootstrap-dry-run.log"; fail authority_bootstrap_build_failed;
 }
)
echo "NEUTRAL_AUTHORITY_BOOTSTRAP_DRY_RUN_PASS=1"
(
 cd "$STAGE/$AUTH"
 ./node_modules/.bin/cf deploy --message "isolated neutral authority preseal bootstrap" > "$STAGE/$AUTH/deploy-bootstrap.log" 2>&1 || {
   tail -80 "$STAGE/$AUTH/deploy-bootstrap.log"; fail authority_bootstrap_deploy_failed;
 }
)
echo "NEUTRAL_AUTHORITY_BOOTSTRAP_DEPLOY_PASS=1"
(
 cd "$STAGE/$MAINT"
 ./node_modules/.bin/cf deploy --message "isolated neutral maintainer preseal, no broker editor" > "$STAGE/$MAINT/deploy.log" 2>&1 || {
   tail -80 "$STAGE/$MAINT/deploy.log"; fail maintainer_deploy_failed;
 }
)
echo "NEUTRAL_MAINTAINER_DEPLOY_PASS=1"
cp "$STAGE/$AUTH/cloudflare.linked.config.ts" "$STAGE/$AUTH/cloudflare.config.ts"
(
 cd "$STAGE/$AUTH"
 ./node_modules/.bin/cf deploy --message "isolated neutral authority service link" > "$STAGE/$AUTH/deploy-linked.log" 2>&1 || {
   tail -80 "$STAGE/$AUTH/deploy-linked.log"; fail authority_link_deploy_failed;
 }
)
echo "NEUTRAL_AUTHORITY_LINK_DEPLOY_PASS=1"
(
 cd "$CLI"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/postdeploy-inventory.json"
)
python3 - "$STAGE/postdeploy-inventory.json" <<'PY'
import json,sys
from pathlib import Path
v=json.loads(Path(sys.argv[1]).read_text())
if isinstance(v,dict):v=v.get('result')
assert isinstance(v,list)
names={str(x.get('script_name') or '') for x in v if isinstance(x,dict)}
want={'reference-release-broker-v1','reference-maintenance-authority-v1','reference-release-maintainer-v1'}
assert want.issubset(names),'missing remote workers: '+str(sorted(want-names))
print('NEUTRAL_THREE_REMOTE_WORKER_NAMES_PASS=1')
PY
health="$(/usr/bin/curl -sS --max-time 20 -o "$STAGE/broker-post-health.txt" -w '%{http_code}' "$ORIGIN/healthz")" || fail broker_health_network
key="$(/usr/bin/curl -sS --max-time 20 -o "$STAGE/broker-post-key.txt" -w '%{http_code}' "$ORIGIN/v1/public-key")" || fail broker_public_key_network
[[ "$health" == 200 && "$key" == 503 ]] || fail broker_preseal_invariant_regression
echo "NEUTRAL_BROKER_STILL_HEALTHY_FAIL_CLOSED=1"
echo "AUTO_APPLY_ENABLED=0"
echo "BROKER_EDITOR_TOKEN_BOUND=NO"
echo "R1_SIGNED_ADOPTABLE_NON_PHI=NO"
echo "REMOTE_BINDING_DETAIL_PROOF=PENDING"
echo "NEXT_GATE=read_only_controller_remote_settings_audit"
