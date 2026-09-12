from __future__ import annotations

"""Homebuilder SEC filed-at quality tilt R1.

Materially different from the exhausted price-state children. The signal uses only
SEC facts that were filed by the signal date:
  * annualized NetIncomeLoss / Assets (ROA), higher is better
  * 1 - Liabilities / Assets (capitalization), higher is better
The two cross-sectional percentile ranks receive equal weight. No fitted model,
threshold search, feature search, horizon search, or parameter sweep is used.

Primary economics are measured on the original eight development builders from
2019 onward. Fresh DFH is never used to fit or tune anything and is reported as a
separate external confirmation: when it would rank in the top two of the combined
cross-section, its next-quarter peer excess after the same 50 bps hurdle is scored.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

import homebuilder_peer_relative_alpha_r1 as prices

DEV = ("DHI", "LEN", "PHM", "NVR", "TOL", "MTH", "KBH", "LGIH")
EXTERNAL = "DFH"
ALL_PRICE = (*DEV, EXTERNAL, "ITB")
UA = "XoticHaze market-research SEC-quality contact@example.com"
MAX_STALE_DAYS = 200
REBALANCE_SESSIONS = 63
DELAY = 1
HOLD = 63
COMMON_COST_BPS = 25.0
MARGINAL_HURDLE_BPS = 50.0
TILT_WEIGHT = 0.25
TOP_N = 2
FOLDS = 5
MIN_DECISIONS = 27
MIN_DEV_SYMBOL_PASSES = 5
MIN_DEV_SELECTED_EVENTS = 3
MIN_EXTERNAL_SELECTED_EVENTS = 2
OUTPUT = Path("research/results/homebuilder_sec_quality_tilt_r1.json")
SOURCE_PROBE = {"run": 34684026346, "job": 103527731517, "decision": "HOMEBUILDER_SEC_PIT_PANEL_ADMITTED_FOR_ECONOMIC_TEST"}


def get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:  # noqa: S310 fixed HTTPS source
        return json.loads(response.read().decode("utf-8"))


def fact_rows(us: dict, concept: str) -> list[dict]:
    rows = []
    for unit, vals in us.get(concept, {}).get("units", {}).items():
        if unit != "USD":
            continue
        for row in vals:
            if row.get("form") not in ("10-K", "10-Q"):
                continue
            if not row.get("filed") or not row.get("end") or row.get("val") is None:
                continue
            rows.append(row)
    return rows


def latest_instant(rows: list[dict], asof: date) -> dict | None:
    eligible = []
    for row in rows:
        filed = date.fromisoformat(row["filed"])
        end = date.fromisoformat(row["end"])
        if filed <= asof and end <= asof and (asof - end).days <= MAX_STALE_DAYS:
            eligible.append(row)
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row["end"], row["filed"], row.get("accn") or ""))


def latest_income(rows: list[dict], asof: date) -> dict | None:
    eligible = []
    for row in rows:
        if not row.get("start"):
            continue
        filed = date.fromisoformat(row["filed"])
        start = date.fromisoformat(row["start"])
        end = date.fromisoformat(row["end"])
        span = (end - start).days + 1
        if filed <= asof and end <= asof and 60 <= span <= 400 and (asof - end).days <= MAX_STALE_DAYS:
            eligible.append((row, span))
    if not eligible:
        return None
    row, span = max(
        eligible,
        key=lambda item: (
            item[0]["end"],
            1 if 70 <= item[1] <= 110 else 0,
            -item[1],
            item[0]["filed"],
            item[0].get("accn") or "",
        ),
    )
    return {**row, "span_days": span}


def equity_at(us: dict, asof: date, assets: dict | None, liabilities: dict | None) -> tuple[float | None, str | None]:
    for concept in ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"):
        row = latest_instant(fact_rows(us, concept), asof)
        if row is not None:
            return float(row["val"]), concept
    if assets is not None and liabilities is not None:
        return float(assets["val"]) - float(liabilities["val"]), "AssetsMinusLiabilities"
    return None, None


def quality_state(us: dict, asof: date) -> dict | None:
    assets = latest_instant(fact_rows(us, "Assets"), asof)
    liabilities = latest_instant(fact_rows(us, "Liabilities"), asof)
    income = latest_income(fact_rows(us, "NetIncomeLoss"), asof)
    equity, equity_source = equity_at(us, asof, assets, liabilities)
    if assets is None or income is None or equity is None:
        return None
    assets_value = float(assets["val"])
    if assets_value <= 0 or equity <= 0:
        return None
    liabilities_value = float(liabilities["val"]) if liabilities is not None else assets_value - equity
    if liabilities_value < 0:
        return None
    annualized_income = float(income["val"]) * 365.0 / float(income["span_days"])
    return {
        "roa": annualized_income / assets_value,
        "capitalization": 1.0 - liabilities_value / assets_value,
        "assets_end": assets["end"],
        "assets_filed": assets["filed"],
        "income_end": income["end"],
        "income_filed": income["filed"],
        "income_span_days": int(income["span_days"]),
        "equity_source": equity_source,
    }


def percentile(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    n = len(ordered)
    if n == 1:
        return {ordered[0][0]: 1.0}
    return {symbol: rank / (n - 1) for rank, (symbol, _) in enumerate(ordered)}


def annualize(returns: list[float]) -> float | None:
    if not returns:
        return None
    arr = np.asarray(returns, dtype=float)
    if np.any(arr <= -1.0):
        return None
    growth = float(np.prod(1.0 + arr))
    return float(growth ** ((252.0 / REBALANCE_SESSIONS) / len(arr)) - 1.0)


def mean(values: list[float]) -> float | None:
    return None if not values else float(np.mean(np.asarray(values, dtype=float)))


def main() -> None:
    ticker_map = get("https://www.sec.gov/files/company_tickers.json")
    cik = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in ticker_map.values()}
    facts = {}
    for symbol in (*DEV, EXTERNAL):
        facts[symbol] = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik[symbol]}.json").get("facts", {}).get("us-gaap", {})

    raw_prices = {symbol: prices.load(symbol) for symbol in ALL_PRICE}
    dev_common = pd.DatetimeIndex(sorted(set.intersection(*[set(raw_prices[s].index) for s in (*DEV, "ITB")])))
    dev_frame = pd.DataFrame({symbol: raw_prices[symbol].reindex(dev_common) for symbol in (*DEV, "ITB")}).dropna()

    first_i = 0
    while first_i < len(dev_frame) and dev_frame.index[first_i].date() < date(2019, 3, 1):
        first_i += 1
    decision_indices = list(range(first_i, len(dev_frame) - HOLD - DELAY, REBALANCE_SESSIONS))
    if len(decision_indices) < MIN_DECISIONS:
        raise RuntimeError(f"insufficient primary decisions={len(decision_indices)}")

    decisions = []
    per_dev: dict[str, list[float]] = {symbol: [] for symbol in DEV}
    external_events: list[float] = []

    for signal_i in decision_indices:
        signal_ts = dev_frame.index[signal_i]
        signal_date = signal_ts.date()
        states = {symbol: quality_state(facts[symbol], signal_date) for symbol in DEV}
        if any(state is None for state in states.values()):
            continue

        roa_rank = percentile({symbol: float(states[symbol]["roa"]) for symbol in DEV})
        cap_rank = percentile({symbol: float(states[symbol]["capitalization"]) for symbol in DEV})
        scores = {symbol: 0.5 * roa_rank[symbol] + 0.5 * cap_rank[symbol] for symbol in DEV}
        selected = [symbol for symbol, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:TOP_N]]

        entry_i = signal_i + DELAY
        exit_i = entry_i + HOLD
        gross = {symbol: float(dev_frame[symbol].iloc[exit_i] / dev_frame[symbol].iloc[entry_i] - 1.0) for symbol in DEV}
        baseline_gross = float(np.mean(list(gross.values())))
        baseline_net = baseline_gross - COMMON_COST_BPS / 10000.0
        selected_gross = float(np.mean([gross[s] for s in selected]))
        selected_peer_excess_bps = (selected_gross - baseline_gross) * 10000.0 - MARGINAL_HURDLE_BPS
        overlay_net = baseline_net + TILT_WEIGHT * (selected_gross - baseline_gross - MARGINAL_HURDLE_BPS / 10000.0)
        itb_gross = float(dev_frame["ITB"].iloc[exit_i] / dev_frame["ITB"].iloc[entry_i] - 1.0)
        itb_net = itb_gross - COMMON_COST_BPS / 10000.0
        for symbol in selected:
            per_dev[symbol].append((gross[symbol] - baseline_gross) * 10000.0 - MARGINAL_HURDLE_BPS)

        external = None
        if signal_ts in raw_prices[EXTERNAL].index:
            external_state = quality_state(facts[EXTERNAL], signal_date)
            if external_state is not None:
                combined_roa = {symbol: float(states[symbol]["roa"]) for symbol in DEV}
                combined_cap = {symbol: float(states[symbol]["capitalization"]) for symbol in DEV}
                combined_roa[EXTERNAL] = float(external_state["roa"])
                combined_cap[EXTERNAL] = float(external_state["capitalization"])
                rr = percentile(combined_roa)
                cr = percentile(combined_cap)
                combined_score = {symbol: 0.5 * rr[symbol] + 0.5 * cr[symbol] for symbol in (*DEV, EXTERNAL)}
                combined_top = [symbol for symbol, _ in sorted(combined_score.items(), key=lambda item: (-item[1], item[0]))[:TOP_N]]
                ext_index = raw_prices[EXTERNAL].index.get_loc(signal_ts)
                if isinstance(ext_index, (int, np.integer)) and ext_index + DELAY + HOLD < len(raw_prices[EXTERNAL]):
                    ext_ret = float(raw_prices[EXTERNAL].iloc[ext_index + DELAY + HOLD] / raw_prices[EXTERNAL].iloc[ext_index + DELAY] - 1.0)
                    ext_excess_bps = (ext_ret - baseline_gross) * 10000.0 - MARGINAL_HURDLE_BPS
                    selected_external = EXTERNAL in combined_top
                    if selected_external:
                        external_events.append(ext_excess_bps)
                    external = {
                        "score": combined_score[EXTERNAL],
                        "selected_top2": selected_external,
                        "peer_excess_after50_bps": ext_excess_bps,
                        "state": external_state,
                    }

        decisions.append({
            "signal_date": signal_ts.isoformat(),
            "entry_date": dev_frame.index[entry_i].isoformat(),
            "exit_date": dev_frame.index[exit_i].isoformat(),
            "selected": selected,
            "scores": scores,
            "states": states,
            "baseline_equal_dev_net": baseline_net,
            "overlay_75core_25quality_net": overlay_net,
            "incremental_overlay_bps": float((overlay_net - baseline_net) * 10000.0),
            "selected_peer_excess_after50_bps": selected_peer_excess_bps,
            "itb_net": itb_net,
            "external_DFH": external,
        })

    if len(decisions) < MIN_DECISIONS:
        raise RuntimeError(f"eligible economic decisions fell below gate={len(decisions)}")

    parts = [list(map(int, p)) for p in np.array_split(np.arange(len(decisions)), FOLDS)]
    folds = []
    for fold_no, indexes in enumerate(parts, start=1):
        rows = [decisions[i] for i in indexes]
        folds.append({
            "fold": fold_no,
            "decisions": len(rows),
            "mean_incremental_overlay_bps": mean([float(r["incremental_overlay_bps"]) for r in rows]),
            "mean_selected_peer_excess_after50_bps": mean([float(r["selected_peer_excess_after50_bps"]) for r in rows]),
        })

    dev_rows = []
    dev_passes = 0
    for symbol in DEV:
        vals = per_dev[symbol]
        avg = mean(vals)
        passed = len(vals) >= MIN_DEV_SELECTED_EVENTS and avg is not None and avg > 0.0
        dev_passes += int(passed)
        dev_rows.append({"symbol": symbol, "selected_events": len(vals), "mean_peer_excess_after50_bps": avg, "pass": passed})

    baseline = [float(r["baseline_equal_dev_net"]) for r in decisions]
    overlay = [float(r["overlay_75core_25quality_net"]) for r in decisions]
    itb = [float(r["itb_net"]) for r in decisions]
    selected_excess = [float(r["selected_peer_excess_after50_bps"]) for r in decisions]
    baseline_ann = annualize(baseline)
    overlay_ann = annualize(overlay)
    itb_ann = annualize(itb)
    increment = None if baseline_ann is None or overlay_ann is None else overlay_ann - baseline_ann
    positive_folds = sum(row["mean_incremental_overlay_bps"] is not None and row["mean_incremental_overlay_bps"] > 0 for row in folds)
    external_mean = mean(external_events)
    external_pass = len(external_events) >= MIN_EXTERNAL_SELECTED_EVENTS and external_mean is not None and external_mean > 0.0

    gate = (
        len(decisions) >= MIN_DECISIONS
        and increment is not None and increment > 0.0
        and mean(selected_excess) is not None and mean(selected_excess) > 0.0
        and positive_folds >= 4
        and dev_passes >= MIN_DEV_SYMBOL_PASSES
        and external_pass
    )
    decision = "HOMEBUILDER_SEC_QUALITY_TILT_PASSES_GATE" if gate else "HOMEBUILDER_SEC_QUALITY_TILT_REJECTED_AS_SPECIFIED"

    out = {
        "schema": "public_research.homebuilder_sec_quality_tilt_r1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parent_source_probe": SOURCE_PROBE,
        "claim": "Filed-at profitability on assets plus conservative capitalization identifies a robust marginal Homebuilder tilt over equal weight.",
        "contract": {
            "development_symbols": list(DEV),
            "fresh_external_symbol": EXTERNAL,
            "signal": "0.5 cross-sectional percentile annualized ROA + 0.5 cross-sectional percentile capitalization (1-liabilities/assets)",
            "equity_fallback": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Assets-Liabilities"],
            "max_fact_staleness_days": MAX_STALE_DAYS,
            "rebalance_sessions": REBALANCE_SESSIONS,
            "delay_sessions": DELAY,
            "hold_sessions": HOLD,
            "top_n": TOP_N,
            "portfolio": "75% equal-weight eight-builder core + 25% equal-weight top-2 SEC quality tilt",
            "common_cost_bps": COMMON_COST_BPS,
            "marginal_hurdle_bps": MARGINAL_HURDLE_BPS,
            "model_fit": False,
            "threshold_search": False,
            "parameter_search": False,
            "external_outcome_used_for_design": False,
        },
        "acceptance_gate": {
            "minimum_decisions": MIN_DECISIONS,
            "annualized_increment_over_equal_core_gt_zero": True,
            "positive_folds_required": 4,
            "minimum_development_symbol_passes": MIN_DEV_SYMBOL_PASSES,
            "minimum_selected_events_per_development_symbol": MIN_DEV_SELECTED_EVENTS,
            "fresh_DFH_minimum_selected_events": MIN_EXTERNAL_SELECTED_EVENTS,
            "fresh_DFH_mean_peer_excess_after50_bps_gt_zero": True,
        },
        "metrics": {
            "decisions": len(decisions),
            "baseline_equal_dev_annualized": baseline_ann,
            "quality_overlay_annualized": overlay_ann,
            "itb_annualized": itb_ann,
            "annualized_increment_over_equal_core": increment,
            "mean_incremental_overlay_bps": mean([float(r["incremental_overlay_bps"]) for r in decisions]),
            "mean_selected_peer_excess_after50_bps": mean(selected_excess),
            "positive_folds": positive_folds,
            "development_symbol_passes": dev_passes,
            "fresh_DFH_selected_events": len(external_events),
            "fresh_DFH_mean_peer_excess_after50_bps": external_mean,
            "fresh_DFH_pass": external_pass,
        },
        "folds": folds,
        "development_symbols": dev_rows,
        "decision": decision,
        "boundaries": {"research_only": True, "allocation_authority": False, "runtime_mutation": False, "broker_authority": False, "live_trading_change": False},
        "decisions": decisions,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    receipt = {k: out[k] for k in ("schema", "decision", "metrics", "folds", "development_symbols")}
    print("HOMEBUILDER_SEC_QUALITY_RECEIPT=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
