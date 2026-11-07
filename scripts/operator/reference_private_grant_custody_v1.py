"""Create-once independent P-256 private grant signer and atomic SQLite journal.

Operator-side trusted private-node custody only. No Cloudflare mutation,
no broker key, no token, no public workflow or arbitrary signing endpoint.
The current broker signs tickets separately, inside its own Durable Object.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import sys

from scripts.reference_release_intent_v1 import generate_signer

ROOT = Path.home() / '.local/share/commandcenter/private-grant-authority-v1'
PRIVATE = 'authority-private.pkcs8.b64'
PUBLIC = 'authority-public.b64'
KEY_ID = 'authority-key-id.txt'
JOURNAL = 'grant-intent-issuance.sqlite3'


class Held(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Held(code)


def check_dir(directory):
    require(directory.is_dir() and not directory.is_symlink(),
            'PRIVATE_CUSTODY_DIRECTORY_INVALID')
    require(stat.S_IMODE(directory.stat().st_mode) & 0o077 == 0,
            'PRIVATE_CUSTODY_DIRECTORY_TOO_PUBLIC')
    require(directory.stat().st_uid == os.getuid(), 'PRIVATE_CUSTODY_UID_MISMATCH')


def _write_new(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='ascii') as stream:
        stream.write(content + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def initialize(root: Path = ROOT) -> str:
    require(not root.exists() and not root.is_symlink(),
            'PRIVATE_AUTHORITY_ALREADY_PRESENT__NO_ROTATION')
    # Fixed local custody. No caller-provided path, GitHub directory or shell.
    expected = Path.home() / '.local/share/commandcenter/private-grant-authority-v1'
    require(root == expected, 'PRIVATE_CUSTODY_PATH_NOT_ADMITTED')
    for parent in (root.parent.parent, root.parent):
        if parent.exists():
            require(not parent.is_symlink() and parent.is_dir()
                    and parent.stat().st_uid == os.getuid()
                    and stat.S_IMODE(parent.stat().st_mode) & 0o022 == 0,
                    'PRIVATE_CUSTODY_PARENT_UNTRUSTED')
        else:
            parent.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    check_dir(root)
    old = os.umask(0o077)
    try:
        private, public, key_id = generate_signer()
        _write_new(root / PRIVATE, private)
        _write_new(root / PUBLIC, public)
        _write_new(root / KEY_ID, key_id)
        with sqlite3.connect(root / JOURNAL, timeout=5) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA secure_delete=ON')
            db.execute("CREATE TABLE intent_claim("
                       "grant_id TEXT PRIMARY KEY,"
                       "payload_sha256 TEXT NOT NULL,"
                       "created_utc TEXT NOT NULL DEFAULT (datetime('now')))")
            db.commit()
        os.chmod(root / JOURNAL, 0o600)
    finally:
        os.umask(old)
    return key_id


def status(root: Path = ROOT) -> str:
    check_dir(root)
    for name in (PRIVATE, PUBLIC, KEY_ID, JOURNAL):
        file = root / name
        require(file.is_file() and not file.is_symlink()
                and stat.S_IMODE(file.stat().st_mode) & 0o077 == 0,
                'PRIVATE_AUTHORITY_FILE_UNVERIFIED')
    try:
        public = base64.b64decode((root / PUBLIC).read_text().strip(), validate=True)
        key_id = 'sha256:' + hashlib.sha256(public).hexdigest()
        require(len(public) == 65 and public[0] == 4
                and (root / KEY_ID).read_text().strip() == key_id,
                'PRIVATE_AUTHORITY_PUBLIC_KEY_ID_MISMATCH')
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        private = serialization.load_der_private_key(
            base64.b64decode((root / PRIVATE).read_text().strip(), validate=True),
            password=None)
        require(isinstance(private, ec.EllipticCurvePrivateKey)
                and isinstance(private.curve, ec.SECP256R1)
                and private.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint) == public,
                'PRIVATE_AUTHORITY_PRIVATE_PUBLIC_MISMATCH')
        with sqlite3.connect(root / JOURNAL, timeout=5) as db:
            result = db.execute("SELECT name FROM sqlite_master "
                                "WHERE type='table' AND name='intent_claim'").fetchall()
            require(len(result) == 1, 'PRIVATE_AUTHORITY_ATOMIC_JOURNAL_MISSING')
    except (ValueError, sqlite3.Error):
        raise Held('PRIVATE_AUTHORITY_CONTENT_UNVERIFIED') from None
    return key_id


class PrivateIntentSQLiteJournal:
    """Persistent create-once atomic issuer journal for approved private owner."""

    def __init__(self, root: Path = ROOT):
        status(root)
        self.path = root / JOURNAL

    def consume_once(self, *, grant_id: str, payload_sha256: str) -> bool:
        require(isinstance(grant_id, str) and 1 <= len(grant_id) <= 128
                and isinstance(payload_sha256, str) and len(payload_sha256) == 64
                and all(x in '0123456789abcdef' for x in payload_sha256),
                'JOURNAL_CLAIM_REJECTED')
        try:
            with sqlite3.connect(self.path, timeout=5, isolation_level=None) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('INSERT INTO intent_claim(grant_id,payload_sha256) '
                               'VALUES (?,?)', (grant_id, payload_sha256))
                except sqlite3.IntegrityError:
                    db.execute('ROLLBACK')
                    return False
                db.execute('COMMIT')
                return True
        except sqlite3.Error:
            raise Held('JOURNAL_DURABLE_CONSUME_UNAVAILABLE') from None


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('action', choices=('status', 'initialize'))
    args = parser.parse_args()
    if args.action == 'initialize':
        require(sys.stdin.isatty(), 'ATTENDED_PRIVATE_OWNER_REQUIRED')
        print('Independent P-256 private grant signer + local atomic journal.')
        print('Never run on a public GitHub worker or inside neutral broker.')
        print('Only if NO previous approved private grant signer exists.')
        reply = input('Type APPROVE_CREATE_ONCE_PRIVATE_GRANT_IDENTITY to continue: ').strip()
        require(reply == 'APPROVE_CREATE_ONCE_PRIVATE_GRANT_IDENTITY',
                'PRIVATE_ISSUANCE_NOT_APPROVED')
        key_id = initialize()
        print('PRIVATE_AUTHORITY_INITIALIZED=YES')
    else:
        key_id = status()
        print('PRIVATE_AUTHORITY_CUSTODY_VERIFIED=YES')
    print('PRIVATE_AUTHORITY_PUBLIC_KEY_ID=' + key_id)
    print('PRIVATE_AUTHORITY_JOURNAL=PRIVATE_ATOMIC_SQLITE')
    print('PRIVATE_AUTHORITY_CLOUDFLARE_MUTATION=NONE')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Held as exc:
        print('PRIVATE_AUTHORITY_HELD=' + str(exc), file=sys.stderr)
        raise SystemExit(2)
