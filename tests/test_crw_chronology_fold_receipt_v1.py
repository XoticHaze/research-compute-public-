from scripts.crw_chronology_fold_receipt_v1 import chronology_fold_receipt


def test_chronology_fold_receipt_is_bounded_and_sorted():
    rows = [
        {"exit_timestamp": "2026-01-04T00:00:00Z", "net_pnl": -2},
        {"exit_timestamp": "2026-01-01T00:00:00Z", "net_pnl": 1},
        {"exit_timestamp": "2026-01-03T00:00:00Z", "net_pnl": 3},
        {"exit_timestamp": "2026-01-02T00:00:00Z", "net_pnl": -1},
    ]
    receipt = chronology_fold_receipt(rows, fold_count=2)
    assert receipt["raw_rows_emitted"] is False
    assert receipt["parsed_trade_count"] == 4
    assert receipt["rejected_row_count"] == 0
    assert receipt["folds"] == [
        {"fold": 1, "trade_count": 2, "net_pnl": 0.0, "win_count": 1, "loss_count": 1, "flat_count": 0},
        {"fold": 2, "trade_count": 2, "net_pnl": 1.0, "win_count": 1, "loss_count": 1, "flat_count": 0},
    ]


def test_chronology_fold_receipt_rejects_unusable_rows_without_leaking_them():
    receipt = chronology_fold_receipt([{"timestamp": "not-a-time", "pnl": 99}, {"timestamp": "2026-01-01T00:00:00Z"}], fold_count=4)
    assert receipt["source_row_count"] == 2
    assert receipt["parsed_trade_count"] == 0
    assert receipt["rejected_row_count"] == 2
    assert all(fold["trade_count"] == 0 for fold in receipt["folds"])
