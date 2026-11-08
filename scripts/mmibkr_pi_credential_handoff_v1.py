#!/usr/bin/env python3
"""Pi-recipient encryption for the existing OIDC-authorized Fleet live seal.

No broker login, network client, order submission, or arbitrary execution.
The decrypted output is reduced to an API read-only Gateway credential env.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = 'mmibkr.pi.gateway_credentials_envelope.v1'
DOMAIN = 'mmibkr-pi-gateway-sealed-v1'
MAX_FILE = 8192
RUN_ID = re.compile(r'[0-9]{4,24}\Z')
B64 = lambda b: base64.b64encode(b).decode('ascii')

def raw64(v, size, field):
    if not isinstance(v, str):
        raise ValueError(field + '_invalid')
    try:
        raw = base64.b64decode(v, validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(field + '_invalid') from e
    if size is not None and len(raw) != size:
        raise ValueError(field + '_invalid')
    return raw

def fingerprint(public):
    return 'sha256:' + hashlib.sha256(public).hexdigest()

def get_public(private):
    return private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

def require_file(path, *, private=False):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or (private and (st.st_mode & 0o077)):
        raise ValueError('unsafe_file')
    if st.st_size > MAX_FILE or st.st_size == 0:
        raise ValueError('file_size_invalid')
    return path.read_bytes()

def create_exclusive(path, contents, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise

def init(private_path, public_path):
    if private_path.exists() or private_path.is_symlink():
        raise ValueError('recipient_key_already_exists')
    private = x25519.X25519PrivateKey.generate()
    public = get_public(private)
    key = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    create_exclusive(private_path, key)
    try:
        create_exclusive(public_path, (B64(public) + '\n').encode(), 0o644)
    except Exception:
        private_path.unlink()
        raise
    print(json.dumps({'result':'PI_RECIPIENT_CREATED','public_key_file':str(public_path),
                      'recipient_key_id':fingerprint(public)},sort_keys=True))

def parse_env(src):
    result = {}
    for line in src.decode('utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('env_invalid')
        k, v = line.split('=',1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,64}',k) or k in result:
            raise ValueError('env_key_invalid')
        if len(v)>512 or any(c in v for c in ('\x00','\r','\n')):
            raise ValueError('env_value_invalid')
        result[k]=v
    for key in ('TWS_USERID','TWS_PASSWORD','MMIBKR_PRODUCTION_LIVE_ACCOUNT'):
        if not result.get(key):
            raise ValueError('missing_sealed_live_field')
    if result.get('TRADING_MODE') != 'live' or result.get('MMIBKR_ACCOUNT_MODE') != 'production_live':
        raise ValueError('wrong_account_mode')
    account=result['MMIBKR_PRODUCTION_LIVE_ACCOUNT']
    if account.upper().startswith('DU'):
        raise ValueError('paper_account_rejected')
    return result

def sanitized_env(d):
    # The source may be a writable Fleet seal; this receiver never grants
    # another order writer.
    pairs=[('TWS_USERID',d['TWS_USERID']), ('TWS_PASSWORD',d['TWS_PASSWORD']),
           ('TWS_USERID_LIVE',d['TWS_USERID']), ('TWS_PASSWORD_LIVE',d['TWS_PASSWORD']),
           ('MMIBKR_PRODUCTION_LIVE_ACCOUNT',d['MMIBKR_PRODUCTION_LIVE_ACCOUNT']),
           ('MMIBKR_ACCOUNT_MODE','production_live'), ('TRADING_MODE','live'),
           ('READ_ONLY_API','yes'), ('ENABLE_LIVE_TRADING','0'),
           ('TWS_ACCEPT_INCOMING','accept'), ('TWOFA_TIMEOUT_ACTION','exit'),
           ('RELOGIN_AFTER_TWOFA_TIMEOUT','no'),('SAVE_TWS_SETTINGS','no'),
           ('ENABLE_VNC','false')]
    for opt in ('TWOFA_DEVICE','TWS_SERVER','TWS_SERVER_LIVE'):
        if d.get(opt):
            pairs.append((opt,d[opt]))
    for _,v in pairs:
        if not v or len(v)>512 or any(c in v for c in ('\n','\r','\x00')):
            raise ValueError('unsafe_env_value')
    return ('\n'.join(k+'='+v for k,v in pairs)+'\n').encode()

def encrypt_envelope(src, public, run_id):
    if not RUN_ID.fullmatch(run_id):
        raise ValueError('run_id_invalid')
    if len(public)!=32:
        raise ValueError('public_key_invalid')
    env=sanitized_env(parse_env(src))
    if len(env)>4096:
        raise ValueError('env_too_large')
    pk=x25519.X25519PublicKey.from_public_bytes(public)
    eph=x25519.X25519PrivateKey.generate()
    salt=os.urandom(32)
    iv=os.urandom(12)
    rid=fingerprint(public)
    aad=f'{DOMAIN}|{run_id}|{rid}'.encode()
    shared=eph.exchange(pk)
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=aad).derive(shared)
    cipher=AESGCM(key).encrypt(iv,env,aad)
    return {'schema':SCHEMA,'run_id':run_id,'recipient_key_id':rid,
            'ephemeral_public_b64':B64(get_public(eph)), 'salt_b64':B64(salt),
            'iv_b64':B64(iv), 'ciphertext_b64':B64(cipher)}

def decrypt_envelope(envelope,private):
    expected={'schema','run_id','recipient_key_id','ephemeral_public_b64','salt_b64','iv_b64','ciphertext_b64'}
    if not isinstance(envelope,dict) or set(envelope)!=expected or envelope['schema']!=SCHEMA:
        raise ValueError('envelope_schema_invalid')
    run_id=envelope['run_id']
    if not isinstance(run_id,str) or not RUN_ID.fullmatch(run_id):
        raise ValueError('envelope_run_invalid')
    rid=fingerprint(get_public(private))
    if envelope['recipient_key_id']!=rid:
        raise ValueError('recipient_mismatch')
    eph=raw64(envelope['ephemeral_public_b64'],32,'ephemeral')
    salt=raw64(envelope['salt_b64'],32,'salt')
    iv=raw64(envelope['iv_b64'],12,'iv')
    cipher=raw64(envelope['ciphertext_b64'],None,'ciphertext')
    if len(cipher)>MAX_FILE or len(cipher)<17:
        raise ValueError('ciphertext_invalid')
    aad=f'{DOMAIN}|{run_id}|{rid}'.encode()
    shared=private.exchange(x25519.X25519PublicKey.from_public_bytes(eph))
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=aad).derive(shared)
    plaintext=AESGCM(key).decrypt(iv,cipher,aad)
    env=parse_env(plaintext)
    if env.get('READ_ONLY_API')!='yes' or env.get('ENABLE_LIVE_TRADING')!='0':
        raise ValueError('broker_api_readonly_required')
    if plaintext!=sanitized_env(env):
        raise ValueError('unexpected_environment_fields')
    return plaintext

def install(private_path,envelope_path,dest):
    if os.geteuid()!=0:
        raise PermissionError('pi_install_requires_root')
    root=dest.parent
    st=root.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or (st.st_mode&0o077):
        raise ValueError('destination_directory_must_be_root_0700')
    if dest.is_symlink():
        raise ValueError('destination_symlink')
    if dest.exists() and dest.stat().st_size>0:
        raise ValueError('credentials_already_provisioned_refuse_overwrite')
    pstat=private_path.lstat()
    if pstat.st_uid!=0 or (pstat.st_mode&0o077):
        raise ValueError('recipient_private_key_must_be_root_only')
    private=x25519.X25519PrivateKey.from_private_bytes(require_file(private_path,private=True))
    envelope=json.loads(require_file(envelope_path))
    plaintext=decrypt_envelope(envelope,private)
    tmp=None
    try:
        fd,tmpname=tempfile.mkstemp(prefix='.live-gateway.',dir=root)
        tmp=Path(tmpname)
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),0o600)
            f.write(plaintext)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
        os.chmod(dest,0o600)
        dr=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dr)
        finally:os.close(dr)
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)
    print(json.dumps({'result':'PI_CREDENTIALS_INSTALLED','recipient_key_id':fingerprint(get_public(private)),
                      'run_id':envelope['run_id'],'read_only_api':True,'live_order_submit':False},sort_keys=True))

def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest='command',required=True)
    ki=sp.add_parser('init-recipient')
    ki.add_argument('--private-key',required=True,type=Path);ki.add_argument('--public-key',required=True,type=Path)
    se=sp.add_parser('seal')
    se.add_argument('--source-env',required=True,type=Path)
    se.add_argument('--recipient-public-key-b64',required=True)
    se.add_argument('--run-id',required=True)
    se.add_argument('--output',required=True,type=Path)
    ins=sp.add_parser('install')
    ins.add_argument('--private-key',required=True,type=Path)
    ins.add_argument('--envelope',required=True,type=Path)
    ins.add_argument('--destination',required=True,type=Path)
    args=p.parse_args()
    try:
        if args.command=='init-recipient':
            init(args.private_key,args.public_key)
        elif args.command=='seal':
            pub=raw64(args.recipient_public_key_b64,32,'public_key')
            output=encrypt_envelope(require_file(args.source_env,private=True),pub,args.run_id)
            create_exclusive(args.output,(json.dumps(output,sort_keys=True)+'\n').encode())
            print(json.dumps({'result':'PI_ENCRYPTED_CAPSULE_CREATED','run_id':args.run_id,
                              'recipient_key_id':fingerprint(pub),'broker_login_attempted':False},sort_keys=True))
        else:
            install(args.private_key,args.envelope,args.destination)
    except Exception as exc:
        print('MMIBKR_PI_HANDOFF_FAILED='+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
if __name__=='__main__':main()
