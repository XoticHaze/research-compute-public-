#!/usr/bin/env python3
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

WORKFLOW = Path('.github/workflows/mnq-dca-reserve-release-r3-h24-concordance-20260912.yml')
INCLUDE = 'rendezvous/requests/mnq-dca-reserve-release-r3-h24-concordance-*.txt'
EXCLUDE = 'rendezvous/requests/mnq-dca-reserve-release-r3-h24-concordance-longwait-*.txt'


def eligible(path: str) -> bool:
    return fnmatchcase(path, INCLUDE) and not fnmatchcase(path, EXCLUDE)


def main() -> int:
    text = WORKFLOW.read_text(encoding='utf-8')
    include_line = f"      - '{INCLUDE}'"
    exclude_line = f"      - '!{EXCLUDE}'"
    if include_line not in text:
        raise SystemExit('missing short-wait request include')
    if exclude_line not in text:
        raise SystemExit('missing long-wait request exclusion')
    if text.index(include_line) > text.index(exclude_line):
        raise SystemExit('GitHub negative path pattern must follow positive include')

    short = 'rendezvous/requests/mnq-dca-reserve-release-r3-h24-concordance-20260913-r8.txt'
    longwait = 'rendezvous/requests/mnq-dca-reserve-release-r3-h24-concordance-longwait-20260913-r8.txt'
    unrelated = 'rendezvous/requests/p08-curve-transfer-r1.txt'
    assert eligible(short), short
    assert not eligible(longwait), longwait
    assert not eligible(unrelated), unrelated
    print('P04_R3_TRIGGER_PARTITION=PASS')
    print('SHORT_WAIT_ELIGIBLE=1')
    print('LONG_WAIT_ELIGIBLE=0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
