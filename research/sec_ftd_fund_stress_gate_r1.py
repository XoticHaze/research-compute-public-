from __future__ import annotations

import csv
import io
import json
import math
import statistics
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

SEMANTIC_ID = "SEC_FTD_FUND_STRESS_GATE_R1"
SCHEMA = "research.sec_ftd_fund_stress_gate.v1"
ETFS = ["QQQ", "IWM", "HYG", "XLK", "XLF"]
MARKET = "SPY"
START_YEAR = 2020
END_YEAR = 2026
TRAILING_PERIODS = 12
MIN_HISTORY = 8
STRESS_QUANTILE = 0.75
DISCLOSURE_LAG_DAYS = 30
COST_PER_SWITCH_BPS = 5.0
RECENT_START = "2022-01-01"
HEADERS = {
    "User-Agent": "XoticHaze/1.0 market-research contact 152584286+XoticHaze@users.noreply.github.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "*/*",
}


def percentile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def archive_periods() -> list[tuple[int, int, str, date]]:
    out = []
    today = date.today()
    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            for half in ("a", "b"):
                if half == "a":
                    period_end = date(year, month, 15)
                else:
                    if month == 12:
                        period_end = date(year, 12, 31)
                    else:
                        period_end = date(year, month + 1, 1) - timedelta(days=1)
                if period_end + timedelta(days=DISCLOSURE_LAG_DAYS) <= today:
                    out.append((year, month, half, period_end))
    return out


def parse_ftd_zip(raw: bytes) -> dict[str, float]:
    totals = {s: 0.0 for s in ETFS}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            return totals
        payload = zf.read(names[0]).decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(payload), delimiter="|")
    for row in reader:
        symbol = (row.get("SYMBOL") or "").strip().upper()
        if symbol not in totals:
            continue
        q = row.get("QUANTITY (FAILS)") or row.get("QUANTITY") or "0"
        p = row.get("PRICE") or "0"
        try:
            totals[symbol] += float(q.replace(",", "")) * float(p.replace("$", "").replace(",", ""))
        except (ValueError, AttributeError):
            continue
    return totals


def fetch_ftd() -> tuple[list[dict], dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    periods = []
    errors = []
    for year, month, half, period_end in archive_periods():
        url = f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{year}{month:02d}{half}.zip"
        try:
            r = session.get(url, timeout=(10, 45))
            if r.status_code == 404:
                errors.append({"url": url, "status": 404})
                continue
            r.raise_for_status()
            totals = parse_ftd_zip(r.content)
            periods.append({
                "period_end": period_end.isoformat(),
                "available_date": (period_end + timedelta(days=DISCLOSURE_LAG_DAYS)).isoformat(),
                "url": url,
                "ftd_dollar": totals,
            })
            time.sleep(0.10)
        except Exception as exc:
            errors.append({"url": url, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})
    return periods, {"requested": len(archive_periods()), "loaded": len(periods), "errors": errors}


def yahoo_prices(symbol: str, start: date, end: date) -> dict[date, float]:
    p1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(10, 45))
    r.raise_for_status()
    obj = r.json()["chart"]["result"][0]
    ts = obj["timestamp"]
    adj = obj["indicators"].get("adjclose", [{}])[0].get("adjclose")
    if adj is None:
        adj = obj["indicators"]["quote"][0]["close"]
    out = {}
    for t, px in zip(ts, adj):
        if px is not None:
            out[datetime.fromtimestamp(t, tz=timezone.utc).date()] = float(px)
    return out


def returns(prices: dict[date, float]) -> dict[date, float]:
    ds = sorted(prices)
    out = {}
    for prev, cur in zip(ds, ds[1:]):
        if prices[prev] > 0:
            out[cur] = prices[cur] / prices[prev] - 1.0
    return out


def signals(periods: list[dict]) -> dict[str, list[tuple[date, bool, float, float]]]:
    out = {s: [] for s in ETFS}
    hist = {s: [] for s in ETFS}
    for rec in sorted(periods, key=lambda x: x["period_end"]):
        available = date.fromisoformat(rec["available_date"])
        for s in ETFS:
            v = float(rec["ftd_dollar"].get(s, 0.0))
            prior = hist[s][-TRAILING_PERIODS:]
            if len(prior) >= MIN_HISTORY:
                threshold = percentile(prior, STRESS_QUANTILE)
                out[s].append((available, v > threshold, v, threshold))
            hist[s].append(v)
    return out


def active_signal(points: list[tuple[date, bool, float, float]], d: date) -> bool | None:
    value = None
    for available, stress, _, _ in points:
        if available <= d:
            value = stress
        else:
            break
    return value


def max_drawdown(daily: list[tuple[date, float]]) -> float:
    nav = 1.0
    peak = 1.0
    worst = 0.0
    for _, r in daily:
        nav *= 1.0 + r
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst


def cagr(daily: list[tuple[date, float]]) -> float:
    if len(daily) < 2:
        return float("nan")
    nav = 1.0
    for _, r in daily:
        nav *= 1.0 + r
    years = max((daily[-1][0] - daily[0][0]).days / 365.25, 1 / 365.25)
    return nav ** (1.0 / years) - 1.0


def annual_returns(daily: list[tuple[date, float]]) -> dict[int, float]:
    by = {}
    for d, r in daily:
        by.setdefault(d.year, []).append(r)
    out = {}
    for y, rs in by.items():
        nav = 1.0
        for r in rs:
            nav *= 1.0 + r
        out[y] = nav - 1.0
    return out


def recent_cagr(daily: list[tuple[date, float]]) -> float:
    cutoff = date.fromisoformat(RECENT_START)
    return cagr([(d, r) for d, r in daily if d >= cutoff])


def main() -> None:
    periods, source = fetch_ftd()
    if len(periods) < 40:
        raise RuntimeError(f"insufficient SEC FTD history: loaded={len(periods)}")
    sig = signals(periods)
    first_ready = [pts[0][0] for pts in sig.values() if pts]
    if len(first_ready) != len(ETFS):
        raise RuntimeError("not all ETFs obtained an admissible FTD signal history")
    eval_start = max(first_ready)
    price_start = eval_start - timedelta(days=10)
    price_end = date.today()
    price = {s: yahoo_prices(s, price_start, price_end) for s in ETFS + [MARKET]}
    ret = {s: returns(price[s]) for s in price}
    common_dates = sorted(set.intersection(*(set(ret[s]) for s in ETFS + [MARKET])))
    common_dates = [d for d in common_dates if d >= eval_start]
    if len(common_dates) < 500:
        raise RuntimeError(f"insufficient common price days: {len(common_dates)}")

    model_daily = []
    basket_daily = []
    market_daily = []
    per_etf_model = {s: [] for s in ETFS}
    per_etf_bh = {s: [] for s in ETFS}
    prior_state = {s: None for s in ETFS}
    switches = {s: 0 for s in ETFS}

    for d in common_dates:
        model_components = []
        basket_components = []
        for s in ETFS:
            stress = active_signal(sig[s], d)
            if stress is None:
                continue
            invested = not stress
            cost = 0.0
            if prior_state[s] is not None and invested != prior_state[s]:
                cost = COST_PER_SWITCH_BPS / 10000.0
                switches[s] += 1
            prior_state[s] = invested
            mr = (ret[s][d] if invested else 0.0) - cost
            br = ret[s][d]
            model_components.append(mr)
            basket_components.append(br)
            per_etf_model[s].append((d, mr))
            per_etf_bh[s].append((d, br))
        if len(model_components) == len(ETFS):
            model_daily.append((d, statistics.fmean(model_components)))
            basket_daily.append((d, statistics.fmean(basket_components)))
            market_daily.append((d, ret[MARKET][d]))

    model_cagr = cagr(model_daily)
    basket_cagr = cagr(basket_daily)
    market_cagr = cagr(market_daily)
    model_year = annual_returns(model_daily)
    basket_year = annual_returns(basket_daily)
    years = sorted(set(model_year) & set(basket_year))
    year_excess = {str(y): model_year[y] - basket_year[y] for y in years}
    positive_year_fraction = sum(1 for y in years if year_excess[str(y)] > 0) / len(years)

    per_etf = {}
    positive_etf = 0
    for s in ETFS:
        mc = cagr(per_etf_model[s])
        bc = cagr(per_etf_bh[s])
        ex = mc - bc
        positive_etf += int(ex > 0)
        per_etf[s] = {
            "model_cagr": mc,
            "buy_hold_cagr": bc,
            "excess_cagr": ex,
            "model_max_drawdown": max_drawdown(per_etf_model[s]),
            "buy_hold_max_drawdown": max_drawdown(per_etf_bh[s]),
            "switches": switches[s],
        }

    metrics = {
        "model_cagr": model_cagr,
        "matched_equal_weight_buy_hold_cagr": basket_cagr,
        "spy_cagr": market_cagr,
        "excess_cagr_vs_matched": model_cagr - basket_cagr,
        "excess_cagr_vs_spy": model_cagr - market_cagr,
        "model_max_drawdown": max_drawdown(model_daily),
        "matched_max_drawdown": max_drawdown(basket_daily),
        "spy_max_drawdown": max_drawdown(market_daily),
        "recent_model_cagr": recent_cagr(model_daily),
        "recent_matched_cagr": recent_cagr(basket_daily),
        "recent_excess_cagr_vs_matched": recent_cagr(model_daily) - recent_cagr(basket_daily),
        "positive_calendar_year_fraction_vs_matched": positive_year_fraction,
        "positive_etf_count": positive_etf,
        "calendar_year_excess": year_excess,
        "per_etf": per_etf,
    }
    gates = {
        "excess_cagr_vs_matched_gte_1pct": metrics["excess_cagr_vs_matched"] >= 0.01,
        "recent_excess_gte_0_5pct": metrics["recent_excess_cagr_vs_matched"] >= 0.005,
        "positive_calendar_year_fraction_gte_60pct": positive_year_fraction >= 0.60,
        "model_drawdown_not_worse_than_matched": metrics["model_max_drawdown"] >= metrics["matched_max_drawdown"],
        "positive_etfs_gte_3_of_5": positive_etf >= 3,
    }
    decision = "PROMOTE_FOR_INDEPENDENT_VALIDATION" if all(gates.values()) else "REJECT_NO_PARAMETER_RESCUE"
    out = {
        "schema": SCHEMA,
        "semantic_id": SEMANTIC_ID,
        "claim_tested": "Conservatively disclosed, unusually high ETF failures-to-deliver stress predicts enough subsequent underperformance that a frozen cash gate improves a diversified ETF basket after switching costs.",
        "inheritance": {
            "scientific_parent_state": "unconditional realized-accounting, quarterly-EPS, expectation-relative EPS-sign, and insider-purchase branches are terminally rejected; this child tests orthogonal settlement-stress information",
            "unresolved_uncertainty": "whether market-microstructure settlement stress contains durable fund-level timing information beyond those rejected corporate-event signals",
        },
        "frozen_spec": {
            "etfs": ETFS,
            "market_control": MARKET,
            "sec_source": "SEC CNS failures-to-deliver half-month archives",
            "start_year": START_YEAR,
            "trailing_periods": TRAILING_PERIODS,
            "min_history": MIN_HISTORY,
            "stress_definition": "current half-month FTD dollar notional above the 75th percentile of the prior 12 half-month observations for the same ETF",
            "disclosure_lag_days": DISCLOSURE_LAG_DAYS,
            "portfolio": "equal weight across five ETFs; each sleeve holds ETF when non-stress and cash when stress",
            "cost_per_position_switch_bps": COST_PER_SWITCH_BPS,
            "forbidden_parameter_rescue": ["stress percentile", "lookback", "disclosure lag", "ETF panel", "cost", "recent cutoff", "post-hoc year exclusion"],
        },
        "source_coverage": source,
        "evaluation_start": eval_start.isoformat(),
        "evaluation_end": common_dates[-1].isoformat(),
        "metrics": metrics,
        "promotion_gates": gates,
        "decision": decision,
        "best_current_explanation": "unknown until the frozen discriminator is observed",
        "strongest_competing_explanation": "FTD is heterogeneous settlement plumbing rather than directional information and therefore should not reliably forecast ETF excess returns.",
        "forward_eligibility": decision == "PROMOTE_FOR_INDEPENDENT_VALIDATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path("artifacts").mkdir(exist_ok=True)
    path = Path("artifacts/sec_ftd_fund_stress_gate_r1.json")
    path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
