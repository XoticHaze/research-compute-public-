from scripts import mmibkr_canonical_workload_dispatch_chronology_v1 as adapter


def test_sanitizer_adds_aggregate_chronology_without_raw_rows(monkeypatch):
    monkeypatch.setattr(
        adapter,
        "_ORIGINAL_SANITIZE",
        lambda raw, args: {"ok": True, "row_artifact_counts": {"trade_rows": len(raw.get("trade_rows") or [])}},
    )
    raw = {
        "trade_rows": [
            {"exit_timestamp": "2026-01-01T00:00:00Z", "net_pnl": 1.25},
            {"exit_timestamp": "2026-01-02T00:00:00Z", "net_pnl": -0.50},
            {"exit_timestamp": "2026-01-03T00:00:00Z", "net_pnl": 2.00},
            {"exit_timestamp": "2026-01-04T00:00:00Z", "net_pnl": 0.00},
        ]
    }
    result = adapter.sanitize_crw_result(raw, {"datasets": {}})
    folds = result["chronology_folds"]
    assert folds["schema"] == "crw.chronology_fold_receipt.v1"
    assert folds["fold_count"] == 4
    assert folds["parsed_trade_count"] == 4
    assert folds["raw_rows_emitted"] is False
    assert [row["net_pnl"] for row in folds["folds"]] == [1.25, -0.5, 2.0, 0.0]
    assert "trade_rows" not in result


def test_install_replaces_only_canonical_sanitizer(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(adapter.canonical, "sanitize_crw_result", sentinel)
    adapter.install()
    assert adapter.canonical.sanitize_crw_result is adapter.sanitize_crw_result
