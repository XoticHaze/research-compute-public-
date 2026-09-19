from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import mmibkr_private_source_materialize_v1 as mod


class MmibkrPrivateSourceMaterializeTests(unittest.TestCase):
    def test_source_only_materialization_does_not_require_tws_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            extracted = root / "mm-ibkr-source" / "repo"
            extracted.mkdir(parents=True)
            with patch.dict(
                os.environ,
                {"IBKR_REMOTE_SOURCE_TOKEN": "source-token"},
                clear=True,
            ), patch.object(
                mod,
                "resolve_private_head",
                return_value="a" * 40,
            ) as resolve, patch.object(
                mod,
                "fetch_private_archive",
                side_effect=lambda token, head, destination: (
                    destination.write_bytes(b"archive"),
                    "b" * 64,
                )[1],
            ), patch.object(
                mod,
                "_safe_extract_tar",
                return_value=extracted,
            ):
                result = mod.materialize(
                    runner_temp=root,
                    source_ref="assistant/cloud-runtime",
                )

            self.assertEqual(result["mmibkr_head"], "a" * 40)
            self.assertEqual(result["source_archive_sha256"], "b" * 64)
            self.assertFalse(result["broker_credentials_materialized"])
            self.assertFalse(result["tws_credentials_required"])
            self.assertFalse(result["source_token_emitted"])
            self.assertFalse(result["paper_or_live_authority"])
            resolve.assert_called_once_with(
                "source-token",
                "assistant/cloud-runtime",
            )
            runtime = json.loads(
                Path(result["runtime_path"]).read_text(encoding="utf-8")
            )
            serialized = json.dumps(runtime)
            self.assertNotIn("source-token", serialized)
            self.assertNotIn("TWS_USERID", serialized)
            self.assertNotIn("TWS_PASSWORD", serialized)

    def test_blank_source_ref_fails_closed(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(
            os.environ,
            {"IBKR_REMOTE_SOURCE_TOKEN": "source-token"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "private source ref is required",
            ):
                mod.materialize(
                    runner_temp=Path(td),
                    source_ref="",
                )


if __name__ == "__main__":
    unittest.main()
