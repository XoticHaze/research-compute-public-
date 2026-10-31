#!/usr/bin/env python3
"""Recipient-only quarantine capsule for bot_data from authenticated original checkpoint.

Operates only on authenticated plaintext passed in memory by the existing codec.
Never publishes master key, tar plaintext, historical Gateway, or order rights.
Not a Pi installer or runtime admission mechanism.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = 'mmibkr.original_checkpoint_botdata_quarantine_x25519.v1'
INFO = b'mmibkr-original-checkpoint-botdata-quarantine-r1'
MAX_RAW = 512 * 1024 * 1024
MAX_FILE_MEMBERS = 250000
MAX_CAPSULE = 200 * 1024 * 1024
EXPECTED_PRODUCER = '39499524894'
EXPECTED_HISTORICAL_SOURCE = '46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b'
EXPECTED_SELECTED_SOURCE = '45339615b1a8b27a5e34233f9cb849c0ae6ecab8'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_botdata_tar(authenticated_plaintext: bytes) -> tuple[bytes, int]:
    if not authenticated_plaintext or len(authenticated_plaintext) > MAX_RAW:
        raise ValueError('authenticated_checkpoint_size_invalid')
    target = io.BytesIO()
    written = 0
    total = 0
    seen_paths: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(authenticated_plaintext), mode='r:gz') as source:
        members = source.getmembers()
        if not 0 < len(members) <= MAX_FILE_MEMBERS:
            raise ValueError('historical_tar_member_count_invalid')
        with tarfile.open(fileobj=target, mode='w:gz', format=tarfile.USTAR_FORMAT) as destination:
            for original in members:
                name = original.name
                if name == 'bot_data':
                    continue
                if not name.startswith('bot_data/'):
                    continue
                if original.issym() or original.islnk() or original.isdev() or not (original.isfile() or original.isdir()):
                    raise ValueError('historical_botdata_member_type_invalid')
                # Reject aliases, duplicate members and platform-specific paths
                # before constructing any portable quarantine tar. Do not rely
                # solely on PurePosixPath, which normalizes repeated separators.
                parts = name.split('/')
                if (name.startswith('/') or '\\' in name or
                        any(part in ('', '.', '..') for part in parts)):
                    raise ValueError('historical_botdata_path_invalid')
                if name in seen_paths:
                    raise ValueError('historical_botdata_duplicate_member')
                seen_paths.add(name)
                if original.size < 0:
                    raise ValueError('historical_botdata_size_invalid')
                total += original.size
                if total > MAX_RAW:
                    raise ValueError('historical_botdata_unpacked_limit')
                clean = tarfile.TarInfo(name)
                clean.uid = clean.gid = clean.mtime = 0
                clean.uname = clean.gname = ''
                clean.mode = 0o700 if original.isdir() else 0o600
                clean.type = tarfile.DIRTYPE if original.isdir() else tarfile.REGTYPE
                clean.size = 0 if original.isdir() else original.size
                source_stream = source.extractfile(original) if original.isfile() else None
                destination.addfile(clean, source_stream)
                if original.isfile():
                    written += 1
    if written < 1:
        raise ValueError('botdata_files_missing')
    data = target.getvalue()
    if len(data) < 1 or len(data) > MAX_CAPSULE:
        raise ValueError('botdata_archive_size_invalid')
    return data, written


def seal_quarantine(authenticated_plaintext: bytes, recipient_public_b64: str, consumer_run: str) -> tuple[bytes, dict]:
    if not re.fullmatch(r'[0-9]{4,24}', consumer_run) or consumer_run == EXPECTED_PRODUCER:
        raise ValueError('consumer_run_invalid')
    try:
        recipient_raw = base64.b64decode(recipient_public_b64, validate=True)
    except Exception as exc:
        raise ValueError('recipient_public_key_invalid') from exc
    if len(recipient_raw) != 32:
        raise ValueError('recipient_public_key_size_invalid')
    tar, count = make_botdata_tar(authenticated_plaintext)
    recipient_id = 'sha256:' + digest(recipient_raw)
    sender = x25519.X25519PrivateKey.generate()
    sender_pub = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    salt = os.urandom(32)
    nonce = os.urandom(12)
    aad_fields = {
        'schema': SCHEMA,
        'producer_run': EXPECTED_PRODUCER,
        'historical_source_sha': EXPECTED_HISTORICAL_SOURCE,
        'selected_pi_source_sha': EXPECTED_SELECTED_SOURCE,
        'consumer_run': consumer_run,
        'recipient_key_id': recipient_id,
        'root_import_authorized': False,
        'live_submission_authorized': False,
        'gateway_excluded': True,
    }
    aad = json.dumps(aad_fields, sort_keys=True, separators=(',', ':')).encode()
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO + aad).derive(shared)
    encrypted = AESGCM(key).encrypt(nonce, tar, aad)
    envelope = {
        **aad_fields,
        'sender_public_b64': base64.b64encode(sender_pub).decode(),
        'salt_b64': base64.b64encode(salt).decode(),
        'nonce_b64': base64.b64encode(nonce).decode(),
        'ciphertext_sha256': digest(encrypted),
        'ciphertext_bytes': len(encrypted),
        'plaintext_published': False,
        'master_key_published': False,
    }
    return encrypted, envelope


def write_capsule(output: Path, encrypted: bytes, envelope: dict) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError('capsule_destination_exists_refuse_overwrite')
    os.mkdir(output, 0o700)
    for name, data in (
        ('ciphertext.bin', encrypted),
        ('envelope.json', (json.dumps(envelope, sort_keys=True) + '\n').encode()),
    ):
        path = output / name
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
