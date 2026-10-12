#!/bin/bash
# Read-only check of existing factory bootstrap and narrow cf OAuth capability.
# No credential values retrieved. No OAuth login initiated. No cloud mutations.
set -euo pipefail
ROOT="/Users/cr0nix/Documents/pfSense/tmp"
CLI="$ROOT/cf-cli"
ORIGINAL="ce43cd7b917d98a4bb4866d30eed99c0"
NEUTRAL="b33595eb85f346b0d1bf201810b4499a"
KEYCHAIN_SERVICE="Shared Compute Token Provisioner TEMP"
fail(){ echo "NEUTRAL_BOOTSTRAP_PREFLIGHT_FAIL=$1" >&2; exit 2; }
[[ -d "$CLI" ]] || fail cf_workspace_missing
[[ -f "$ROOT/cloudflare_account_id" ]] || fail original_id_file_missing
[[ -f "$ROOT/cloudflare_neutral_account_id" ]] || fail neutral_id_file_missing
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_account_id")" == "$ORIGINAL" ]] || fail original_account_id_mismatch
[[ "$(tr -d '\r\n' < "$ROOT/cloudflare_neutral_account_id")" == "$NEUTRAL" ]] || fail neutral_account_id_mismatch
[[ -z "$(printenv CLOUDFLARE_API_TOKEN || true)" ]] || fail ambient_token_override
[[ -z "$(printenv CLOUDFLARE_API_KEY || true)" ]] || fail ambient_key_override
[[ ! -e "$CLI/.env" ]] || fail dotenv_override
NODE="$(find "$ROOT/runtime" -type f -path '*/bin/node' -print -quit)"
[[ -n "$NODE" && -x "$NODE" ]] || fail portable_node_missing
export PATH="$(dirname "$NODE"):$PATH"
export CLOUDFLARE_ACCOUNT_ID="$NEUTRAL"
export npm_config_cache="$ROOT/npm-cache" NPM_CONFIG_CACHE="$ROOT/npm-cache"
cd "$CLI"
python3 - "$ORIGINAL" "$NEUTRAL" "$KEYCHAIN_SERVICE" <<'PY'
import getpass,json,re,subprocess,sys
original, neutral, service = sys.argv[1:]
cli=['npx','--yes','cf@1.0.0-beta.14']
def run(cmd):
 try:
  return subprocess.run(cmd,capture_output=True,text=True,timeout=70)
 except Exception:
  return None
print('ACCOUNT_SEPARATION_ANCHORS_PASS=1',flush=True)
# Do not use -w, -g, or read passwords. This is metadata existence ONLY.
kc=run(['/usr/bin/security','find-generic-password','-a',getpass.getuser(),'-s',service])
print('ORIGINAL_TEMP_KEYCHAIN_METADATA='+('PRESENT' if kc and kc.returncode==0 else 'NOT_FOUND_OR_INACCESSIBLE'),flush=True)
help_result=run(cli+['auth','login','--help'])
help_text=(help_result.stdout+' '+help_result.stderr) if help_result else ''
print('CF_AUTH_LOGIN_HELP_PASS='+str(bool(help_result and help_result.returncode==0)).lower(),flush=True)
print('CF_EXPLICIT_SCOPES_OPTION='+('SUPPORTED' if re.search(r'--scopes\b',help_text) else 'NOT_FOUND'),flush=True)
print('CF_FORCE_LOGIN_OPTION='+('SUPPORTED' if re.search(r'--force\b',help_text) else 'NOT_FOUND'),flush=True)
print('CF_NO_BROWSER_OPTION='+('SUPPORTED' if re.search(r'--no-browser\b',help_text) else 'NOT_FOUND'),flush=True)
schema=run(cli+['schema','accounts','tokens','create'])
valid=False
if schema and schema.returncode==0:
 try:
  node=json.loads(schema.stdout)
  valid=(str(node.get('httpMethod') or node.get('method') or '').upper()=='POST'
         and str(node.get('path') or '').lstrip('/')=='accounts/{account_id}/tokens')
 except ValueError: pass
print('NEUTRAL_TOKEN_CREATE_POST_SCHEMA='+('PASS_OFFLINE_ONLY' if valid else 'UNAVAILABLE'),flush=True)
account=run(cli+['accounts','get'])
ok=False
if account and account.returncode==0:
 try:
  node=json.loads(account.stdout)
  ok=(node.get('id')==neutral and node.get('name')=='Shared Compute Neutral Authorization')
 except (ValueError,AttributeError):pass
print('CF_NEUTRAL_ACCOUNT_READBACK='+('PASS' if ok else 'FAILED'),flush=True)
if ok and valid and re.search(r'--scopes\b',help_text):
 print('NEXT_GATE=isolated_explicit_scope_OAuth_bootstrap',flush=True)
else:
 print('NEXT_GATE=repair_exact_offline_CLI_preflight',flush=True)
print('NEUTRAL_TOKEN_CREATION_PERMISSION=UNPROVEN',flush=True)
print('ACCOUNT_TOKEN_CREATED=NO',flush=True)
print('KEYCHAIN_SECRET_READ=NO',flush=True)
print('CLOUDFLARE_MUTATIONS=NONE',flush=True)
if not(ok and valid and re.search(r'--scopes\b',help_text)):
 raise SystemExit(2)
PY
