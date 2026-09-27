from __future__ import annotations
"""Consume one PLACED receipt through the existing portable canonical session executor."""
import argparse,json
from pathlib import Path
from typing import Any,Callable
from compute.executor_adapter import invocation_for
from compute.github_actions_generic_driver import GithubActionsGenericDriver
from compute.launch_transport import launch_and_wait

WORKFLOW_BY_EXECUTOR={"github_actions_generic":".github/workflows/mmibkr-canonical-research-session-bau-r1.yml"}

def launch_packet(packet:dict[str,Any], *, driver_factory:Callable[...,Any]=GithubActionsGenericDriver)->dict[str,Any]:
    if not isinstance(packet,dict): raise ValueError("packet invalid")
    placement=packet.get("placement_receipt"); job=packet.get("job")
    if not isinstance(placement,dict) or placement.get("state")!="PLACED": raise ValueError("PLACED receipt required")
    if not isinstance(job,dict): raise ValueError("job missing")
    invocation=invocation_for(placement,job)
    workflow=WORKFLOW_BY_EXECUTOR.get(invocation["executor_kind"])
    if not workflow: raise RuntimeError("selected-surface workflow unavailable")
    source=((job.get("inputs") or {}).get("source") or {}).get("commit")
    source=str(source or "").strip().lower()
    if len(source)!=40 or any(ch not in "0123456789abcdef" for ch in source): raise ValueError("exact source commit required")
    driver=driver_factory(workflow_path=workflow,source_ref=source,ref="main")
    terminal=launch_and_wait(invocation,driver)
    return {"schema":"commandcenter.placed_terminal_receipt.v1","placement_receipt":placement,
      "invocation":{"job_id":invocation["job_id"],"job_sha256":invocation["job_sha256"],
        "compute_id":invocation["compute_id"],"executor_kind":invocation["executor_kind"],
        "repository":invocation["repository"],"entrypoint":invocation["entrypoint"]},
      "terminal":terminal}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("packet",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=launch_packet(json.loads(a.packet.read_text()))
    a.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n");print(json.dumps(out,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())