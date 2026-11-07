#!/usr/bin/env python3
"""First-seal the existing neutral Cloudflare broker with reviewed exports.

Cloudflare Durable Object class exports require an atomic wrangler deploy,
NOT an off-traffic versions upload. No new Worker, token, Secrets Store,
private grant key or broker JWK is created. The scheduled vault creates its
broker ticket key exactly once after two attended independent approvals.
Must run ONLY with the already authenticated independent neutral OAuth.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
WORKER = 'reference-release-broker-v1'
ACCOUNT = 'b33595eb85f346b0d1bf201810b4499a'
PUBLIC_BASE = 'https://reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev'
SOURCE = ROOT / 'cloudflare/reference-release-broker'
EXPECTED_FILES = {
    'src/index.js': 'eb8fa24b8fa4726bf5fd4ea50a556f5c796415ce',
    'src/intent.js': 'dccdb3f981214762db0ea6d9655f3ff7bb13eb16',
    'src/placement.js': 'ace151085666b05866407e2c0c5d55aa5d10ee11',
    'src/ticket.js': '08b37449eb5ec532c20b19506d221f4ebee49c40',
    'src/signer_vault.js': '9e37b06daf6e6deed3e0ec8100fce6904693ca3f',
    'wrangler.jsonc': '40a2450e099ab2ff2ba7f3ec4522e15c622ea8d0',
}
WORKFLOW_SHA = '477b76085c06f77fee72b57771225a66545aa43f'
UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
P256_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
P256_B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b


class Held(Exception):
    pass


def require(predicate: bool, reason: str) -> None:
    if not predicate:
        raise Held(reason)


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def exact_source() -> tuple[dict, str]:
    pieces = []
    for rel, expected in EXPECTED_FILES.items():
        f = SOURCE / rel
        require(f.is_file() and not f.is_symlink() and blob_id(f.read_bytes()) == expected,
                'MERGED_SOURCE_BLOB_NOT_EXACT')
        pieces.append(f.read_bytes())
    config = json.loads((SOURCE / 'wrangler.jsonc').read_text())
    require(config.get('name') == WORKER and config.get('workers_dev') is True
            and config.get('preview_urls') is False, 'WORKER_IDENTITY_INVALID')
    bindings = [{'name': 'GRANT_LEDGER', 'class_name': 'GrantLedger'},
                {'name': 'BROKER_SIGNER_VAULT', 'class_name': 'BrokerSignerVault'}]
    require(config.get('durable_objects', {}).get('bindings') == bindings,
            'DO_BINDING_SOURCE_DRIFT')
    exports = config.get('exports')
    require(isinstance(exports, dict) and set(exports) == {'GrantLedger', 'BrokerSignerVault'}
            and all(exports[k] == {'type': 'durable-object', 'state': 'created',
                                   'storage': 'sqlite'} for k in exports),
            'DO_EXPORTS_MUST_BE_NONDESTRUCTIVE_SQLITE')
    variables = config.get('vars', {})
    require(variables.get('BROKER_SIGNER_MODE') == 'legacy-jwk-v1'
            and variables.get('ALLOWED_JOB_WORKFLOW_SHA') == WORKFLOW_SHA
            and str(variables.get('ALLOWED_JOB_WORKFLOW_REF', '')).endswith('@'+WORKFLOW_SHA)
            and config.get('triggers', {}).get('crons') == ['*/5 * * * *'],
            'PRODUCTION_HARNESS_OR_SCHEDULE_PIN_DRIFT')
    return config, hashlib.sha256(b''.join(pieces)).hexdigest()


def authority_public(path: Path) -> tuple[str, str]:
    require(path.is_file() and not path.is_symlink(), 'AUTHORITY_PUBLIC_NOT_FOUND')
    raw = path.read_bytes()
    require(len(raw) < 256, 'AUTHORITY_PUBLIC_SIZE_REJECTED')
    try:
        value = raw.decode('ascii').strip()
        point = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError):
        raise Held('AUTHORITY_PUBLIC_INVALID') from None
    require(len(point) == 65 and point[0] == 4 and
            base64.b64encode(point).decode() == value, 'AUTHORITY_PUBLIC_INVALID')
    x, y = int.from_bytes(point[1:33], 'big'), int.from_bytes(point[33:], 'big')
    require(0 < x < P256_P and 0 < y < P256_P and
            (y*y-x*x*x+3*x-P256_B) % P256_P == 0,
            'AUTHORITY_PUBLIC_P256_POINT_INVALID')
    return value, 'sha256:' + hashlib.sha256(point).hexdigest()


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 50) -> str:
    try:
        cp = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Held('NEUTRAL_CLI_UNAVAILABLE') from None
    require(cp.returncode == 0 and len(cp.stdout) < 100000,
            'NEUTRAL_CLI_FAILED')
    return cp.stdout


def wrangler() -> str:
    require(all(not os.environ.get(k) for k in
                ('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_API_KEY', 'CLOUDFLARE_EMAIL')),
            'AMBIENT_BEARER_OVERRIDE_REFUSED')
    require(os.environ.get('CLOUDFLARE_ACCOUNT_ID') == ACCOUNT,
            'NEUTRAL_ACCOUNT_ENV_NOT_SELECTED')
    executable = shutil.which('wrangler')
    require(bool(executable), 'WRANGLER_NOT_INSTALLED_IN_AUTHENTICATED_SESSION')
    require(re.search(r'\b4\.135\.0\b', run([executable, '--version'], timeout=15)) is not None,
            'WRANGLER_VERSION_NOT_PINNED_4_135_0')
    require(ACCOUNT in run([executable, 'whoami'], timeout=35),
            'INDEPENDENT_NEUTRAL_OAUTH_UNVERIFIED')
    return executable


def deployment_status(executable: str) -> str:
    raw = run([executable, 'deployments', 'status', '--json', '--name', WORKER])
    try:
        doc = json.loads(raw)
        if isinstance(doc, dict) and isinstance(doc.get('deployment'), dict):
            doc = doc['deployment']
        versions = doc['versions']
        require(isinstance(versions, list) and len(versions) == 1,
                'NON_SINGLE_100_PERCENT_DEPLOYMENT')
        one = versions[0]
        active = str(one.get('version_id') or one.get('id') or '')
        require(UUID.fullmatch(active) is not None and float(one.get('percentage', 0)) == 100,
                'ACTIVE_VERSION_NOT_UNIQUE_100_PERCENT')
        return active
    except (TypeError, KeyError, ValueError):
        raise Held('ACTIVE_DEPLOYMENT_JSON_UNKNOWN') from None


def live_bindings(executable: str, version: str) -> dict:
    raw = run([executable, 'versions', 'view', version, '--json', '--name', WORKER])
    try:
        doc = json.loads(raw)
        for parent in (doc, doc.get('version', {}), doc.get('resources', {})):
            if isinstance(parent, dict) and isinstance(parent.get('bindings'), list):
                bindings = parent['bindings']
                require(all(isinstance(x, dict) and isinstance(x.get('name'), str)
                            for x in bindings), 'BINDINGS_MALFORMED')
                names = [x['name'] for x in bindings]
                require(len(names) == len(set(names)), 'BINDINGS_DUPLICATED')
                return {x['name']: x for x in bindings}
    except (TypeError, ValueError):
        pass
    raise Held('VERSION_BINDING_READBACK_UNAVAILABLE')


def preflight(executable: str, expected_active: str) -> tuple[str, dict]:
    active = deployment_status(executable)
    require(active == expected_active, 'ACTIVE_VERSION_RACED_OR_CHANGED')
    bindings = live_bindings(executable, active)
    ledger = bindings.get('GRANT_LEDGER')
    require(isinstance(ledger, dict) and ledger.get('class_name') == 'GrantLedger',
            'EXISTING_GRANT_LEDGER_UNATTESTED')
    require(not any(name in bindings for name in
                ('BROKER_SIGNING_PRIVATE_JWK', 'BROKER_FIRST_SEAL_APPROVAL_ID',
                 'AUTHORITY_PUBLIC_B64', 'BROKER_SIGNER_VAULT')),
            'POSSIBLE_PRIOR_SIGNER_OR_SEAL__NO_ROTATION')
    return active, ledger


def approval(what: str) -> None:
    require(sys.stdin.isatty(), 'ATTENDED_NEUTRAL_OWNER_REQUIRED')
    print('APPROVAL_REQUIRED=' + what, flush=True)
    decision = input('Type APPROVE_' + what + ' to continue: ').strip()
    require(decision == 'APPROVE_' + what, 'INDEPENDENT_APPROVAL_DENIED')


def public_proof() -> dict:
    result = {}
    for name, endpoint in [('health', '/healthz'), ('key', '/v1/public-key')]:
        try:
            req = Request(PUBLIC_BASE + endpoint,
                          headers={'User-Agent': 'cc809-first-seal-proof/1'})
            with urlopen(req, timeout=10) as response:
                result[name + '_http'] = response.status
                node = json.loads(response.read(2048))
                if name == 'key' and response.status == 200:
                    key_id = str(node.get('key_id') or '')
                    pub = str(node.get('public_b64') or '')
                    raw = base64.b64decode(pub, validate=True)
                    require(len(raw) == 65 and raw[0] == 4
                            and key_id == 'sha256:' + hashlib.sha256(raw).hexdigest(),
                            'PUBLIC_BROKER_SIGNER_INVALID')
                    result['broker_public_key_id'] = key_id
        except Held:
            raise
        except Exception:
            result[name + '_http'] = 'UNAVAILABLE'
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('source', 'inspect', 'deploy', 'verify'))
    parser.add_argument('--expected-active-version')
    parser.add_argument('--authority-public-file', type=Path)
    args = parser.parse_args()
    config, package_sha = exact_source()
    print('CC809_SOURCE_BLOBS=VERIFIED', flush=True)
    print('CC809_PINNED_PACKAGE_SHA256=' + package_sha, flush=True)
    print('CC809_EXPORTS_LIFECYCLE=REQUIRES_ATOMIC_WRANGLER_DEPLOY', flush=True)
    if args.operation == 'source':
        return 0
    binary = wrangler()
    if args.operation == 'verify':
        active = deployment_status(binary)
        evidence = public_proof()
        print('CC809_CURRENT_LIVE_VERSION=' + active)
        for k, value in evidence.items():
            print('CC809_' + k.upper() + '=' + str(value))
        return 0 if (evidence.get('health_http') == 200
                     and evidence.get('key_http') == 200) else 2
    require(args.expected_active_version and UUID.fullmatch(args.expected_active_version)
            is not None, 'EXACT_OBSERVED_ACTIVE_VERSION_REQUIRED')
    active, ledger = preflight(binary, args.expected_active_version)
    print('CC809_NEUTRAL_ACTIVE_VERSION=' + active)
    print('CC809_BASELINE_GRANT_LEDGER=OBSERVED')
    if args.operation == 'inspect':
        print('CC809_CLOUDFLARE_MUTATION=NONE')
        print('CC809_CREDENTIAL_NEUTRAL_WRITE_DENY=REQUIRES_INDEPENDENT_REVIEW')
        return 0
    require(args.authority_public_file is not None,
            'INDEPENDENT_AUTHORITY_PUBLIC_FILE_REQUIRED')
    public, key_id = authority_public(args.authority_public_file)
    print('CC809_AUTHORITY_PUBLIC_KEY_ID=' + key_id)
    # Attended attestations are NOT cryptographic proof of private key custody
    # or original credential mutation DENY; those require independent owner review.
    approval('GITHUB_CREDENTIALS_NEUTRAL_WRITE_DENIED_AND_PRIVATE_SIGNER_CUSTODY_VERIFIED')
    approval('ONE_TIME_P256_VAULT_ISSUANCE_AND_IMMEDIATE_100_PERCENT_DEPLOY')
    with tempfile.TemporaryDirectory(prefix='cc809-neutral-first-seal-') as temp:
        root = Path(temp)
        root.chmod(0o700)
        shutil.copytree(SOURCE / 'src', root / 'src', symlinks=False)
        config['vars']['BROKER_SIGNER_MODE'] = 'vault-v1'
        config_file = root / 'wrangler.jsonc'
        config_file.write_text(json.dumps(config, indent=2) + '\n')
        approval_id = 'cc809-' + secrets.token_hex(16)
        expires = int(time.time()) + 1800
        secret_file = root / 'first-issue-secrets.json'
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'AUTHORITY_PUBLIC_B64': public,
                       'BROKER_FIRST_SEAL_APPROVAL_ID': approval_id,
                       'BROKER_FIRST_SEAL_APPROVAL_NOT_AFTER': str(expires)}, f)
        dry = run([binary, 'deploy', '--strict', '--dry-run',
                   '--config', str(config_file)], cwd=root, timeout=90)
        require(bool(dry.strip()), 'WRANGLER_DRYRUN_NO_BUILD')
        require(deployment_status(binary) == active,
                'ACTIVE_VERSION_CHANGED_DURING_DRYRUN')
        print('CC809_DRYRUN=PASS')
        # Real 100% atomic deployment. This lifecycle change CANNOT roll
        # back to the old class set; forward-only recovery if it fails.
        try:
            deployed = subprocess.run(
                [binary, 'deploy', '--strict', '--secrets-file', str(secret_file),
                 '--config', str(config_file)],
                cwd=root, timeout=180, check=False, capture_output=True, text=True)
        except (OSError, subprocess.TimeoutExpired):
            raise Held('DEPLOY_RESULT_AMBIGUOUS__READBACK_REQUIRED') from None
        require(deployed.returncode == 0,
                'DEPLOY_RESULT_AMBIGUOUS__READBACK_REQUIRED')
        current = deployment_status(binary)
        require(current != active, 'NO_NEW_VERSION_DEPLOYED')
        bindings = live_bindings(binary, current)
        require(bindings.get('GRANT_LEDGER') == ledger,
                'POSTDEPLOY_GRANT_LEDGER_IDENTITY_CHANGED__NO_AUTOROLLBACK')
        require('BROKER_SIGNER_VAULT' in bindings
                and 'AUTHORITY_PUBLIC_B64' in bindings,
                'POSTDEPLOY_VAULT_OR_AUTHORITY_BINDING_MISSING')
        print('CC809_DEPLOYMENT_APPLIED=YES')
        print('CC809_EFFECTIVE_VERSION=' + current)
        print('CC809_ORIGINAL_GRANT_LEDGER_PRESERVED=YES')
        print('CC809_INITIAL_SEAL_APPROVAL_EXPIRES_UTC='
              + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(expires)))
        # Cron propagation may take up to 15m. Wait in this attended process,
        # no unobserved background task or claim of later success.
        deadline = min(time.monotonic() + 1080,
                       time.monotonic() + max(0, expires - int(time.time()) - 60))
        while True:
            evidence = public_proof()
            if evidence.get('health_http') == 200 and evidence.get('key_http') == 200:
                for k, value in evidence.items():
                    print('CC809_' + k.upper() + '=' + str(value))
                require(deployment_status(binary) == current,
                        'CONCURRENT_CLOUDFLARE_DEPLOYMENT_DURING_SEAL')
                print('CC809_BROKER_FIRST_SEAL=LIVE_SIGNING_KEY_READY')
                return 0
            if time.monotonic() >= deadline:
                for k, value in evidence.items():
                    print('CC809_' + k.upper() + '=' + str(value))
                print('CC809_BROKER_FIRST_SEAL=NO_PUBLIC_KEY_READINESS__REVIEW_REQUIRED')
                return 3
            time.sleep(20)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Held as exc:
        print('CC809_FIRST_SEAL_HELD=' + str(exc), file=sys.stderr)
        raise SystemExit(2)
