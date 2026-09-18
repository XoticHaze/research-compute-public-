from __future__ import annotations

import unittest

from research.forward_bar_contract_v2 import normalize_frame


class ForwardBarMultiTimeframeTests(unittest.TestCase):
    def row(self, *, bar_size: str, close: float):
        return {
            "symbol": "MNQ",
            "timestamp": "2026-09-18T10:00:00Z",
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1,
            "source": "ibkr",
            "asset_type": "FUT",
            "bar_size": bar_size,
            "session": "all",
            "contract_id": "conid:793356225",
            "wap": close,
            "bar_count": 1,
        }

    def test_same_symbol_timestamp_contract_can_coexist_across_bar_sizes(self):
        frame = normalize_frame([
            self.row(bar_size="1 min", close=24000.0),
            self.row(bar_size="15 mins", close=24001.0),
        ])
        self.assertEqual(len(frame), 2)
        self.assertEqual(set(frame["bar_size"]), {"1 min", "15 mins"})

    def test_duplicate_same_bar_size_still_fails(self):
        row = self.row(bar_size="1 min", close=24000.0)
        with self.assertRaisesRegex(ValueError, "duplicate normalized bars"):
            normalize_frame([row, dict(row)])


if __name__ == "__main__":
    unittest.main()
