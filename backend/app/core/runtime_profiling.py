from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator


logger = logging.getLogger("app.runtime_profiling")

DEFAULT_SLOW_WARNING_MS = 1500.0


@contextmanager
def profile_endpoint(endpoint: str, **metadata: object) -> Iterator[None]:
    started = time.perf_counter()
    ok = False
    try:
        yield
        ok = True
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        extra = {
            "endpoint": endpoint,
            "elapsed_ms": round(elapsed_ms, 1),
            "ok": ok,
            **metadata,
        }
        log = logger.warning if elapsed_ms > DEFAULT_SLOW_WARNING_MS else logger.info
        log(
            "finance_core_endpoint_timing endpoint=%s elapsed_ms=%.1f ok=%s",
            endpoint,
            elapsed_ms,
            ok,
            extra=extra,
        )
