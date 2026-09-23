import csv

from p01_crw_dca_adapter_consumer_v1 import _arm, _metrics


def test_arm_changes_only_consumed_dca_mode_and_sets_absolute_cost():
    seed = {
        "params": {
            "ENABLE_DCA": True,
            "DCA_TRIGGER_MODE": "tiered_previous_buy",
            "DCA_BASE_QTY": 1,
            "DCA_MAX_CONTRACTS": 3,
            "slippage_bps": 2.5,
            "SLIPPAGE_BPS": 2.5,
            "ENTRY_EXTREME": -2.52,
            "EXIT_EXTREME": 4.5,
        }
    }
    challenger = _arm(seed, trigger_mode="legacy_pine_v0_2", slippage_bps=5.0)
    assert challenger["params"]["DCA_TRIGGER_MODE"] == "legacy_pine_v0_2"
    assert challenger["params"]["DCA_BASE_QTY"] == 1
    assert challenger["params"]["DCA_MAX_CONTRACTS"] == 3
    assert challenger["params"]["ENTRY_EXTREME"] == -2.52
    assert challenger["params"]["EXIT_EXTREME"] == 4.5
    assert challenger["params"]["slippage_bps"] == 5.0
    assert challenger["params"]["SLIPPAGE_BPS"] == 5.0
    assert challenger["paper_only"] is True
    assert challenger["live_allowed"] is False
    assert seed["params"]["DCA_TRIGGER_MODE"] == "tiered_previous_buy"
    assert seed["params"]["slippage_bps"] == 2.5


def test_metrics_use_simulated_next_bar_open_and_frozen_folds(tmp_path):
    artifact = tmp_path / "artifacts" / "run"
    artifact.mkdir(parents=True)
    rows = [
        {"exit_ts": "2020-02-01T00:00:00Z", "net_pnl": "10"},
        {"exit_ts": "2022-02-01T00:00:00Z", "net_pnl": "20"},
        {"exit_ts": "2024-02-01T00:00:00Z", "net_pnl": "30"},
        {"exit_ts": "2025-02-01T00:00:00Z", "net_pnl": "40"},
    ]
    with (artifact / "simulation_trade_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["exit_ts", "net_pnl"])
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "artifact_dir": "artifacts/run",
        "net_pnl": -9999.0,
        "max_drawdown": 9999.0,
        "total_trades": 99,
        "cost_model": {"slippage_bps": 2.5},
        "execution_views": {
            "simulated_next_bar_open": {
                "execution_view": "simulated_next_bar_open",
                "net_pnl": 100.0,
                "max_drawdown": 25.0,
                "total_trades": 4,
            }
        },
        "symbol_rows": [{"bar_count": 100}],
        "simulation_trade_rows": rows[:1],
    }
    got = _metrics(result, 10000.0, tmp_path)
    assert got["execution_view"] == "simulated_next_bar_open"
    assert got["after_cost_net_pnl"] == 100.0
    assert got["after_cost_return_pct"] == 1.0
    assert got["max_drawdown"] == 25.0
    assert got["trade_count"] == 4
    assert got["bar_support"] == 100
    assert got["chronology_folds"] == [
        {"fold": "2019-2020", "trades": 1, "net_pnl": 10.0},
        {"fold": "2021-2022", "trades": 1, "net_pnl": 20.0},
        {"fold": "2023-2024", "trades": 1, "net_pnl": 30.0},
        {"fold": "2025-development-cutoff", "trades": 1, "net_pnl": 40.0},
    ]
