"""Fixed output A1 ciphertext adapter for one native FORM v23 jar Cycles view.

Only the existing P256/AES-GCM seal/open primitives are used. This module does
not grant placement authority, dispatch compute, nor turn source QA into native
render proof. Its files are *private result-consumer* inputs after an admitted
signed job finishes. The unencrypted files never belong in public GitHub.
"""
from __future__ import annotations
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import zipfile

from scripts.creative.form_v23_fixed_payload_v1 import (
    CHUNK, MAX_CHUNKS, RUN_RE, SHA_RE, fixed_job, fixed_job_digest)

SCHEMA="incomeengine.form_v23.fixed_blender_encrypted_result.v1"
RECEIPT_SCHEMA="incomeengine.form_v23.paired_fixed_jar_hero_cycles_review.v1"
FILES=("jar_editable_native.blend","jar_hero_cycles.png",
       "FORM_V23_SECOND_PROCESS_SCENE_QA.json",
       "FORM_V23_JAR_HERO_NATIVE_REVIEW_RECEIPT.json")
MAX_RESULT=32*1024*1024
MAX_FILE=24*1024*1024
MAX_PARTS=(MAX_RESULT+CHUNK-1)//CHUNK


def canonical(node):
    return json.dumps(node,sort_keys=True,separators=(",", ":"),ensure_ascii=True,allow_nan=False).encode()


def sha(raw):return sha256(raw).hexdigest()


def validate_native_outputs(files:dict[str,bytes], *, job:dict) -> dict:
    fixed_job(job)
    if not isinstance(files,dict) or set(files)!=set(FILES):raise ValueError("unexpected_native_output_names")
    for name,blob in files.items():
        if not isinstance(blob,bytes) or not 0<len(blob)<=MAX_FILE:
            raise ValueError("native_output_size_invalid:"+name)
    if not files[FILES[0]].startswith(b"BLENDER"):
        raise ValueError("not_native_blend")
    png=files[FILES[1]]
    if not (len(png)>33 and png[:8]==b"\x89PNG\r\n\x1a\n" and png[12:16]==b"IHDR"):
        raise ValueError("not_png")
    w,h=struct.unpack_from(">II",png,16)
    if (w,h)!=(768,768):raise ValueError("invalid_native_review_dimensions")
    qa=json.loads(files[FILES[2]])
    if (not isinstance(qa,dict) or qa.get("status")!="PASS_NATIVE_SECOND_PROCESS_READBACK"
        or qa.get("product_mesh_count")!=3 or qa.get("scene_engine")!="CYCLES"):
        raise ValueError("second_blender_process_not_proven")
    r=json.loads(files[FILES[3]])
    if (not isinstance(r,dict) or r.get("schema")!=RECEIPT_SCHEMA
        or r.get("status")!="ONE_NATIVE_JAR_REVIEW_EXECUTED__NOT_MERCHANT_READY"
        or r.get("native_blender_executed") is not True
        or r.get("selected_variant")!=job["variant"]):
        raise ValueError("native_receipt_invalid")
    expected={
      "original":"cb9fc92c5161e34b5a45aaf862038acad6544efb722db7636713b5241314f4e4",
      "candidate":"46a481ed9c71f2565ffcd0ddeecc3e0ab0f57eee43d942ecab2251d8799d32a5",
    }
    if r.get("selected_jar_sha256")!=expected[job["variant"]]:
        raise ValueError("wrong_frozen_product_model")
    if r.get("independent_second_blender_process")!=qa:
        raise ValueError("second_process_qa_not_bound")
    entries={FILES[0]:r.get("output",{}).get("blend",{}),FILES[1]:r.get("output",{}).get("hero_png",{})}
    for name,metadata in entries.items():
        if metadata.get("sha256")!=sha(files[name]) or metadata.get("bytes")!=len(files[name]):
            raise ValueError("native_receipt_artifact_sha_or_length_mismatch")
    if r.get("output",{}).get("hero_png",{}).get("dimensions")!=[768,768]:
        raise ValueError("native_png_dimensions_receipt_missing")
    return {n:{"bytes":len(b),"sha256":sha(b)} for n,b in sorted(files.items())}


def seal_native_outputs(files, *, job, run_id, recipient_public_b64, seal_fn):
    if not isinstance(run_id,str) or not RUN_RE.fullmatch(run_id):raise ValueError("run_id_invalid")
    manifests=validate_native_outputs(files,job=job)
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=False) as z:
        for n in FILES:
            i=zipfile.ZipInfo(n,date_time=(1980,1,1,0,0,0));i.create_system=3
            i.external_attr=0o100600<<16;i.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(i,files[n],compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    raw=archive.getvalue()
    if not 0<len(raw)<=MAX_RESULT:raise ValueError("native_result_archive_too_large")
    chunks=[raw[i:i+CHUNK] for i in range(0,len(raw),CHUNK)]
    if not 1<=len(chunks)<=MAX_PARTS:raise ValueError("result_parts_invalid")
    header={"schema":SCHEMA,"run_id":run_id,"job_sha256":fixed_job_digest(job),
       "variant":job["variant"],"archive_sha256":sha(raw),"archive_bytes":len(raw),
       "part_count":len(chunks),"file_manifest":manifests}
    ret={"header.json":seal_fn(canonical(header),recipient_public_b64=recipient_public_b64,
               run_id=run_id+":form:header",direction="result")}
    for i,part in enumerate(chunks):
        ret[f"part-{i:04d}.json"]=seal_fn(part,recipient_public_b64=recipient_public_b64,
               run_id=run_id+f":form:part:{i:04d}",direction="result")
    ret["manifest.json"]={"schema":SCHEMA,"run_id":run_id,"result_kind":"CIPHERTEXT_ONLY",
          "header":"header.json","parts":[f"part-{i:04d}.json" for i in range(len(chunks))]}
    return ret


def open_native_outputs(sealed:dict, *, job, run_id, recipient_private_b64, open_capsule_fn):
    fixed_job(job)
    if not isinstance(run_id,str) or not RUN_RE.fullmatch(run_id):raise ValueError("run_id_invalid")
    m=sealed.get("manifest.json")
    if (not isinstance(m,dict) or set(m)!={"schema","run_id","result_kind","header","parts"}
        or m["schema"]!=SCHEMA or m["run_id"]!=run_id
        or m["result_kind"]!="CIPHERTEXT_ONLY" or m["header"]!="header.json"):
        raise ValueError("result_manifest_invalid")
    names=m["parts"]
    if (not isinstance(names,list) or not 1<=len(names)<=MAX_PARTS
        or names!=[f"part-{i:04d}.json" for i in range(len(names))]
        or set(sealed)!={"header.json","manifest.json",*names}):
        raise ValueError("result_piece_names_invalid")
    head=json.loads(open_capsule_fn(sealed["header.json"],recipient_private_b64=recipient_private_b64,
                   expected_run_id=run_id+":form:header",expected_direction="result"))
    if (not isinstance(head,dict) or set(head)!={"schema","run_id","job_sha256","variant","archive_sha256","archive_bytes","part_count","file_manifest"}
        or head["schema"]!=SCHEMA or head["run_id"]!=run_id
        or head["job_sha256"]!=fixed_job_digest(job) or head["variant"]!=job["variant"]
        or type(head["archive_bytes"]) is not int or not 0<head["archive_bytes"]<=MAX_RESULT
        or head["part_count"]!=len(names)):
        raise ValueError("result_private_header_mismatch")
    out=bytearray()
    for i,n in enumerate(names):
        part=open_capsule_fn(sealed[n],recipient_private_b64=recipient_private_b64,
                     expected_run_id=run_id+f":form:part:{i:04d}",expected_direction="result")
        if not 0<len(part)<=CHUNK:raise ValueError("result_piece_length_rejected")
        out.extend(part)
        if len(out)>MAX_RESULT:raise ValueError("result_overlimit")
    raw=bytes(out)
    if len(raw)!=head["archive_bytes"] or sha(raw)!=head["archive_sha256"]:
        raise ValueError("result_archive_sha_mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sorted(z.namelist())!=sorted(FILES) or len(z.infolist())!=len(FILES):
            raise ValueError("result_file_list_invalid")
        for i in z.infolist():
            if i.is_dir() or i.flag_bits&1 or not 0<i.file_size<=MAX_FILE:
                raise ValueError("result_entry_invalid")
        files={n:z.read(n) for n in FILES}
    actual=validate_native_outputs(files,job=job)
    if actual!=head["file_manifest"]:raise ValueError("result_file_manifest_not_bound")
    return files
