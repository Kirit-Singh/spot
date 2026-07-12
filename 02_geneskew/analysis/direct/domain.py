"""The EVIDENCE DOMAIN of this release pass: global, all-condition, pooled-main.

Two different universes were being conflated, and the conflation is the P0 bug.

  * the SELECTED-CONDITION estimate universe — every estimate the release ships for
    the one condition a run analyses: main + by-guide slots + donor pairs
    (Rest 40,189 / Stim8hr 41,808 / Stim48hr 40,679). The old runner demanded the
    contributor manifest cover exactly THIS set.
  * the EVIDENCE DOMAIN — the scopes for which contributor evidence actually exists.
    The audited Claude Science artifact is global (all three conditions) and
    pooled-main ONLY: 33,983 scopes, 64,115 rows, 64,109 determined records.

The second cannot satisfy the first, and it was never meant to: they are not the same
universe. So the manifest is matched against the GLOBAL POOLED-MAIN universe, and the
selected-condition support estimates are enumerated separately, for ACCOUNTING ONLY.

SUPPORT IS UNAVAILABLE IN THIS PASS
-----------------------------------
By-guide and donor-pair support have no contributor evidence here, so they get none:
no mask, no projection, no replication claim, and no power to elevate an evidence
tier. They are not guessed, not borrowed from the pooled estimate, and not inferred
from a slot name. Support is feasible later, but it needs its own provenance method
and its own contract — the public release DOES define guide_1/guide_2 by alphanumeric
guide-ID rank and the donor modalities by named donor pairs
(``data_sharing_readme.md``, sha256
9275bad99701534e109691f2ce6ff8c474dacb3912e9a6f22cbaa009237ceab7, lines 135-153), so
the rank is a PUBLISHED rule and not a guess. It is simply not evidence of which guide
contributed to which estimate, which is the thing a mask needs.

Two facts measured against the release make the borrowing especially dangerous:

  * support ``n_guides`` is COPIED pooled metadata — 59,414/59,414 guide rows and
    29,279/29,279 donor rows — not the estimate's own contributor count;
  * honest donor-pair contributor counts disagree with it in 2,383 scopes.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# The one estimate class this pass carries evidence for.
POOLED_MAIN_TYPE = "main"
POOLED_MAIN_ID = "main"

# THE scope identity, everywhere: the estimate AND the whole released target identity.
SCOPE_KEY_FIELDS = ("estimate_type", "estimate_id", "released_estimate_id",
                    "target_id", "target_id_namespace", "target_symbol",
                    "target_ensembl", "condition", "donor_pair")

DOMAIN_ID = "spot.stage02.direct.evidence_domain.pooled_main_all_condition.v1"
EVIDENCE_METHOD = "released_per_guide_identity_column"
# A compact rule ID, not a paragraph. Emitted artifacts carry enums, counts, hashes and
# version ids; what the rule MEANS is stated once, here and in the method docs, not
# re-narrated inside every file the lane writes.
DOMAIN_RULE_ID = "spot.stage02.direct.domain_rule.pooled_main_exact_scope_match.v1"

# Support, explicitly unavailable (never silently absent).
SUPPORT_UNAVAILABLE = "unavailable_no_contributor_evidence_in_this_release_pass"
SUPPORT_STATE_UNAVAILABLE = "support_unavailable"
SUPPORT_CONTRACT_ID = "spot.stage02.direct.support_contract.unavailable.v1"


class DomainError(ValueError):
    """A row is outside the pooled-main evidence domain. Refuse; never coerce."""


def is_nullish(v: Any) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "nan", "null", "na",
                                                   "<na>")


def is_pooled_main(row: dict[str, Any]) -> bool:
    """Is this row an all-condition pooled-main scope — the only evidence class here?"""
    return (str(row.get("estimate_type")) == POOLED_MAIN_TYPE
            and str(row.get("estimate_id")) == POOLED_MAIN_ID
            and is_nullish(row.get("donor_pair")))


def domain_violation(row: dict[str, Any]) -> Optional[str]:
    """Why this row is not in the pooled-main evidence domain, or None.

    A by-guide or donor-pair row inside a pooled-main artifact is not a bonus: it is
    a claim this pass has no method to check, and admitting it would let a support
    estimate acquire a mask it never earned.
    """
    if str(row.get("estimate_type")) != POOLED_MAIN_TYPE:
        return (f"estimate_type={row.get('estimate_type')!r} is outside the "
                f"pooled-main evidence domain (expected {POOLED_MAIN_TYPE!r})")
    if str(row.get("estimate_id")) != POOLED_MAIN_ID:
        return (f"estimate_id={row.get('estimate_id')!r} is outside the pooled-main "
                f"evidence domain (expected {POOLED_MAIN_ID!r})")
    if not is_nullish(row.get("donor_pair")):
        return (f"donor_pair={row.get('donor_pair')!r} is non-null; a pooled-main "
                "scope is not a donor-pair scope")
    return None


def scope_of_identity(ident, condition: str) -> tuple:
    """The pooled-main scope of one released main estimate, in ``scope_of`` shape.

    ``released_target_ensembl`` — not ``target_ensembl`` — is bound: a run-level
    identity map may enrich a symbol target's Ensembl id for the RUN, but it does not
    change what the release published, and the contributor evidence describes the
    release.
    """
    return (POOLED_MAIN_TYPE, POOLED_MAIN_ID, ident.released_estimate_id,
            ident.target_id, ident.target_id_namespace, ident.target_symbol,
            ident.released_target_ensembl, condition, None)


def global_pooled_main_scopes(identities_by_condition: dict[str, dict]) -> set[tuple]:
    """THE evidence domain: every pooled-main scope the release ships, ALL conditions.

    ``identities_by_condition`` maps condition -> {target_id -> Identity}, built by the
    metadata-only main-identity loader. This is the set the contributor manifest must
    match exactly — 33,983 scopes for the pinned GWCD4i release.
    """
    scopes: set[tuple] = set()
    for condition, identities in identities_by_condition.items():
        for ident in identities.values():
            scopes.add(scope_of_identity(ident, condition))
    return scopes


def observed_support_scopes(guide_ids_by_modality: dict[str, Iterable[str]],
                            donor_ids_by_pair: dict[str, Iterable[str]],
                            condition: str) -> dict[str, Any]:
    """The selected-condition support estimates — ACCOUNTING ONLY, never evidence.

    Enumerated so every released support estimate can be reported as explicitly
    unavailable rather than silently dropped. Nothing here is projected, masked, or
    allowed to reach a score.
    """
    guide = {m: sorted({str(t) for t in ts})
             for m, ts in guide_ids_by_modality.items()}
    donor = {p: sorted({str(t) for t in ts}) for p, ts in donor_ids_by_pair.items()}
    n_guide = sum(len(v) for v in guide.values())
    n_donor = sum(len(v) for v in donor.values())
    return {
        "condition": condition,
        "guide_modalities": sorted(guide),
        "donor_pairs": sorted(donor),
        "n_guide_estimates": n_guide,
        "n_donor_pair_estimates": n_donor,
        "n_support_estimates": n_guide + n_donor,
        "targets_by_guide_modality": guide,
        "targets_by_donor_pair": donor,
    }


def support_contract(observed: dict[str, Any]) -> dict[str, Any]:
    """The machine-readable statement that support is unavailable, and WHY.

    Bound into run_id and re-checked by the standalone verifier, so a later run cannot
    quietly start granting guide/donor support without changing the contract it
    declared.
    """
    return {
        "contract_id": SUPPORT_CONTRACT_ID,
        "state": SUPPORT_STATE_UNAVAILABLE,
        "reason": SUPPORT_UNAVAILABLE,
        "guide_support_available": False,
        "donor_support_available": False,
        "support_may_elevate_evidence_tier": False,
        "support_n_guides_read_as_estimate_own": False,
        "support_estimates_projected": 0,
        "support_masks_built": 0,
        "n_support_estimates_observed": observed["n_support_estimates"],
        "n_guide_estimates_observed": observed["n_guide_estimates"],
        "n_donor_pair_estimates_observed": observed["n_donor_pair_estimates"],
        "guide_modalities_observed": observed["guide_modalities"],
        "donor_pairs_observed": observed["donor_pairs"],
    }
