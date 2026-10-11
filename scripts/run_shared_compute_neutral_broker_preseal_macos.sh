#!/bin/bash
# Canonical authority: XoticHaze/CommandCenter issue #809
# Prepare and build the preseal broker from immutable public source.
# No account creation, token creation, Worker upload/deploy, or secret writes.
set -euo pipefail

BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
CF_DIR="$WORK/cf-cli"
STAGE="$WORK/neutral-broker-preseal"
PINNED_SOURCE="b4f82f60ad90cc1e99a67c94bdf97cdf6f8cf647"
RAW="https://raw.githubusercontent.com/XoticHaze/research-compute-public-/$PINNED_SOURCE/cloudflare/reference-release-broker"
ACCOUNT_FILE="$WORK/cloudflare_neutral_account_id"

fail() { echo "NEUTRAL_BROKER_PRESEAL_FAIL=$1"; exit 2; }

[[ -d "$CF_DIR" && -f "$ACCOUNT_FILE" ]] || fail missing_existing_bootstrap
NODE_BIN="$(find "$WORK/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE_BIN" && -x "$NODE_BIN" ]] || fail node_runtime_missing
export PATH="$(dirname "$NODE_BIN"):$PATH"
export npm_config_cache="$WORK/npm-cache"
export NPM_CONFIG_CACHE="$WORK/npm-cache"

ACCOUNT_ID="$(tr -d '\r\n' < "$ACCOUNT_FILE")"
[[ "$ACCOUNT_ID" =~ ^[[:xdigit:]]{32}$ ]] || fail saved_account_id_invalid
[[ "${ACCOUNT_ID: -8}" == "10b4499a" ]] || fail unexpected_neutral_account_id
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

umask 077
mkdir -p "$STAGE/src" "$WORK/npm-cache"

# The readback uses only the neutral-account OAuth session and asserts exact
# account identity before any project is downloaded or built.
(
  cd "$CF_DIR"
  npx --yes cf@1.0.0-beta.14 accounts get > "$STAGE/account-readback.json"
  npx --yes cf@1.0.0-beta.14 workers scripts search --name reference- > "$STAGE/worker-name-search.json"
)

python3 - "$STAGE/account-readback.json" "$STAGE/worker-name-search.json" "$ACCOUNT_ID" <<'PY'
import json, sys
from pathlib import Path
account = json.loads(Path(sys.argv[1]).read_text())
workers = json.loads(Path(sys.argv[2]).read_text())
expected = sys.argv[3]
if not isinstance(account, dict) or account.get('id') != expected or account.get('name') != 'Shared Compute Neutral Authorization':
    raise SystemExit('NEUTRAL_ACCOUNT_READBACK_MISMATCH=1')
if isinstance(workers, dict):
    workers = workers.get('result')
if not isinstance(workers, list):
    raise SystemExit('NEUTRAL_WORKER_SEARCH_SHAPE_INVALID=1')
targets = {'reference-release-broker-v1', 'reference-release-maintainer-v1', 'reference-maintenance-authority-v1'}
found = {str(x.get('name') or x.get('id') or '') for x in workers if isinstance(x,dict)} & targets
if found:
    raise SystemExit('NEUTRAL_TARGET_WORKERS_ALREADY_EXIST=' + ','.join(sorted(found)))
print('NEUTRAL_ACCOUNT_ID_READBACK_PASS=1')
print('NEUTRAL_TARGET_WORKER_NAMES_ABSENT=1')
PY

# Immutable source, fully separate from existing-account Workers/Secrets Store.
for file in wrangler.jsonc src/index.js src/intent.js src/grant.js src/ticket.js; do
  /usr/bin/curl --fail --silent --show-error --location --retry 3 \
    "$RAW/$file" --output "$STAGE/$file"
done
python3 - "$STAGE/wrangler.jsonc" <<'PY'
import json, sys
from pathlib import Path
cfg=json.loads(Path(sys.argv[1]).read_text())
assert cfg['name']=='reference-release-broker-v1'
assert cfg['workers_dev'] is True and cfg['preview_urls'] is False
assert cfg['durable_objects']['bindings']==[{'name':'GRANT_LEDGER','class_name':'GrantLedger'}]
assert cfg['exports']['GrantLedger']['storage']=='sqlite'
assert 'secrets_store_secrets' not in cfg
assert 'BROKER_SIGNING_PRIVATE_JWK' not in cfg.get('vars',{})
assert 'AUTHORITY_PUBLIC_B64' not in cfg.get('vars',{})
print('BROKER_PRESEAL_SOURCE_CONTRACT_PASS=1')
PY

# Build/validate only. --dry-run performs no remote Worker upload or deploy.
(
  cd "$STAGE"
  npx --yes wrangler@4.136.0 deploy --dry-run > "$STAGE/build-readback.txt" 2>&1 || {
    tail -50 "$STAGE/build-readback.txt"
    fail wrangler_dry_run_failed
  }
)

echo "BROKER_PRESEAL_BUILD_PASS=1"
echo "SOURCE_PIN=$PINNED_SOURCE"
echo "STAGE=pfSense/tmp/neutral-broker-preseal"
echo "CLOUDFLARE_MUTATIONS=NONE"
echo "NEXT_GATE=review_and_authorize_neutral_broker_deployment"
