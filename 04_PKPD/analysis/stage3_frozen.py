"""The FROZEN Stage-3 contract, pinned — and the combined-objective firewall, restated.

Stage 3 froze its contract and machinery (§11.6 / §12.1). The hashes below ARE that
freeze, as Stage 4 received it. They are not decoration: `test_stage3_frozen_pin` re-hashes
the live Stage-3 checkout against them, so the bytes Stage 4 was handed cannot drift out
from under this consumer without a red test.

    handoff doc   1f347168…   the r7 HANDOFF.md Stage 4 rebased onto
    contract      361d0833…   spot.stage03_drug_annotation.v1.json  <- the Stage-4 contract
    schema set    5b42a64c…   sorted-name + per-file-hash digest of schemas/
    commit        cb99125…    the frozen Stage-3 commit

### Why this module exists at all: schema validation is NOT admission

The Stage-3 document schema is deliberately `additionalProperties: true`. A bundle can
therefore be **schema-valid and still refused**, and the Stage-3 owner says so explicitly:
the firewall against a combined/headline objective lives in the verifier's recursive
banned-key scan, NOT in the JSON Schema.

Stage 4 had exactly this hole, and it was live. `RETIRED_KEYS` in `stage3_contract_v2`
guards the *promotion lattice* (`namespace`, `production_candidate`, …). It says nothing
about a *combined objective*. So a bundle carrying `overall_rank: 1` was admitted:

  * `overall_rank` is not a retired key            -> the retired-key scan misses it;
  * it is not in `CANONICAL_CONTENT_KEYS`          -> canonical content hash is UNCHANGED,
                                                      so `bundle_id` is unchanged too, and
                                                      the directory-name binding still holds;
  * re-seal `document_sha256`, the manifest's
    `file_sha256` for the document, and
    `manifest_sha256`                              -> every remaining Stage-4 check passes.

Three re-seals and a combined objective walks in wearing the bundle's own identity. That is
the whole attack, and `test_a_resealed_combined_objective_is_refused` reproduces it.

### Why RESTATED here rather than imported from Stage 3

`stage3_contract_v2` imports nothing from Stage 3 by design — a verifier that imported the
producer's hasher would let a Stage-3 bug validate itself. The same logic applies to the
denylist, with a second reason: an imported denylist is only as available as the Stage-3
checkout. On a machine without one, a runtime import would degrade the firewall to nothing,
silently. A restated denylist works everywhere, always.

A restatement can drift, so it is pinned in the other direction: `test_stage4_denylist_covers_stage3`
asserts Stage-4's set is a SUPERSET of the live `verifier.policy.BANNED_KEYS`. If Stage 3
bans a new objective and Stage 4 has not, that test goes red. Restated, not guessed.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------- the frozen pin

STAGE3_FROZEN_COMMIT = "cb99125e6ed6a450cbb7a4f7d1d6e9e2114590c9"
STAGE3_HANDOFF_SHA256 = "1f347168489bcf6de92b7eb60c950abb74ece89e0f35679c5a082563b3cf49a6"
STAGE3_CONTRACT_SHA256 = "361d0833d5cb099155ac6ad87557c728fcd64feba1e2ccbf7938bd2c6f4c9eed"
STAGE3_SCHEMA_SET_SHA256 = "5b42a64c8aca0fd279ba1440cb956ce034246f542362a6a8b470d27ca2f11b82"

# Every schema in the frozen set, by name. The set-level digest above catches a renamed,
# deleted or newly added schema; these catch an edited one, by name.
STAGE3_SCHEMA_SHA256: dict[str, str] = {
    "spot.fixture.stage03_drug_annotation.v1.json":
        "e3a44c01e2129ebdb0c58e309ffa343f0a404d768e6b656543b8c9a5e3b23ce9",
    "spot.science_evidence_record.v1.json":
        "490d371e6b51b93a42e1e9bd1b041d6929b1aa3c01227084b9a206f9c7bb0a58",
    "spot.stage02_pathway_hypotheses.v1.json":
        "b6aad105703b49deff67bdf70936b75fb765ebce4f336867d5cee84952bbd72e",
    "spot.stage03_disease_context_review.v1.json":
        "6b2cfaa102537493be89e41f82af6bcebcfb825b63c78f2c975bd59365177beb",
    "spot.stage03_drug_annotation.v1.json":
        "361d0833d5cb099155ac6ad87557c728fcd64feba1e2ccbf7938bd2c6f4c9eed",
    "stage03_acquisition_manifest.v1.json":
        "3ea0d197e9e0f3a3805e5e2e64448eea9d0e95d0114dbf630ab60a4eeac6a333",
}

# --------------------------------------------------- the combined-objective firewall

# Restated from the frozen `verifier/policy.py:BANNED_KEYS`. A combined objective can always
# be given a new name, so this denylist backs up the per-table column allowlists.
#
# NOT banned, and deliberately so: `joint_status`, `pareto_tier` and `joint_ordering_method_id`
# are Stage-2 joint CONTEXT. They are typed strings/labels, nothing reads them for direction,
# and they are carried through verbatim. Banning them would refuse every real Stage-2 bundle.
BANNED_KEYS = frozenset({
    "combination", "combination_score", "combination_state", "combined_score",
    "combined_rank", "balanced_score", "balanced_skew", "balanced_a_to_b",
    "composite_score", "total_skew", "overall_score", "overall_rank",
    "aggregate_score", "mean_arm_score", "arms_both_positive", "rank",
    "primary_rank", "rank_primary", "headline_rank", "best_arm", "best_of_arms",
    "primary_arm", "headline_arm", "rank_tuple",
    # the retired field that called an INHIBITOR a "decrease"
    "pharmacologic_effect",
})


def banned_keys_in(node: Any, path: str = "$") -> list[str]:
    """Every combined/headline objective key in `node`, at ANY depth. -> JSON paths."""
    hits: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in BANNED_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(banned_keys_in(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            hits.extend(banned_keys_in(value, f"{path}[{i}]"))
    return hits


def banned_in_table(table: str, columns: list[str],
                    rows: list[dict[str, Any]]) -> list[str]:
    """Every combined/headline objective in ONE table — as a column, or nested inside a cell.

    Three ways a banned objective reaches a table, all closed here:

      * a plain COLUMN — caught by the `columns` membership check. `columns` comes from the
        parquet SCHEMA, so it is populated even for an EMPTY table, whose zero rows would
        otherwise hide a banned column name entirely;
      * nested inside a struct/list CELL — `arm_evidence_states` is a `list<struct>`, so
        `overall_rank` can ride in one level down under an innocent column name. The row scan
        is recursive for exactly this;
      * a per-ROW key a uniform column view would miss — every row is scanned, not just the
        first, because a struct cell's keys are per-row.
    """
    hits: set[str] = set()
    hits.update(f"{table}.{c}" for c in columns if c in BANNED_KEYS)
    for row in rows:
        # `$.x` -> `<table>.x`; the row index is dropped so a banned COLUMN reports once, not
        # once per row.
        hits.update(f"{table}{p[1:]}" for p in banned_keys_in(row))
    return sorted(hits)
