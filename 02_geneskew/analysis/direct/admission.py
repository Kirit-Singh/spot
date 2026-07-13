"""The SHARED artifact-admission contract: read the shipped bytes off disk, and firewall
them for disguised inference or a combined objective.

It lived in ``temporal.admission`` — beside the retired fixed-pair verifier — but neither
half was temporal-specific: the temporal reusable-arm lane firewalls its bundle with
``forbidden_keys``, and the pathway lane reads its shipped provenance with ``load_shipped``
and scans it with ``forbidden_keys``. When the fixed-pair flat lane was retired, this moved
HERE, to the shared ``direct`` root, so both lanes depend on shared infra rather than on a
retired sibling. Only the retired verifier's own ``temporal.parquet``/``endpoints.parquet``
COLUMN allowlists stayed behind; they were the fixed-pair artifact's contract, used by
nothing that survives.

TWO THINGS LIVE HERE
--------------------
1. THE SHIPPED-BYTES READER (``load_shipped``/``caller_matches``). A verifier that firewalls
   the dictionary its CALLER handed it, while merely hashing the file on disk, is verifying
   two different objects and comparing neither. So the bytes are read here, the object is
   parsed from THOSE bytes, and everything downstream runs on what was actually shipped; the
   caller's copy is admissible only as a cross-check, never as the subject.

2. THE KEY FIREWALL (``forbidden_keys``). Case-insensitive, matched as a SUBSTRING of a key
   name at ANY depth, plus a standalone p/q token. Written from a real failure, not from
   memory: an earlier cut caught ``pvalue`` but NOT ``qval``/``qvalue``/``nominal_p``/
   ``bh_significance``, and six disguised inference fields were admitted. The pattern closes
   that hole.

EXACT-NAME EXEMPTIONS. ``away_from_A_zscore`` and ``toward_B_zscore`` match ``/score/`` and
are the within-condition SENSITIVITY effect layer carried verbatim — not an objective,
nothing ranks or gates on them. The exemption is the exact spelling, not the shape.

NEGATIVE DECLARATIONS. An artifact stating its own prohibition (e.g.
``combined_objective_permitted``) matches ``/combined/``; a firewall that refused it would
make the artifact unable to write down its own ban. So each is exempt ONLY while its value
is exactly ``False`` — flip it to ``True`` and the firewall fires, which is the event it
exists to catch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

# --------------------------------------------------------------------------- #
# THE KEY FIREWALL.
# --------------------------------------------------------------------------- #
FORBIDDEN_KEY_PATTERN = (
    r"p_value|q_value|q_val|qval|fdr|pval|padj|adj_|significance"
    r"|combined|balanced|weighted|score")
FORBIDDEN_KEY_RE = re.compile(FORBIDDEN_KEY_PATTERN, re.IGNORECASE)

# ...and a STANDALONE p/q TOKEN anywhere in a snake_case key (catches ``nominal_p``,
# ``raw_p``, ``emp_q``). A TOKEN rule, not a substring rule: a bare "p" substring would
# refuse every key containing the letter.
FORBIDDEN_TOKEN_RE = re.compile(r"(^|_)[pq](_|$)", re.IGNORECASE)

# The ONLY names exempt from the firewall, by exact spelling.
KEY_FIREWALL_EXCEPTIONS = frozenset({"away_from_A_zscore", "toward_B_zscore"})

# NEGATIVE DECLARATIONS: exempt ONLY while they still say "forbidden".
NEGATIVE_DECLARATIONS = {
    "combined_objective_permitted": False,
    "evidence_lines_are_combined": False,
    "reliability_is_a_significance_test": False,
    "combined_arm_eligibility_permitted": False,
}


def _forbidden(key: str) -> bool:
    """The word pattern, plus a standalone p/q token (``nominal_p``, ``raw_q``, ``p``)."""
    return bool(FORBIDDEN_KEY_RE.search(key) or FORBIDDEN_TOKEN_RE.search(key))


def _exempt(key: str, value: Any) -> bool:
    """Is this matching key one of the enumerated exceptions? See the module docstring."""
    if key in KEY_FIREWALL_EXCEPTIONS:
        return True
    if key in NEGATIVE_DECLARATIONS:
        # exempt ONLY while it still says "forbidden": `is` on the literal, so a truthy 1
        # or "false" cannot pose as the prohibition
        return value is NEGATIVE_DECLARATIONS[key]
    return False


def forbidden_keys(obj: Any, path: str = "") -> list[str]:
    """Every key name matching the firewall, at ANY depth, as a dotted path.

    Walks dicts and lists alike: a p-value buried in a list of diagnostics inside a
    comparison block is exactly the shape a disguised one would take, and a scan that only
    looked at the top level would never see it.
    """
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if _forbidden(str(key)) and not _exempt(str(key), value):
                hits.append(here)
            hits.extend(forbidden_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(forbidden_keys(value, f"{path}[{i}]"))
    return hits


# --------------------------------------------------------------------------- #
# THE SHIPPED-BYTES READER.
# --------------------------------------------------------------------------- #
class ShippedDocError(ValueError):
    """The shipped document is absent or unparseable. Refuse; never fall back."""


def load_shipped(out_dir: str, filename: str) -> dict[str, Any]:
    """Read the SHIPPED bytes off disk. The verifier's only source of truth.

    THE HOLE THIS CLOSES. A verifier used to take the provenance as a CALLER ARGUMENT: it
    hashed the file on disk, then firewalled the dictionary the caller handed it. Those are
    two different objects, and nothing compared them. An attacker poisons the emitted
    ``*_provenance.json`` with ``empirical_q_value``, passes the pristine in-memory dict to
    the verifier, and the verifier ADMITS — while its own report prints the sha256 of the
    file it never looked inside.

    A verifier that trusts its caller's copy of the thing it is verifying is not a verifier.
    It is a formality with a hash beside it.

    So: the bytes are read HERE, the object is parsed from THOSE bytes, and everything
    downstream — the firewall, every re-derivation — runs on what was actually shipped. The
    caller's dict is admissible only as a cross-check (``caller_matches``), never as the
    subject.
    """
    path = os.path.join(out_dir, filename)
    if not os.path.exists(path):
        raise ShippedDocError(f"the shipped document {filename!r} is absent from "
                              f"{out_dir!r}; an absent artifact confirms nothing")
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ShippedDocError(
            f"the shipped document {filename!r} is not parseable JSON: {exc}") from exc
    return {
        "doc": doc,
        "raw": raw,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_sha256": hashlib.sha256(_canonical(doc).encode()).hexdigest(),
    }


def caller_matches(shipped_doc: Any, caller_doc: Any) -> bool:
    """Is the caller's dictionary the SAME OBJECT the artifact shipped?

    Compared on canonical content, not on identity or key order: a re-serialised dict is the
    same document. A caller whose copy DIFFERS from the shipped bytes is either stale or
    lying, and either way the shipped bytes are what get verified.
    """
    if caller_doc is None:
        return True
    return _canonical(shipped_doc) == _canonical(caller_doc)


def _canonical(obj: Any) -> str:
    """Canonical bytes: sorted keys, no whitespace. Key order is not content."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
