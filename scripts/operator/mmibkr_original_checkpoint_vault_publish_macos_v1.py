#!/usr/bin/env python3
"""Explicitly approved ciphertext-only publication through existing public Source Vault.

Preflight (default) is offline and readonly. Publish is deliberately gated
by a merged owning public PR, an explicit local approval marker, existing
GitHub CLI authentication, and a nonforce source-vault branch push.
No plaintext, broker interaction, Gateway, Pi, or protected master-key access.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile

RUN = '39499524894'
FILENAME = 'MMIBKR_LIVE_RUNTIME_CHECKPOINT_RUN39499524894.zip'
ZIP_SHA = '13029f3f99fb4023e34540a34ad162ca9b165cd669b24066ac5672dfcc72f8ad'
ZIP_BYTES = 33571275
CIPHER_SHA = '7fa732e25dbb9044ba66c8fb9e3f7da4e269434ee7b2708d635f58c7d914bc66'
CIPHER_BYTES = 33560349
REPO = 'XoticHaze/mm-ibkr-runtime'
BRANCH = 'mmibkr-source-vault'
DEST = 'checkpoint-vault/run39499524894'
MERGED_PR = '2077'
CONSENT = 'MMIBKR_P0_ORIGINAL_CHECKPOINT_PUBLIC_ENCRYPTED_APPROVED'
PROTECTED_MANIFEST_SECRET = 'MMIBKR_ORIGINAL_CHECKPOINT_39499524894_MANIFEST_B64'
PROTECTED_CONSUMER_REPO = 'XoticHaze/research-compute-public-'


def cmd(*args: str, cwd: Path | None = None) -> str:
    cp = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=False)
    if cp.returncode:
        raise RuntimeError('git_or_gh_operation_failed_' + str(cp.returncode))
    return cp.stdout.strip()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_exact_archive(archive: Path) -> tuple[bytes, bytes]:
    st = archive.lstat()
    if archive.name != FILENAME or not stat.S_ISREG(st.st_mode) or st.st_size != ZIP_BYTES:
        raise ValueError('original_archive_file_identity_mismatch')
    with archive.open('rb') as fh:
        digest = hashlib.sha256()
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != ZIP_SHA:
        raise ValueError('original_archive_sha_mismatch')
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if sorted(i.filename for i in infos) != ['checkpoint.enc', 'manifest.json']:
            raise ValueError('historical_archive_members_invalid')
        if any(i.is_dir() or (i.external_attr >> 16) & 0o170000 not in (0, stat.S_IFREG) for i in infos):
            raise ValueError('historical_archive_member_type_invalid')
        if zf.getinfo('checkpoint.enc').file_size != CIPHER_BYTES or zf.getinfo('manifest.json').file_size > 8192:
            raise ValueError('historical_archive_inner_sizes_invalid')
        ciphertext = zf.read('checkpoint.enc')
        manifest = zf.read('manifest.json')
    if len(ciphertext) != CIPHER_BYTES or sha(ciphertext) != CIPHER_SHA:
        raise ValueError('historical_ciphertext_identity_mismatch')
    node = json.loads(manifest)
    ctx = node.get('context') if isinstance(node, dict) else None
    if not isinstance(ctx, dict) or ctx.get('run_id') != RUN or ctx.get('source_sha') != '46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b':
        raise ValueError('original_checkpoint_context_mismatch')
    if node.get('ciphertext_sha256') != CIPHER_SHA:
        raise ValueError('original_checkpoint_inner_manifest_mismatch')
    # The original archive SHA independently pins these exact manifest bytes;
    # the existing AES-GCM unseal codec validates the original plaintext hash.
    embedded_sha = node.get('archive_sha256')
    if not isinstance(embedded_sha, str) or len(embedded_sha) != 64 or any(ch not in '0123456789abcdef' for ch in embedded_sha):
        raise ValueError('original_checkpoint_plaintext_digest_field_invalid')
    return ciphertext, manifest


def publish(ciphertext: bytes, manifest: bytes) -> None:
    if os.environ.get(CONSENT) != 'YES_AFTER_SECURITY_REVIEW':
        raise RuntimeError('public_encrypted_ciphertext_operator_approval_missing')
    if cmd('gh', 'pr', 'view', MERGED_PR, '--repo', 'XoticHaze/research-compute-public-',
           '--json', 'mergedAt', '--jq', '.mergedAt != null') != 'true':
        raise RuntimeError('checkpoint_consumer_pr_not_merged')
    # The original manifest contains the digest of private decrypted data.
    # Seal it to the protected Actions secret via authenticated gh stdin.
    # Never publish it in public Git, argv, logs, or source-vault artifacts.
    encoded = base64.b64encode(manifest).decode('ascii')
    cp = subprocess.run(
        ['gh', 'secret', 'set', PROTECTED_MANIFEST_SECRET, '--repo', PROTECTED_CONSUMER_REPO],
        input=encoded, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError('historical_manifest_protected_secret_registration_failed')
    with tempfile.TemporaryDirectory(prefix='mmibkr-original-ciphertext-vault-') as tmp:
        root = Path(tmp)
        repo = root / 'repository'
        cmd('gh', 'repo', 'clone', REPO, str(repo), '--', '--branch', BRANCH,
            '--depth', '1', '--filter=blob:none', '--no-checkout')
        cmd('git', 'sparse-checkout', 'init', '--cone', cwd=repo)
        cmd('git', 'sparse-checkout', 'set', DEST, cwd=repo)
        cmd('git', 'checkout', BRANCH, cwd=repo)
        if cmd('git', 'branch', '--show-current', cwd=repo) != BRANCH:
            raise RuntimeError('source_vault_branch_identity_invalid')
        target = repo / DEST
        if target.exists() or target.is_symlink():
            raise RuntimeError('immutable_checkpoint_vault_target_already_exists')
        target.mkdir(parents=True)
        (target / 'checkpoint.enc').write_bytes(ciphertext)
        cmd('git', 'add', '--', DEST, cwd=repo)
        staged = cmd('git', 'diff', '--cached', '--name-only', cwd=repo).splitlines()
        if sorted(staged) != [DEST + '/checkpoint.enc']:
            raise RuntimeError('unexpected_staged_file_set')
        cmd('git', 'commit', '-m', 'admit exact owner-reviewed encrypted historical checkpoint 39499524894 (no plaintext)', cwd=repo)
        cmd('git', 'push', 'origin', 'HEAD:refs/heads/' + BRANCH, cwd=repo)
    print('MMIBKR_ORIGINAL_CHECKPOINT_CIPHERTEXT_ONLY_PUBLIC_PUBLISHED=1')
    print('MMIBKR_HISTORICAL_MANIFEST_PUBLIC_PUBLISHED=0; MASTER_KEY_PUBLISHED=0; PLAINTEXT_PUBLISHED=0; BROKER_AND_PI_MUTATIONS=0')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--publish-after-approved-review', action='store_true')
    args = ap.parse_args()
    ciphertext, manifest = verify_exact_archive(args.archive)
    print('MMIBKR_ORIGINAL_CHECKPOINT_EXACT_ARCHIVE_AND_CIPHERTEXT=VERIFIED')
    if args.publish_after_approved_review:
        publish(ciphertext, manifest)
    else:
        print('MMIBKR_ENCRYPTED_VAULT_UPLOAD=NOT_REQUESTED')
        print('MMIBKR_ORIGINAL_CHECKPOINT_SECURITY_REVIEW_AND_PR_MERGE_REQUIRED=1')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('MMIBKR_VAULT_INTAKE=HOLD:' + type(exc).__name__)
        raise SystemExit(2)
