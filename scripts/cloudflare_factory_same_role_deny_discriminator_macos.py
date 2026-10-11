# Canonical authority: XoticHaze/CommandCenter@e5650489cf11c30e2be116a3289cd94bcbccd0fd
#!/usr/bin/env python3
from __future__ import annotations
import getpass, json, os, secrets, subprocess
from datetime import datetime, timedelta, timezone

API="https://api.cloudflare.com/client/v4"
PG_WORKERS_ADMIN="98d78cd2433d4c3687191bc0244ef948"
FAILED_FACTORY_NAME="Shared Compute Worker Factory"
TOKEN_PREFIXES=(
    "Shared Compute Factory Bootstrap TEMP ",
    "Shared Compute Secrets Bootstrap TEMP ",
    "Shared Compute SameRole DENY TEMP ",
)
WORKER_PREFIXES=(
    "shared-compute-deny-sentinel-",
    "shared-compute-allow-proof-",
)

def die(msg):
    raise SystemExit(msg)

def request(token, method, path, body=None, accepted=(200,)):
    cfg=f'header = "Authorization: Bearer {token}"\nheader = "Accept: application/json"\n'
    if body is not None:
        cfg+='header = "Content-Type: application/json"\n'
    rfd,wfd=os.pipe()
    try:
        os.write(wfd,cfg.encode())
    finally:
        os.close(wfd)
    cmd=["/usr/bin/curl","--silent","--show-error","--connect-timeout","15","--max-time","45",
         "--config",f"/dev/fd/{rfd}","--request",method,
         "--write-out","__CC_HTTP__%{http_code}",API+path]
    payload=None
    if body is not None:
        cmd += ["--data-binary","@-"]
        payload=json.dumps(body,separators=(",",":"))
    try:
        p=subprocess.run(cmd,input=payload,text=True,capture_output=True,pass_fds=(rfd,))
    finally:
        os.close(rfd)
    if p.returncode:
        die(f"transport failure {method} {path}: curl={p.returncode}")
    if "__CC_HTTP__" not in p.stdout:
        die("HTTP status marker missing")
    raw,status=p.stdout.rsplit("__CC_HTTP__",1)
    status=int(status.strip())
    try:
        node=json.loads(raw) if raw else {}
    except Exception:
        node={}
    if status not in accepted:
        errs="; ".join(str(e.get("message") or e) for e in node.get("errors",[]) if isinstance(e,dict))
        die(f"HTTP {status} {method} {path}: {errs or 'rejected'}")
    return status,node

def create_token(temp, account, name, policies, minutes=10, accepted=(200,)):
    body={"name":name,"policies":policies}
    if minutes:
        body["expires_on"]=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat().replace("+00:00","Z")
    return request(temp,"POST",f"/accounts/{account}/tokens",body,accepted)

def delete_token(temp, account, tid):
    request(temp,"DELETE",f"/accounts/{account}/tokens/{tid}",None,(200,404))

account=(os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
if not account:
    account=input("Cloudflare Account ID: ").strip()
if len(account)!=32:
    die("invalid account id")

temp=""
service=(os.environ.get("CLOUDFLARE_TEMP_KEYCHAIN_SERVICE") or "").strip()
if service:
    p=subprocess.run(
        ["/usr/bin/security","find-generic-password","-a",getpass.getuser(),"-s",service,"-w"],
        text=True,capture_output=True
    )
    if p.returncode==0:
        temp=p.stdout.strip()
if not temp:
    temp=getpass.getpass("Shared Compute Token Provisioner TEMP secret: ").strip()
if not temp:
    die("empty TEMP token")

request(temp,"GET",f"/accounts/{account}/tokens/verify")
print("TEMP_PROVISIONER_VERIFY_PASS=1")

# Remove any failed-candidate tokens left from prior fail-closed attempts.
_,token_node=request(temp,"GET",f"/accounts/{account}/tokens?per_page=100")
rows=token_node.get("result") or []
if isinstance(rows,dict):
    rows=list(rows.values())
removed=[]
for t in rows:
    if not isinstance(t,dict):
        continue
    name=str(t.get("name") or "")
    tid=str(t.get("id") or "")
    if name==FAILED_FACTORY_NAME or any(name.startswith(p) for p in TOKEN_PREFIXES):
        if len(tid)==32:
            delete_token(temp,account,tid)
            removed.append(name)
print(f"FAILED_TOKEN_CLEANUP_COUNT={len(removed)}")

account_resources={f"com.cloudflare.api.account.{account}":"*"}
nonce=secrets.token_hex(5)
helper_name=f"Shared Compute SameRole DENY TEMP {nonce}"
helper_id=helper_value=None
candidate_id=candidate_value=None
sentinel_id=None
sentinel_name=f"shared-compute-deny-sentinel-{nonce}"

try:
    # Short-lived broad helper for cleanup + disposable sentinel only.
    _,helper_node=create_token(
        temp,account,helper_name,
        [{"effect":"allow","permission_groups":[{"id":PG_WORKERS_ADMIN}],"resources":account_resources}],
        10
    )
    h=helper_node.get("result") or {}
    helper_id=str(h.get("id") or "")
    helper_value=str(h.get("value") or "")
    if len(helper_id)!=32 or not helper_value:
        die("bootstrap helper creation missing id/value")
    print("CLEANUP_HELPER_CREATED=1")

    # Clean any disposable Worker leftovers from failed proof attempts.
    _,workers=request(helper_value,"GET",f"/accounts/{account}/workers/workers?per_page=100")
    wrows=workers.get("result") or []
    if isinstance(wrows,dict):
        wrows=list(wrows.values())
    cleaned=0
    for w in wrows:
        if not isinstance(w,dict):
            continue
        name=str(w.get("name") or "")
        wid=str(w.get("id") or "")
        if any(name.startswith(p) for p in WORKER_PREFIXES) and len(wid)==32:
            request(helper_value,"DELETE",f"/accounts/{account}/workers/workers/{wid}",None,(200,404))
            cleaned+=1
    print(f"FAILED_WORKER_CLEANUP_COUNT={cleaned}")

    # Fresh disposable Worker. No neutral Worker is touched by this discriminator.
    _,made=request(
        helper_value,"POST",f"/accounts/{account}/workers/workers",
        {"name":sentinel_name,"subdomain":{"enabled":False,"previews_enabled":False}},
        (200,201)
    )
    sentinel_id=str((made.get("result") or {}).get("id") or "")
    if len(sentinel_id)!=32:
        die("sentinel worker ID missing")
    print("SAME_ROLE_DENY_SENTINEL_CREATED=1")

    denied_resources={
        f"com.cloudflare.api.account.{account}":{
            f"com.cloudflare.edge.worker.script.{sentinel_id}":"*"
        }
    }
    policies=[
        {"effect":"allow","permission_groups":[{"id":PG_WORKERS_ADMIN}],"resources":account_resources},
        {"effect":"deny","permission_groups":[{"id":PG_WORKERS_ADMIN}],"resources":denied_resources},
    ]
    status,node=create_token(
        temp,account,
        f"Shared Compute SameRole DENY Candidate {nonce}",
        policies,10,accepted=(200,400)
    )

    if status==400:
        errors=[
            str(e.get("message") or e)
            for e in (node.get("errors") or [])
            if isinstance(e,dict)
        ]
        print("SAME_ROLE_RESOURCE_DENY_API_ACCEPTED=0")
        print("SAME_ACCOUNT_TOKEN_LEVEL_NEUTRAL_ISOLATION=DISPROVEN")
        print("NEXT_ARCHITECTURE=ACCOUNT_SEPARATION")
        print("CLOUDFLARE_ERROR_COUNT="+str(len(errors)))
    else:
        r=node.get("result") or {}
        candidate_id=str(r.get("id") or "")
        candidate_value=str(r.get("value") or "")
        if len(candidate_id)!=32 or not candidate_value:
            die("candidate creation missing id/value")
        print("SAME_ROLE_RESOURCE_DENY_API_ACCEPTED=1")

        read_status,_=request(
            candidate_value,"GET",
            f"/accounts/{account}/workers/workers/{sentinel_id}",
            None,(200,401,403,404)
        )
        print(f"SAME_ROLE_SENTINEL_GET_HTTP={read_status}")
        if read_status==200:
            print("SAME_ROLE_RESOURCE_DENY_ENFORCED=0")
            print("SAME_ACCOUNT_TOKEN_LEVEL_NEUTRAL_ISOLATION=DISPROVEN")
            print("NEXT_ARCHITECTURE=ACCOUNT_SEPARATION")
        else:
            print("SAME_ROLE_RESOURCE_DENY_ENFORCED=1")
            print("SAME_ACCOUNT_TOKEN_LEVEL_NEUTRAL_ISOLATION=VIABLE_PENDING_REAL_NEUTRAL_PROOF")
finally:
    if candidate_id:
        try:
            delete_token(temp,account,candidate_id)
        except BaseException:
            pass
    if sentinel_id and helper_value:
        try:
            request(helper_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",None,(200,404))
        except BaseException:
            pass
    if helper_id:
        try:
            delete_token(temp,account,helper_id)
        except BaseException:
            pass

print("DISCRIMINATOR_TEMP_CLEANUP_COMPLETE=1")
print("SHARED_COMPUTE_FACTORY_DENY_DISCRIMINATOR_COMPLETE=1")
