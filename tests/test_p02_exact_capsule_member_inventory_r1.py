"""Focused P02 encrypted-capsule source/data identity acceptance.

Synthetic regular tar members only; no private source, real corpus or broker.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

# These tests exercise archive validation only, not private-key decryption.
# Import the exact consumer source without requiring crypto dependencies.
consumer_path = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "p02_model_lab_xgboost_capsule_consumer_v1.py"
)
spec = importlib.util.spec_from_file_location("p02_consumer_under_test", consumer_path)
assert spec is not None and spec.loader is not None
consumer = importlib.util.module_from_spec(spec)
crypto_stub = types.ModuleType("ephemeral_x25519_chunked_v1")
crypto_stub.decrypt_assembled_ciphertext = lambda **kwargs: b""
with patch.dict(sys.modules, {"ephemeral_x25519_chunked_v1": crypto_stub}):
    spec.loader.exec_module(consumer)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(*, replace: tuple[str, str] | None = None,
             special: str | None = None, tamper_data: bool = False,
             extra_manifest_file: bool = False,
             duplicate_name: str | None = None) -> bytes:
    source = {name: ("source:" + name).encode() for name in consumer.EXPECTED_SOURCE_FILES}
    data = {name: ("data:" + name).encode() for name in consumer.EXPECTED_DATA_FILES.values()}
    manifest = {
        "schema": consumer.SCHEMA,
        "mm_commit": consumer.EXPECTED_MM_COMMIT,
        "entrypoint": consumer.EXPECTED_ENTRYPOINT,
        "symbol": consumer.EXPECTED_SYMBOL,
        "timeframe": consumer.EXPECTED_TIMEFRAME,
        "data_identity": {
            **{key: _sha(data[name]) for key, name in consumer.EXPECTED_DATA_FILES.items()},
            "feature_manifest_hash": "synthetic-manifest",
            "feature_semantic_hash": "synthetic-semantics",
        },
        "files": {name: _sha(raw) for name, raw in source.items()},
    }
    if extra_manifest_file:
        manifest["files"]["unlisted.py"] = _sha(b"unlisted")
    members = {
        "payload_manifest.json": (json.dumps(manifest, sort_keys=True) + "\n").encode(),
        **source, **data,
    }
    if tamper_data:
        members[consumer.EXPECTED_DATA_FILES["raw_sha256"]] = b"altered raw source"
    if replace:
        original, alternate = replace
        members[alternate] = members.pop(original)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tf:
        for name, raw in members.items():
            emitted_name = duplicate_name if name == "timeframe_adapters.py" and duplicate_name else name
            info = tarfile.TarInfo(emitted_name)
            if name == special:
                info.type = tarfile.SYMTYPE
                info.linkname = "payload_manifest.json"
                tf.addfile(info)
            else:
                info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))
    return output.getvalue()


class P02ExactCapsuleInventoryTest(unittest.TestCase):
    def test_pinned_private_packager_shape_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            consumer._safe_extract(_fixture(), root)
            self.assertEqual(consumer._validate(root)["schema"], consumer.SCHEMA)

    def test_undeclared_executable_member_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = _fixture(replace=("timeframe_adapters.py", "sitecustomize.py"))
            with self.assertRaisesRegex(RuntimeError, "member inventory"):
                consumer._safe_extract(archive, root)
            self.assertFalse((root / "sitecustomize.py").exists())

    def test_duplicate_name_rejected_even_with_same_member_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # A same-count duplicate is a real ambiguous tar-member attack.
            archive = _fixture(duplicate_name="payload_manifest.json")
            with self.assertRaisesRegex(RuntimeError, "member inventory"):
                consumer._safe_extract(archive, root)

    def test_nonregular_expected_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "member inventory"):
                consumer._safe_extract(
                    _fixture(special="timeframe_adapters.py"), Path(td)
                )

    def test_data_bytes_bound_to_declared_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            consumer._safe_extract(_fixture(tamper_data=True), root)
            with self.assertRaisesRegex(RuntimeError, "data digest mismatch"):
                consumer._validate(root)

    def test_source_manifest_must_match_exact_nine_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            consumer._safe_extract(_fixture(extra_manifest_file=True), root)
            with self.assertRaisesRegex(RuntimeError, "source file identity map mismatch"):
                consumer._validate(root)


    def test_private_subprocess_output_is_never_public_stdio(self):
        private = types.SimpleNamespace(
            returncode=0, stdout=b"SECRET_PRIVATE_RESULT", stderr=b"SECRET_PRIVATE_ERROR"
        )
        with patch.object(consumer.subprocess, "run", return_value=private) as run:
            consumer._run_private_consumer(["python", "private_consumer.py"], Path("/tmp"))
            self.assertEqual(run.call_args.kwargs["stdout"], consumer.subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs["stderr"], consumer.subprocess.DEVNULL)
            self.assertIs(run.call_args.kwargs["check"], False)

    def test_private_subprocess_failure_is_generic(self):
        private = types.SimpleNamespace(
            returncode=17, stdout=b"SECRET_PRIVATE_RESULT", stderr=b"SECRET_PRIVATE_ERROR"
        )
        with patch.object(consumer.subprocess, "run", return_value=private):
            with self.assertRaisesRegex(RuntimeError, "private consumer failed; output withheld") as error:
                consumer._run_private_consumer(["python", "private_consumer.py"], Path("/tmp"))
            self.assertNotIn("SECRET_PRIVATE", str(error.exception))


if __name__ == "__main__":
    unittest.main()
