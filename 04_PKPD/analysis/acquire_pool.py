"""Bounded concurrency for acquisition. It makes the queue faster; it may not make it different.

One rule, and it is the whole module: **concurrency may not change a result.** `bounded_map`
returns results in INPUT order, never completion order, so the manifest a queue produces does not
depend on which host happened to answer first. A refusal anywhere propagates — an item that failed
is never quietly dropped from a set that then looks complete.

The worker bound exists because the public sources are shared infrastructure. PubChem asks for no
more than a handful of requests per second; openFDA rate-limits by IP. Politeness here is not
courtesy, it is the difference between an acquisition that finishes and one that gets throttled
into failure halfway through a candidate queue.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_MAX_WORKERS = 4


def bounded_map(items: Iterable[T], work: Callable[[T], R], *,
                max_workers: int = DEFAULT_MAX_WORKERS) -> list[R]:
    """Run `work` over `items` with at most `max_workers` in flight. -> results in INPUT order.

    The first exception raised by any worker propagates (after the pool drains), so a queue can
    never come back looking complete when one of its items refused.
    """
    todo = list(items)
    if not todo:
        return []
    if max_workers <= 1 or len(todo) == 1:
        return [work(item) for item in todo]

    with ThreadPoolExecutor(max_workers=min(max_workers, len(todo))) as pool:
        futures = [pool.submit(work, item) for item in todo]
        # .result() in submission order: input order out, whatever the completion order was.
        return [f.result() for f in futures]
