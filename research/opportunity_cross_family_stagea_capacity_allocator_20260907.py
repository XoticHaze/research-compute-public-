from __future__ import annotations

import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ADAPTER = Path(".campaign/stagea.py")
CONTRACT = Path(".campaign/stagea_contract.json")
OUT = Path("opportunity_cross_family_stagea_capacity_allocator_20260907.json")

CAPACITY = 3
EVAL_FOLDS = (4, 5, 6)
ETF_COST_BPS = 10.0
STOCK_COST_BPS = 25.0
TARGET_FAMILIES = ("homebuilders", "biotech")


def load_adapter():
    spec = importlib.util.spec_from_file_location("accepted_stagea", ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load accepted Stage-A adapter")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pct_rank(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(ordered)
    if n == 1:
        return {ordered[0][0]: 0.5}
    out = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][1] == ordered[i][1]:
            j += 1
        avg_rank = 0.5 * ((i + 1) + j)
        p = (avg_rank - 1.0) / (n - 1.0)
        for k in range(i, j):
            out[ordered[k][0]] = float(p)
        i = j
    return out


def build_records(mod, contract):
    parity = contract["parity_control"]
    target = contract["target"]
    families = {
        "homebuilders": parity["families"]["homebuilders"],
        "biotech": target["families"]["biotech"],
    }
    cutoff = pd.Timestamp("2026-09-01T13:30:00+00:00")
    symbols = []
    symbol_family = {}
    for family, spec in families.items():
        for symbol in spec["development_universe"]:
            if symbol in symbol_family:
                raise RuntimeError(f"duplicate symbol={symbol}")
            symbols.append(symbol)
            symbol_family[symbol] = family

    selection_symbols = (*mod.TRAIN, *symbols, "QQQ")
    raw = {s: mod._bounded(s, cutoff) for s in selection_symbols}
    calendar = pd.DatetimeIndex(sorted(set.intersection(*[set(frame.timestamp) for frame in raw.values()])))
    if len(calendar) < 1500 or calendar[-1] != cutoff:
        raise RuntimeError("cross-family common selection calendar invalid")
    prices = {s: raw[s].set_index("timestamp").price.reindex(calendar) for s in raw}
    if any(v.isna().any() for v in prices.values()):
        raise RuntimeError("missing selection price on frozen common calendar")

    benchmarks = {}
    for family, spec in families.items():
        etf = spec["primary_industry_etf"]
        series = mod._bounded(etf, cutoff).set_index("timestamp").price.reindex(calendar)
        if series.isna().any():
            raise RuntimeError(f"{etf}: missing benchmark rows")
        benchmarks[family] = series

    data = mod._engineer(prices, calendar, (*mod.TRAIN, *symbols))
    folds = mod._global_folds(len(calendar))
    train_states = mod._state_frame(mod.TRAIN, data, folds)
    test_states = mod._state_frame(tuple(symbols), data, folds)

    records = []
    for fold in range(mod.EVAL_FIRST_FOLD, mod.FOLDS + 1):
        start, _ = folds[fold - 1]
        train = train_states[train_states.signal_i < start - mod.PURGE]
        if len(train) < 1000:
            raise RuntimeError(f"fold={fold} insufficient train={len(train)}")
        model = mod._fit(train)
        for symbol in symbols:
            family = symbol_family[symbol]
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)].copy()
            pred = model.predict(test[mod.FEATURES].to_numpy(float))
            test["prediction_bps"] = pred
            chosen = test.loc[test.prediction_bps > 0].copy()
            prior_mom = data[symbol].iloc[: start - mod.PURGE].mom20.dropna()
            if len(prior_mom) < 250:
                raise RuntimeError(f"{symbol} fold={fold} insufficient prior momentum")
            threshold = float(prior_mom.quantile(1.0 - mod.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]
            for row in primary.itertuples(index=False):
                signal_i = int(row.signal_i)
                entry_i = signal_i + mod.DELAY
                exit_i = entry_i + mod.HOLD
                stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[entry_i] - 1.0)
                etf_gross = float(benchmarks[family].iloc[exit_i] / benchmarks[family].iloc[entry_i] - 1.0)
                qqq_gross = float(prices["QQQ"].iloc[exit_i] / prices["QQQ"].iloc[entry_i] - 1.0)
                records.append(
                    {
                        "fold": fold,
                        "family": family,
                        "symbol": symbol,
                        "signal_i": signal_i,
                        "entry_i": entry_i,
                        "exit_i": exit_i,
                        "signal_date": calendar[signal_i].isoformat(),
                        "entry_date": calendar[entry_i].isoformat(),
                        "exit_date": calendar[exit_i].isoformat(),
                        "prediction_bps": float(row.prediction_bps),
                        "stock_net": stock_gross - STOCK_COST_BPS / 10000.0,
                        "etf_net": etf_gross - ETF_COST_BPS / 10000.0,
                        "qqq_net": qqq_gross - ETF_COST_BPS / 10000.0,
                        "stock_minus_etf_bps": (stock_gross - STOCK_COST_BPS / 10000.0 - etf_gross) * 10000.0,
                        "stock_minus_qqq_bps": (stock_gross - STOCK_COST_BPS / 10000.0 - qqq_gross) * 10000.0,
                    }
                )
    return calendar, folds, families, records


def prior_symbol_alpha(records, before_fold, symbols):
    values = {}
    support = {}
    for symbol in symbols:
        rows = [r for r in records if r["symbol"] == symbol and r["fold"] < before_fold]
        values[symbol] = float(np.mean([r["stock_minus_etf_bps"] for r in rows])) if rows else 0.0
        support[symbol] = len(rows)
    return values, support


def score_candidates(candidates, policy, prior_alpha_pct):
    pred = {str(i): float(r["prediction_bps"]) for i, r in enumerate(candidates)}
    pred_pct = pct_rank(pred)
    family_pred_pct = {}
    for family in TARGET_FAMILIES:
        local = {str(i): float(r["prediction_bps"]) for i, r in enumerate(candidates) if r["family"] == family}
        family_pred_pct.update(pct_rank(local))
    scored = []
    for i, r in enumerate(candidates):
        key = str(i)
        if policy == "global_raw_prediction":
            score = float(r["prediction_bps"])
        elif policy == "family_normalized_prediction":
            score = float(family_pred_pct.get(key, 0.5))
        elif policy == "prior_alpha_blend":
            score = 0.5 * float(pred_pct.get(key, 0.5)) + 0.5 * float(prior_alpha_pct.get(r["symbol"], 0.5))
        else:
            raise RuntimeError(f"unknown score policy={policy}")
        scored.append((score, r))
    return sorted(scored, key=lambda x: (-x[0], -x[1]["prediction_bps"], x[1]["family"], x[1]["symbol"]))


def simulate(records, fold, policy, prior_alpha_pct):
    candidates = [r for r in records if r["fold"] == fold]
    grouped = defaultdict(list)
    for r in candidates:
        grouped[r["entry_i"]].append(r)

    slots = [
        {"stock": 1.0 / CAPACITY, "etf": 1.0 / CAPACITY, "qqq": 1.0 / CAPACITY, "record": None, "exit_i": -1}
        for _ in range(CAPACITY)
    ]
    accepted = []

    def realize(index):
        for slot in slots:
            r = slot["record"]
            if r is not None and slot["exit_i"] <= index:
                slot["stock"] *= 1.0 + r["stock_net"]
                slot["etf"] *= 1.0 + r["etf_net"]
                slot["qqq"] *= 1.0 + r["qqq_net"]
                slot["record"] = None
                slot["exit_i"] = -1

    for entry_i in sorted(grouped):
        realize(entry_i)
        free = [slot for slot in slots if slot["record"] is None]
        if not free:
            continue
        active_symbols = {slot["record"]["symbol"] for slot in slots if slot["record"] is not None}
        day = grouped[entry_i]
        if policy == "family_balanced_prediction":
            ordered = []
            best_by_family = {}
            for family in TARGET_FAMILIES:
                local = sorted([r for r in day if r["family"] == family], key=lambda r: (-r["prediction_bps"], r["symbol"]))
                if local:
                    best_by_family[family] = local[0]
            for family in TARGET_FAMILIES:
                if family in best_by_family:
                    ordered.append(best_by_family[family])
            remaining = sorted(day, key=lambda r: (-r["prediction_bps"], r["family"], r["symbol"]))
            seen = {(r["family"], r["symbol"]) for r in ordered}
            ordered.extend([r for r in remaining if (r["family"], r["symbol"]) not in seen])
        else:
            ordered = [r for _, r in score_candidates(day, policy, prior_alpha_pct)]

        for r in ordered:
            if not free:
                break
            if r["symbol"] in active_symbols:
                continue
            slot = free.pop(0)
            slot["record"] = r
            slot["exit_i"] = r["exit_i"]
            active_symbols.add(r["symbol"])
            accepted.append(r)
    realize(10**9)

    stock_wealth = float(sum(s["stock"] for s in slots))
    etf_wealth = float(sum(s["etf"] for s in slots))
    qqq_wealth = float(sum(s["qqq"] for s in slots))
    by_family = defaultdict(int)
    for r in accepted:
        by_family[r["family"]] += 1
    return {
        "stock_return": stock_wealth - 1.0,
        "matched_etf_return": etf_wealth - 1.0,
        "qqq_return": qqq_wealth - 1.0,
        "stock_minus_matched_etf_return": stock_wealth - etf_wealth,
        "stock_minus_qqq_return": stock_wealth - qqq_wealth,
        "accepted_trades": len(accepted),
        "family_trade_counts": dict(sorted(by_family.items())),
        "mean_trade_matched_excess_bps": float(np.mean([r["stock_minus_etf_bps"] for r in accepted])) if accepted else None,
    }


def main():
    mod = load_adapter()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract["boundaries"]["research_only"] is not True or contract["boundaries"]["external_holdouts_loaded"] is not False:
        raise RuntimeError("accepted Stage-A boundary drift")
    calendar, folds, families, records = build_records(mod, contract)
    symbols = sorted({r["symbol"] for r in records})
    if len(symbols) != 16:
        raise RuntimeError(f"unexpected cross-family symbol count={len(symbols)}")

    policies = (
        "global_raw_prediction",
        "family_normalized_prediction",
        "prior_alpha_blend",
        "family_balanced_prediction",
    )
    fold_rows = []
    for fold in EVAL_FOLDS:
        prior_alpha, prior_support = prior_symbol_alpha(records, fold, symbols)
        prior_alpha_pct = pct_rank(prior_alpha)
        row = {
            "fold": fold,
            "prior_folds": list(range(mod.EVAL_FIRST_FOLD, fold)),
            "prior_symbol_matched_alpha_bps": prior_alpha,
            "prior_symbol_state_counts": prior_support,
            "policies": {},
        }
        for policy in policies:
            row["policies"][policy] = simulate(records, fold, policy, prior_alpha_pct)
        fold_rows.append(row)

    aggregate = {}
    for policy in policies:
        rows = [f["policies"][policy] for f in fold_rows]
        stock = float(np.prod([1.0 + r["stock_return"] for r in rows]) - 1.0)
        etf = float(np.prod([1.0 + r["matched_etf_return"] for r in rows]) - 1.0)
        qqq = float(np.prod([1.0 + r["qqq_return"] for r in rows]) - 1.0)
        aggregate[policy] = {
            "compound_stock_return": stock,
            "compound_matched_etf_return": etf,
            "compound_qqq_return": qqq,
            "compound_stock_minus_matched_etf": stock - etf,
            "compound_stock_minus_qqq": stock - qqq,
            "accepted_trades": int(sum(r["accepted_trades"] for r in rows)),
            "fold_stock_returns": [r["stock_return"] for r in rows],
            "fold_stock_minus_matched_etf": [r["stock_minus_matched_etf_return"] for r in rows],
            "family_trade_counts": {
                family: int(sum(r["family_trade_counts"].get(family, 0) for r in rows)) for family in TARGET_FAMILIES
            },
        }

    control = aggregate["global_raw_prediction"]
    decisions = {}
    for challenger in ("family_normalized_prediction", "prior_alpha_blend", "family_balanced_prediction"):
        c = aggregate[challenger]
        fold_win = sum(
            f["policies"][challenger]["stock_return"] > f["policies"]["global_raw_prediction"]["stock_return"]
            for f in fold_rows
        )
        positive_etf_folds = sum(f["policies"][challenger]["stock_minus_matched_etf_return"] > 0 for f in fold_rows)
        supported = bool(
            c["compound_stock_return"] > control["compound_stock_return"]
            and c["compound_stock_minus_matched_etf"] > 0
            and c["compound_stock_minus_matched_etf"] > control["compound_stock_minus_matched_etf"]
            and fold_win >= 2
            and positive_etf_folds >= 2
            and c["accepted_trades"] >= 0.70 * control["accepted_trades"]
        )
        decisions[challenger] = {
            "decision": "SUPPORTED" if supported else "NOT_SUPPORTED",
            "fold_wins_vs_raw_prediction": fold_win,
            "positive_matched_etf_excess_folds": positive_etf_folds,
        }

    receipt = {
        "schema": "public_research.opportunity_cross_family_stagea_capacity_allocator.v1",
        "research_only": True,
        "objective": "Improve opportunity ranking and scarce-capital allocation across heterogeneous Homebuilder and Biotech opportunities under one shared capacity budget.",
        "scientific_authority": contract["scientific_authority"],
        "accepted_adapter": "XoticHaze/TextConverterToolbox@2d8995ba66502a4de25c64c1c32a67e132b05522",
        "families": families,
        "family_status_entering_test": {
            "homebuilders": "accepted Stage-A family, 5/8 symbols passed",
            "biotech": "family breadth failed 4/8; included here only as individual opportunities, not promoted as a family",
        },
        "capacity": CAPACITY,
        "stock_roundtrip_cost_bps": STOCK_COST_BPS,
        "matched_etf_and_qqq_cost_bps": ETF_COST_BPS,
        "evaluation_folds": list(EVAL_FOLDS),
        "candidate_primary_states": len(records),
        "selection_calendar": {"rows": len(calendar), "first": calendar[0].isoformat(), "last": calendar[-1].isoformat()},
        "policies": {
            "global_raw_prediction": "Control: rank all currently available cross-family candidates by the shared Ridge predicted fixed20 net bps.",
            "family_normalized_prediction": "Rank by within-family same-day percentile of current model prediction; tests scale normalization without outcome history.",
            "prior_alpha_blend": "Fixed 50/50 blend of current same-day prediction percentile and ticker matched-ETF alpha percentile computed only from completed earlier folds.",
            "family_balanced_prediction": "When both families have current candidates, offer the best prediction from each family before filling remaining slot(s) globally.",
        },
        "fold_results": fold_rows,
        "aggregate": aggregate,
        "decisions": decisions,
        "interpretation_boundary": "Development-only cross-family allocation evidence. No external holdouts are loaded, Biotech family status is not changed, and no allocator/runtime authority is granted.",
        "external_holdouts_loaded": False,
        "threshold_search": False,
        "hyperparameter_search": False,
        "allocation_runtime_authority": False,
        "strategy_spec_mutation": False,
        "promotion_authority": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("OPPORTUNITY_CROSS_FAMILY_STAGEA_CAPACITY_ALLOCATOR=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
