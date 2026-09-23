from p01_crw_dca_adapter_consumer_v1 import _arm, _metrics


def test_arm_changes_only_consumed_dca_mode_and_cost():
    seed = {
        "params": {
            "ENABLE_DCA": True,
            "DCA_TRIGGER_MODE": "tiered_previous_buy",
            "DCA_BASE_QTY": 1,
            "DCA_MAX_CONTRACTS": 3,
            "slippage_bps": 2.5,
            "ENTRY_EXTREME": -2.52,
            "EXIT_EXTREME": 4.5,
        }
    }
    challenger = _arm(seed, trigger_mode="legacy_pine_v0_2", extra_cost_bps=5.0)
    assert challenger["params"]["DCA_TRIGGER_MODE"] == "legacy_pine_v0_2"
    assert challenger["params"]["DCA_BASE_QTY"] == 1
    assert challenger["params"]["DCA_MAX_CONTRACTS"] == 3
    assert challenger["params"]["ENTRY_EXTREME"] == -2.52
    assert challenger["params"]["EXIT_EXTREME"] == 4.5
    assert challenger["params"]["slippage_bps"] == 7.5
    assert challenger["paper_only"] is True
    assert challenger["live_allowed"] is False
    assert seed["params"]["DCA_TRIGGER_MODE"] == "tiered_previous_buy"
    assert seed["params"]["slippage_bps"] == 2.5


def test_metrics_are_capital_normalized_and_deterministic():
    result = {
        "net_pnl": 125.0,
        "max_drawdown": -40.0,
        "total_trades": 2,
        "symbol_rows": [{"bar_count": 100}],
        "trade_rows": [
            {"exit_ts": "2024-02-01T00:00:00Z", "net_pnl": 50.0},
            {"exit_ts": "2025-02-01T00:00:00Z", "net_pnl": 75.0},
        ],
    }
    got = _metrics(result, 10000.0)
    assert got["after_cost_net_pnl"] == 125.0
    assert got["after_cost_return_pct"] == 1.25
    assert got["max_drawdown"] == -40.0
    assert got["trade_count"] == 2
    assert got["bar_support"] == 100
    assert got["chronology_folds"] == [
        {"year": 2024, "trades": 1, "net_pnl": 50.0},
        {"year": 2025, "trades": 1, "net_pnl": 75.0},
    ]
