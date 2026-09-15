from __future__ import annotations

"""Transport-optimized runner for P791.

Scientific scoring, cohort construction, chronology folds, controls, and decision
rules remain owned by the frozen R1 module.  This runner replaces only the SEC
filing-document transport: instead of requesting index.json plus up to six
individual filing documents for every candidate 8-K, it fetches the canonical
EDGAR complete-submission text once per accession and applies the same frozen
RAISE/LOWER regexes to that text.

This is a transport repair, not a hypothesis or decision-rule change.
"""

import html
import re
import time
import urllib.request

import p791_sec_management_guidance_revision_r1 as r1

_FETCH_COUNT = 0


def _complete_submission_url(cik10: str, accession: str) -> str:
    cik = str(int(cik10))
    directory = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{directory}/{accession}.txt"


def _fetch_complete_submission(cik10: str, accession: str) -> bytes:
    url = _complete_submission_url(cik10, accession)
    headers = {
        "User-Agent": r1.UA,
        "Accept": "text/plain,text/html,*/*",
        "Accept-Encoding": "gzip, deflate",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as exc:  # transport evidence is emitted to the CI log
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + 1.5 * attempt)
    assert last_error is not None
    raise last_error


def _normalize_submission(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def classify_guidance_complete_submission(cik10: str, event: dict):
    global _FETCH_COUNT
    accession = event["accession"]
    try:
        text = _normalize_submission(_fetch_complete_submission(cik10, accession))
    except Exception as exc:
        print(
            f"P791_SEC_FETCH_FAIL accession={accession} "
            f"error={type(exc).__name__}",
            flush=True,
        )
        raise

    _FETCH_COUNT += 1
    if _FETCH_COUNT == 1 or _FETCH_COUNT % 25 == 0:
        print(
            f"P791_SEC_PROGRESS complete_submissions_scanned={_FETCH_COUNT} "
            f"latest_accession={accession}",
            flush=True,
        )

    raise_hits = []
    lower_hits = []
    for label, patterns, sink in (
        ("RAISE", r1.RAISE_PATTERNS, raise_hits),
        ("LOWER", r1.LOWER_PATTERNS, lower_hits),
    ):
        for pattern in patterns:
            for match in pattern.finditer(text):
                lo = max(0, match.start() - 80)
                hi = min(len(text), match.end() + 80)
                sink.append(
                    {
                        "document": f"{accession}.txt",
                        "snippet": text[lo:hi][:360],
                        "pattern": label,
                    }
                )
                if len(sink) >= 3:
                    break
            if len(sink) >= 3:
                break

    direction = None
    if raise_hits and not lower_hits:
        direction = "RAISE"
    elif lower_hits and not raise_hits:
        direction = "LOWER"

    return {
        "direction": direction,
        "raise_hit_count": len(raise_hits),
        "lower_hit_count": len(lower_hits),
        "raise_hits": raise_hits[:3],
        "lower_hits": lower_hits[:3],
        "documents_scanned": [f"{accession}.txt"],
        "transport": "SEC_COMPLETE_SUBMISSION_ONE_REQUEST_PER_ACCESSION",
    }


def main() -> None:
    r1.classify_guidance = classify_guidance_complete_submission
    print(
        "P791_TRANSPORT=SEC_COMPLETE_SUBMISSION_ONE_REQUEST_PER_ACCESSION",
        flush=True,
    )
    r1.main()


if __name__ == "__main__":
    main()
