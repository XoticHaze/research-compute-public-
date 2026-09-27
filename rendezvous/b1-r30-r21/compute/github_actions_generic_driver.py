from __future__ import annotations
"""Concrete GitHub Actions selected-surface driver for portable canonical research sessions.

Transport only: no StrategySpec, workload, runtime, broker, promotion, or live authority.
"""
import base64,hashlib,io,json,os,time,urllib.parse,urllib.request,uuid,zlib,zipfile
from typing import Any

class GithubActionsDriverError(RuntimeError): pass

class GithubActionsGenericDriver:
    def __init__(self, *, workflow_path:str, ref:str="main", source_ref:str, token:str|None=None,
                 api_base:str="https://api.github.com", poll_seconds:float=1.0, timeout_seconds:float=90.0):
        self.workflow_path=workflow_path
        self.ref=ref
        self.source_ref=source_ref
        self.token=token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.api_base=api_base.rstrip("/")
        self.poll_seconds=poll_seconds
        self.timeout_seconds=timeout_seconds
        if not self.token: raise GithubActionsDriverError("GitHub token unavailable")
        if len(source_ref)!=40 or any(ch not in "0123456789abcdef" for ch in source_ref):
            raise GithubActionsDriverError("source_ref invalid")

    def _request(self, method:str, url:str, body:dict|None=None)->tuple[int,Any]:
        data=None if body is None else json.dumps(body,separators=(",",":")).encode()
        req=urllib.request.Request(url,data=data,method=method,headers={
            "Authorization":"Bearer "+self.token,"Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                raw=r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw=exc.read().decode("utf-8","replace")
            raise GithubActionsDriverError(f"GitHub API {method} {url} failed HTTP {exc.code}: {raw[:500]}") from exc


    def _request_bytes(self, url:str)->bytes:
        req=urllib.request.Request(url,headers={
            "Authorization":"Bearer "+self.token,"Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: return r.read()
        except urllib.error.HTTPError as exc:
            raw=exc.read().decode("utf-8","replace")
            raise GithubActionsDriverError(f"GitHub artifact GET failed HTTP {exc.code}: {raw[:500]}") from exc

    def wait_terminal(self, invocation:dict[str,Any], launch_result:dict[str,Any])->dict[str,Any]:
        repo=str(invocation["repository"]); run_id=str(launch_result.get("surface_run_id") or "")
        if not run_id.isdigit(): raise GithubActionsDriverError("surface run id invalid")
        if launch_result.get("job_sha256")!=invocation["job_sha256"]: raise GithubActionsDriverError("launch/job identity mismatch")
        expected_public_head=str(launch_result.get("public_head") or "").lower()
        if len(expected_public_head)!=40 or any(ch not in "0123456789abcdef" for ch in expected_public_head):
            raise GithubActionsDriverError("launch public head invalid")
        session_budget=int((invocation.get("portable_session") or {}).get("budget_seconds") or 0)
        terminal_timeout=min(max(float(session_budget)+900.0,self.timeout_seconds,300.0),19_800.0)
        deadline=time.monotonic()+terminal_timeout
        run=None
        while time.monotonic()<deadline:
            _,run=self._request("GET",f"{self.api_base}/repos/{repo}/actions/runs/{run_id}")
            if (run or {}).get("status")=="completed": break
            time.sleep(max(self.poll_seconds,1.0))
        if not run or run.get("status")!="completed": raise GithubActionsDriverError("workflow run did not reach terminal state")
        if run.get("conclusion")!="success": raise GithubActionsDriverError(f"workflow run terminal conclusion={run.get('conclusion')}")
        if str(run.get("head_sha") or "").lower()!=expected_public_head:
            raise GithubActionsDriverError("terminal workflow public head mismatch")
        _,node=self._request("GET",f"{self.api_base}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
        expected_name=f"canonical-session-terminal-{run_id}"
        matches=[a for a in ((node or {}).get("artifacts") or []) if a.get("name")==expected_name and not a.get("expired")]
        if len(matches)!=1: raise GithubActionsDriverError("exact terminal artifact not found")
        art=matches[0]; archive=self._request_bytes(str(art["archive_download_url"]))
        archive_sha=hashlib.sha256(archive).hexdigest()
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            names=z.namelist()
            if names!=["terminal-receipt.json"]: raise GithubActionsDriverError("terminal artifact member set rejected")
            receipt=json.loads(z.read("terminal-receipt.json"))
        if receipt.get("job_sha256")!=invocation["job_sha256"]: raise GithubActionsDriverError("terminal job identity mismatch")
        if str(receipt.get("surface_run_id") or "")!=run_id: raise GithubActionsDriverError("terminal run identity mismatch")
        if receipt.get("workflow_ref")!=launch_result.get("workflow_ref"): raise GithubActionsDriverError("terminal workflow identity mismatch")
        if str(receipt.get("public_head") or "").lower()!=expected_public_head: raise GithubActionsDriverError("terminal public head mismatch")
        return {"job_id":invocation["job_id"],"job_sha256":invocation["job_sha256"],"surface_run_id":run_id,
          "workflow_ref":launch_result["workflow_ref"],"public_head":expected_public_head,"artifact_id":str(art["id"]),"artifact_digest":art.get("digest"),
          "artifact_archive_sha256":archive_sha,"terminal_receipt":receipt}

    def launch(self, invocation:dict[str,Any])->dict[str,Any]:
        repo=str(invocation.get("repository") or "")
        if "/" not in repo: raise GithubActionsDriverError("execution repository invalid")
        session=invocation.get("portable_session")
        if not isinstance(session,dict) or session.get("schema")!="mmibkr.canonical_session.v1":
            raise GithubActionsDriverError("portable canonical session missing")
        raw=json.dumps(session,sort_keys=True,separators=(",",":")).encode()
        packed=base64.b64encode(zlib.compress(raw,9)).decode("ascii")
        if len(packed)>60000: raise GithubActionsDriverError("portable session exceeds workflow input budget")
        nonce=uuid.uuid4().hex
        title=f"canonical-session-{invocation['job_sha256']}-{nonce}"
        workflow=urllib.parse.quote(self.workflow_path,safe="")
        base=f"{self.api_base}/repos/{repo}/actions/workflows/{workflow}"
        _,ref_node=self._request("GET",f"{self.api_base}/repos/{repo}/git/ref/heads/{urllib.parse.quote(self.ref,safe='')}")
        expected_public_head=str((((ref_node or {}).get("object") or {}).get("sha")) or "").lower()
        if len(expected_public_head)!=40 or any(ch not in "0123456789abcdef" for ch in expected_public_head):
            raise GithubActionsDriverError("public execution head unavailable")
        status,_=self._request("POST",base+"/dispatches",{"ref":self.ref,"inputs":{
            "source_ref":self.source_ref,"session_zlib_b64":packed,
            "expected_job_sha256":invocation["job_sha256"],"dispatch_nonce":nonce}})
        if status not in (201,204): raise GithubActionsDriverError(f"workflow dispatch returned {status}")
        deadline=time.monotonic()+self.timeout_seconds
        run=None
        while time.monotonic()<deadline:
            _,node=self._request("GET",base+f"/runs?event=workflow_dispatch&branch={urllib.parse.quote(self.ref)}&per_page=30")
            for candidate in (node or {}).get("workflow_runs") or []:
                if candidate.get("display_title")==title:
                    if str(candidate.get("head_sha") or "").lower()!=expected_public_head:
                        raise GithubActionsDriverError("dispatched workflow public head mismatch")
                    run=candidate;break
            if run:break
            time.sleep(self.poll_seconds)
        if not run: raise GithubActionsDriverError("dispatched workflow run identity not observed before timeout")
        return {
            "job_id":invocation["job_id"],"job_sha256":invocation["job_sha256"],
            "execution_repository":repo,
            "workflow_ref":f"{repo}/{self.workflow_path}@refs/heads/{self.ref}",
            "public_head":expected_public_head,
            "surface_run_id":str(run["id"]),
        }
