from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalAutoTunerDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        bridge = self.source_root / "autotuner_strategy_bridge.py"
        bridge.write_text(
            "import hashlib,json\n"
            "def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
            "def normalize_strategy_spec(payload):\n"
            "    raw=dict(payload); spec=dict(raw.get('strategy_spec') or raw)\n"
            "    spec['strategy_id']=str(spec.get('strategy_id') or '')\n"
            "    spec['symbol']=str(spec.get('symbol') or '').upper()\n"
            "    spec['timeframe']=str(spec.get('timeframe') or '')\n"
            "    spec['parameters']=dict(spec.get('parameters') or raw.get('params') or {})\n"
            "    if not spec['strategy_id'] or not spec['symbol'] or not spec['timeframe']: raise ValueError('identity missing')\n"
            "    return {'strategy_spec':spec,'strategy_spec_digest':_digest(spec),'source_payload':raw}\n"
            "def candidate_mutations(strategy_spec, parameter_schema, *, tune_parameters=(), max_candidates=128):\n"
            "    params=dict(strategy_spec.get('parameters') or {}); keys=list(tune_parameters) or list(parameter_schema); out=[]\n"
            "    for key in keys:\n"
            "        node=parameter_schema[key]; cur=params.get(key,node.get('default'))\n"
            "        if node.get('type')=='float': vals=[cur-0.1,cur+0.1]\n"
            "        elif node.get('type')=='bool': vals=[not bool(cur)]\n"
            "        else: vals=[]\n"
            "        for value in vals:\n"
            "            out.append({'parameter':key,'from':cur,'to':value})\n"
            "            if len(out)>=max_candidates:return out\n"
            "    return out\n",
            encoding="utf-8",
        )
        consumption = self.source_root / "autotuner_parameter_consumption.py"
        consumption.write_text(
            "def parameter_schema_for_tuning(strategy_spec, parameter_schema, *, tune_parameters=()):\n"
            "    requested=list(tune_parameters)\n"
            "    allowed=['ENTRY_EXTREME','EXIT_EXTREME','ENABLE_DCA']\n"
            "    keys=requested or allowed\n"
            "    unknown=[k for k in keys if k not in parameter_schema]\n"
            "    if unknown: raise ValueError('unknown tunable parameter')\n"
            "    blocked=[k for k in keys if k not in allowed]\n"
            "    if blocked: raise ValueError('parameter consumption gate blocked')\n"
            "    filtered={k:dict(parameter_schema[k]) for k in keys}\n"
            "    return filtered, {'schema':'mm.autotuner_parameter_consumption.v1','strategy_id':'crw_score_multi_mode','searchable_parameters':keys,'authority':{'research_only':True,'automatic_strategy_spec_write':False,'runtime_activation':False,'broker_submit':False}}\n",
            encoding="utf-8",
        )
        strategy_dir = self.source_root / "strategies" / "python"
        strategy_dir.mkdir(parents=True)
        (self.source_root / "strategies" / "__init__.py").write_text("", encoding="utf-8")
        (strategy_dir / "__init__.py").write_text("", encoding="utf-8")
        strategy = strategy_dir / "crw_score_multi_mode.py"
        strategy.write_text(
            "class CrwScoreMultiModeStrategy:\n"
            "    @classmethod\n"
            "    def parameter_schema(cls):\n"
            "        return {'ENTRY_EXTREME':{'type':'float','default':-2.8},'EXIT_EXTREME':{'type':'float','default':4.5},'ENABLE_DCA':{'type':'bool','default':True},'DCA_BASE_QTY':{'type':'int','default':1}}\n",
            encoding="utf-8",
        )
        self.blobs = {
            "bridge": blob(bridge.read_bytes()),
            "consumption": blob(consumption.read_bytes()),
            "strategy": blob(strategy.read_bytes()),
        }
        self.commit = "a" * 40
        self.archive = "b" * 64
        self.source_receipt = {
            "schema": mod.SOURCE_RECEIPT_SCHEMA,
            "mmibkr_repository": mod.SOURCE_REPOSITORY,
            "requested_source_ref": self.commit,
            "mmibkr_head": self.commit,
            "source_archive_sha256": self.archive,
            "source_root": str(self.source_root.resolve()),
            "broker_credentials_materialized": False,
            "tws_credentials_required": False,
            "source_token_emitted": False,
            "paper_or_live_authority": False,
        }
        self.spec = {
            "strategy_id": "crw_score_multi_mode",
            "symbol": "mnq",
            "timeframe": "12Min",
            "parameters": {"ENTRY_EXTREME": -2.8, "EXIT_EXTREME": 4.5, "ENABLE_DCA": True},
        }

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self, capability: str, *, tune=None, max_candidates=3) -> dict:
        if capability == "AUTOTUNER_PARAMETER_CONSUMPTION":
            path, module, callable_name, entry_blob = (
                "autotuner_parameter_consumption.py",
                "autotuner_parameter_consumption",
                "parameter_schema_for_tuning",
                self.blobs["consumption"],
            )
            arguments = {"strategy_spec": self.spec, "tune_parameters": list(tune or [])}
        else:
            path, module, callable_name, entry_blob = (
                "autotuner_strategy_bridge.py",
                "autotuner_strategy_bridge",
                "candidate_mutations",
                self.blobs["bridge"],
            )
            arguments = {"strategy_spec": self.spec, "tune_parameters": list(tune or []), "max_candidates": max_candidates}
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "auto-one",
            "capability_id": capability,
            "mmibkr": {"repository": mod.SOURCE_REPOSITORY, "commit": self.commit, "source_archive_sha256": self.archive},
            "entrypoint": {"path": path, "module": module, "callable": callable_name, "git_blob_sha1": entry_blob},
            "arguments": arguments,
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_parameter_consumption_derives_canonical_schema_and_receipt(self):
        out = mod.execute_request(
            self.request("AUTOTUNER_PARAMETER_CONSUMPTION", tune=["ENTRY_EXTREME"]),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
        )["receipt"]
        result = out["result"]
        self.assertEqual(list(result["searchable_parameter_schema"]), ["ENTRY_EXTREME"])
        self.assertEqual(result["consumption"]["searchable_parameters"], ["ENTRY_EXTREME"])
        self.assertEqual(result["canonical_dependencies"]["strategies/python/crw_score_multi_mode.py"], self.blobs["strategy"])
        self.assertRegex(result["strategy_spec_digest"], r"^[0-9a-f]{64}$")
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])

    def test_candidate_generation_is_bounded_and_read_only(self):
        out = mod.execute_request(
            self.request("AUTOTUNER_CANDIDATE_GENERATE", tune=["ENTRY_EXTREME", "ENABLE_DCA"], max_candidates=2),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
        )["receipt"]
        result = out["result"]
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertRegex(result["candidate_set_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("source_payload", result)
        self.assertFalse(result["consumption"]["authority"]["automatic_strategy_spec_write"])
        self.assertFalse(result["consumption"]["authority"]["runtime_activation"])
        self.assertFalse(result["consumption"]["authority"]["broker_submit"])

    def test_caller_cannot_supply_parameter_schema(self):
        req = self.request("AUTOTUNER_PARAMETER_CONSUMPTION")
        req["arguments"]["parameter_schema"] = {"ENTRY_EXTREME": {"type": "float", "default": 999}}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt)

    def test_candidate_budget_and_non_crw_strategy_fail_closed(self):
        req = self.request("AUTOTUNER_CANDIDATE_GENERATE", max_candidates=9999)
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "max_candidates"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt)
        req = self.request("AUTOTUNER_CANDIDATE_GENERATE")
        req["arguments"]["strategy_spec"]["strategy_id"] = "other"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "crw_score_multi_mode"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt)


if __name__ == "__main__":
    unittest.main()
