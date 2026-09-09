from __future__ import annotations

import io
import json
import math
import re
import urllib.request
from datetime import date, datetime
from html import unescape
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from lxml import etree

SYMBOLS = ("SPY", "QQQ", "TLT", "GLD", "DBC")
COSTS_BPS = (25, 50, 100)
START_MONTH = pd.Period("2016-08", freq="M")
END_MONTH = pd.Period("2026-08", freq="M")
URL = {
    "SPY_NAV": "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx",
    "SPY_DIST": "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx",
    "TLT_DOC": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual",
    "TLT_PAGE": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
    "GLD": "https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld",
    "QQQ_NAV": "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF",
    "QQQ_TR": "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/rolling?idType=ticker&variationType=1M&productType=ETF",
    "DBC_NAV": "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF",
}
DBC_DISTS = {
    date(2018, 12, 31): 0.18853,
    date(2019, 12, 31): 0.25383,
    date(2022, 12, 23): 0.14467,
    date(2023, 12, 22): 1.08926,
    date(2024, 12, 27): 1.11582,
    date(2025, 12, 26): 0.74424,
}


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 CC-Market-Research/1.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def frame(dates, values) -> pd.Series:
    x = pd.DataFrame({"date": pd.to_datetime(dates, errors="coerce"), "value": pd.to_numeric(values, errors="coerce")})
    x = x.dropna().drop_duplicates("date", keep="last").sort_values("date")
    return x.set_index("date").value.astype(float)


def workbook_rows(blob: bytes, sheet: str):
    ws = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)[sheet]
    return [list(row) for row in ws.iter_rows(values_only=True)]


def spy_nav(blob: bytes) -> pd.Series:
    rows = workbook_rows(blob, "navhist")
    i = next(i for i, row in enumerate(rows) if row and row[0] == "Date")
    h = rows[i]
    return frame([r[h.index("Date")] for r in rows[i + 1 :]], [r[h.index("NAV")] for r in rows[i + 1 :]])


def spy_dists(blob: bytes):
    rows = workbook_rows(blob, "dividend")
    h = rows[0]
    ti, ei = h.index("TICKER"), h.index("EX-DATE")
    cols = [h.index("DIVIDEND ($)"), h.index("SHORT TERM CAPITAL GAIN ($)"), h.index("LONG TERM CAPITAL GAIN ($)")]
    out = []
    for row in rows[1:]:
        if str(row[ti]).strip() != "SPY":
            continue
        d = pd.to_datetime(row[ei], errors="coerce")
        if pd.isna(d):
            continue
        amount = sum(float(row[j]) if row[j] not in (None, "") else 0.0 for j in cols)
        out.append((d.date(), amount))
    return sorted(out)


def sparse_xml_rows(blob: bytes):
    root = etree.fromstring(blob, etree.XMLParser(recover=True, huge_tree=True))
    rows = []
    for row in root.xpath('//*[local-name()="Row"]'):
        vals = []
        for cell in row.xpath('./*[local-name()="Cell"]'):
            idx = None
            for key, value in cell.attrib.items():
                if key == "Index" or key.endswith("}Index"):
                    try:
                        idx = int(value) - 1
                    except ValueError:
                        pass
                    break
            if idx is not None:
                while len(vals) < idx:
                    vals.append(None)
            data = cell.xpath('.//*[local-name()="Data"]')
            vals.append(data[0].text if data else None)
        rows.append(vals)
    return rows


def tlt_nav(blob: bytes) -> pd.Series:
    rows = sparse_xml_rows(blob)
    i = next(i for i, r in enumerate(rows) if "As Of" in r and "NAV per Share" in r)
    h = rows[i]
    di, ni = h.index("As Of"), h.index("NAV per Share")
    d, v = [], []
    for row in rows[i + 1 :]:
        if max(di, ni) >= len(row):
            continue
        dt = pd.to_datetime(row[di], errors="coerce")
        val = pd.to_numeric(row[ni], errors="coerce")
        if pd.isna(dt) or pd.isna(val) or not (20.0 <= float(val) <= 300.0):
            continue
        d.append(dt)
        v.append(float(val))
    return frame(d, v)


def tlt_dists(page_blob: bytes):
    text = unescape(page_blob.decode("utf-8", "ignore"))
    for _ in range(3):
        text = text.replace('\\"', '"').replace('\\/', '/')
    def field(name: str):
        pat = re.compile(
            rf'"fullName":"performance\.distributions\.table\.{re.escape(name)}".*?"formattedValue":(\[[^\]]*\])',
            re.S,
        )
        m = pat.search(text)
        if not m:
            raise RuntimeError(f"TLT distribution field missing: {name}")
        return json.loads(m.group(1))
    dates, amounts = field("exDate"), field("totalDistribution")
    if len(dates) != len(amounts):
        raise RuntimeError("TLT distribution field lengths differ")
    out = []
    for ds, amount in zip(dates, amounts):
        d = datetime.strptime(ds, "%b %d, %Y").date()
        out.append((d, float(amount)))
    return sorted(out)


def invesco_nav(blob: bytes) -> pd.Series:
    rows = json.loads(blob.decode("utf-8"))
    return frame([x.get("effectiveDate") for x in rows], [x.get("netAssetValue") for x in rows])


def gld_nav(blob: bytes) -> pd.Series:
    rows = workbook_rows(blob, "US GLD Historical Archive")
    h = rows[0]
    return frame([r[h.index("Date")] for r in rows[1:]], [r[h.index("NAV/Share at 10:30am NYT")] for r in rows[1:]])


def qqq_total_return_level(blob: bytes) -> pd.Series:
    payload = json.loads(blob.decode("utf-8"))
    series = next(s for s in payload["lineChart10YData"] if str(s.get("type", "")).lower() == "shareclass")
    data = series["data"]
    s = frame([x["date"] for x in data], [x["value"] for x in data])
    s.index = s.index.to_period("M")
    return s[~s.index.duplicated(keep="last")]


def last_on_or_before(s: pd.Series, d: pd.Timestamp):
    eligible = s.loc[:d]
    if eligible.empty:
        raise KeyError(str(d))
    return eligible.index[-1], float(eligible.iloc[-1])


def monthly_total_return(nav: pd.Series, dists, start: pd.Period, end: pd.Period) -> pd.Series:
    periods = pd.period_range(start, end, freq="M")
    levels = []
    level = 1.0
    prev_date = None
    prev_nav = None
    for period in periods:
        month_end = period.to_timestamp("M")
        dt, nav_end = last_on_or_before(nav, month_end)
        if prev_date is None:
            levels.append(level)
            prev_date, prev_nav = dt, nav_end
            continue
        growth = nav_end / prev_nav
        for dist_date, amount in dists:
            dist_ts = pd.Timestamp(dist_date)
            if prev_date < dist_ts <= dt:
                _, reinvest_nav = last_on_or_before(nav, dist_ts)
                growth *= 1.0 + float(amount) / reinvest_nav
        level *= growth
        levels.append(level)
        prev_date, prev_nav = dt, nav_end
    return pd.Series(levels, index=periods, dtype=float)


def features(nav: dict[str, pd.Series]):
    mapped = {}
    for symbol, daily in nav.items():
        daily = daily.sort_index()
        m = daily.resample("ME").last()
        dr = daily.pct_change(fill_method=None)
        mapped[symbol] = {
            "mom6": m.pct_change(6),
            "trend200": (daily / daily.rolling(200, min_periods=160).mean() - 1).resample("ME").last(),
            "low_vol6": -(dr.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last(),
            "drawdown6": (daily / daily.rolling(126, min_periods=100).max() - 1).resample("ME").last(),
        }
    months = sorted(set.intersection(*[set(v["mom6"].index.to_period("M")) for v in mapped.values()]))
    selections = {}
    factor_values = {}
    for p in months:
        dt = p.to_timestamp("M")
        table = pd.DataFrame(index=list(SYMBOLS))
        for factor_name in ("mom6", "trend200", "low_vol6", "drawdown6"):
            vals = {}
            for symbol in SYMBOLS:
                ser = mapped[symbol][factor_name]
                eligible = ser.loc[:dt].dropna()
                vals[symbol] = float(eligible.iloc[-1]) if not eligible.empty and eligible.index[-1].to_period("M") == p else np.nan
            table[factor_name] = pd.Series(vals)
        if table.isna().any().any():
            continue
        ranks = table.rank(axis=0, pct=True)
        score = ranks.mean(axis=1)
        selections[p] = tuple(score.sort_values(ascending=False).head(2).index)
        factor_values[str(p)] = {s: {k: float(table.loc[s, k]) for k in table.columns} for s in SYMBOLS}
    return selections, factor_values


def cagr(r: pd.Series):
    r = pd.Series(r).dropna()
    return float((1.0 + r).prod() ** (12.0 / len(r)) - 1.0) if len(r) else None


def max_drawdown(r: pd.Series):
    eq = (1.0 + pd.Series(r).dropna()).cumprod()
    return float((eq / eq.cummax() - 1.0).min()) if len(eq) else None


def fold_excess(candidate: pd.Series, control: pd.Series):
    idxs = np.array_split(np.arange(len(candidate)), 5)
    folds = []
    for idx in idxs:
        c = candidate.iloc[idx]
        b = control.iloc[idx]
        folds.append(cagr(c) - cagr(b))
    return {"values": [float(x) for x in folds], "positive": int(sum(x > 0 for x in folds))}


def main():
    raw = {k: download(v) for k, v in URL.items()}
    nav = {
        "SPY": spy_nav(raw["SPY_NAV"]),
        "TLT": tlt_nav(raw["TLT_DOC"]),
        "GLD": gld_nav(raw["GLD"]),
        "QQQ": invesco_nav(raw["QQQ_NAV"]),
        "DBC": invesco_nav(raw["DBC_NAV"]),
    }
    tr_level = {
        "SPY": monthly_total_return(nav["SPY"], spy_dists(raw["SPY_DIST"]), START_MONTH, END_MONTH),
        "TLT": monthly_total_return(nav["TLT"], tlt_dists(raw["TLT_PAGE"]), START_MONTH, END_MONTH),
        "GLD": monthly_total_return(nav["GLD"], [], START_MONTH, END_MONTH),
        "DBC": monthly_total_return(nav["DBC"], sorted(DBC_DISTS.items()), START_MONTH, END_MONTH),
        "QQQ": qqq_total_return_level(raw["QQQ_TR"]),
    }
    level = pd.concat(tr_level, axis=1).dropna().sort_index()
    level = level.loc[(level.index >= START_MONTH) & (level.index <= END_MONTH), list(SYMBOLS)]
    returns = level.pct_change(fill_method=None).dropna()
    selections, factor_values = features(nav)
    rows = []
    prev = {s: 0.0 for s in SYMBOLS}
    for feature_month in sorted(selections):
        return_month = feature_month + 1
        if return_month not in returns.index:
            continue
        chosen = selections[feature_month]
        w = {s: (0.5 if s in chosen else 0.0) for s in SYMBOLS}
        turnover = 0.5 * sum(abs(w[s] - prev[s]) for s in SYMBOLS)
        r = returns.loc[return_month]
        gross = sum(w[s] * float(r[s]) for s in SYMBOLS)
        rows.append(
            {
                "feature_month": str(feature_month),
                "return_month": str(return_month),
                "chosen": list(chosen),
                "gross": gross,
                "matched_ew": float(r.mean()),
                "spy": float(r["SPY"]),
                "qqq": float(r["QQQ"]),
                "turnover": turnover,
            }
        )
        prev = w
    f = pd.DataFrame(rows)
    if len(f) < 80:
        raise RuntimeError(f"insufficient replay months: {len(f)}")
    output = {
        "schema": "research.p46_issuer_totalreturn_replay_r1",
        "parent": "P46",
        "contract": {
            "selector": "frozen four equal-weight factors (6m momentum, 200d trend, negative 126d volatility, 126d drawdown), cross-sectional percentile ranks, top-2, 50/50 next month",
            "feature_representation": "issuer daily NAV, because validated direct QQQ daily total-return route is unavailable",
            "realized_return_representation": "identity-bound issuer total return for every sleeve",
            "matched_control": "same five issuer total-return series equal-weight monthly",
            "opportunity_controls": ["SPY issuer total return", "QQQ issuer total return"],
            "costs_bps": list(COSTS_BPS),
            "no_model_parameter_or_weight_changes": True,
            "representation_limitation": "daily feature state is NAV rather than total-return level; economic return scoring is issuer total return. This is a predeclared source-fidelity replay, not proof of identical daily adjusted-price feature paths.",
        },
        "source_monthly_window": [str(level.index.min()), str(level.index.max())],
        "source_monthly_levels": int(len(level)),
        "evaluated_months": int(len(f)),
        "first_return_month": f.iloc[0].return_month,
        "last_return_month": f.iloc[-1].return_month,
        "selection_counts": {s: int(sum(s in chosen for chosen in f.chosen)) for s in SYMBOLS},
        "mean_turnover": float(f.turnover.mean()),
        "full_turnover": float(f.turnover.sum()),
        "capital_usage": {"candidate_mean_invested_fraction": 1.0, "matched_control_mean_invested_fraction": 1.0},
        "controls": {
            "matched_ew_cagr": cagr(f.matched_ew),
            "matched_ew_max_drawdown": max_drawdown(f.matched_ew),
            "spy_cagr": cagr(f.spy),
            "spy_max_drawdown": max_drawdown(f.spy),
            "qqq_cagr": cagr(f.qqq),
            "qqq_max_drawdown": max_drawdown(f.qqq),
        },
        "costs": {},
        "factor_values": factor_values,
        "rows": rows,
    }
    for bps in COSTS_BPS:
        candidate = f.gross - f.turnover * (bps / 10000.0)
        excess = cagr(candidate) - cagr(f.matched_ew)
        output["costs"][str(bps)] = {
            "candidate_cagr": cagr(candidate),
            "matched_ew_excess_cagr": excess,
            "spy_excess_cagr": cagr(candidate) - cagr(f.spy),
            "qqq_excess_cagr": cagr(candidate) - cagr(f.qqq),
            "candidate_max_drawdown": max_drawdown(candidate),
            "matched_ew_max_drawdown": max_drawdown(f.matched_ew),
            "folds_vs_matched": fold_excess(candidate, f.matched_ew),
        }
    c50 = output["costs"]["50"]
    output["decision"] = (
        "P46_ISSUER_TOTAL_RETURN_REPLAY_SUPPORTED"
        if c50["matched_ew_excess_cagr"] > 0 and c50["folds_vs_matched"]["positive"] >= 3
        else "P46_ISSUER_TOTAL_RETURN_REPLAY_NOT_SUPPORTED"
    )
    Path("results").mkdir(exist_ok=True)
    Path("results/p46_issuer_totalreturn_replay_r1.json").write_text(json.dumps(output, indent=2, sort_keys=True))
    print(json.dumps({k: output[k] for k in ("decision", "source_monthly_window", "evaluated_months", "selection_counts", "mean_turnover", "controls", "costs")}, sort_keys=True))


if __name__ == "__main__":
    main()
