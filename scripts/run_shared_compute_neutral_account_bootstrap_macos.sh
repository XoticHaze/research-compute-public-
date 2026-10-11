#!/bin/bash
# Canonical authority: XoticHaze/CommandCenter@8981323ba8294b5d721c673a19411bfc73054816
set -euo pipefail

BASE="/Users/cr0nix/Documents/pfSense"
WORK="$BASE/tmp"
REPORT="$WORK/currentreport.txt"
RUNTIME="$WORK/runtime"
CF_WORK="$WORK/cf-cli"
NPM_CACHE="$WORK/npm-cache"
NODE_RELEASE_BASE="https://nodejs.org/download/release/latest-v22.x"

mkdir -p "$WORK" "$RUNTIME" "$CF_WORK" "$NPM_CACHE"
chmod 700 "$WORK" "$RUNTIME" "$CF_WORK" "$NPM_CACHE" 2>/dev/null || true
rm -f "$REPORT"

log() { printf '%s\n' "$*" | tee -a "$REPORT"; }

version_ge_22_18() {
  python3 - "$1" <<'PY'
import re,sys
m=re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)",sys.argv[1].strip())
raise SystemExit(0 if m and tuple(map(int,m.groups())) >= (22,18,0) else 1)
PY
}

NODE_CMD=""
if command -v node >/dev/null 2>&1; then
  SYS_NODE_VERSION="$(node --version 2>/dev/null || true)"
  if [[ -n "$SYS_NODE_VERSION" ]] && version_ge_22_18 "$SYS_NODE_VERSION"; then
    NODE_CMD="$(command -v node)"
    log "NODE_SOURCE=system"
    log "NODE_VERSION=$SYS_NODE_VERSION"
  fi
fi

if [[ -z "$NODE_CMD" ]]; then
  case "$(uname -m)" in
    arm64) NODE_ARCH="arm64" ;;
    x86_64) NODE_ARCH="x64" ;;
    *)
      log "NODE_BOOTSTRAP_FAIL=unsupported_macos_arch_$(uname -m)"
      exit 2
      ;;
  esac

  SHAS="$RUNTIME/SHASUMS256.txt"
  /usr/bin/curl --fail --silent --show-error --location     "$NODE_RELEASE_BASE/SHASUMS256.txt" --output "$SHAS"

  NODE_FILE="$(awk -v suffix="darwin-$NODE_ARCH.tar.gz" '$2 ~ suffix"$" {print $2; exit}' "$SHAS")"
  NODE_SHA="$(awk -v file="$NODE_FILE" '$2 == file {print $1; exit}' "$SHAS")"

  if [[ -z "$NODE_FILE" || -z "$NODE_SHA" ]]; then
    log "NODE_BOOTSTRAP_FAIL=release_manifest_missing_macos_artifact"
    exit 2
  fi

  NODE_VERSION="$(printf '%s' "$NODE_FILE" | sed -E 's/^node-(v[^-]+)-darwin-.*$/\1/')"
  NODE_DIR="$RUNTIME/node-$NODE_VERSION-darwin-$NODE_ARCH"
  NODE_TGZ="$RUNTIME/$NODE_FILE"

  if [[ ! -x "$NODE_DIR/bin/node" ]]; then
    rm -rf "$NODE_DIR" "$NODE_TGZ"
    /usr/bin/curl --fail --silent --show-error --location       "$NODE_RELEASE_BASE/$NODE_FILE" --output "$NODE_TGZ"

    ACTUAL_SHA="$(/usr/bin/shasum -a 256 "$NODE_TGZ" | awk '{print $1}')"
    if [[ "$ACTUAL_SHA" != "$NODE_SHA" ]]; then
      rm -f "$NODE_TGZ"
      log "NODE_BOOTSTRAP_FAIL=sha256_mismatch"
      exit 2
    fi

    /usr/bin/tar -xzf "$NODE_TGZ" -C "$RUNTIME"
    rm -f "$NODE_TGZ"
  fi

  NODE_CMD="$NODE_DIR/bin/node"
  export PATH="$NODE_DIR/bin:$PATH"

  log "NODE_SOURCE=pfSense/tmp/runtime"
  log "NODE_VERSION=$("$NODE_CMD" --version)"
  log "NODE_SHA256_VERIFIED=1"
fi

export npm_config_cache="$NPM_CACHE"
export NPM_CONFIG_CACHE="$NPM_CACHE"

cd "$CF_WORK"
CF=(npx --yes cf@latest)

CF_VERSION="$("${CF[@]}" --version 2>&1 | tr '\n' ' ')"
log "CF_VERSION=$CF_VERSION"

AUTH_PROBE="$WORK/cf-auth-probe.txt"
rm -f "$AUTH_PROBE"

if "${CF[@]}" accounts list --per-page 1 >"$AUTH_PROBE" 2>&1; then
  log "CF_API_AUTH_STATE=READY"
else
  log "CF_API_AUTH_STATE=REAUTH_REQUIRED"
  printf '%s\n' "Cloudflare CLI has no usable API token. A browser window will open for OAuth approval."
  "${CF[@]}" auth login --force
  if ! "${CF[@]}" accounts list --per-page 1 >"$AUTH_PROBE" 2>&1; then
    log "CF_API_AUTH_STATE=FAILED_AFTER_LOGIN"
    sed -n '1,40p' "$AUTH_PROBE" | tee -a "$REPORT"
    rm -f "$AUTH_PROBE"
    exit 2
  fi
  log "CF_OAUTH_LOGIN_PASS=1"
  log "CF_API_AUTH_STATE=READY_AFTER_LOGIN"
fi
rm -f "$AUTH_PROBE"

TARGET_ACCOUNT_NAME="Shared Compute Neutral Authorization"
TARGET_ACCOUNT_FILE="$WORK/cloudflare_neutral_account_id"
IDEMPOTENCY_KEY="commandcenter-shared-compute-neutral-authorization-v1"
LIST_JSON="$WORK/cf-neutral-account-list.json"
CREATE_JSON="$WORK/cf-neutral-account-create.json"

rm -f "$LIST_JSON" "$CREATE_JSON"

parse_exact_account() {
  python3 - "$1" "$TARGET_ACCOUNT_NAME" <<'PY'
import json,sys
p,name=sys.argv[1],sys.argv[2]
with open(p,encoding="utf-8") as fh:
    data=json.load(fh)
if isinstance(data,dict) and "result" in data:
    data=data.get("result")
if isinstance(data,dict):
    items=[data]
elif isinstance(data,list):
    items=data
else:
    items=[]
matches=[x for x in items if isinstance(x,dict) and x.get("name")==name]
valid=[str(x.get("id") or "") for x in matches if len(str(x.get("id") or ""))==32]
print(len(matches), valid[0] if len(matches)==1 and len(valid)==1 else "")
PY
}

"${CF[@]}" accounts list --name "$TARGET_ACCOUNT_NAME" > "$LIST_JSON"
read -r MATCH_COUNT NEUTRAL_ACCOUNT_ID < <(parse_exact_account "$LIST_JSON")

if [[ "$MATCH_COUNT" -gt 1 ]]; then
  log "NEUTRAL_ACCOUNT_CREATE_FAIL=duplicate_exact_name"
  exit 2
fi

if [[ "$MATCH_COUNT" -eq 1 ]]; then
  if [[ ! "$NEUTRAL_ACCOUNT_ID" =~ ^[0-9a-fA-F]{32}$ ]]; then
    log "NEUTRAL_ACCOUNT_CREATE_FAIL=existing_account_id_invalid"
    exit 2
  fi
  log "NEUTRAL_ACCOUNT_STATE=EXISTING"
else
  log "NEUTRAL_ACCOUNT_CREATE_DRY_RUN_BEGIN"
  "${CF[@]}" accounts create \
    --name "$TARGET_ACCOUNT_NAME" \
    --standalone \
    --idempotency-key "$IDEMPOTENCY_KEY" \
    --dry-run | tee -a "$REPORT"
  log "NEUTRAL_ACCOUNT_CREATE_DRY_RUN_PASS=1"

  # The idempotency key intentionally remains fixed across retries. If a prior
  # run already created the account but list propagation lagged, Cloudflare
  # replays the same create result instead of creating a duplicate.
  "${CF[@]}" accounts create \
    --name "$TARGET_ACCOUNT_NAME" \
    --standalone \
    --idempotency-key "$IDEMPOTENCY_KEY" > "$CREATE_JSON"

  read -r CREATE_MATCH_COUNT CREATE_ACCOUNT_ID < <(parse_exact_account "$CREATE_JSON")
  if [[ "$CREATE_MATCH_COUNT" -ne 1 || ! "$CREATE_ACCOUNT_ID" =~ ^[0-9a-fA-F]{32}$ ]]; then
    log "NEUTRAL_ACCOUNT_CREATE_FAIL=create_response_missing_exact_account"
    exit 2
  fi

  NEUTRAL_ACCOUNT_ID="$CREATE_ACCOUNT_ID"
  log "NEUTRAL_ACCOUNT_CREATE_RESPONSE_PASS=1"

  # Account listing can lag immediately after successful creation. Retry for
  # discovery, but do not discard the authoritative create response.
  DISCOVERY_PASS=0
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    "${CF[@]}" accounts list --name "$TARGET_ACCOUNT_NAME" > "$LIST_JSON"
    read -r MATCH_COUNT DISCOVERED_ACCOUNT_ID < <(parse_exact_account "$LIST_JSON")
    if [[ "$MATCH_COUNT" -gt 1 ]]; then
      log "NEUTRAL_ACCOUNT_CREATE_FAIL=duplicate_exact_name_after_create"
      exit 2
    fi
    if [[ "$MATCH_COUNT" -eq 1 && "$DISCOVERED_ACCOUNT_ID" == "$NEUTRAL_ACCOUNT_ID" ]]; then
      DISCOVERY_PASS=1
      break
    fi
  done

  if [[ "$DISCOVERY_PASS" -eq 1 ]]; then
    log "NEUTRAL_ACCOUNT_POST_CREATE_DISCOVERY_PASS=1"
  else
    log "NEUTRAL_ACCOUNT_POST_CREATE_DISCOVERY_PENDING=1"
  fi
  log "NEUTRAL_ACCOUNT_STATE=CREATED"
fi

umask 077
printf '%s\n' "$NEUTRAL_ACCOUNT_ID" > "$TARGET_ACCOUNT_FILE"
chmod 600 "$TARGET_ACCOUNT_FILE"

rm -f "$LIST_JSON" "$CREATE_JSON"

log "NEUTRAL_ACCOUNT_NAME=$TARGET_ACCOUNT_NAME"
log "NEUTRAL_ACCOUNT_ID_SUFFIX=${NEUTRAL_ACCOUNT_ID: -8}"
log "NEUTRAL_ACCOUNT_ID_FILE=pfSense/tmp/cloudflare_neutral_account_id"
log "NEUTRAL_ACCOUNT_CREATE_OR_REUSE_PASS=1"
log "NEXT_GATE=neutral_account_worker_deployment_bootstrap"

log "RUN_COMPLETE=1"
log "REPORT=$REPORT"
