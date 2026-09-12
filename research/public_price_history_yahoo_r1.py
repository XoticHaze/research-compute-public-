from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_RETRYABLE = {429, 500, 502, 503, 504}
_UA = "Mozilla/5.0 XoticHaze market-research public-history study"


def _get_json(url: str):
    last = None
    for delay in (0.0, 2.0, 5.0, 10.0):
        if delay:
            time.sleep(delay)
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE:
                raise
        except urllib.error.URLError as exc:
            last = exc
    raise last


def adjusted_daily_prices(symbol: str):
    # Public chart endpoint; no account, token, cookie, or private input.
    # Use adjusted close when supplied; fall back to close only when adjclose is absent.
    params = urllib.parse.urlencode({
        "period1": 946684800,          # 2000-01-01 UTC
        "period2": 1789257600,         # 2026-09-13 UTC, exclusive upper bound
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    data = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{params}")
    result = data.get("chart", {}).get("result") or []
    if not result:
        err = data.get("chart", {}).get("error")
        raise RuntimeError(f"Yahoo chart returned no result for {symbol}: {err}")
    r = result[0]
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    adj_sets = (r.get("indicators") or {}).get("adjclose") or []
    adjs = adj_sets[0].get("adjclose", []) if adj_sets else []
    rows = []
    for i, ts in enumerate(stamps):
        p = adjs[i] if i < len(adjs) and adjs[i] is not None else (closes[i] if i < len(closes) else None)
        if p is None:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        rows.append((d, float(p)))
    rows.sort()
    if len(rows) < 500:
        raise RuntimeError(f"insufficient Yahoo history for {symbol}: {len(rows)} rows")
    return rows
