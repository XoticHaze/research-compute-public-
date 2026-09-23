from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalModelLabCompareValidateDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()

        comparison = self.source_root / "model_lab_comparison_matrix.py"
        comparison.write_text(
            "import csv,hashlib,json\n"
            "class Frame(list):\n"
            "    def __getitem__(self,key):\n"
            "        if isinstance(key,str): return [row[key] for row in self]\n"
            "        return super().__getitem__(key)\n"
            "class _PD:\n"
            "    @staticmethod\n"
            "    def read_csv(path):\n"
            "        with open(path,newline='',encoding='utf-8') as h: return Frame(list(csv.DictReader(h)))\n"
            "pd=_PD()\n"
            "def _sha(rows): return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
            "def align_training_matrices_for_comparison(incumbent,challenger,*,target_name,target_identity,min_shared_rows=5000):\n"
            "    left={row['timestamp']:row for row in incumbent}; right={row['timestamp']:row for row in challenger}\n"
            "    shared=sorted(set(left).intersection(right))\n"
            "    if len(shared)<int(min_shared_rows): raise ValueError('comparison matrices have insufficient shared observations')\n"
            "    for ts in shared:\n"
            "        if float(left[ts][target_name])!=float(right[ts][target_name]): raise ValueError('incumbent and challenger targets differ on shared timestamps')\n"
            "    li=Frame([left[ts] for ts in shared]); ri=Frame([right[ts] for ts in shared])\n"
            "    ev={'schema':'mm.model_lab_comparison_alignment_evidence.v1','target_name':target_name,'target_identity':target_identity,'incumbent_rows_before':len(incumbent),'challenger_rows_before':len(challenger),'shared_rows':len(shared),'incumbent_rows_dropped_for_alignment':len(incumbent)-len(shared),'challenger_rows_dropped_for_alignment':len(challenger)-len(shared),'first_timestamp':shared[0],'last_timestamp':shared[-1],'shared_timestamp_sha256':hashlib.sha256(json.dumps(shared).encode()).hexdigest(),'target_exact_match':True,'incumbent_feature_columns':['legacy_f'],'challenger_feature_columns':['canonical_f'],'incumbent_matrix_content_sha256':_sha(li),'challenger_matrix_content_sha256':_sha(ri),'safety':{'feature_recompute':False,'target_recompute':False,'resample':False,'fill_or_backfill':False,'row_reorder':False,'order_submission':False}}\n"
            "    return li,ri,ev\n",
            encoding="utf-8",
        )
        self.entry_blob = blob(comparison.read_bytes())

        validation = self.source_root / "model_lab_validation.py"
        validation.write_text(
            "def non_overlapping_purged_walk_forward_splits(index,*,start_year,test_span_years,embargo_bars,purge_bars,min_test_rows):\n"
            "    values=list(index); cut=max(1,len(values)//2); train=values[:max(0,cut-int(embargo_bars))]; test=values[cut:len(values)-int(purge_bars) if int(purge_bars) else None]\n"
            "    return [(train,test)] if len(test)>=int(min_test_rows) else []\n"
            "def split_manifest(splits,*,contract,embargo_bars,purge_bars,test_span_years):\n"
            "    rows=sum(len(test) for _,test in splits)\n"
            "    return {'schema':'mm.model_lab_walk_forward_manifest.v1','contract':contract,'fold_count':len(splits),'test_span_years':int(test_span_years),'embargo_bars':int(embargo_bars),'purge_bars':int(purge_bars),'oos_rows_total':rows,'oos_unique_timestamps':rows,'oos_repeated_timestamp_values':0,'oos_duplicate_row_contribution':0,'oos_max_multiplicity':1 if rows else 0,'unique_oos':True,'folds':[]}\n"
            "def require_target_safe_validation(manifest,target_spec):\n"
            "    h=int(target_spec.horizon_bars); emb=int(manifest['embargo_bars']); purge=int(manifest['purge_bars']); unique=bool(manifest['unique_oos'])\n"
            "    if not unique or emb<h or purge<h: raise ValueError('target validation boundary rejected')\n"
            "    return {'schema':'mm.model_lab_target_validation_manifest.v1','target_identity':target_spec.identity,'target_horizon_bars':h,'target_leakage_guard':target_spec.leakage_guard,'embargo_bars':emb,'purge_bars':purge,'train_boundary_safe':True,'test_boundary_safe':True,'unique_oos':True,'leakage_safe':True,'walk_forward_contract':manifest['contract'],'fold_count':manifest['fold_count']}\n",
            encoding="utf-8",
        )

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

        self.input_root = self.root / "inputs"
        self.input_root.mkdir()
        self.incumbent = self.input_root / "incumbent.csv"
        self.challenger = self.input_root / "challenger.csv"
        self._write_matrices()

    def tearDown(self) -> None:
        self.td.cleanup()

    def _write_matrices(self, challenger_targets: tuple[int, ...] = (0, 1, 0, 1, 0, 1)) -> None:
        timestamps = [f"2024-01-01T00:{minute:02d}:00Z" for minute in (0, 12, 24, 36, 48, 59)]
        self.incumbent.write_text(
            "timestamp,legacy_f,target\n"
            + "".join(f"{ts},{idx + 1},{idx % 2}\n" for idx, ts in enumerate(timestamps)),
            encoding="utf-8",
        )
        self.challenger.write_text(
            "timestamp,canonical_f,target\n"
            + "".join(f"{ts},{idx + 10},{challenger_targets[idx]}\n" for idx, ts in enumerate(timestamps)),
            encoding="utf-8",
        )

    def descriptor(self, path: Path) -> dict:
        raw = path.read_bytes()
        return {
            "relative_path": path.relative_to(self.input_root).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    def request(self) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "model-lab-compare",
            "capability_id": "MODEL_LAB_COMPARE_VALIDATE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "model_lab_comparison_matrix.py",
                "module": "model_lab_comparison_matrix",
                "callable": "align_training_matrices_for_comparison",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "target_name": "target",
                "target_identity": "fixture-target-h1",
                "min_shared_rows": 4,
                "horizon_bars": 1,
                "start_year": 2023,
                "test_span_years": 1,
                "embargo_bars": 1,
                "purge_bars": 1,
                "min_test_rows": 1,
                "inputs": {
                    "incumbent_matrix": self.descriptor(self.incumbent),
                    "challenger_matrix": self.descriptor(self.challenger),
                },
            },
            "resources": {"max_wall_seconds": 300, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_compare_validate_preserves_frozen_alignment_and_leakage_evidence(self):
        out = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = out["result"]
        self.assertEqual(result["schema"], "mmibkr.model_lab_compare_validate.v1")
        self.assertTrue(result["alignment"]["target_exact_match"])
        self.assertEqual(result["alignment"]["shared_rows"], 6)
        self.assertTrue(result["target_validation"]["leakage_safe"])
        self.assertEqual(result["walk_forward_validation"]["contract"], "canonical_nonoverlap_purged_compare")
        self.assertEqual(
            set(result["governed_inputs"]),
            {"incumbent_matrix", "challenger_matrix"},
        )
        self.assertEqual(
            set(result["canonical_dependencies"]),
            {"model_lab_comparison_matrix.py", "model_lab_validation.py"},
        )
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])
        self.assertTrue(result["safety"]["read_only"])
        for key in (
            "feature_recompute",
            "target_recompute",
            "training",
            "model_promotion",
            "strategy_spec_write",
            "runtime_activation",
            "order_submission",
            "live_trading_change",
        ):
            self.assertFalse(result["safety"][key])

    def test_governed_matrix_digest_drift_fails_before_private_owner(self):
        req = self.request()
        req["arguments"]["inputs"]["challenger_matrix"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_private_target_divergence_fails_with_sanitized_error_class(self):
        self._write_matrices(challenger_targets=(0, 1, 9, 1, 0, 1))
        req = self.request()
        with self.assertRaisesRegex(
            mod.CanonicalDispatchError,
            r"canonical MODEL_LAB_COMPARE_VALIDATE execution failed: ValueError",
        ) as ctx:
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )
        self.assertNotIn(str(self.root), str(ctx.exception))
        self.assertNotIn("targets differ", str(ctx.exception))

    def test_target_horizon_and_matrix_bounds_fail_closed(self):
        req = self.request()
        req["arguments"]["horizon_bars"] = 2
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "cover horizon_bars"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

        req = self.request()
        req["arguments"]["min_shared_rows"] = 0
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "min_shared_rows"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )


if __name__ == "__main__":
    unittest.main()
