"""Donor-pair modalities: one exact token parser, three complementary splits.

The release ships one DE matrix per donor pair. Over four donors that is six
matrices, and they OVERLAP — each donor appears in three of them. They are not
six independent replicates. The only honest replication unit the release
supports is the COMPLEMENTARY SPLIT: a pair and its complement partition the
donors into two disjoint halves, so the two halves of one split are genuinely
independent of each other.

Donor identity comes from ONE exact parser over the released modality names, and
the parsed tokens are emitted verbatim. Nothing invents or renames a donor: the
release's tokens (e.g. ``CE0006864``) are the identity. Mapping those tokens to
Stage-1's donor labels requires an EXPLICIT crosswalk; without one the crosswalk
is recorded as unavailable rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Optional

from . import config, domain
from .projection import sign_of

COMPLETE = "complete"
INCOMPLETE = "incomplete"
PAIR_SEPARATOR = "_"
TOKENS_PER_PAIR = 2


class DonorTokenError(ValueError):
    """A released modality name is not an exact donor-pair token pair."""


@dataclass(frozen=True)
class Split:
    split_id: str
    half_a: str          # donor-pair modality id
    half_b: str          # its complement modality id

    @property
    def halves(self) -> tuple[str, str]:
        return (self.half_a, self.half_b)


def parse_pair_tokens(modality: str, sep: str = PAIR_SEPARATOR) -> tuple[str, ...]:
    """The exact donor tokens of one released pair modality.

    A name that is not exactly two non-empty tokens is a hard failure: donor
    identity is never inferred from a name we cannot parse.
    """
    tokens = tuple(t for t in str(modality).split(sep))
    if len(tokens) != TOKENS_PER_PAIR or any(not t for t in tokens):
        raise DonorTokenError(
            f"donor-pair modality {modality!r} does not parse into exactly "
            f"{TOKENS_PER_PAIR} donor tokens on {sep!r}")
    return tokens


def complementary_splits(pair_ids: list[str], sep: str = PAIR_SEPARATOR) -> dict:
    """Group donor-pair modality ids into complementary splits.

    Returns the parsed donor tokens, the splits, an explicit status, and any pair
    whose complement is not released (reported, never dropped silently).
    """
    members = {p: frozenset(parse_pair_tokens(p, sep)) for p in pair_ids}
    donor_tokens = sorted({d for m in members.values() for d in m})
    by_set = {s: p for p, s in members.items()}

    splits: list[Split] = []
    unpaired: list[str] = []
    seen: set[str] = set()
    for pair in sorted(pair_ids):
        if pair in seen:
            continue
        complement = frozenset(donor_tokens) - members[pair]
        mate = by_set.get(complement)
        if mate is None or mate == pair:
            unpaired.append(pair)
            seen.add(pair)
            continue
        seen.update({pair, mate})
        a, b = sorted((pair, mate))
        splits.append(Split(split_id=f"{a}|{b}", half_a=a, half_b=b))

    splits.sort(key=lambda s: s.split_id)
    n_donors = len(donor_tokens)
    # an even donor set of size n has comb(n, n/2)/2 complementary halvings
    expected = (comb(n_donors, n_donors // 2) // 2) if n_donors and not n_donors % 2 else 0
    status = (COMPLETE
              if (not unpaired and expected > 0 and len(splits) == expected)
              else INCOMPLETE)
    return {
        "donor_tokens": donor_tokens,          # verbatim from the release
        "n_donors": n_donors,
        "splits": splits,
        "n_splits": len(splits),
        "n_splits_expected": expected,
        "unpaired_pairs": sorted(unpaired),
        "status": status,
        # WHY only complementary splits are a replication unit is stated once, in this
        # module's docstring and in the method docs. The artifact carries the rule ID
        # and the flag a consumer must actually branch on.
        "rule_id": config.DONOR_SPLIT_RULE_ID,
        "pairs_are_independent_replicates": False,
    }


def donor_crosswalk(tokens: list[str],
                    crosswalk: Optional[dict[str, str]]) -> dict:
    """Bind release donor tokens to Stage-1 donor labels, or say it is unavailable.

    An explicit crosswalk is verified to cover exactly the released tokens. No
    positional or name-similarity mapping is ever attempted.
    """
    # The STATUS is the contract; a consumer branches on it, never on a sentence. No
    # positional or name-similarity mapping is ever attempted — that rule is stated in
    # this module's docstring, not re-serialised into every run.
    if not crosswalk:
        return {
            "status": "unavailable",
            "release_tokens": tokens,
            "stage1_labels": None,
            "inferred_by_name_or_position": False,
        }
    mapped = {str(k): str(v) for k, v in crosswalk.items()}
    covered = set(mapped.values())
    missing = sorted(set(tokens) - covered)
    extra = sorted(covered - set(tokens))
    if missing or extra:
        return {
            "status": "invalid",
            "release_tokens": tokens,
            "stage1_labels": mapped,
            "unmapped_release_tokens": missing,
            "crosswalk_tokens_not_released": extra,
            "usable": False,
        }
    return {"status": "bound", "release_tokens": tokens, "stage1_labels": mapped}


def split_support(main_value: Optional[float],
                  pair_values: dict[str, Optional[float]],
                  splits: list[Split], eps: float,
                  arm_evaluable: bool = True,
                  support_available: bool = True) -> dict:
    """Sign support across complementary splits, with honest denominators.

    A split is EVALUABLE only when both of its disjoint halves produced a value.
    Concordance is first asked WITHIN a split (do the two independent donor
    halves agree with each other), then against the main estimate.

    ``support_available=False`` is the state of this release pass: the donor-pair
    estimates carry no contributor evidence, so they were never projected and there
    are no halves to compare. The splits are still COUNTED — the denominator is what
    the release actually ships — but every one of them is explicitly missing for a
    named reason, and no support verdict can be positive.
    """
    main_sign = sign_of(main_value, eps)
    rows: list[dict] = []
    n_eval = n_internal_concordant = n_internal_discordant = 0
    n_main_concordant = 0
    absent_reason = (domain.SUPPORT_UNAVAILABLE if not support_available
                     else "half_estimate_unavailable")

    for sp in splits:
        va, vb = pair_values.get(sp.half_a), pair_values.get(sp.half_b)
        sa, sb = sign_of(va, eps), sign_of(vb, eps)
        if va is None or vb is None:
            missing = [h for h, v in ((sp.half_a, va), (sp.half_b, vb)) if v is None]
            rows.append({
                "split_id": sp.split_id, "half_a": sp.half_a, "half_b": sp.half_b,
                "half_a_value": va, "half_b_value": vb,
                "evaluable": False,
                "missing_halves": ";".join(missing),
                "missing_reason": absent_reason,
                "internal_sign_agreement": None,
                "agrees_with_main": None,
            })
            continue
        n_eval += 1
        internal = (sa == sb and sa != 0)
        if internal:
            n_internal_concordant += 1
        else:
            n_internal_discordant += 1
        agrees_main = (None if main_sign is None
                       else (sa == main_sign and sb == main_sign and main_sign != 0))
        if agrees_main:
            n_main_concordant += 1
        rows.append({
            "split_id": sp.split_id, "half_a": sp.half_a, "half_b": sp.half_b,
            "half_a_value": va, "half_b_value": vb,
            "evaluable": True,
            "missing_halves": "",
            "missing_reason": None,
            "internal_sign_agreement": internal,
            "agrees_with_main": agrees_main,
        })

    n_total = len(splits)
    # Support is inferential: a non-evaluable arm gets denominators (diagnostics)
    # but never a positive support verdict. Neither does an arm whose donor evidence
    # is out of domain — support that was never measured cannot be support.
    supported = (support_available and arm_evaluable
                 and n_eval == n_total and n_total > 0
                 and n_main_concordant == n_total and n_internal_discordant == 0)
    return {
        "rows": rows,
        "arm_evaluable": arm_evaluable,
        "support_available": support_available,
        "n_splits_total": n_total,
        "n_splits_evaluable": n_eval,
        "n_splits_missing": n_total - n_eval,
        "n_splits_internally_concordant": n_internal_concordant,
        "n_splits_internally_discordant": n_internal_discordant,
        "n_splits_agreeing_with_main": n_main_concordant,
        # support requires an evaluable arm AND every split to agree internally
        # AND with the target estimate
        "donor_split_support": supported,
        "donor_split_support_denominator": n_total,
    }
