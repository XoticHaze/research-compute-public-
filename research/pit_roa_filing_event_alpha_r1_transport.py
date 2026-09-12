from __future__ import annotations

import time
import urllib.error
import urllib.request

import pit_roa_filing_event_alpha_r1 as experiment

_ORIGINAL_URLOPEN = urllib.request.urlopen
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}
_DELAYS = (0.0, 2.0, 5.0, 10.0)


def resilient_urlopen(request, *args, **kwargs):
    last = None
    for delay in _DELAYS:
        if delay:
            time.sleep(delay)
        try:
            return _ORIGINAL_URLOPEN(request, *args, **kwargs)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE_HTTP:
                raise
        except urllib.error.URLError as exc:
            last = exc
    raise last


urllib.request.urlopen = resilient_urlopen
experiment.main()
