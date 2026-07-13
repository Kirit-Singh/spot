"""Selecting one record out of many, without ever picking by position.

Every `results[0]` is a bet that the result set has exactly one element. The bet is usually
right, which is what makes it dangerous: it fails silently, on the one drug where it matters.
The live openFDA data settled the argument — TEMODAR's label declares TWO application numbers
(NDA021029 capsule, NDA022277 injection) and its Drugs@FDA record carries SIX products.

So a selection here is exactly one of three things:

  * `exactly_one` — matched on an identity PIN, with zero and many both typed refusals. Never on
    position, and never a silent de-duplication: two records claiming one identity are two
    records, and choosing between them is a decision this layer does not get to make.
  * `sorted_unique` — a collect-all set in canonical order. Nothing dropped, nothing chosen.
  * `assert_result_set_complete` — the source's own total must match what we can see. A truncated
    page cannot prove uniqueness, so `limit=1` did not merely risk the wrong record; it removed
    the evidence that would have shown the risk.

Ordering must never change an outcome.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, TypeVar

from .firewall import Rejection

T = TypeVar("T")


def exactly_one(rows: list[T], *, matches: Callable[[T], bool], what: str, pin: str,
                zero_code: str, many_code: str,
                describe: Optional[Callable[[T], str]] = None) -> T:
    """The row whose identity IS the pin. Zero or many is a refusal that names what it saw."""
    hits = [row for row in rows if matches(row)]
    if not hits:
        raise Rejection(
            zero_code,
            f"no {what} matches {pin!r} in a response of {len(rows)} record(s). The source "
            "answered, but not about the thing that was asked for — which is not evidence of "
            "absence, and is certainly not grounds to read the nearest record instead.")
    if len(hits) > 1:
        shown = "; ".join((describe or repr)(h) for h in hits[:8])
        raise Rejection(
            many_code,
            f"{len(hits)} {what} records claim the identity {pin!r}. Stage 4 does not take the "
            f"first, and does not silently collapse them into one: {shown}")
    return hits[0]


def sorted_unique(values: Iterable[Any]) -> tuple[str, ...]:
    """A collect-all set in canonical order. Order in must not change the result out."""
    return tuple(sorted({str(v).strip() for v in values if v is not None and str(v).strip()}))


def assert_result_set_complete(*, total: Optional[int], returned: int, what: str, pin: str,
                               code: str, require_total: bool = False) -> None:
    """The source's own match count must agree with what we can actually see.

    A response that says `total: 7` while handing back 1 row has not shown us the other 6, so
    nothing about that row can be called unique. `limit=1` is exactly this failure, and it is
    why the previous code could not detect a duplicate even in principle.
    """
    if total is None:
        if require_total:
            raise Rejection(
                code,
                f"the source reported no match total for {what} {pin!r}, so the {returned} "
                "record(s) that arrived cannot be shown to be all of them. Uniqueness that "
                "cannot be proven is not assumed.")
        return
    if total > returned:
        raise Rejection(
            code,
            f"the source reports {total} {what} record(s) matching {pin!r} but returned only "
            f"{returned}. A truncated result set cannot prove uniqueness — raise the query limit "
            "or pin the record explicitly; do not read the rows that happened to arrive.")
