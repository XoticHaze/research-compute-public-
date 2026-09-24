from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


FUTURES_MANAGER = """\
from pathlib import Path
import hashlib
import json
import pandas as pd

class FuturesManager:
    def __init__(self, config, ib):
        self.config=dict(config)
        self.ib=ib
        self.fut_dir=Path(config["DATA_OUTPUT_DIR"]) / "futures"
        self.fut_dir.mkdir(parents=True, exist_ok=True)

    def ingest_external_source_bars(self, root, month, source_tf, frame, *, target_timeframes=None, source_origin="external"):
        frame=frame.copy()
        frame["timestamp"]=pd.to_datetime(frame["timestamp"], utc=True)
        frame=frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        requested=[]
        for tf in [source_tf] + list(target_timeframes or []):
            if tf not in requested:
                requested.append(tf)
        frames={}
        evidence=[]
        out_dir=self.fut_dir / f"{root}-{month}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for tf in requested:
            node=frame.copy() if tf == source_tf else frame.iloc[::12].reset_index(drop=True).copy()
            node["FEATURE_TEST"]=range(len(node))
            manifest_hash=hashlib.sha256(f"{root}|{month}|{tf}|manifest".encode()).hexdigest()
            semantic_hash=hashlib.sha256(f"{root}|{month}|{tf}|semantic".encode()).hexdigest()
            node.attrs["feature_manifest"]={
                "feature_contract_mode":"canonical",
                "causal":True,
                "manifest_hash":manifest_hash,
                "feature_semantic_hash":semantic_hash,
                "features":[{"feature_id":"fixture","output_column":"FEATURE_TEST","causal":True}],
            }
            pretty=node.copy()
            pretty.to_csv(out_dir / f"{tf}.csv", index=False)
            node[["timestamp","FEATURE_TEST"]].to_csv(out_dir / f"{tf}.features.csv", index=False)
            frames[tf]=node
            evidence.append({
                "target_timeframe":tf,
                "source_timeframe":source_tf,
                "rows":len(node),
                "derived":tf != source_tf,
            })
        return {
            "ok":True,
            "schema":"mmibkr.futures_external_source_ingest.v1",
            "root":root,
            "month":month,
            "source_timeframe":source_tf,
            "source_origin":source_origin,
            "external_rows":len(frame),
            "merged_source_rows":len(frame),
            "frames":frames,
            "frame_evidence":evidence,
            "broker_request_made":False,
        }
"""

FEATURE_CONTRACT = """\
def verify_feature_manifest(manifest):
    if not isinstance(manifest,dict):
        raise ValueError("manifest object required")
    if manifest.get("feature_contract_mode") != "canonical":
        raise ValueError("manifest not canonical")
    if manifest.get("causal") is not True:
        raise ValueError("manifest not causal")
    if len(str(manifest.get("manifest_hash") or "")) != 64:
        raise ValueError("manifest hash invalid")
    return dict(manifest)
"""

LINEAGE_HELPER = """\
import json
def _load_lineage(path, *, source_sha256):
    node=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node,dict):
        raise ValueError("lineage object required")
    if str(node.get("source_sha256") or "").lower() != str(source_sha256).lower():
        raise ValueError("source lineage hash mismatch")
    if not str(node.get("authority") or "").strip():
        raise ValueError("source lineage authority required")
    return node

def _validate_dated_lineage(lineage, *, root, contract_month, source_timeframe):
    if str(lineage.get("root") or "").upper() != str(root).upper():
        raise ValueError("dated lineage root mismatch")
    if str(lineage.get("contract_month") or "") != str(contract_month):
        raise ValueError("dated lineage contract_month mismatch")
    if str(lineage.get("source_timeframe") or "") != str(source_timeframe):
        raise ValueError("dated lineage source_timeframe mismatch")
    semantics=str(lineage.get("timestamp_semantics") or "").strip()
    if semantics.lower() in {"","unknown","unresolved","date_only_unresolved","date-only-unresolved"}:
        raise ValueError("dated lineage must declare resolved timestamp_semantics")
    return {
        "root":str(root).upper(),
        "contract_month":str(contract_month),
        "source_timeframe":str(source_timeframe),
        "timestamp_semantics":semantics,
        "source_authority":str(lineage.get("authority") or ""),
    }
"""

SIDECAR_HELPER = """\
import hashlib
import json
from pathlib import Path

def publish_sidecar(feature_csv, manifest_json, *, expected_feature_sha256, expected_manifest_hash):
    feature_path=Path(feature_csv).resolve()
    manifest_path=Path(manifest_json).resolve()
    actual=hashlib.sha256(feature_path.read_bytes()).hexdigest()
    if actual != expected_feature_sha256:
        raise ValueError("feature sha mismatch")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("manifest_hash") or "") != expected_manifest_hash:
        raise ValueError("manifest hash mismatch")
    sidecar=feature_path.with_suffix(feature_path.suffix + ".manifest.json")
    sidecar.write_text(json.dumps({
        "contract_version":"feature_artifact_sidecar.v1",
        "feature_manifest":manifest,
        "feature_manifest_hash":expected_manifest_hash,
        "artifact":{"filename":feature_path.name,"sha256":actual,"size_bytes":feature_path.stat().st_size},
        "publication":{"feature_recompute":False,"downloader":False,"resampler":False,"feature_value_mutation":False},
    }, sort_keys=True) + "\\n", encoding="utf-8")
    return {
        "schema":"mm.canonical_feature_sidecar_publication.v1",
        "status":"PASS",
        "sidecar_path":str(sidecar),
        "feature_sha256":actual,
        "feature_manifest_hash":expected_manifest_hash,
    }
"""


class CanonicalFuturesDataMaterializeDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.source_root=self.root/"mm-source"
        op=self.source_root/"scripts"/"operator"
        op.mkdir(parents=True)
        (self.source_root/"scripts"/"__init__.py").write_text("",encoding="utf-8")
        (op/"__init__.py").write_text("",encoding="utf-8")

        manager=self.source_root/"futures_manager.py"
        manager.write_text(FUTURES_MANAGER,encoding="utf-8")
        (self.source_root/"feature_contract.py").write_text(FEATURE_CONTRACT,encoding="utf-8")
        (self.source_root/"timeframe_adapters.py").write_text("CANONICAL=True\n",encoding="utf-8")
        (op/"materialize_admitted_futures_source_canonical.py").write_text(LINEAGE_HELPER,encoding="utf-8")
        (op/"publish_canonical_feature_sidecar.py").write_text(SIDECAR_HELPER,encoding="utf-8")

        self.entry_blob=git_blob_sha1(manager.read_bytes())
        self.commit="a"*40
        self.archive="b"*64
        self.source_receipt={
            "schema":mod.SOURCE_RECEIPT_SCHEMA,
            "mmibkr_repository":mod.SOURCE_REPOSITORY,
            "requested_source_ref":self.commit,
            "mmibkr_head":self.commit,
            "source_archive_sha256":self.archive,
            "source_root":str(self.source_root.resolve()),
            "broker_credentials_materialized":False,
            "tws_credentials_required":False,
            "source_token_emitted":False,
            "paper_or_live_authority":False,
        }

        self.input_root=self.root/"inputs"
        self.input_root.mkdir()
        self.dataset=self.input_root/"mnq-202612-1min.csv"
        rows=["timestamp,open,high,low,close,volume"]
        for idx in range(24):
            rows.append(
                f"2026-09-23T{14 + idx//60:02d}:{idx%60:02d}:00Z,"
                f"{20000+idx},{20002+idx},{19998+idx},{20001+idx},{100+idx}"
            )
        self.dataset.write_text("\n".join(rows)+"\n",encoding="utf-8")
        self.lineage=self.input_root/"mnq-202612-lineage.json"
        self._write_lineage()
        self.receipt_dir=self.root/"runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def _write_lineage(self, **updates) -> None:
        payload={
            "schema":"test.admitted_futures_source.v1",
            "authority":"research-foundry-fixture",
            "source_sha256":hashlib.sha256(self.dataset.read_bytes()).hexdigest(),
            "root":"MNQ",
            "contract_month":"202612",
            "source_timeframe":"1Min",
            "target_timeframe":"12Min",
            "timestamp_semantics":"utc_bar_open",
            "admitted":True,
        }
        payload.update(updates)
        self.lineage.write_text(json.dumps(payload),encoding="utf-8")

    @staticmethod
    def _descriptor(path: Path) -> dict:
        raw=path.read_bytes()
        return {
            "relative_path":path.name,
            "sha256":hashlib.sha256(raw).hexdigest(),
            "bytes":len(raw),
        }

    def request(self) -> dict:
        return {
            "schema":mod.REQUEST_SCHEMA,
            "job_id":"materialize-mnq-202612",
            "capability_id":"CANONICAL_DATA_MATERIALIZE",
            "mmibkr":{
                "repository":mod.SOURCE_REPOSITORY,
                "commit":self.commit,
                "source_archive_sha256":self.archive,
            },
            "entrypoint":{
                "path":"futures_manager.py",
                "module":"futures_manager",
                "callable":"FuturesManager",
                "git_blob_sha1":self.entry_blob,
            },
            "arguments":{
                "asset_type":"futures",
                "symbol":"MNQ",
                "contract_month":"202612",
                "source_timeframe":"1Min",
                "target_timeframes":["1Min","12Min"],
                "source_origin":"governed_test_snapshot",
                "dataset":self._descriptor(self.dataset),
                "source_lineage":self._descriptor(self.lineage),
            },
            "resources":{"max_wall_seconds":60,"max_output_bytes":500000},
            "authority":mod.AUTHORITY,
            "forbidden_authorities":dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def execute(self, req=None):
        return mod.execute_request(
            req or self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )

    def test_dated_futures_materialization_preserves_canonical_artifacts_without_roll_authority(self):
        out=self.execute()
        self.assertFalse(out["cache_hit"])
        receipt=out["receipt"]; result=receipt["result"]
        self.assertEqual(result["schema"],"mmibkr.canonical_data_materialization.v1")
        self.assertEqual(result["asset_type"],"futures")
        self.assertEqual(result["symbol"],"MNQ")
        self.assertEqual(result["contract_month"],"202612")
        self.assertEqual(result["series_identity"],"dated_contract")
        self.assertEqual(result["frame_count"],2)
        self.assertEqual(result["artifact_count"],8)
        self.assertFalse(result["broker_request_made"])
        self.assertEqual(result["lineage_authority"]["timestamp_semantics"],"utc_bar_open")
        self.assertEqual(result["lineage_authority"]["source_authority"],"research-foundry-fixture")
        for key in (
            "market_data_acquisition","historical_data_requests","new_downloader",
            "roll_cutoff_selection","back_adjustment","continuous_splice",
            "broker_submit","broker_cancel","broker_flatten","strategy_spec_write",
            "runtime_activation","promotion_mutation","live_trading",
        ):
            self.assertFalse(result["safety"][key])

        self.assertEqual({row["timeframe"] for row in result["frames"]},{"1Min","12Min"})
        artifact_root=self.receipt_dir/"artifacts"/receipt["job_fingerprint"]
        for row in result["frames"]:
            self.assertRegex(row["feature_manifest_hash"],r"^[0-9a-f]{64}$")
            self.assertRegex(row["feature_semantic_hash"],r"^[0-9a-f]{64}$")
        for node in result["artifacts"]:
            self.assertFalse(Path(node["relative_path"]).is_absolute())
            target=artifact_root/node["relative_path"]
            self.assertTrue(target.is_file())
            self.assertEqual(target.stat().st_size,node["bytes"])
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),node["sha256"])

        rendered=json.dumps(receipt,sort_keys=True)
        self.assertNotIn(str(self.root),rendered)
        for dep in (
            "futures_manager.py","feature_contract.py","timeframe_adapters.py",
            "scripts/operator/materialize_admitted_futures_source_canonical.py",
            "scripts/operator/publish_canonical_feature_sidecar.py",
        ):
            self.assertRegex(result["canonical_dependencies"][dep],r"^[0-9a-f]{40}$")

    def test_futures_lineage_root_month_and_timestamp_semantics_fail_closed(self):
        for updates, message in (
            ({"root":"ES"},"canonical dated futures lineage rejected"),
            ({"contract_month":"202603"},"canonical dated futures lineage rejected"),
            ({"timestamp_semantics":"unresolved"},"canonical dated futures lineage rejected"),
        ):
            self._write_lineage(**updates)
            req=self.request()
            with self.assertRaisesRegex(mod.CanonicalDispatchError,message):
                self.execute(req)
            self._write_lineage()

    def test_source_lineage_sha_and_continuous_month_fail_closed(self):
        req=self.request()
        req["arguments"]["source_lineage"]["sha256"]="c"*64
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"sha256 mismatch"):
            self.execute(req)

        req=self.request()
        req["arguments"]["contract_month"]="CONTINUOUS"
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"contract_month must be YYYYMM"):
            self.execute(req)

    def test_futures_entrypoint_must_match_asset_specific_binding(self):
        req=self.request()
        req["entrypoint"]={
            "path":"data_manager.py",
            "module":"data_manager",
            "callable":"DataManager",
            "git_blob_sha1":"d"*40,
        }
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"entrypoint path does not match capability registry"):
            self.execute(req)

    def test_requires_receipt_storage_and_cached_artifact_tamper_is_detected(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

        first=self.execute()
        second=self.execute()
        self.assertTrue(second["cache_hit"])
        result=first["receipt"]["result"]
        artifact_root=self.receipt_dir/"artifacts"/first["receipt"]["job_fingerprint"]
        target=artifact_root/result["artifacts"][0]["relative_path"]
        target.write_text("tampered\n",encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"artifact hash mismatch"):
            self.execute()


if __name__=="__main__":
    unittest.main()
