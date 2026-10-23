from scripts.mmibkr_canonical_workload_dispatch_v1 import sanitize_crw_result


def _args():
    return {
        "datasets": {
            "MNQ": {
                "relative_path": "mnq.csv",
                "sha256": "a" * 64,
                "bytes": 123,
            }
        }
    }


def _raw():
    return {
        "safety": {
            "broker_submit": False,
            "cancel": False,
            "replace": False,
            "live_unlock": False,
            "backtest_only": True,
        },
        "trade_rows": [
            {"exit_timestamp": "2026-01-04T00:00:00Z", "net_pnl": -2},
            {"exit_timestamp": "2026-01-01T00:00:00Z", "net_pnl": 1},
            {"exit_timestamp": "2026-01-03T00:00:00Z", "net_pnl": 3},
            {"exit_timestamp": "2026-01-02T00:00:00Z", "net_pnl": -1},
        ],
        "simulation_trade_rows": [],
    }


def test_crw_sanitized_result_exposes_only_bounded_chronology_receipt():
    result = sanitize_crw_result(_raw(), _args())
    receipt = result["chronology_fold_receipt"]
    assert receipt["raw_rows_emitted"] is False
    assert receipt["source_row_count"] == 4
    assert receipt["parsed_trade_count"] == 4
    assert receipt["rejected_row_count"] == 0
    assert len(receipt["folds"]) == 4
    assert [fold["trade_count"] for fold in receipt["folds"]] == [1, 1, 1, 1]
    assert [fold["net_pnl"] for fold in receipt["folds"]] == [1.0, -1.0, 3.0, -2.0]
    assert "trade_rows" not in result
    assert "simulation_trade_rows" not in result
