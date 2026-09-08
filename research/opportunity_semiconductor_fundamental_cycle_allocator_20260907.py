from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SEC_CACHE = Path("sec_hf_root_parquet_semiconductor_cache_20260906.json")
CYCLE_CACHE = Path("semiconductor_alfred_information_snapshot_cache_20260906.json")
OUT = Path("opportunity_semiconductor_fundamental_cycle_allocator_20260907.json")

EXPECTED_SEC_SHA = "be686117f6618c458dfbc54d8d247f7a2c184732d504e4a15e8ecce2cd0eee9f"
EXPECTED_SEC_REVISION = "4f36750460fbef3607fb480cc7abbb1ddfbd7bc9"
EXPECTED_CYCLE_SHA = "4f9afee5a077922c9920f33f999b49a11710355828770dd78cc784a4d57669c8"

SOURCE_UNIVERSE = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
PRICE_CONTROLS = ("SMH", "SPY", "QQQ")
START = "2014-01-01"
END = "2026-09-07"
MOMENTUM_LOOKBACK = 126
TOP_N = 3
COSTS_BPS = (10.0, 25.0, 50.0)
PRIMARY_COST_BPS = 25.0
MIN_DURATION_FILINGS = 16
MIN_FILED_YEARS = 5


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value):
    if value in (None, "", "None", "NaT"):
        return None
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


def parse_float(value):
    if value in (None, "", "None", "nan", "NaN"):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def duration_days(row):
    start = parse_date(row.get("start"))
    end = parse_date(row.get("end"))
    if start is None or end is None:
        return None
    return (end - start).days


def accession_duration_observations(rows):
    grouped = {}
    for row in rows:
        accn = str(row.get("accn") or "")
        filed = parse_date(row.get("filed"))
        period_end = parse_date(row.get("end"))
        value = parse_float(row.get("val_dec"))
        form = str(row.get("form") or "")
        fy = row.get("fy")
        fp = str(row.get("fp") or "")
        days = duration_days(row)
        if not accn or filed is None or period_end is None or value is None or days is None:
            continue
        try:
            fy = int(float(fy))
        except Exception:
            continue
        target = 90 if form == "10-Q" else 365 if form == "10-K" else 365
        grouped.setdefault(accn, []).append(
            {
                "filed": filed,
                "period_end": period_end,
                "value": value,
                "form": form,
                "fy": fy,
                "fp": fp,
                "days": days,
                "distance": abs(days - target),
            }
        )
    out = {}
    ambiguous = 0
    for accn, values in grouped.items():
        values.sort(key=lambda x: (x["distance"], -x["days"], x["period_end"], x["filed"]))
        best = values[0]
        tied = [x for x in values if (x["distance"], x["days"], x["period_end"], x["filed"]) == (best["distance"], best["days"], best["period_end"], best["filed"])]
        unique_values = {x["value"] for x in tied}
        if len(unique_values) != 1:
            ambiguous += 1
            continue
        out[accn] = best
    return out, ambiguous


def build_business_snapshots(symbol_payload):
    revenue_rows = symbol_payload["categories"]["revenue"]["rows"]
    operating_rows = symbol_payload["categories"]["operating_income"]["rows"]
    revenue, revenue_ambiguous = accession_duration_observations(revenue_rows)
    operating, operating_ambiguous = accession_duration_observations(operating_rows)
    common = sorted(set(revenue) & set(operating))
    raw = []
    for accn in common:
        r = revenue[accn]
        o = operating[accn]
        if not (r["filed"] == o["filed"] and r["period_end"] == o["period_end"] and r["fy"] == o["fy"] and r["fp"] == o["fp"]):
            continue
        if r["value"] == 0:
            continue
        raw.append(
            {
                "accn": accn,
                "filed": r["filed"],
                "period_end": r["period_end"],
                "fy": r["fy"],
                "fp": r["fp"],
                "revenue": r["value"],
                "operating_income": o["value"],
                "operating_margin": o["value"] / r["value"],
            }
        )
    raw.sort(key=lambda x: (x["filed"], x["period_end"], x["accn"]))
    by_period = {(x["fy"], x["fp"]): x for x in raw}
    snapshots = []
    for current in raw:
        prior = by_period.get((current["fy"] - 1, current["fp"]))
        if prior is None or prior["filed"] >= current["filed"] or prior["revenue"] == 0:
            continue
        revenue_yoy = current["revenue"] / prior["revenue"] - 1.0
        operating_margin_delta = current["operating_margin"] - prior["operating_margin"]
        score = float(np.mean([
            np.clip(revenue_yoy / 0.25, -2.0, 2.0),
            np.clip(operating_margin_delta / 0.05, -2.0, 2.0),
        ]))
        snapshots.append(
            {
                **current,
                "revenue_yoy": float(revenue_yoy),
                "operating_margin_delta": float(operating_margin_delta),
                "fundamental_score": score,
            }
        )
    filed_years = sorted({x["filed"].year for x in snapshots})
    eligible = len(snapshots) >= MIN_DURATION_FILINGS and len(filed_years) >= MIN_FILED_YEARS
    return snapshots, {
        "revenue_accessions": len(revenue),
        "operating_accessions": len(operating),
        "revenue_ambiguous": revenue_ambiguous,
        "operating_ambiguous": operating_ambiguous,
        "same_accession_rows": len(raw),
        "annual_comparable_snapshots": len(snapshots),
        "filed_years": len(filed_years),
        "first_filed": snapshots[0]["filed"].isoformat() if snapshots else None,
        "last_filed": snapshots[-1]["filed"].isoformat() if snapshots else None,
        "source_eligible": eligible,
    }


def latest_snapshot_asof(snapshots, asof_date):
    eligible = [x for x in snapshots if x["filed"] < asof_date]
    if not eligible:
        return None
    return max(eligible, key=lambda x: (x["filed"], x["period_end"], x["accn"]))


def epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def load_price(symbol: str) -> pd.Series:
    query = urlencode({
        "period1": epoch(START),
        "period2": epoch(END),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    req = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0 CommandCenterResearch/1.0"},
    )
    last = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = (payload.get("chart", {}).get("result") or [None])[0]
            if not result:
                raise RuntimeError(f"{symbol}: missing Yahoo chart result")
            idx = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
            indicators = result.get("indicators", {})
            values = (indicators.get("adjclose") or [{}])[0].get("adjclose")
            if values is None:
                values = (indicators.get("quote") or [{}])[0].get("close")
            series = pd.Series(pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(), index=idx, name=symbol).dropna()
            if len(series) < 1500:
                raise RuntimeError(f"{symbol}: insufficient price rows={len(series)}")
            return series[~series.index.duplicated(keep="last")].sort_index()
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(0.6 * (2 ** attempt))
    raise RuntimeError(f"{symbol}: Yahoo fetch failed: {last}")


def perf(rows):
    if not rows:
        return {"periods": 0}
    wealth = 1.0
    peak = 1.0
    max_dd = 0.0
    rets = []
    yearly = {}
    for date, ret in rows:
        wealth *= 1.0 + ret
        peak = max(peak, wealth)
        max_dd = min(max_dd, wealth / peak - 1.0)
        rets.append(ret)
        yearly[str(date.year)] = yearly.get(str(date.year), 1.0) * (1.0 + ret)
    years = max((rows[-1][0] - rows[0][0]).days / 365.25, 1 / 12)
    cagr = wealth ** (1 / years) - 1
    ann_vol = float(np.std(np.asarray(rets), ddof=0) * math.sqrt(12)) if len(rets) > 1 else 0.0
    return {
        "periods": len(rows),
        "total_return": wealth - 1.0,
        "cagr": cagr,
        "annualized_volatility": ann_vol,
        "return_over_volatility": cagr / ann_vol if ann_vol else None,
        "max_drawdown": max_dd,
        "calendar_year_returns": {k: v - 1.0 for k, v in sorted(yearly.items())},
    }


def w(selected, scale=1.0):
    if not selected:
        return {}
    return {s: scale / len(selected) for s in selected}


def turnover(prev, cur):
    names = set(prev) | set(cur)
    risky = sum(abs(cur.get(s, 0.0) - prev.get(s, 0.0)) for s in names)
    cash_prev = 1.0 - sum(prev.values())
    cash_cur = 1.0 - sum(cur.values())
    return 0.5 * (risky + abs(cash_cur - cash_prev))


def expanding_percentile(history, value):
    if len(history) < 12:
        return 0.5
    arr = np.asarray(history, float)
    return float((np.sum(arr < value) + 0.5 * np.sum(arr == value)) / len(arr))


def main():
    if sha256_file(SEC_CACHE) != EXPECTED_SEC_SHA:
        raise RuntimeError("SEC cache SHA drift")
    if sha256_file(CYCLE_CACHE) != EXPECTED_CYCLE_SHA:
        raise RuntimeError("cycle cache SHA drift")
    sec = json.loads(SEC_CACHE.read_text())
    cycle = json.loads(CYCLE_CACHE.read_text())
    if sec.get("source_dataset_revision") != EXPECTED_SEC_REVISION:
        raise RuntimeError("SEC mirror revision drift")

    business = {}
    source_diag = {}
    for symbol in SOURCE_UNIVERSE:
        business[symbol], source_diag[symbol] = build_business_snapshots(sec["symbols"][symbol])
    eligible_symbols = tuple(symbol for symbol in SOURCE_UNIVERSE if source_diag[symbol]["source_eligible"])
    if len(eligible_symbols) < 5:
        raise RuntimeError(f"insufficient source-qualified semiconductor universe={eligible_symbols}")

    cycle_rows = sorted(cycle["rows"], key=lambda x: x["available_from"])
    prices = {s: load_price(s) for s in (*eligible_symbols, *PRICE_CONTROLS)}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(x.index) for x in prices.values()])))
    px = pd.DataFrame({s: series.reindex(common) for s, series in prices.items()}).dropna()
    monthends = [i for i in range(MOMENTUM_LOOKBACK, len(px) - 1) if px.index[i].month != px.index[i + 1].month]

    decisions = []
    cycle_history = []
    for n, i in enumerate(monthends[:-1]):
        j = monthends[n + 1]
        asof = px.index[i]
        asof_date = asof.date()
        panel = []
        for symbol in eligible_symbols:
            snap = latest_snapshot_asof(business[symbol], asof_date)
            if snap is None:
                continue
            panel.append({
                "symbol": symbol,
                "fundamental": snap["fundamental_score"],
                "momentum": float(px[symbol].iloc[i] / px[symbol].iloc[i - MOMENTUM_LOOKBACK] - 1.0),
                "filed": snap["filed"].isoformat(),
            })
        if len(panel) < 5:
            continue
        frame = pd.DataFrame(panel)
        frame["fund_pct"] = frame["fundamental"].rank(method="average", pct=True)
        frame["mom_pct"] = frame["momentum"].rank(method="average", pct=True)
        frame["combined"] = 0.5 * frame["fund_pct"] + 0.5 * frame["mom_pct"]

        cands = [x for x in cycle_rows if x["available_from"] <= asof_date.isoformat()]
        if not cands:
            continue
        c = cands[-1]
        cycle_raw = float(np.mean([
            float(c["semi_ip_change_3m"]) / 0.08,
            float(c["hitek_capacity_utilization_change_3m"]) / 8.0,
        ]))
        cycle_pct = expanding_percentile(cycle_history, cycle_raw)
        cycle_history.append(cycle_raw)
        cycle_scale = 0.5 + 0.5 * cycle_pct

        selections = {
            "fundamental_top3": frame.sort_values(["fundamental", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "momentum_top3": frame.sort_values(["momentum", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "combined_top3": frame.sort_values(["combined", "symbol"], ascending=[False, True]).head(TOP_N)["symbol"].tolist(),
            "equal_universe": sorted(frame["symbol"].tolist()),
        }
        decisions.append((i, j, frame, selections, cycle_scale, cycle_raw, cycle_pct))

    if len(decisions) < 60:
        raise RuntimeError(f"insufficient monthly decisions={len(decisions)}")

    policies = ("fundamental_top3", "momentum_top3", "combined_top3", "cycle_scaled_combined", "equal_universe")
    series = {p: {c: [] for c in COSTS_BPS} for p in policies}
    prev = {p: {} for p in policies}
    turns = {p: [] for p in policies}
    baselines = {s: [] for s in PRICE_CONTROLS}
    rank_diag = []

    for i, j, frame, selections, cycle_scale, cycle_raw, cycle_pct in decisions:
        end_date = px.index[j]
        weights = {
            "fundamental_top3": w(selections["fundamental_top3"]),
            "momentum_top3": w(selections["momentum_top3"]),
            "combined_top3": w(selections["combined_top3"]),
            "cycle_scaled_combined": w(selections["combined_top3"], cycle_scale),
            "equal_universe": w(selections["equal_universe"]),
        }
        future = {s: float(px[s].iloc[j] / px[s].iloc[i] - 1.0) for s in frame["symbol"]}
        for policy in policies:
            gross = sum(weight * future[s] for s, weight in weights[policy].items())
            t = turnover(prev[policy], weights[policy])
            turns[policy].append(t)
            for cost in COSTS_BPS:
                series[policy][cost].append((end_date, gross - t * cost / 10000.0))
            prev[policy] = weights[policy]
        for benchmark in PRICE_CONTROLS:
            baselines[benchmark].append((end_date, float(px[benchmark].iloc[j] / px[benchmark].iloc[i] - 1.0)))

        pairs = concordant = 0
        rows = list(frame.itertuples(index=False))
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                ds = rows[a].fundamental - rows[b].fundamental
                dr = future[rows[a].symbol] - future[rows[b].symbol]
                if ds == 0 or dr == 0:
                    continue
                pairs += 1
                concordant += int(ds * dr > 0)
        rank_diag.append({
            "date": end_date.isoformat(),
            "pairs": pairs,
            "concordance": concordant / pairs if pairs else None,
            "cycle_raw": cycle_raw,
            "cycle_expanding_percentile": cycle_pct,
            "cycle_capital_scale": cycle_scale,
        })

    summaries = {p: {str(int(c)): perf(series[p][c]) for c in COSTS_BPS} for p in policies}
    baseline_summaries = {s: perf(rows) for s, rows in baselines.items()}
    primary = str(int(PRIMARY_COST_BPS))

    folds = []
    for fold_no, idxs in enumerate(np.array_split(np.arange(len(decisions)), 5), start=1):
        row = {"fold": fold_no, "months": int(len(idxs))}
        for p in policies:
            vals = [series[p][PRIMARY_COST_BPS][int(k)][1] for k in idxs]
            row[p] = float(np.prod(np.asarray(vals) + 1.0) - 1.0)
        for b in PRICE_CONTROLS:
            vals = [baselines[b][int(k)][1] for k in idxs]
            row[b] = float(np.prod(np.asarray(vals) + 1.0) - 1.0)
        folds.append(row)

    f = summaries["fundamental_top3"][primary]
    m = summaries["momentum_top3"][primary]
    c = summaries["combined_top3"][primary]
    cs = summaries["cycle_scaled_combined"][primary]
    eq = summaries["equal_universe"][primary]
    smh = baseline_summaries["SMH"]
    fund_fold_wins = sum(row["fundamental_top3"] > row["momentum_top3"] for row in folds)
    comb_mom_fold_wins = sum(row["combined_top3"] > row["momentum_top3"] for row in folds)
    comb_fund_fold_wins = sum(row["combined_top3"] > row["fundamental_top3"] for row in folds)
    cycle_comb_fold_wins = sum(row["cycle_scaled_combined"] > row["combined_top3"] for row in folds)
    valid = [r for r in rank_diag if r["concordance"] is not None and r["pairs"] > 0]
    concordance = float(np.average([r["concordance"] for r in valid], weights=[r["pairs"] for r in valid])) if valid else None

    decisions_out = {
        "fundamental_ranking_increment": "SUPPORTED" if (
            f["cagr"] > m["cagr"] and f["cagr"] > eq["cagr"] and fund_fold_wins >= 3 and concordance is not None and concordance > 0.5
        ) else "NOT_SUPPORTED",
        "fundamental_plus_momentum_increment": "SUPPORTED" if (
            c["cagr"] > m["cagr"] and c["cagr"] > f["cagr"] and comb_mom_fold_wins >= 3 and comb_fund_fold_wins >= 3
        ) else "NOT_SUPPORTED",
        "cycle_capital_scaling_increment": "SUPPORTED" if (
            cs["return_over_volatility"] is not None and c["return_over_volatility"] is not None
            and cs["return_over_volatility"] > c["return_over_volatility"]
            and cs["max_drawdown"] > c["max_drawdown"]
            and cs["cagr"] >= c["cagr"] - 0.02
            and cycle_comb_fold_wins >= 3
        ) else "NOT_SUPPORTED",
        "beats_industry_etf_at_primary_cost": bool(max(f["cagr"], c["cagr"], cs["cagr"]) > smh["cagr"]),
    }

    receipt = {
        "schema": "public_research.opportunity_semiconductor_fundamental_cycle_allocator.v1",
        "research_only": True,
        "objective": "Improve scarce-capital semiconductor opportunity ranking and capital scaling in one batch using already-proven SEC mirror and causal ALFRED source artifacts.",
        "source_artifacts": {
            "sec": {"artifact_id": 9980193167, "cache_sha256": EXPECTED_SEC_SHA, "mirror_revision": EXPECTED_SEC_REVISION},
            "cycle": {"artifact_id": 9980128719, "cache_sha256": EXPECTED_CYCLE_SHA},
        },
        "prior_information_exclusions": {
            "balance_sheet_modality": "already rejected by run 34003476015; inventory/assets, cash/assets, annual changes and filing age are not retested",
            "direct_sec_transport": "not used; exact admitted Hugging Face mirror cache is restored instead",
        },
        "source_qualification": {
            "rule": f"revenue + operating-income annual-comparable snapshots >= {MIN_DURATION_FILINGS} and filed-year coverage >= {MIN_FILED_YEARS}, evaluated before return outcomes",
            "eligible_symbols": list(eligible_symbols),
            "diagnostics": source_diag,
        },
        "fundamental_score": "mean(clipped revenue YoY / 25%, clipped operating-margin YoY delta / 5pp), each clipped [-2,2]",
        "ranking": "top 3 by fundamental score, top 3 by 126-session momentum, and fixed 50/50 cross-sectional percentile combination",
        "cycle_scaling": "combined-top3 risky capital scaled continuously from 50% to 100% using expanding percentile of a fixed 3-month semiconductor-production/high-tech-utilization composite; remaining capital is cash",
        "matched_window": {
            "first_signal": px.index[decisions[0][0]].isoformat(),
            "last_return": px.index[decisions[-1][1]].isoformat(),
            "monthly_decisions": len(decisions),
            "common_daily_rows": len(px),
        },
        "costs_bps": list(COSTS_BPS),
        "primary_cost_bps": PRIMARY_COST_BPS,
        "summaries": summaries,
        "baselines": baseline_summaries,
        "ranking_pairwise_concordance": concordance,
        "folds": folds,
        "fold_counts": {
            "fundamental_beats_momentum": fund_fold_wins,
            "combined_beats_momentum": comb_mom_fold_wins,
            "combined_beats_fundamental": comb_fund_fold_wins,
            "cycle_scaled_beats_combined": cycle_comb_fold_wins,
        },
        "turnover": {p: {"mean_one_way": float(np.mean(v)), "median_one_way": float(np.median(v))} for p, v in turns.items()},
        "decisions": decisions_out,
        "protected_boundaries": {
            "promotion_authority": False,
            "allocation_runtime_authority": False,
            "strategy_spec_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
            "no_parameter_search": True,
        },
    }
    OUT.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print("OPPORTUNITY_SEMICONDUCTOR_FUNDAMENTAL_CYCLE_ALLOCATOR=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
