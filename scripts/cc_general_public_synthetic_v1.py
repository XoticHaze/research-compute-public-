"""Fixed, public-SYNTHETIC general job ABI smoke for the CC router.

This is not an encrypted private compute consumer. All inputs and results in
this file are explicitly PUBLIC synthetic. It is never an alternate route
for real private inputs or an escape from signed broker admission.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re

REQUEST_SCHEMA="commandcenter.public_synthetic_general_job.v1"
RESULT_SCHEMA="commandcenter.public_synthetic_terminal.v1"
JOB_SCHEMA="commandcenter.public_synthetic_abi.v1"
MAX_BYTES=16000

def canonical_bytes(obj: dict) -> bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")

def _operate(task: dict):
    if not isinstance(task,dict) or set(task)!={"operation","values"}:
        raise ValueError("operation_shape_rejected")
    op=task["operation"]
    values=task["values"]
    if not isinstance(values,list) or len(values)>20 or any(type(x) is not int or abs(x)>10_000 for x in values):
        raise ValueError("synthetic_values_rejected")
    if op=="SUM":
        return sum(values)
    if op=="SORT":
        return sorted(values)
    if op=="DIGEST":
        return hashlib.sha256(canonical_bytes(values)).hexdigest()
    raise ValueError("unapproved_synthetic_operation")

def validate_and_run(packet: dict, run_id: str, workflow_ref: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,24}",str(run_id)):
        raise ValueError("run_identity_rejected")
    if not isinstance(packet,dict) or set(packet)!={"schema","job","job_sha256"}:
        raise ValueError("public_packet_shape_rejected")
    if packet["schema"]!=REQUEST_SCHEMA:
        raise ValueError("public_packet_schema_rejected")
    job=packet["job"]
    if not isinstance(job,dict) or len(canonical_bytes(job))>MAX_BYTES:
        raise ValueError("job_shape_rejected")
    required={"job_id","lane","workload","package","dependencies","inputs","output_contract","provenance","compute_requirements"}
    if set(job)!=required or not re.fullmatch(r"synthetic-[a-z0-9-]{1,32}",str(job["job_id"])):
        raise ValueError("canonical_job_fields_rejected")
    req=job["compute_requirements"]
    if req != {"trust_mode":"public_synthetic","runtime":["python"],"features":["artifact_return"]}:
        raise ValueError("public_synthetic_only")
    if job["lane"]!="PUBLIC_SYNTHETIC" or job["workload"]!="PUBLIC_SYNTHETIC":
        raise ValueError("private_semantics_rejected")
    if job["dependencies"]!=[] or job["inputs"]!={} or job["output_contract"]!={"kind":"public_synthetic_artifact"}:
        raise ValueError("private_dependencies_or_inputs_rejected")
    if job["provenance"]!={"kind":"public_synthetic_only"}:
        raise ValueError("private_provenance_rejected")
    pack=job["package"]
    if not isinstance(pack,dict) or set(pack)!={"schema","tasks"} or pack["schema"]!=JOB_SCHEMA:
        raise ValueError("synthetic_abi_rejected")
    tasks=pack["tasks"]
    if not isinstance(tasks,list) or not 1<=len(tasks)<=8:
        raise ValueError("synthetic_tasks_rejected")
    expected=hashlib.sha256(canonical_bytes(job)).hexdigest()
    if packet["job_sha256"]!=expected:
        raise ValueError("upstream_job_identity_rejected")
    answers=[_operate(task) for task in tasks]
    return {
        "schema":RESULT_SCHEMA,
        "state":"PUBLIC_SYNTHETIC_TERMINAL",
        "job_sha256":expected,
        "job_id":job["job_id"],
        "surface_run_id":str(run_id),
        "workflow_ref":workflow_ref,
        "results":answers,
        "private_authority_granted":False,
        "encrypted_private_input":False,
        "broker_mutations":False,
    }

def main() -> int:
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--packet",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        raw=a.packet.read_bytes()
        if len(raw)>MAX_BYTES:
            raise ValueError("packet_too_large")
        request=json.loads(raw)
        run_id=os.environ["GITHUB_RUN_ID"]
        wf=f'{os.environ["GITHUB_REPOSITORY"]}/.github/workflows/cc-general-public-synthetic-v1.yml@refs/heads/{os.environ["GITHUB_REF_NAME"]}'
        receipt=validate_and_run(request,run_id,wf)
        a.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    except Exception:
        print("CC_GENERAL_PUBLIC_SYNTHETIC=FAIL_CLOSED")
        return 1
    print("CC_GENERAL_PUBLIC_SYNTHETIC=PASS")
    print("CC_GENERAL_SYNTHETIC_JOB_IDENTITY_BOUND=1")
    print("CC_GENERAL_PRIVATE_INPUT_ACCEPTED=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
