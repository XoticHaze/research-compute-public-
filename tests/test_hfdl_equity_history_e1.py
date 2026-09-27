from __future__ import annotations

from io import BytesIO
import json

import pandas as pd

from research import hfdl_equity_history_e1 as mod


def _provider_parquet() -> bytes:
    frame = pd.DataFrame(
        {
            "datetime": [
                "2020-01-02 00:00:00",
                "2020-07-02 00:00:00",
                "2022-02-28 00:00:00",
                "2022-03-07 00:00:00",
            ],
            "Open": [10.0, 20.0, 30.0, 40.0],
            "High": [11.0, 21.0, 31.0, 41.0],
            "Low": [9.0, 19.0, 29.0, 39.0],
            "Close": [10.5, 20.5, 30.5, 40.5],
            "Volume": [100, 200, 300, 400],
            "source": ["pitrading", "pitrading", "pitrading", "iex"],
        }
    )
    buf = BytesIO()
    frame.to_parquet(buf, index=False, engine="pyarrow")
    return buf.getvalue()


def test_normalize_filters_iex_and_preserves_dst_utc_shape():
    out, qa = mod.normalize_pitrading_1min(
        _provider_parquet(),
        symbol="AMAT",
        start_date="2020-01-01",
        end_date="2022-02-28",
    )

    assert list(out["open"]) == [10.0, 20.0, 30.0]
    assert out["timestamp"].iloc[0] == pd.Timestamp("2020-01-02T05:00:00Z")
    assert out["timestamp"].iloc[1] == pd.Timestamp("2020-07-02T04:00:00Z")
    assert out["timestamp"].iloc[2] == pd.Timestamp("2022-02-28T05:00:00Z")
    assert qa["source_regime"] == "pitrading"
    assert qa["admission_ready"] is True
    assert qa["local_price_adjustment_applied"] is False
    assert qa["forward_fill_applied"] is False


def test_acquire_symbol_emits_mm_admission_lineage(tmp_path, monkeypatch):
    raw = _provider_parquet()
    monkeypatch.setattr(
        mod,
        "public_symbol_metadata",
        lambda symbol: {
            "ticker": symbol,
            "versions": {"raw": {"size_bytes": len(raw)}},
            "authentication_required": False,
        },
    )
    monkeypatch.setattr(
        mod,
        "_bars_download",
        lambda symbol, api_key: (
            raw,
            {
                "endpoint": f"/v1/bars/{symbol}",
                "version": "raw",
                "timeframe": "1min",
                "format": "parquet",
                "content_type": "application/octet-stream",
                "content_disposition": f'attachment; filename="{symbol}_raw.parquet"',
                "rate_limit_remaining": "99",
                "rate_limit_reset": "fixture",
                "signed_url_persisted": False,
            },
        ),
    )

    receipt = mod.acquire_symbol(
        "AMAT",
        api_key="private-fixture-key",
        output_root=tmp_path,
        start_date="2020-01-01",
        end_date="2022-02-28",
    )

    assert receipt["status"] == "ACQUIRED"
    assert receipt["admission_ready"] is True
    assert receipt["raw_download_bytes"] == len(raw)

    lineage = json.loads((tmp_path / "AMAT" / "AMAT_1Min.lineage.json").read_text())
    assert lineage["source_sha256"] == receipt["normalized_sha256"]
    assert lineage["raw_download_sha256"] == receipt["raw_download_sha256"]
    assert lineage["source_regime"] == "hfdl_pitrading_consolidated_pre_2022"
    assert lineage["source_timeframe"] == "1Min"
    assert "split/dividend adjusted" in lineage["adjustment_policy"]
    assert lineage["download_receipt"]["endpoint"] == "/v1/bars/AMAT"
    assert lineage["download_receipt"]["rate_limit_remaining"] == "99"

    normalized = pd.read_parquet(tmp_path / "AMAT" / "AMAT_1Min.parquet")
    assert list(normalized.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(normalized) == 3


def test_metadata_only_never_requires_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod,
        "public_symbol_metadata",
        lambda symbol: {
            "ticker": symbol,
            "versions": {"raw": {"size_bytes": 123}},
            "authentication_required": False,
        },
    )
    receipt = mod.run(
        symbols=["AMAT", "APH"],
        output_root=tmp_path,
        api_key_file=None,
        start_date="2004-01-01",
        end_date="2022-02-28",
        metadata_only=True,
    )
    assert receipt["status"] == "METADATA_PROBED"
    assert receipt["downloads_attempted"] is False
    coverage = json.loads((tmp_path / "coverage_receipt.json").read_text())
    assert [row["symbol"] for row in coverage["symbols"]] == ["AMAT", "APH"]
