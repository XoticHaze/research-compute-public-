#!/usr/bin/env python3
"""Compatibility runner for the frozen provider-breadth experiment.

Python 3.11 tarfile streaming mode exposes tarfile._Stream without a
seekable() method. ExFileObject delegates seekable() to that stream and
io.TextIOWrapper probes it before reading. The underlying stream is
intentionally non-seekable, so declaring that fact restores the standard
TextIOWrapper contract without changing ingestion, features, gates, or
scientific logic.
"""
from __future__ import annotations

import tarfile

if not hasattr(tarfile._Stream, "seekable"):
    tarfile._Stream.seekable = lambda self: False  # type: ignore[attr-defined]

from compute_provider_breadth_forward import main

if __name__ == "__main__":
    raise SystemExit(main())
