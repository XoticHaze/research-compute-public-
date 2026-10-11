# Canonical authority: XoticHaze/CommandCenter@c3fdb2d1be21f3c86403e432eda0fc0e75090f54
#!/usr/bin/env python3
from __future__ import annotations
import getpass, json, os, secrets, subprocess
from datetime import datetime, timedelta, timezone

API="https://api.cloudflare.com/client/v4"
FACTORY_NAME="Shared Compute Worker Factory"
SECRET_NAME="SHARED_COMPUTE_WORKER_FACTORY_TOKEN"
STORE_NAME="shared-compute-secrets"
NEUTRAL_NAMES=[
    "reference-release-broker-v1",
    "reference-release-maintainer-v1",
    "reference-maintenance-authority-v1",
]
PG_WORKERS_ADMIN="98d78cd2433d4c3687191bc0244ef948"
PG_SECRETS_WRITE="adc8fa2bc6124928a8b3314dc63a1235"

def die(msg):
    raise SystemExit(msg)

def request(token, method, path, body=None, accepted=(200,)):
    cfg=f'header = "Authorization: Bearer {token}"\nheader = "Accept: application/json"\n'
    if body is not None:
        cfg+='header = "Content-Type: application/json"\n'
    rfd,wfd=os.pipe()
    try:
        os.write(wfd,cfg.encode("utf-8"))
    finally:
        os.close(wfd)
    cmd=[
        "/usr/bin/curl","--silent","--show-error","--connect-timeout","15","--max-time","45",
        "--config",f"/dev/fd/{rfd}","--request",method,
        "--write-out","__CC_HTTP__%{http_code}",API+path,
    ]
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

def create_token(temp, account, name, policies, minutes=None):
    body={"name":name,"policies":policies}
    if minutes is not None:
        body["expires_on"]=(
            datetime.now(timezone.utc)+timedelta(minutes=minutes)
        ).replace(microsecond=0).isoformat().replace("+00:00","Z")
    _,node=request(temp,"POST",f"/accounts/{account}/tokens",body,(200,))
    r=node.get("result") or {}
    tid=str(r.get("id") or "")
    value=str(r.get("value") or "")
    if len(tid)!=32 or not value:
        die(f"{name}: token creation response missing id/value")
    return tid,value

def delete_token(temp, account, tid):
    request(temp,"DELETE",f"/accounts/{account}/tokens/{tid}",None,(200,404))

def rows(node):
    r=node.get("result") or []
    if isinstance(r,dict):
        return list(r.values())
    return [x for x in r if isinstance(x,dict)]

account=(os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
if not account:
    account=input("Cloudflare Account ID: ").strip()
if len(account)!=32 or any(c not in "0123456789abcdefABCDEF" for c in account):
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

_,token_list=request(temp,"GET",f"/accounts/{account}/tokens?per_page=100")
existing=[
    t for t in rows(token_list)
    if str(t.get("name") or "")==FACTORY_NAME
]
if existing:
    die("Shared Compute Worker Factory already exists; refusing duplicate finalization")

account_resources={f"com.cloudflare.api.account.{account}":"*"}
nonce=secrets.token_hex(5)
worker_helper_id=worker_helper_value=None
secret_helper_id=secret_helper_value=None
factory_id=factory_value=None
factory_persisted=False
sentinel_id=None
ordinary_id=None

try:
    worker_helper_id,worker_helper_value=create_token(
        temp,account,f"Shared Compute Finalizer Workers TEMP {nonce}",
        [{"effect":"allow","permission_groups":[{"id":PG_WORKERS_ADMIN}],"resources":account_resources}],
        minutes=10
    )
    print("FINALIZER_WORKERS_HELPER_CREATED=1")

    _,worker_list=request(
        worker_helper_value,"GET",f"/accounts/{account}/workers/workers?per_page=100"
    )
    by_name={
        str(w.get("name") or ""):str(w.get("id") or "")
        for w in rows(worker_list)
    }
    missing=[n for n in NEUTRAL_NAMES if len(by_name.get(n,""))!=32]
    if missing:
        die("neutral Worker immutable ID lookup failed: "+",".join(missing))
    neutral_ids=[by_name[n] for n in NEUTRAL_NAMES]
    print("REAL_NEUTRAL_WORKER_ID_MAP_PASS=1")

    sentinel_name=f"shared-compute-final-deny-sentinel-{nonce}"
    _,made=request(
        worker_helper_value,"POST",f"/accounts/{account}/workers/workers",
        {"name":sentinel_name,"subdomain":{"enabled":False,"previews_enabled":False}},
        (200,201)
    )
    sentinel_id=str((made.get("result") or {}).get("id") or "")
    if len(sentinel_id)!=32:
        die("final sentinel Worker ID missing")
    print("FINAL_DENY_SENTINEL_CREATED=1")

    denied_ids=neutral_ids+[sentinel_id]
    denied_resources={
        f"com.cloudflare.api.account.{account}":{
            f"com.cloudflare.edge.worker.script.{wid}":"*" for wid in denied_ids
        }
    }
    policies=[
        {
            "effect":"allow",
            "permission_groups":[{"id":PG_WORKERS_ADMIN}],
            "resources":account_resources,
        },
        {
            "effect":"deny",
            "permission_groups":[{"id":PG_WORKERS_ADMIN}],
            "resources":denied_resources,
        },
    ]
    factory_id,factory_value=create_token(
        temp,account,FACTORY_NAME,policies,minutes=None
    )
    print("STANDING_FACTORY_TOKEN_CREATED=1")
    request(factory_value,"GET",f"/accounts/{account}/tokens/verify")
    print("STANDING_FACTORY_TOKEN_VERIFY_PASS=1")

    ordinary_name=f"shared-compute-final-allow-proof-{nonce}"
    _,ordinary=request(
        factory_value,"POST",f"/accounts/{account}/workers/workers",
        {"name":ordinary_name,"subdomain":{"enabled":False,"previews_enabled":False}},
        (200,201)
    )
    ordinary_id=str((ordinary.get("result") or {}).get("id") or "")
    if len(ordinary_id)!=32:
        die("ordinary proof Worker ID missing")
    request(
        factory_value,"DELETE",f"/accounts/{account}/workers/workers/{ordinary_id}",
        None,(200,)
    )
    ordinary_id=None
    print("STANDING_FACTORY_ORDINARY_CREATE_DELETE_PASS=1")

    neutral_status={}
    for name,wid in zip(NEUTRAL_NAMES,neutral_ids):
        status,_=request(
            factory_value,"GET",f"/accounts/{account}/workers/workers/{wid}",
            None,(401,403,404)
        )
        neutral_status[name]=status
    print("STANDING_FACTORY_REAL_NEUTRAL_READ_DENY_PASS=1")

    sentinel_get,_=request(
        factory_value,"GET",f"/accounts/{account}/workers/workers/{sentinel_id}",
        None,(401,403,404)
    )
    sentinel_delete,_=request(
        factory_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",
        None,(401,403,404)
    )
    print("STANDING_FACTORY_SENTINEL_GET_DELETE_DENY_PASS=1")

    request(
        worker_helper_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",
        None,(200,404)
    )
    sentinel_id=None
    delete_token(temp,account,worker_helper_id)
    worker_helper_id=None
    worker_helper_value=""
    print("FINALIZER_WORKERS_HELPER_REVOKED=1")

    secret_helper_id,secret_helper_value=create_token(
        temp,account,f"Shared Compute Finalizer Secrets TEMP {nonce}",
        [{"effect":"allow","permission_groups":[{"id":PG_SECRETS_WRITE}],"resources":account_resources}],
        minutes=10
    )
    print("FINALIZER_SECRETS_HELPER_CREATED=1")

    _,stores_node=request(
        secret_helper_value,"GET",f"/accounts/{account}/secrets_store/stores"
    )
    stores=rows(stores_node)
    if len(stores)==0:
        _,store_node=request(
            secret_helper_value,"POST",f"/accounts/{account}/secrets_store/stores",
            {"name":STORE_NAME},(200,201)
        )
        store=store_node.get("result") or {}
    elif len(stores)==1:
        store=stores[0]
    else:
        die("unexpected multiple Secrets Store stores")
    store_id=str(store.get("id") or "")
    if len(store_id)!=32:
        die("Secrets Store ID missing")

    _,secret_list_node=request(
        secret_helper_value,"GET",
        f"/accounts/{account}/secrets_store/stores/{store_id}/secrets"
    )
    if any(str(s.get("name") or "")==SECRET_NAME for s in rows(secret_list_node)):
        die("factory secret already exists in Secrets Store; refusing overwrite")

    _,secret_create_node=request(
        secret_helper_value,"POST",
        f"/accounts/{account}/secrets_store/stores/{store_id}/secrets",
        [{
            "name":SECRET_NAME,
            "value":factory_value,
            "scopes":["workers"],
            "comment":"Shared compute ordinary Worker factory; same-role Workers Admin DENY protects neutral authorization Workers",
        }],
        (200,201)
    )
    secret_rows=rows(secret_create_node)
    secret_id=""
    for s in secret_rows:
        if str(s.get("name") or "")==SECRET_NAME:
            secret_id=str(s.get("id") or "")
            break
    factory_persisted=True
    factory_value=""
    print("STANDING_FACTORY_SECRET_STORE_ENROLLMENT_PASS=1")

    delete_token(temp,account,secret_helper_id)
    secret_helper_id=None
    secret_helper_value=""
    print("FINALIZER_SECRETS_HELPER_REVOKED=1")

    receipt={
        "schema":"commandcenter.shared_compute_worker_factory_finalization.v1",
        "factory_name":FACTORY_NAME,
        "factory_token_id_suffix":factory_id[-8:],
        "factory_secret_printed":False,
        "factory_secret_store_name":SECRET_NAME,
        "secret_store_id_suffix":store_id[-8:],
        "secret_id_suffix":secret_id[-8:] if secret_id else "",
        "neutral_workers":[
            {
                "name":name,
                "worker_id_suffix":wid[-8:],
                "factory_get_http":neutral_status[name],
            }
            for name,wid in zip(NEUTRAL_NAMES,neutral_ids)
        ],
        "ordinary_create_delete":True,
        "real_neutral_read_deny":True,
        "sentinel_get_http":sentinel_get,
        "sentinel_delete_http":sentinel_delete,
        "same_role_workers_admin_deny":True,
        "workers_helper_revoked":True,
        "secrets_helper_revoked":True,
        "temp_provisioner_retirement_ready":False,
        "next_gate":"Bind the Cloudflare-side factory executor to the Secrets Store secret and prove OIDC invocation before retiring TEMP and legacy WaterBoys authority.",
    }
    print("FACTORY_FINALIZATION_RECEIPT_BEGIN")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    print("FACTORY_FINALIZATION_RECEIPT_END")
    print("SHARED_COMPUTE_WORKER_FACTORY_FINALIZATION_PASS=1")
finally:
    if ordinary_id and worker_helper_value:
        try:
            request(
                worker_helper_value,"DELETE",
                f"/accounts/{account}/workers/workers/{ordinary_id}",
                None,(200,404)
            )
        except BaseException:
            pass
    if sentinel_id and worker_helper_value:
        try:
            request(
                worker_helper_value,"DELETE",
                f"/accounts/{account}/workers/workers/{sentinel_id}",
                None,(200,404)
            )
        except BaseException:
            pass
    if factory_id and not factory_persisted:
        try:
            delete_token(temp,account,factory_id)
        except BaseException:
            pass
    for tid in (secret_helper_id,worker_helper_id):
        if tid:
            try:
                delete_token(temp,account,tid)
            except BaseException:
                pass
