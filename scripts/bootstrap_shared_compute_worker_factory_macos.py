# Canonical authority: XoticHaze/CommandCenter@ee11c0c1a95d0f4292958748dfc53fd6f0db9818
#!/usr/bin/env python3
from __future__ import annotations
import getpass, json, os, secrets, subprocess, sys
from datetime import datetime, timedelta, timezone

API="https://api.cloudflare.com/client/v4"
FACTORY_NAME="Shared Compute Worker Factory"
NEUTRAL_NAMES=[
 "reference-release-broker-v1",
 "reference-release-maintainer-v1",
 "reference-maintenance-authority-v1",
]
PG={
 "workers_admin":"98d78cd2433d4c3687191bc0244ef948",
 "individual_admin":"1ef41180fdf74cf7b67415d2708167ac",
 "individual_editor":"7e79ec33834341f28dd431ab73884400",
 "individual_metadata":"afa629b86102452b8b744a5485b870e1",
 "individual_content":"1b68681d11f443a4979c6d08c3211f13",
 "secrets_write":"adc8fa2bc6124928a8b3314dc63a1235",
}

def die(msg): raise SystemExit(msg)
def request(token, method, path, body=None, accepted=(200,)):
    cfg=f'header = "Authorization: Bearer {token}"\nheader = "Accept: application/json"\n'
    if body is not None:
        cfg+='header = "Content-Type: application/json"\n'
    rfd,wfd=os.pipe()
    try:
        os.write(wfd,cfg.encode("utf-8"))
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
    marker="__CC_HTTP__"
    if marker not in p.stdout:
        die("HTTP status marker missing")
    raw,status=p.stdout.rsplit(marker,1)
    status=int(status.strip())
    try:
        node=json.loads(raw) if raw else {}
    except Exception:
        node={"raw":raw[:300]}
    if status not in accepted:
        errs="; ".join(str(e.get("message") or e) for e in node.get("errors",[]) if isinstance(e,dict))
        die(f"HTTP {status} {method} {path}: {errs or 'rejected'}")
    return status,node

def create_token(temp, account, name, policies, minutes=None):
    body={"name":name,"policies":policies}
    if minutes:
        body["expires_on"]=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat().replace("+00:00","Z")
    _,node=request(temp,"POST",f"/accounts/{account}/tokens",body,(200,))
    result=node.get("result") or {}
    tid=str(result.get("id") or ""); value=str(result.get("value") or "")
    if len(tid)!=32 or not value: die(f"{name}: token creation response missing id/value")
    return tid,value

def delete_token(temp, account, tid):
    request(temp,"DELETE",f"/accounts/{account}/tokens/{tid}",None,(200,))

account=(os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
if not account:
    account=input("Cloudflare Account ID: ").strip()
if len(account)!=32 or any(c not in "0123456789abcdefABCDEF" for c in account): die("invalid account id")
temp=""
keychain_service=(os.environ.get("CLOUDFLARE_TEMP_KEYCHAIN_SERVICE") or "").strip()
if keychain_service:
    keychain=subprocess.run(
        ["/usr/bin/security","find-generic-password","-a",getpass.getuser(),
         "-s",keychain_service,"-w"],
        text=True,capture_output=True
    )
    if keychain.returncode == 0:
        temp=keychain.stdout.strip()
if not temp:
    temp=getpass.getpass("Shared Compute Token Provisioner TEMP secret: ").strip()
if not temp: die("empty TEMP token")
request(temp,"GET",f"/accounts/{account}/tokens/verify")
print("TEMP_PROVISIONER_VERIFY_PASS=1")

account_resources={f"com.cloudflare.api.account.{account}":"*"}
helper_id=helper_value=None
factory_id=factory_value=None
factory_persisted=False
secret_helper_id=secret_helper_value=None
sentinel_id=None
allow_id=None
nonce=secrets.token_hex(5)
helper_name=f"Shared Compute Factory Bootstrap TEMP {nonce}"
sentinel_name=f"shared-compute-deny-sentinel-{nonce}"
allow_name=f"shared-compute-allow-proof-{nonce}"

# Fail if a standing factory already exists.
_,tokens=request(temp,"GET",f"/accounts/{account}/tokens?per_page=100")
existing=[t for t in (tokens.get("result") or []) if isinstance(t,dict) and t.get("name")==FACTORY_NAME]
if existing: die("Shared Compute Worker Factory already exists; refusing duplicate creation")

try:
    # Short-lived broad bootstrap exists only in memory and expires automatically.
    helper_policy=[{"effect":"allow","permission_groups":[{"id":PG["workers_admin"]}],"resources":account_resources}]
    helper_id,helper_value=create_token(temp,account,helper_name,helper_policy,10)
    print("BOOTSTRAP_HELPER_CREATED=1")

    _,workers=request(helper_value,"GET",f"/accounts/{account}/workers/workers?per_page=100")
    rows=workers.get("result") or []
    if isinstance(rows,dict): rows=list(rows.values())
    by_name={str(x.get("name") or ""):str(x.get("id") or "") for x in rows if isinstance(x,dict)}
    missing=[n for n in NEUTRAL_NAMES if len(by_name.get(n,""))!=32]
    if missing: die("neutral Worker immutable ID lookup failed: "+",".join(missing))
    neutral_ids=[by_name[n] for n in NEUTRAL_NAMES]
    print("NEUTRAL_WORKER_ID_MAP_PASS=1")

    # Disposable denied sentinel.
    _,created=request(helper_value,"POST",f"/accounts/{account}/workers/workers",
        {"name":sentinel_name,"subdomain":{"enabled":False,"previews_enabled":False}},(200,201))
    sentinel_id=str((created.get("result") or {}).get("id") or "")
    if len(sentinel_id)!=32: die("sentinel worker ID missing")
    print("DENY_SENTINEL_CREATED=1")

    denied_ids=neutral_ids+[sentinel_id]
    denied_resources={f"com.cloudflare.api.account.{account}":{
        f"com.cloudflare.edge.worker.script.{wid}":"*" for wid in denied_ids
    }}
    factory_policies=[
      {"effect":"allow","permission_groups":[{"id":PG["workers_admin"]}],"resources":account_resources},
      {"effect":"deny","permission_groups":[
          {"id":PG["individual_admin"]},{"id":PG["individual_editor"]},
          {"id":PG["individual_metadata"]},{"id":PG["individual_content"]}
        ],"resources":denied_resources},
    ]
    factory_id,factory_value=create_token(temp,account,FACTORY_NAME,factory_policies,None)
    print("FACTORY_TOKEN_CREATED=1")
    request(factory_value,"GET",f"/accounts/{account}/tokens/verify")
    print("FACTORY_TOKEN_VERIFY_PASS=1")

    # Account-wide ordinary Worker administration remains available.
    request(factory_value,"GET",f"/accounts/{account}/workers/workers?per_page=10")
    _,ordinary=request(factory_value,"POST",f"/accounts/{account}/workers/workers",
        {"name":allow_name,"subdomain":{"enabled":False,"previews_enabled":False}},(200,201))
    allow_id=str((ordinary.get("result") or {}).get("id") or "")
    if len(allow_id)!=32: die("allow-proof worker ID missing")
    request(factory_value,"DELETE",f"/accounts/{account}/workers/workers/{allow_id}",None,(200,))
    allow_id=None
    print("FACTORY_ORDINARY_CREATE_DELETE_PASS=1")

    # Real neutral Workers must be unreadable.
    for name,wid in zip(NEUTRAL_NAMES,neutral_ids):
        status,_=request(factory_value,"GET",f"/accounts/{account}/workers/workers/{wid}",None,(401,403,404))
        if status not in (401,403,404): die(f"neutral read unexpectedly allowed: {name}")
    print("FACTORY_REAL_NEUTRAL_READ_DENY_PASS=1")

    # The sentinel uses the exact same DENY resource shape, so destructive proof is safe.
    sget,_=request(factory_value,"GET",f"/accounts/{account}/workers/workers/{sentinel_id}",None,(401,403,404))
    sdel,_=request(factory_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",None,(401,403,404))
    if sget not in (401,403,404) or sdel not in (401,403,404): die("sentinel deny enforcement failed")
    print("FACTORY_SENTINEL_READ_DELETE_DENY_PASS=1")

    # Bootstrap helper cleans the sentinel, then loses authority.
    request(helper_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",None,(200,))
    sentinel_id=None
    delete_token(temp,account,helper_id); helper_id=None; helper_value=""
    print("BOOTSTRAP_HELPER_REVOKED=1")

    # Short-lived secret writer stores the standing factory bearer without printing it.
    secret_policy=[{"effect":"allow","permission_groups":[{"id":PG["secrets_write"]}],"resources":account_resources}]
    secret_helper_id,secret_helper_value=create_token(temp,account,f"Shared Compute Secrets Bootstrap TEMP {nonce}",secret_policy,10)
    _,stores=request(secret_helper_value,"GET",f"/accounts/{account}/secrets_store/stores")
    store_rows=stores.get("result") or []
    if isinstance(store_rows,dict): store_rows=list(store_rows.values())
    if len(store_rows)==0:
        _,made=request(secret_helper_value,"POST",f"/accounts/{account}/secrets_store/stores",{"name":"shared-compute-secrets"},(200,201))
        store=(made.get("result") or {})
    elif len(store_rows)==1:
        store=store_rows[0]
    else:
        die("unexpected multiple Secrets Store stores")
    store_id=str(store.get("id") or "")
    if len(store_id)!=32: die("Secrets Store ID missing")

    _,secrets_list=request(secret_helper_value,"GET",f"/accounts/{account}/secrets_store/stores/{store_id}/secrets")
    secret_rows=secrets_list.get("result") or []
    if isinstance(secret_rows,dict): secret_rows=list(secret_rows.values())
    if any(isinstance(x,dict) and x.get("name")=="SHARED_COMPUTE_WORKER_FACTORY_TOKEN" for x in secret_rows):
        die("factory secret already exists in Secrets Store; refusing overwrite")

    secret_body=[{"name":"SHARED_COMPUTE_WORKER_FACTORY_TOKEN","value":factory_value,
                  "scopes":["workers"],"comment":"Shared compute ordinary Worker factory; neutral Workers explicitly denied"}]
    request(secret_helper_value,"POST",f"/accounts/{account}/secrets_store/stores/{store_id}/secrets",secret_body,(200,201))
    factory_persisted=True
    factory_value=""
    delete_token(temp,account,secret_helper_id); secret_helper_id=None; secret_helper_value=""
    print("FACTORY_SECRET_STORE_ENROLLMENT_PASS=1")
    print("SECRETS_BOOTSTRAP_HELPER_REVOKED=1")

    receipt={
      "schema":"commandcenter.shared_compute_worker_factory_bootstrap.v1",
      "factory_name":FACTORY_NAME,
      "factory_token_id_suffix":factory_id[-8:],
      "factory_secret_printed":False,
      "factory_secret_store_name":"SHARED_COMPUTE_WORKER_FACTORY_TOKEN",
      "secret_store_id_suffix":store_id[-8:],
      "neutral_workers":[{"name":n,"worker_id_suffix":w[-8:]} for n,w in zip(NEUTRAL_NAMES,neutral_ids)],
      "allow_create_delete":True,
      "neutral_read_deny":True,
      "sentinel_read_delete_deny":True,
      "bootstrap_helper_revoked":True,
      "secrets_helper_revoked":True,
      "temp_provisioner_should_remain_active_until_factory_executor_binding":True,
    }
    print("FACTORY_BOOTSTRAP_RECEIPT_BEGIN")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    print("FACTORY_BOOTSTRAP_RECEIPT_END")
    print("SHARED_COMPUTE_WORKER_FACTORY_BOOTSTRAP_PASS=1")
finally:
    # Best-effort cleanup. Short-lived helpers also auto-expire.
    if allow_id and helper_value:
        try: request(helper_value,"DELETE",f"/accounts/{account}/workers/workers/{allow_id}",None,(200,404))
        except BaseException: pass
    if sentinel_id and helper_value:
        try: request(helper_value,"DELETE",f"/accounts/{account}/workers/workers/{sentinel_id}",None,(200,404))
        except BaseException: pass
    if factory_id and not factory_persisted:
        try: delete_token(temp,account,factory_id)
        except BaseException: pass
    for tid in (secret_helper_id,helper_id):
        if tid:
            try: delete_token(temp,account,tid)
            except BaseException: pass
