from __future__ import annotations
"""Fail-closed validator/executor boundary for sealed research jobs."""
import argparse, hashlib, json, subprocess, tarfile, tempfile
from pathlib import Path

FORBIDDEN={"payload","plaintext","command","shell","script","promotion","runtime","trading"}
ALLOWED_TOP={"schema_version","job_id","mode","authority","ciphertext","encryption","harness"}
M1_HARNESS="research_foundry_m1_h12_r18_v1"
ALLOWED_HARNESS={"deterministic_sum_v1","research_foundry_pr285_stage1_v1",M1_HARNESS}
PR285_FILES={"payload-manifest.json","research/industry_relative_value_stage1_20260905.py","research/energy_ep_relative_value_stage1_contract_20260905.json","research/aerospace_defense_relative_value_stage1_contract_20260905.json","research/industry_component_stage1_mechanical.py","tests/test_industry_relative_value_stage1_contracts_20260905.py"}
M1_SOURCE_BLOBS={
".github/workflows/m1-h12-frozen-robustness-r18.yml":"e82a1c14e012a95e7c4916c50a76d7cee7896a03",
"m1_h12_frozen_folds_run33358415504.json":"09ebd0ef29765a4e55fbd6122d8d30121f44d6f0",
"m1_h12_runner_oos_probability_r18.patch":"0e0c812c2e7d500a4e28277d38c641ab82327c8e",
"pyproject.toml":"6b15201c4ad7600db2edebea820113af9c2e578b",
"schemas/foundry.mm_frozen_folds.v1.schema.json":"012886780504a24f4e3ccb3770a428c911043669",
"schemas/foundry.mm_ml_challenger_task.v2.schema.json":"2dd60760b1ad0a7201c724d3b667daa106400b0f",
"schemas/mm.training_corpus.v1.schema.json":"67cd88efebe880610afc459f018dfdde778684af",
"src/foundry_mm_ml/__init__.py":"49547bef38cc34c5795d55bde940568e1cb1cc33",
"src/foundry_mm_ml/frozen_folds.py":"bbb93a693569b6121788a88ddc2e61470ebdeac1",
"src/foundry_mm_ml/robustness.py":"15c70268a4eeb5f40d0871d844ca20e4be26239e",
"src/foundry_mm_ml/robustness_cli_r18.py":"0efa7e81e3bc95b579e4c77ae103c483cbfbd21a",
"src/foundry_mm_ml/runner.py":"018f882d4e212c33c4de3a398a8b85a5769f33cc",
"src/foundry_mm_ml/serious.py":"ac32d90c1b66c2973a19fcb5c7fb24c6a2aaf87d",
"tests/test_robustness_r18.py":"0852f04d455b4e0b6b363d94f81a4f785823145c"}
M1_SCI_SHA={
".github/workflows/m1-h12-frozen-robustness-r18.yml":"4f89bc91a3d0b1738b523100b386180549b4e85e5054361ded466e04e70e2112",
"m1_h12_frozen_folds_run33358415504.json":"b81c89ce34d4533036617f98edad112cf6522ca154331a8adf2c072a5ac20498",
"m1_h12_runner_oos_probability_r18.patch":"183a692f3c61fa855dbfba3a6aa26a0453037e44cf515c34378a97ac3a4cc02b",
"src/foundry_mm_ml/robustness.py":"4193ef8a5a6725dc25ce9d05290232a3159b626e021b8688c652b8e62113fb53",
"src/foundry_mm_ml/robustness_cli_r18.py":"a92e841ddab4b859c2ef42d2d572c242c80eab7c444d26b503bbbd847b2220f7",
"tests/test_robustness_r18.py":"3fa193690a2951ecfbf0d93548bef4912aadaa35215a8d0312353518f3e27ca6"}
M1_HEAD="90d8588bc0dfc0da2b502b6f61041c3debd78f10"; M1_TREE="e9ab8e04d94ec91365175d2869604af4543940a4"
FOLD_SHA="b81c89ce34d4533036617f98edad112cf6522ca154331a8adf2c072a5ac20498"
ANCHOR_SHA="07b0a02cbd32d5e3e0f015f17a2781f1be034333dbbabba751803de40bfdb775"
M1_DATASET_ID="mnq_external_unadjusted_12m_v1"
M1_CORPUS_SHA="c5607530eb36d352ec0519a70f82032d9ed6a87b1ceb3c0cf2beb6202b71889f"
M1_TARGET="forward_12bar_close_direction_within_contract.v1"
EXPECTED_FOLDS=[
{"fold":0,"train_start":0,"train_end_exclusive":84828,"test_start":84840,"test_end_exclusive":106050,"embargo_rows":12},
{"fold":1,"train_start":0,"train_end_exclusive":106038,"test_start":106050,"test_end_exclusive":127260,"embargo_rows":12},
{"fold":2,"train_start":0,"train_end_exclusive":127248,"test_start":127260,"test_end_exclusive":148470,"embargo_rows":12},
{"fold":3,"train_start":0,"train_end_exclusive":148458,"test_start":148470,"test_end_exclusive":169681,"embargo_rows":12},
]

def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for c in iter(lambda:f.read(1048576),b""): h.update(c)
 return h.hexdigest()
def git_blob(path):
 b=Path(path).read_bytes(); return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def validate_manifest(path):
 obj=json.loads(Path(path).read_text()); unexpected=set(obj)-ALLOWED_TOP
 if unexpected or FORBIDDEN.intersection(obj): raise RuntimeError("manifest fields forbidden/unexpected")
 if obj.get("schema_version")!="sealed-job-v1" or obj.get("mode")!="sealed" or obj.get("authority")!="research_only": raise RuntimeError("manifest identity invalid")
 if obj.get("harness") not in ALLOWED_HARNESS: raise RuntimeError("unapproved fixed harness")
 c=obj.get("ciphertext"); e=obj.get("encryption")
 if not isinstance(c,dict) or set(c)!={"path","sha256"}: raise RuntimeError("ciphertext shape")
 if not isinstance(e,dict) or set(e)!={"algorithm","recipient_key_id"} or e["algorithm"]!="age-x25519": raise RuntimeError("encryption shape")
 cp=Path(c["path"])
 if not cp.is_file() or sha256(cp)!=c["sha256"]: raise RuntimeError("ciphertext digest mismatch")
 if not e["recipient_key_id"].startswith("sha256:"): raise RuntimeError("recipient fingerprint")
 return obj
def safe_extract(tf,root,expected):
 names={m.name for m in tf.getmembers()}
 if names!=expected: raise RuntimeError("payload file set mismatch")
 for m in tf.getmembers():
  target=(root/m.name).resolve()
  if root.resolve() not in target.parents or not m.isfile(): raise RuntimeError("unsafe archive member")
 tf.extractall(root)
def quiet(args,cwd,timeout=3600):
 p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
 if p.returncode: raise RuntimeError("private harness command failed rc="+str(p.returncode))
def run_pr285(payload_path):
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)
  with tarfile.open(payload_path,"r:gz") as tf: safe_extract(tf,root,PR285_FILES)
  pm=json.loads((root/"payload-manifest.json").read_text())
  if pm.get("schema")!="research-foundry-pr285-stage1-payload-v1" or pm.get("harness")!="research_foundry_pr285_stage1_v1": raise RuntimeError("PR285 identity")
  expected=pm.get("files") or {}
  if set(expected)!=PR285_FILES-{"payload-manifest.json"}: raise RuntimeError("PR285 files")
  for rel,d in expected.items():
   if sha256(root/rel)!=d: raise RuntimeError("PR285 digest")
  quiet(["python","-m","py_compile","research/industry_relative_value_stage1_20260905.py"],root)
  quiet(["python","-m","pytest","-q","tests/test_industry_relative_value_stage1_contracts_20260905.py"],root)
  results={}
  for fam,contract in {"energy_ep":"research/energy_ep_relative_value_stage1_contract_20260905.json","aerospace_defense":"research/aerospace_defense_relative_value_stage1_contract_20260905.json"}.items():
   out=root/(fam+".json"); quiet(["python","-m","research.industry_relative_value_stage1_20260905","--contract",contract,"--output",str(out)],root)
   r=json.loads(out.read_text())
   if r.get("family")!=fam or r.get("external_holdouts",{}).get("loaded") is not False: raise RuntimeError("PR285 result")
   results[fam]={"classification":r.get("classification"),"external_holdouts_loaded":False,"result_sha256":sha256(out)}
  return {"harness":"research_foundry_pr285_stage1_v1","families":results}
def run_m1(payload_path):
 with tempfile.TemporaryDirectory(prefix="m1-sealed-") as td:
  root=Path(td)
  with tarfile.open(payload_path,"r:gz") as tf:
   names={m.name for m in tf.getmembers()}
   if "payload-manifest.json" not in names: raise RuntimeError("M1 manifest missing")
   for m in tf.getmembers():
    target=(root/m.name).resolve()
    if root.resolve() not in target.parents or not m.isfile(): raise RuntimeError("unsafe M1 archive")
    if m.name != "payload-manifest.json" and not (m.name.startswith("anchor/") or m.name in M1_SOURCE_BLOBS):
     raise RuntimeError("unexpected M1 archive namespace")
   tf.extractall(root)
  pm=json.loads((root/"payload-manifest.json").read_text())
  required={"schema","harness","authority","source_head","source_tree","source_git_blobs","scientific_sha256","anchor"}
  if set(pm)!=required or pm["schema"]!="research-foundry-m1-h12-sealed-payload-r19-v1" or pm["harness"]!=M1_HARNESS or pm["authority"]!="research_only": raise RuntimeError("M1 manifest identity")
  if pm["source_head"]!=M1_HEAD or pm["source_tree"]!=M1_TREE or pm["source_git_blobs"]!=M1_SOURCE_BLOBS or pm["scientific_sha256"]!=M1_SCI_SHA: raise RuntimeError("M1 source closure mismatch")
  expected={"payload-manifest.json","anchor/preservation_manifest.json"}|set(M1_SOURCE_BLOBS)
  pres=json.loads((root/"anchor/preservation_manifest.json").read_text())
  if pres.get("schema")!="market_research.m1_h12_minimal_refit_anchor.v2" or pres.get("source_artifact_id")!=9784705106 or pres.get("source_artifact_digest")!="sha256:"+ANCHOR_SHA or pres.get("dataset_id")!=M1_DATASET_ID: raise RuntimeError("anchor identity")
  if set(pres.get("files",{}))!={"model-task","corpus-manifest","dataset","frozen-folds"}: raise RuntimeError("anchor labels")
  for label,meta in pres["files"].items():
   if set(meta)!={"path","bytes","sha256"}: raise RuntimeError("anchor file metadata shape "+label)
   rel="anchor/"+meta["path"]; expected.add(rel); p=(root/rel).resolve()
   if root.resolve() not in p.parents: raise RuntimeError("anchor manifest path traversal "+label)
   if not p.is_file() or p.stat().st_size!=meta["bytes"] or sha256(p)!=meta["sha256"]: raise RuntimeError("anchor file mismatch "+label)
  fp=pres.get("fold_provenance") or {}
  if fp!={"source_run_id":33358415504,"source_job_id":99723580022,"oos_unique_rows":84841,"tail_purge_rows":0,"embargo_rows":12}: raise RuntimeError("fold provenance")
  if names!=expected: raise RuntimeError("M1 exact payload file set mismatch")
  for rel,blob in M1_SOURCE_BLOBS.items():
   p=root/rel
   if git_blob(p)!=blob: raise RuntimeError("source blob mismatch "+rel)
  for rel,d in M1_SCI_SHA.items():
   if sha256(root/rel)!=d: raise RuntimeError("scientific digest mismatch "+rel)
  contract_path=Path(__file__).resolve().parents[1]/"contracts"/"research_foundry_m1_h12_r18_v1.json"
  contract=json.loads(contract_path.read_text(encoding="utf-8"))
  if contract.get("harness")!=M1_HARNESS or contract.get("authority")!="research_only": raise RuntimeError("public contract identity")
  cs=contract.get("source") or {}
  if cs.get("head")!=M1_HEAD or cs.get("git_tree")!=M1_TREE: raise RuntimeError("public contract source identity")
  if contract.get("scientific_files_sha256")!=M1_SCI_SHA: raise RuntimeError("public contract scientific hashes")
  pyproject=(root/"pyproject.toml").read_text(encoding="utf-8")
  required_pins=("numpy==1.26.4","pandas==2.2.3","scikit-learn==1.5.2","xgboost==1.7.6","pyarrow==17.0.0","jsonschema==4.23.0","joblib==1.4.2","zstandard==0.25.0","pytest==8.3.3")
  if any(pin not in pyproject for pin in required_pins): raise RuntimeError("sealed pyproject dependency authority mismatch")
  if sha256(root/"anchor"/pres["files"]["frozen-folds"]["path"])!=FOLD_SHA: raise RuntimeError("fold sha")
  quiet(["git","apply","--check","m1_h12_runner_oos_probability_r18.patch"],root); quiet(["git","apply","m1_h12_runner_oos_probability_r18.patch"],root)
  quiet(["python","-m","pip","install","-e",".[test]"],root)
  quiet(["python","-m","py_compile","src/foundry_mm_ml/robustness.py","src/foundry_mm_ml/robustness_cli_r18.py","tests/test_robustness_r18.py"],root)
  quiet(["python","-m","pytest","-q","tests/test_robustness_r18.py"],root)
  out=root/"robustness-results"
  quiet(["python","-m","foundry_mm_ml.robustness_cli_r18","anchor/"+pres["files"]["model-task"]["path"],"--output",str(out),"--frozen-folds","anchor/"+pres["files"]["frozen-folds"]["path"],"--frozen-folds-sha256",FOLD_SHA],root)
  result=out/"robustness_result.json"; node=json.loads(result.read_text())
  if node.get("selection")!="NONE__REPORT_ALL" or list(node.get("families",{}))!=["xgboost","logistic_regression","hist_gradient_boosting","extra_trees"]: raise RuntimeError("M1 result identity")
  for fam in node["families"].values():
   if list(fam["ablations"])!=["price_path","volume_liquidity","volatility","momentum_trend","calendar"]: raise RuntimeError("ablation identity")
   if fam.get("base",{}).get("folds")!=EXPECTED_FOLDS: raise RuntimeError("frozen fold boundaries")
  a=node.get("authority") or {}
  if a.get("dataset_id")!=M1_DATASET_ID or a.get("corpus_sha256")!=M1_CORPUS_SHA or a.get("target_contract")!=M1_TARGET: raise RuntimeError("result authority")
  return {"harness":M1_HARNESS,"result_sha256":sha256(result),"source_head":M1_HEAD,"source_tree":M1_TREE,"frozen_fold_sha256":FOLD_SHA,"oos_rows":84841,"families":list(node["families"])}
def run_fixed_harness(harness,payload_path):
 if harness=="deterministic_sum_v1":
  p=json.loads(payload_path.read_text())
  if set(p)!={"schema","values"} or p["schema"]!="sealed-fixture-v1": raise RuntimeError("fixture")
  return {"harness":harness,"count":len(p["values"]),"sum":float(sum(p["values"]))}
 if harness=="research_foundry_pr285_stage1_v1": return run_pr285(payload_path)
 if harness==M1_HARNESS: return run_m1(payload_path)
 raise RuntimeError("harness not implemented")
def main():
 p=argparse.ArgumentParser();p.add_argument("manifest");p.add_argument("--decrypted");a=p.parse_args()
 m=validate_manifest(Path(a.manifest)); out={"manifest_status":"PASS","job_id":m["job_id"],"authority":m["authority"]}
 if a.decrypted: out["harness_result"]=run_fixed_harness(m["harness"],Path(a.decrypted))
 print(json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
