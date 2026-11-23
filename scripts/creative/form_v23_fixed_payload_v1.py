"""Fixed private FORM v23 jar-Cycles input, data binding only.

This is a workload-specific adapter, NOT placement, signer, workflow trigger,
remote shell, runtime selector, or a way to introduce unreviewed scripts.
All product assets stay in sealed request chunks; no private bytes are written
into the public source repository. Execution requires a separately admitted
CommandCenter placed job and a trusted live Blender runtime.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

SCHEMA = "incomeengine.form_v23.fixed_blender_input.v1"
ARCHIVE_SCHEMA = "incomeengine.form_v23.immutable_private_payload.v1"
CIPHER_SCHEMA = "incomeengine.form_v23.input_ciphertext.v1"
PINNED_RELEASE_SHA = "c7b82ff8ab4bd1a2efc72bd865462e28454357fcda11f8d2fe82de75415974cc"
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_BLOB_BYTES = 4 * 1024 * 1024
CHUNK = 196608
MAX_CHUNKS = (MAX_ZIP_BYTES + CHUNK - 1)//CHUNK
VARIANTS = ("original", "candidate")
RECIPE = "form_v23_jar_hero_768_cycles_v1"
IN_RE = re.compile(r"^blender-form-v23-[a-z0-9-]{6,48}$")
RUN_RE = re.compile(r"^[A-Za-z0-9._:-]{6,128}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# These are hash-pinned native-reviewed *source candidate* inputs, not claimed
# production-ready assets or permission to run an arbitrary third-party script.
FIXED_MEMBERS = {
    "assets/jar_hero_yup.glb": (
        "native_input/assets/jar_hero_yup.glb",
        "cb9fc92c5161e34b5a45aaf862038acad6544efb722db7636713b5241314f4e4"),
    "candidate/jar_hero_yup.glb": (
        "native_input/candidate/jar_hero_yup.glb",
        "46a481ed9c71f2565ffcd0ddeecc3e0ab0f57eee43d942ecab2251d8799d32a5"),
    "source/form_cycles_native_52_v23_candidate.py": (
        "native_input/source/form_cycles_native_52_v23_candidate.py",
        "3f393707e09c0c03416c93fd0c2ed12956822247ba44bc8fb19f81c8d8b096c6"),
    "source/verify_form_v23_native_shader_readback.py": (
        "native_input/source/verify_form_v23_native_shader_readback.py",
        "aa217eae8ba0568e91018ab874c55137db393768e2977b51bd450c31a303c569"),
    "source/form_v23_pair_first_native_review.py": (
        "source/form_v23_pair_first_native_review.py",
        "b7d822fcabc3bc8b2e712b0c67bfb785137a5cd41c3a71c8133b4aacf07d3737"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(node: dict) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def fixed_job(job: dict) -> dict:
    """A caller-written job is a *proposal*. Its validation is not placement."""
    if not isinstance(job, dict) or set(job) != {"schema", "job_id", "recipe_id", "variant",
        "classification", "private_bundle_sha256", "source", "revision", "parent_job_sha256"}:
        raise ValueError("job_shape_rejected")
    if job["schema"] != SCHEMA or job["recipe_id"] != RECIPE:
        raise ValueError("unapproved_product_recipe")
    if type(job["job_id"]) is not str or not IN_RE.fullmatch(job["job_id"]):
        raise ValueError("job_identity_rejected")
    if job["variant"] not in VARIANTS or job["classification"] != "private_encrypted_fixed_recipe":
        raise ValueError("unapproved_variant_or_trust_class")
    if not isinstance(job["private_bundle_sha256"], str) or not SHA_RE.fullmatch(job["private_bundle_sha256"]):
        raise ValueError("private_input_digest_missing")
    if type(job["revision"]) is not int or not 0 <= job["revision"] <= 2:
        raise ValueError("revision_limit")
    if ((job["revision"] == 0 and job["parent_job_sha256"] is not None) or
        (job["revision"] > 0 and (not isinstance(job["parent_job_sha256"], str)
                                    or not SHA_RE.fullmatch(job["parent_job_sha256"])))):
        raise ValueError("invalid_revision_chain")
    source=job["source"]
    if (not isinstance(source,dict) or set(source)!={"repository","commit"}
        or source["repository"] != "XoticHaze/research-compute-public-"
        or not isinstance(source["commit"],str)
        or not re.fullmatch(r"[0-9a-f]{40}",source["commit"])):
        raise ValueError("executor_identity_invalid")
    if len(canonical(job))>2048:
        raise ValueError("oversize_product_job")
    return job


def fixed_job_digest(job:dict)->str:
    return sha(canonical(fixed_job(job)))


def _exact_zip_members(raw: bytes, *, source_names: set[str]) -> dict[str, bytes]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ZIP_BYTES:
        raise ValueError("input_archive_size_invalid")
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        infos=zf.infolist()
        if len(infos)!=len(source_names) or set(zf.namelist())!=source_names:
            raise ValueError("unapproved_source_members_or_duplicates")
        out={}
        for info in infos:
            if info.is_dir() or info.flag_bits&1 or info.external_attr>>16&0o170000==0o120000:
                raise ValueError("archive_link_directory_or_encryption")
            if info.filename.startswith("/") or "\\" in info.filename or ".." in info.filename.split("/"):
                raise ValueError("archive_traversal")
            if not 0 < info.file_size <= MAX_BLOB_BYTES or info.compress_size > MAX_ZIP_BYTES:
                raise ValueError("archive_member_size")
            out[info.filename]=zf.read(info)
        return out


def construct_fixed_payload_from_release(release: bytes) -> tuple[bytes, dict]:
    """Owner-side deterministic private payload from immutable existing release."""
    if not isinstance(release, bytes) or not 0 < len(release) <= 12_000_000:
        raise ValueError("immutable_release_size")
    if sha(release) != PINNED_RELEASE_SHA:
        raise ValueError("original_release_sha256_mismatch")
    with zipfile.ZipFile(io.BytesIO(release)) as zf:
        names=set(zf.namelist()); out={}
        for dst,(src,pin) in FIXED_MEMBERS.items():
            if src not in names or zf.namelist().count(src)!=1:
                raise ValueError("original_release_member_missing_or_duplicate")
            info=zf.getinfo(src)
            if info.is_dir() or info.flag_bits&1 or info.external_attr>>16&0o170000==0o120000:
                raise ValueError("source_archive_symlink_or_encrypted")
            if not 0 < info.file_size <= MAX_BLOB_BYTES:
                raise ValueError("original_release_member_size")
            raw=zf.read(src)
            if sha(raw)!=pin:
                raise ValueError("original_source_pin_mismatch:"+dst)
            out[dst]=raw
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,
                         allowZip64=False) as zf:
        for name in sorted(FIXED_MEMBERS):
            i=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            i.create_system=3;i.external_attr=0o100600 << 16
            i.compress_type=zipfile.ZIP_DEFLATED
            zf.writestr(i,out[name],compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    data=archive.getvalue()
    if len(data)>MAX_ZIP_BYTES:raise ValueError("fixed_payload_too_large")
    checked=inspect_fixed_payload(data)
    return data, {"schema":ARCHIVE_SCHEMA,"payload_sha256":sha(data),"bytes":len(data),"members":checked}


def inspect_fixed_payload(payload:bytes)->dict[str,dict]:
    out=_exact_zip_members(payload,source_names=set(FIXED_MEMBERS))
    if sum(len(x) for x in out.values()) > 8_000_000:raise ValueError("payload_expanded_size")
    for name,(_,expected) in FIXED_MEMBERS.items():
        if sha(out[name]) != expected:
            raise ValueError("private_member_digest_mismatch:"+name)
    return {name:{"bytes":len(raw),"sha256":sha(raw)} for name,raw in sorted(out.items())}


def read_fixed_payload(payload:bytes)->dict[str,bytes]:
    inspect_fixed_payload(payload)
    return _exact_zip_members(payload,source_names=set(FIXED_MEMBERS))


def make_sealed_inputs(payload:bytes, *, job:dict, run_id:str, recipient_public_b64:str,
                       seal_fn) -> dict[str,dict]:
    """Use existing A1 seal, input ciphertext first, manifest last after admission.

    No network/dispatch/signing occurs here. Producer's caller must validate the
    independently signed PLACED identity before publishing any ciphertext.
    """
    fixed_job(job)
    if not isinstance(run_id,str) or not RUN_RE.fullmatch(run_id):raise ValueError("run_id_invalid")
    if sha(payload)!=job["private_bundle_sha256"]:raise ValueError("job_input_digest_mismatch")
    inspect_fixed_payload(payload)
    chunks=[payload[i:i+CHUNK] for i in range(0,len(payload),CHUNK)]
    if not 1<=len(chunks)<=MAX_CHUNKS:raise ValueError("input_chunk_limit")
    sealed={}
    header={"schema":ARCHIVE_SCHEMA,"run_id":run_id,"job_sha256":fixed_job_digest(job),
            "archive_sha256":sha(payload),"archive_bytes":len(payload),"part_count":len(chunks)}
    sealed["header.json"]=seal_fn(canonical(header),recipient_public_b64=recipient_public_b64,
                                  run_id=run_id+":input:header",direction="request")
    for i,raw in enumerate(chunks):
        sealed[f"part-{i:04d}.json"]=seal_fn(raw,recipient_public_b64=recipient_public_b64,
                                            run_id=run_id+f":input:{i:04d}",direction="request")
    sealed["manifest.json"]={"schema":CIPHER_SCHEMA,"run_id":run_id,
        "result_kind":"CIPHERTEXT_ONLY", "header":"header.json",
        "parts":[f"part-{i:04d}.json" for i in range(len(chunks))]}
    return sealed


def open_sealed_inputs(sealed:dict, *, job:dict, run_id:str, recipient_private_b64:str,
                       open_capsule_fn) -> bytes:
    """Strict run-bound A1 decryption; nothing from caller chooses file names."""
    fixed_job(job)
    if not isinstance(run_id,str) or not RUN_RE.fullmatch(run_id):raise ValueError("run_id_invalid")
    m=sealed.get("manifest.json")
    if (not isinstance(m,dict) or set(m)!={"schema","run_id","result_kind","header","parts"}
        or m["schema"]!=CIPHER_SCHEMA or m["run_id"]!=run_id
        or m["result_kind"]!="CIPHERTEXT_ONLY" or m["header"]!="header.json"):
        raise ValueError("cipher_manifest_invalid")
    parts=m["parts"]
    if not isinstance(parts,list) or not 1<=len(parts)<=MAX_CHUNKS or parts!=[f"part-{i:04d}.json" for i in range(len(parts))]:
        raise ValueError("cipher_part_names_invalid")
    if set(sealed)!={"manifest.json","header.json",*parts}:
        raise ValueError("cipher_file_count_invalid")
    header=json.loads(open_capsule_fn(sealed["header.json"],recipient_private_b64=recipient_private_b64,
                 expected_run_id=run_id+":input:header",expected_direction="request"))
    if (not isinstance(header,dict) or set(header)!={"schema","run_id","job_sha256","archive_sha256","archive_bytes","part_count"}
        or header["schema"]!=ARCHIVE_SCHEMA or header["run_id"]!=run_id
        or header["job_sha256"]!=fixed_job_digest(job) or header["archive_sha256"]!=job["private_bundle_sha256"]
        or type(header["archive_bytes"]) is not int or not 0<header["archive_bytes"]<=MAX_ZIP_BYTES
        or header["part_count"]!=len(parts)):
        raise ValueError("cipher_private_header_invalid")
    buf=bytearray()
    for i,name in enumerate(parts):
        piece=open_capsule_fn(sealed[name],recipient_private_b64=recipient_private_b64,
              expected_run_id=run_id+f":input:{i:04d}",expected_direction="request")
        if not 0<len(piece)<=CHUNK:raise ValueError("cipher_piece_size_invalid")
        buf.extend(piece)
        if len(buf)>MAX_ZIP_BYTES:raise ValueError("cipher_expanded_too_large")
    raw=bytes(buf)
    if len(raw)!=header["archive_bytes"] or sha(raw)!=header["archive_sha256"]:
        raise ValueError("cipher_payload_digest_mismatch")
    inspect_fixed_payload(raw)
    return raw