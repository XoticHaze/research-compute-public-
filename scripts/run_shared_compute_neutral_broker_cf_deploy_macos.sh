#!/bin/bash
# Shared Compute neutral broker cf-stage v1. Authority: CommandCenter #809.
# No existing-account changes. PRESEAL only; no signer/secret creation.
set -euo pipefail
BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
CF_DIR="$WORK/cf-cli"
STAGE="$WORK/neutral-broker-cf-deploy"
PIN="b4f82f60ad90cc1e99a67c94bdf97cdf6f8cf647"
RAW="https://raw.githubusercontent.com/XoticHaze/research-compute-public-/$PIN/cloudflare/reference-release-broker"
MODE=preflight
if [[ $# -gt 0 ]]; then MODE="$1"; fi
fail(){ echo "NEUTRAL_BROKER_CF_FAIL=$1" >&2; exit 2; }
case "$MODE" in
  preflight) ;;
  deploy) [[ "$(printenv CONFIRM_NEUTRAL_PRESEAL_DEPLOY || true)" == YES ]] || fail deploy_confirmation_missing ;;
  *) fail unsupported_mode ;;
esac
[[ -f "$WORK/cloudflare_neutral_account_id" && -d "$CF_DIR" ]] || fail saved_account_missing
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_api_token
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_api_key
[[ -z "$(printenv CLOUDFLARE_EMAIL || true)" ]] || fail ambient_api_email
NODE="$(find "$WORK/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail node_missing
export PATH="$(dirname "$NODE"):$PATH"
export npm_config_cache="$WORK/npm-cache"
export NPM_CONFIG_CACHE="$WORK/npm-cache"
ACCOUNT_ID="$(tr -d '\r\n' < "$WORK/cloudflare_neutral_account_id")"
[[ "$ACCOUNT_ID" == "b33595eb85f346b0d1bf201810b4499a" ]] || fail neutral_id_mismatch
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"
umask 077
mkdir -p "$STAGE/src" "$WORK/npm-cache"
chmod 700 "$STAGE"
[[ ! -e "$STAGE/.env" && ! -e "$CF_DIR/.env" ]] || fail dotenv_credential_override
echo "NEUTRAL_BROKER_MODE=$MODE"
(
 cd "$CF_DIR"
 npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/account.json"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/search.json"
)
python3 - "$STAGE/account.json" "$STAGE/search.json" "$ACCOUNT_ID" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text())
x=json.loads(Path(sys.argv[2]).read_text())
assert isinstance(a,dict) and a.get('id')==sys.argv[3] and a.get('name')=='Shared Compute Neutral Authorization', 'wrong Cloudflare account'
if isinstance(x,dict): x=x.get('result')
assert isinstance(x,list), 'Worker search unrecognized'
names={str(v.get('name') or v.get('id') or '') for v in x if isinstance(v,dict)}
targets={'reference-release-broker-v1','reference-release-maintainer-v1','reference-maintenance-authority-v1'}
assert not names.intersection(targets), 'target Worker already present'
print('NEUTRAL_ACCOUNT_READBACK_PASS=1')
print('NEUTRAL_WORKER_COLLISION_GUARD_PASS=1')
PY
for file in wrangler.jsonc src/index.js src/intent.js src/grant.js src/ticket.js; do
  /usr/bin/curl -fLsS --retry 3 "$RAW/$file" -o "$STAGE/$file"
done
python3 - "$STAGE/wrangler.jsonc" "$STAGE/cloudflare.config.ts" <<'PY'
import json,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
assert set(c)=={'$schema','name','main','compatibility_date','workers_dev','preview_urls','keep_vars','durable_objects','exports','vars'}
assert (c['name'],c['main'],c['compatibility_date'])==('reference-release-broker-v1','src/index.js','2026-09-25')
assert c['workers_dev'] is True and c['preview_urls'] is False and c['keep_vars'] is False
assert c['durable_objects']['bindings']==[{'name':'GRANT_LEDGER','class_name':'GrantLedger'}]
assert c['exports']=={'GrantLedger':{'type':'durable-object','state':'created','storage':'sqlite'}}
assert set(c['vars'])=={'ALLOWED_JOB_WORKFLOW_REF','ALLOWED_JOB_WORKFLOW_SHA','MAX_ADMISSION_SECONDS','MAX_INTENT_SECONDS'}
assert c['vars']['ALLOWED_JOB_WORKFLOW_SHA']=='477b76085c06f77fee72b57771225a66545aa43f'
assert all(isinstance(v,str) for v in c['vars'].values())
v=',\n'.join('      '+k+': bindings.text('+json.dumps(s)+')' for k,s in sorted(c['vars'].items()))
source='''import {defineConfig, bindings, exports} from "cf/config";
export default defineConfig({
  worker: {
    name: "reference-release-broker-v1",
    entrypoint: "./src/index.js",
    compatibilityDate: "2026-09-25",
    workersDev: true,
    previewUrls: false,
    exports: {GrantLedger: exports.durableObject({storage: "sqlite"})},
    env: {
      GRANT_LEDGER: bindings.durableObject({
        worker: "reference-release-broker-v1",
        exportName: "GrantLedger"
      }),
'''+v+'''
    }
  }
});
'''
Path(sys.argv[2]).write_text(source)
print('NEUTRAL_BROKER_CF_CONFIG_EQUIVALENCE_PASS=1')
PY
cat > "$STAGE/package.json" <<'JSON'
{"private":true,"type":"module","name":"neutral-broker-preseal-transport"}
JSON
(
 cd "$STAGE"
 npm install --no-audit --no-fund --save-dev cf@1.0.0-beta.14 wrangler@4.136.0 > "$STAGE/npm-install.log" 2>&1 || {
   tail -30 "$STAGE/npm-install.log" >&2; fail npm_install_failed;
 }
 ./node_modules/.bin/cf deploy --dry-run > "$STAGE/cf-build.log" 2>&1 || {
   tail -70 "$STAGE/cf-build.log" >&2; fail cf_build_failed;
 }
)
echo "NEUTRAL_BROKER_CF_DRY_RUN_PASS=1"
if [[ "$MODE" == preflight ]]; then
  echo "CLOUDFLARE_MUTATIONS=NONE"
  echo "NEXT_GATE=isolated_broker_live_deployment"
  exit 0
fi
(
 cd "$STAGE"
 ./node_modules/.bin/cf deploy --message "isolated neutral broker preseal pinned source" \
   > "$STAGE/cf-deploy.log" 2>&1 || {
   tail -70 "$STAGE/cf-deploy.log" >&2; fail cf_deploy_failed;
 }
)
echo "NEUTRAL_BROKER_DEPLOY_COMMAND_PASS=1"
(
 cd "$CF_DIR"
 npx --yes cf@1.0.0-beta.14 workers scripts search --name reference-release-broker-v1 > "$STAGE/postsearch.json"
)
python3 - "$STAGE/postsearch.json" <<'PY'
import json,sys
from pathlib import Path
v=json.loads(Path(sys.argv[1]).read_text())
if isinstance(v,dict): v=v.get('result')
assert isinstance(v,list), 'invalid search response'
assert any((r.get('name') or r.get('id'))=='reference-release-broker-v1' for r in v if isinstance(r,dict)), 'broker missing after deployment'
print('NEUTRAL_BROKER_REMOTE_READBACK_PASS=1')
PY
echo "BROKER_SIGNER_CONFIGURED=NO"
echo "BROKER_SENSITIVE_AUTHORITY_CONFIGURED=NO"
echo "R1_SIGNED_ADOPTABLE_NON_PHI=NO"
echo "NEXT_GATE=broker_preseal_health_and_fail_closed_checks"
