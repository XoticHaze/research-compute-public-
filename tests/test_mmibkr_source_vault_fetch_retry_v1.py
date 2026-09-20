from __future__ import annotations

from urllib.error import HTTPError
import unittest
from unittest.mock import patch

from scripts import mmibkr_source_vault_consumer_v1 as mod


class _Response:
    def __init__(self, raw: bytes):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.raw


class SourceVaultFetchRetryTests(unittest.TestCase):
    def test_transient_raw_github_404_retries_then_succeeds(self):
        err = HTTPError(
            "https://raw.githubusercontent.com/example",
            404,
            "not found",
            hdrs=None,
            fp=None,
        )
        with (
            patch.object(mod, "urlopen", side_effect=[err, _Response(b"ok")]) as opened,
            patch.object(mod.time, "sleep") as slept,
        ):
            raw = mod._fetch(
                "https://raw.githubusercontent.com/example",
                retry_404=2,
                retry_delay_sec=0.25,
            )
        self.assertEqual(raw, b"ok")
        self.assertEqual(opened.call_count, 2)
        slept.assert_called_once_with(0.25)

    def test_non_404_failure_does_not_retry(self):
        err = HTTPError(
            "https://raw.githubusercontent.com/example",
            403,
            "forbidden",
            hdrs=None,
            fp=None,
        )
        with (
            patch.object(mod, "urlopen", side_effect=err) as opened,
            patch.object(mod.time, "sleep") as slept,
        ):
            with self.assertRaisesRegex(RuntimeError, "snapshot_fetch_http_403"):
                mod._fetch(
                    "https://raw.githubusercontent.com/example",
                    retry_404=6,
                    retry_delay_sec=0.25,
                )
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()


if __name__ == "__main__":
    unittest.main()
