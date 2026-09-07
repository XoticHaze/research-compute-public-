from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "2008-01-01"
END = "2026-09-07"
COSTS_BPS = [10.0, 25.0, 50.0]
PRIMARY_COST_BPS = 25.0
MOMENTUM_LOOKBACK = 126
TOP_N = 3
MIN_SCORE_COMPONENTS = 2
OUT = "opportunity-parallel-sec-fundamentals-receipt.json"

GROUPS = {
    "semiconductors": {
        "symbols": ["AMAT", "LRCX", "KLAC", "MU", "AMD", "QCOM"],
        "benchmark": "SMH",
    },
    "homebuilders": {
        "symbols": ["DHI", "LEN", "PHM", "TOL", "NVR", "MHO"],
        "benchmark": "ITB",
    },
}
ALL_STOCKS = [s for g in GROUPS.values() for s in g["symbols"]]
BENCHMARKS = sorted({g["benchmark"] for g in GROUPS.values()})
ALL_PRICE_SYMBOLS = ALL_STOCKS + BENCHMARKS + ["SPY", "QQQ"]

SEC_UA = "CommandCenterResearch/1.0 https://github.com/XoticHaze/research-compute-public-"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
OPERATING_TAGS = ("OperatingIncomeLoss",)
CFO_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_json(url: str, *, sec: bool = False) -> tuple[dict, str]:
    headers = {"User-Agent": SEC_UA if sec else "Mozilla/5.0 CommandCenterResearch/1.0"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=45) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def load_price(symbol: str) -> pd.Series:
    query = urlencode(
        {
            "period1": epoch(START),
            "period2": epoch(END),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    payload, _ = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}")
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no Yahoo chart result")
    timestamps = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
    indicators = result.get("indicators", {})
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    close = adjusted or (indicators.get("quote") or [{}])[0].get("close")
    series = pd.Series(
        pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(),
        index=timestamps,
        name=symbol,
    ).dropna()
    if len(series) < 1500:
        raise RuntimeError(f"{symbol}: insufficient price rows {len(series)}")
    return series[~series.index.duplicated(keep="last")].sort_index()


def ticker_ciks() -> tuple[dict[str, int], str]:
    payload, digest = fetch_json(SEC_TICKERS_URL, sec=True)
    mapping: dict[str, int] = {}
    for row in payload.values():
        ticker = str(row.get("ticker", "")).upper()
        if ticker:
            mapping[ticker] = int(row["cik_str"])
    missing = [symbol for symbol in ALL_STOCKS if symbol not in mapping]
    if missing:
        raise RuntimeError(f"SEC ticker map missing symbols: {missing}")
    return mapping, digest


def choose_tag(facts: dict, candidates: tuple[str, ...]) -> str | None:
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in candidates:
        if tag in usgaap and "USD" in usgaap[tag].get("units", {}):
            return tag
    return None


def period_days(row: dict) -> int | None:
    try:
        return (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).days
    except Exception:
        return None


def select_accession_value(rows: list[dict], accn: str, form: str, target_days: int) -> dict | None:
    candidates = []
    for row in rows:
        if row.get("accn") != accn or row.get("form") != form or "val" not in row:
            continue
        days = period_days(row)
        if days is None or not math.isfinite(float(row["val"])):
            continue
        candidates.append((abs(days - target_days), -days, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def extract_fundamental_events(symbol: str, cik: int) -> tuple[pd.DataFrame, dict]:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    facts, digest = fetch_json(url, sec=True)
    time.sleep(0.12)

    rev_tag = choose_tag(facts, REVENUE_TAGS)
    op_tag = choose_tag(facts, OPERATING_TAGS)
    cfo_tag = choose_tag(facts, CFO_TAGS)
    if not rev_tag or not op_tag:
        return pd.DataFrame(), {
            "cik": cik,
            "companyfacts_sha256": digest,
            "revenue_tag": rev_tag,
            "operating_income_tag": op_tag,
            "cfo_tag": cfo_tag,
            "status": "INSUFFICIENT_TAGS",
        }

    usgaap = facts["facts"]["us-gaap"]
    rev_rows = usgaap[rev_tag]["units"]["USD"]
    op_rows = usgaap[op_tag]["units"]["USD"]
    cfo_rows = usgaap[cfo_tag]["units"]["USD"] if cfo_tag else []

    accessions: dict[str, dict] = {}
    for source_row in rev_rows:
        form = source_row.get("form")
        accn = source_row.get("accn")
        filed = source_row.get("filed")
        if form not in {"10-Q", "10-K"} or not accn or not filed:
            continue
        target_days = 90 if form == "10-Q" else 365
        chosen_rev = select_accession_value(rev_rows, accn, form, target_days)
        chosen_op = select_accession_value(op_rows, accn, form, target_days)
        if not chosen_rev or not chosen_op:
            continue
        fy = chosen_rev.get("fy")
        fp = chosen_rev.get("fp")
        if fy is None or not fp:
            continue
        chosen_cfo = select_accession_value(cfo_rows, accn, form, target_days) if cfo_rows else None
        accessions[accn] = {
            "symbol": symbol,
            "accn": accn,
            "filed": pd.Timestamp(filed, tz="UTC"),
            "form": form,
            "fy": int(fy),
            "fp": str(fp),
            "revenue": float(chosen_rev["val"]),
            "operating_income": float(chosen_op["val"]),
            "cfo": float(chosen_cfo["val"]) if chosen_cfo else np.nan,
            "period_end": pd.Timestamp(chosen_rev["end"], tz="UTC"),
        }

    rows = sorted(accessions.values(), key=lambda row: (row["filed"], row["accn"]))
    history: dict[tuple[str, int], dict] = {}
    output = []
    for row in rows:
        previous = history.get((row["fp"], row["fy"] - 1))
        history[(row["fp"], row["fy"])] = row
        if not previous or previous["revenue"] == 0:
            continue

        revenue_yoy = row["revenue"] / previous["revenue"] - 1.0
        operating_margin = row["operating_income"] / row["revenue"] if row["revenue"] else np.nan
        prior_operating_margin = previous["operating_income"] / previous["revenue"] if previous["revenue"] else np.nan
        operating_margin_delta = operating_margin - prior_operating_margin
        components = [
            float(np.clip(revenue_yoy / 0.25, -2.0, 2.0)),
            float(np.clip(operating_margin_delta / 0.05, -2.0, 2.0)),
        ]
        cfo_margin_delta = np.nan
        if (
            math.isfinite(row["cfo"])
            and math.isfinite(previous["cfo"])
            and row["revenue"]
            and previous["revenue"]
        ):
            cfo_margin_delta = row["cfo"] / row["revenue"] - previous["cfo"] / previous["revenue"]
            components.append(float(np.clip(cfo_margin_delta / 0.05, -2.0, 2.0)))
        if len(components) < MIN_SCORE_COMPONENTS:
            continue
        output.append(
            {
                **row,
                "revenue_yoy": float(revenue_yoy),
                "operating_margin_delta": float(operating_margin_delta),
                "cfo_margin_delta": float(cfo_margin_delta) if math.isfinite(cfo_margin_delta) else np.nan,
                "fundamental_score": float(np.mean(components)),
                "score_components": len(components),
            }
        )

    return pd.DataFrame(output), {
        "cik": cik,
        "companyfacts_sha256": digest,
        "revenue_tag": rev_tag,
        "operating_income_tag": op_tag,
        "cfo_tag": cfo_tag,
        "status": "PASS" if output else "NO_CAUSAL_EVENTS",
        "causal_events": len(output),
    }


def latest_event_asof(events: pd.DataFrame, asof: pd.Timestamp) -> pd.Series | None:
    if events.empty:
        return None
    eligible = events.loc[events["filed"] < asof]
    if eligible.empty:
        return None
    return eligible.sort_values(["filed", "accn"]).iloc[-1]


def percentile(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True)


def weights(selected: list[str]) -> dict[str, float]:
    return {symbol: 1.0 / len(selected) for symbol in selected} if selected else {}


def turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    names = set(previous) | set(current)
    risky = sum(abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in names)
    return 0.5 * (risky + abs((1.0 - sum(current.values())) - (1.0 - sum(previous.values()))))


def performance(rows: list[tuple[pd.Timestamp, float]]) -> dict:
    if not rows:
        return {"periods": 0}
    wealth = [1.0]
    yearly: dict[str, float] = {}
    for date, ret in rows:
        wealth.append(wealth[-1] * (1.0 + ret))
        yearly[str(date.year)] = yearly.get(str(date.year), 1.0) * (1.0 + ret)
    span = max((rows[-1][0] - rows[0][0]).days / 365.25, 1.0 / 12.0)
    peak = wealth[0]
    max_drawdown = 0.0
    for value in wealth:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)
    monthly = np.array([ret for _, ret in rows], dtype=float)
    ann_vol = float(np.std(monthly, ddof=0) * math.sqrt(12.0)) if len(monthly) > 1 else 0.0
    cagr = wealth[-1] ** (1.0 / span) - 1.0
    return {
        "periods": len(rows),
        "total_return": wealth[-1] - 1.0,
        "cagr": cagr,
        "annualized_volatility": ann_vol,
        "return_over_volatility": cagr / ann_vol if ann_vol else None,
        "max_drawdown": max_drawdown,
        "calendar_year_returns": {year: value - 1.0 for year, value in sorted(yearly.items())},
    }


def main() -> None:
    ciks, ticker_map_sha = ticker_ciks()
    events: dict[str, pd.DataFrame] = {}
    sec_sources: dict[str, dict] = {}
    for symbol in ALL_STOCKS:
        frame, source = extract_fundamental_events(symbol, ciks[symbol])
        events[symbol] = frame
        sec_sources[symbol] = source

    price_series = {symbol: load_price(symbol) for symbol in ALL_PRICE_SYMBOLS}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(series.index) for series in price_series.values()])))
    prices = pd.DataFrame({symbol: series.reindex(common) for symbol, series in price_series.items()}).dropna()
    if len(prices) < 1500:
        raise RuntimeError(f"insufficient common price rows: {len(prices)}")

    monthends = [
        i
        for i in range(MOMENTUM_LOOKBACK, len(prices) - 1)
        if prices.index[i].month != prices.index[i + 1].month
    ]
    decisions = []
    for n, i in enumerate(monthends[:-1]):
        j = monthends[n + 1]
        asof = prices.index[i]
        rows = []
        for group_name, spec in GROUPS.items():
            for symbol in spec["symbols"]:
                event = latest_event_asof(events[symbol], asof)
                if event is None:
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "group": group_name,
                        "benchmark": spec["benchmark"],
                        "fundamental_score": float(event["fundamental_score"]),
                        "momentum": float(prices[symbol].iloc[i] / prices[symbol].iloc[i - MOMENTUM_LOOKBACK] - 1.0),
                        "filed": event["filed"],
                    }
                )
        if len(rows) < 8:
            continue
        panel = pd.DataFrame(rows)
        panel["fundamental_pct"] = percentile(panel["fundamental_score"])
        panel["momentum_pct"] = percentile(panel["momentum"])
        panel["combined_score"] = 0.5 * panel["fundamental_pct"] + 0.5 * panel["momentum_pct"]
        selections = {
            "fundamental_top3": panel.sort_values(["fundamental_score", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "momentum_top3": panel.sort_values(["momentum", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "combined_top3": panel.sort_values(["combined_score", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "equal_all": sorted(panel["symbol"].tolist()),
        }
        for group_name in GROUPS:
            group_panel = panel.loc[panel["group"] == group_name]
            if len(group_panel) >= 3:
                selections[f"{group_name}_fundamental_top2"] = group_panel.sort_values(
                    ["fundamental_score", "symbol"], ascending=[False, True]
                ).head(2)["symbol"].tolist()
                selections[f"{group_name}_equal"] = sorted(group_panel["symbol"].tolist())
        decisions.append((i, j, panel, selections))

    if len(decisions) < 60:
        raise RuntimeError(f"insufficient monthly decisions: {len(decisions)}")

    policy_names = ["fundamental_top3", "momentum_top3", "combined_top3", "equal_all"]
    for group_name in GROUPS:
        policy_names.extend([f"{group_name}_fundamental_top2", f"{group_name}_equal"])
    results = {policy: {cost: [] for cost in COSTS_BPS} for policy in policy_names}
    previous_weights = {policy: {} for policy in policy_names}
    turns = {policy: [] for policy in policy_names}
    baselines = {name: [] for name in BENCHMARKS + ["SPY", "QQQ", "equal_industry_etfs"]}
    diagnostics = []

    for i, j, panel, selections in decisions:
        end_date = prices.index[j]
        for policy in policy_names:
            selected = selections.get(policy, [])
            current_weights = weights(selected)
            gross = sum(
                weight * float(prices[symbol].iloc[j] / prices[symbol].iloc[i] - 1.0)
                for symbol, weight in current_weights.items()
            )
            one_way_turnover = turnover(previous_weights[policy], current_weights)
            turns[policy].append(one_way_turnover)
            for cost in COSTS_BPS:
                results[policy][cost].append((end_date, gross - one_way_turnover * cost / 10000.0))
            previous_weights[policy] = current_weights

        for benchmark in BENCHMARKS + ["SPY", "QQQ"]:
            baselines[benchmark].append((end_date, float(prices[benchmark].iloc[j] / prices[benchmark].iloc[i] - 1.0)))
        baselines["equal_industry_etfs"].append(
            (
                end_date,
                float(np.mean([prices[benchmark].iloc[j] / prices[benchmark].iloc[i] - 1.0 for benchmark in BENCHMARKS])),
            )
        )

        future = {
            row.symbol: float(prices[row.symbol].iloc[j] / prices[row.symbol].iloc[i] - 1.0)
            for row in panel.itertuples(index=False)
        }
        pairs = 0
        concordant = 0
        for a_idx in range(len(panel)):
            for b_idx in range(a_idx + 1, len(panel)):
                a = panel.iloc[a_idx]
                b = panel.iloc[b_idx]
                score_delta = float(a["fundamental_score"] - b["fundamental_score"])
                return_delta = future[a["symbol"]] - future[b["symbol"]]
                if score_delta == 0 or return_delta == 0:
                    continue
                pairs += 1
                concordant += int(score_delta * return_delta > 0)
        fundamental_top = selections["fundamental_top3"]
        rest = [symbol for symbol in panel["symbol"] if symbol not in fundamental_top]
        diagnostics.append(
            {
                "date": end_date.isoformat(),
                "pair_count": pairs,
                "pairwise_concordance": concordant / pairs if pairs else None,
                "fundamental_top3_minus_rest": float(np.mean([future[s] for s in fundamental_top]) - np.mean([future[s] for s in rest])) if rest else None,
                "combined_minus_fundamental": float(
                    np.mean([future[s] for s in selections["combined_top3"]])
                    - np.mean([future[s] for s in selections["fundamental_top3"]])
                ),
            }
        )

    summaries = {
        policy: {str(int(cost)): performance(results[policy][cost]) for cost in COSTS_BPS}
        for policy in policy_names
    }
    baseline_summaries = {name: performance(rows) for name, rows in baselines.items()}
    primary_key = str(int(PRIMARY_COST_BPS))

    fold_indexes = np.array_split(np.arange(len(decisions)), 5)
    folds = []
    for fold_number, indexes in enumerate(fold_indexes, start=1):
        if len(indexes) == 0:
            continue
        fold_row = {"fold": fold_number, "months": int(len(indexes))}
        for policy in ["fundamental_top3", "momentum_top3", "combined_top3", "equal_all"]:
            values = [results[policy][PRIMARY_COST_BPS][int(k)][1] for k in indexes]
            fold_row[policy] = float(np.prod(np.array(values) + 1.0) - 1.0)
        for benchmark in ["equal_industry_etfs", "SPY", "QQQ"]:
            values = [baselines[benchmark][int(k)][1] for k in indexes]
            fold_row[benchmark] = float(np.prod(np.array(values) + 1.0) - 1.0)
        folds.append(fold_row)

    diagnostic_frame = pd.DataFrame(diagnostics)
    valid_concordance = diagnostic_frame["pairwise_concordance"].notna()
    mean_concordance = (
        float(
            np.average(
                diagnostic_frame.loc[valid_concordance, "pairwise_concordance"],
                weights=diagnostic_frame.loc[valid_concordance, "pair_count"],
            )
        )
        if valid_concordance.any()
        else None
    )
    mean_top_delta = float(diagnostic_frame["fundamental_top3_minus_rest"].dropna().mean())
    mean_combined_increment = float(diagnostic_frame["combined_minus_fundamental"].dropna().mean())

    fundamental = summaries["fundamental_top3"][primary_key]
    momentum = summaries["momentum_top3"][primary_key]
    combined = summaries["combined_top3"][primary_key]
    equal_all = summaries["equal_all"][primary_key]
    equal_etfs = baseline_summaries["equal_industry_etfs"]
    fundamental_fold_wins = sum(row["fundamental_top3"] > row["momentum_top3"] for row in folds)
    combined_momentum_fold_wins = sum(row["combined_top3"] > row["momentum_top3"] for row in folds)
    combined_fundamental_fold_wins = sum(row["combined_top3"] > row["fundamental_top3"] for row in folds)

    fundamental_evidence = (
        fundamental["cagr"] > momentum["cagr"]
        and fundamental["cagr"] > equal_all["cagr"]
        and fundamental["cagr"] > equal_etfs["cagr"]
        and fundamental_fold_wins >= 3
        and mean_top_delta > 0
        and mean_concordance is not None
        and mean_concordance > 0.5
    )
    combined_evidence = (
        combined["cagr"] > momentum["cagr"]
        and combined["cagr"] > fundamental["cagr"]
        and combined_momentum_fold_wins >= 3
        and combined_fundamental_fold_wins >= 3
        and mean_combined_increment > 0
    )

    per_group = {}
    for group_name, spec in GROUPS.items():
        ranked = summaries[f"{group_name}_fundamental_top2"][primary_key]
        equal = summaries[f"{group_name}_equal"][primary_key]
        benchmark = baseline_summaries[spec["benchmark"]]
        per_group[group_name] = {
            "fundamental_top2": ranked,
            "equal_components": equal,
            "industry_etf": benchmark,
            "cagr_excess_vs_equal_components": ranked["cagr"] - equal["cagr"],
            "cagr_excess_vs_industry_etf": ranked["cagr"] - benchmark["cagr"],
        }

    receipt = {
        "schema": "public_research.opportunity_parallel_sec_fundamentals.v1",
        "research_only": True,
        "as_of": END,
        "objective": "Advance opportunity ranking, scarce-capital selection, transport/generalization, and independent-information value in one chronology-causal batch using SEC filing-derived fundamental change across Semiconductors and Homebuilders.",
        "source": {
            "fundamentals": {
                "provider": "SEC companyfacts",
                "ticker_map_url": SEC_TICKERS_URL,
                "ticker_map_sha256": ticker_map_sha,
                "per_symbol": sec_sources,
                "causality": "Each monthly decision uses only filing observations with SEC filed date strictly before the decision date. Same-filing accession values are paired with the same fiscal-period observation from the prior fiscal year. Later restatement filings are not backdated.",
            },
            "prices": {"provider": "Yahoo chart adjusted close", "query_host": "query1.finance.yahoo.com"},
        },
        "universe": GROUPS,
        "parameters": {
            "momentum_lookback_sessions": MOMENTUM_LOOKBACK,
            "top_n_cross_universe": TOP_N,
            "within_industry_top_n": 2,
            "costs_bps": COSTS_BPS,
            "primary_cost_bps": PRIMARY_COST_BPS,
            "fundamental_score": "mean of clipped revenue YoY / 25%, operating-margin delta / 5pp, and when available operating-cash-flow-margin delta / 5pp; each component clipped to [-2,2]",
            "combined_score": "50% cross-sectional fundamental percentile + 50% cross-sectional 126-session momentum percentile",
        },
        "matched_window": {
            "signal_start": prices.index[decisions[0][0]].isoformat(),
            "return_end": prices.index[decisions[-1][1]].isoformat(),
            "common_daily_rows": len(prices),
            "monthly_decisions": len(decisions),
        },
        "summaries": summaries,
        "baselines": baseline_summaries,
        "ranking_diagnostics": {
            "pairwise_concordance": mean_concordance,
            "mean_fundamental_top3_minus_rest_monthly_return": mean_top_delta,
            "mean_combined_minus_fundamental_monthly_return": mean_combined_increment,
        },
        "chronological_folds": folds,
        "primary_fold_counts": {
            "fundamental_beats_momentum": fundamental_fold_wins,
            "combined_beats_momentum": combined_momentum_fold_wins,
            "combined_beats_fundamental": combined_fundamental_fold_wins,
        },
        "per_group_transport": per_group,
        "turnover": {
            policy: {"mean_one_way": float(np.mean(values)), "median_one_way": float(np.median(values))}
            for policy, values in turns.items()
        },
        "decisions": {
            "independent_fundamental_information": "SUPPORTED" if fundamental_evidence else "NOT_SUPPORTED",
            "fundamental_plus_price_increment": "SUPPORTED" if combined_evidence else "NOT_SUPPORTED",
            "overall": "OPPORTUNITY_SYSTEM_FUNDAMENTAL_BATCH_SUPPORTED" if fundamental_evidence or combined_evidence else "OPPORTUNITY_SYSTEM_FUNDAMENTAL_BATCH_NOT_SUPPORTED",
        },
        "interpretation_boundaries": {
            "allocation_authority": False,
            "promotion_authority": False,
            "runtime_authority": False,
            "broker_authority": False,
            "live_trading_change": False,
            "no_parameter_search": True,
            "no_model_refit": True,
        },
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    print("OPPORTUNITY_PARALLEL_RESULT=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
