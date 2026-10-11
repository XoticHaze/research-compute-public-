# Canonical authority: XoticHaze/CommandCenter@8a51860bf3e73e343773a6806624ff75ab75ccf3
#!/bin/bash
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

if "${CF[@]}" auth whoami >/dev/null 2>&1; then
  log "CF_OAUTH_SESSION=EXISTING"
else
  log "CF_OAUTH_SESSION=LOGIN_REQUIRED"
  printf '%s\n' "A browser window will open for one-time Cloudflare CLI OAuth approval."
  "${CF[@]}" auth login
  "${CF[@]}" auth whoami >/dev/null
  log "CF_OAUTH_LOGIN_PASS=1"
fi

log "CF_ACCOUNT_CREATE_DISCOVERY_BEGIN"
"${CF[@]}" cli search "create a standalone Free account named Shared Compute Neutral Authorization" | tee -a "$REPORT"
log "CF_ACCOUNT_CREATE_DISCOVERY_END"

log "RUN_COMPLETE=1"
log "REPORT=$REPORT"
