"""Which selection does a Stage-3 candidate actually BELONG to — and can Stage 4 re-derive it?

THE SEAM. Stage 4's store is GLOBAL over the admitted Stage-3 candidate universe; a selection is a
deterministic PROJECTION of it, never an admission-time filter. So every displayed row makes a
membership claim — "this candidate is on an arm this selection selected" — and that is the one claim
a projection cannot be trusted to make about itself. A view that both decides membership and reports
it has no independent check anywhere in the chain.

Stage 4 therefore RE-DERIVES membership from the STORE and refuses any row whose claim it cannot
reproduce. The store's typed arm-key lists are ground truth; the view's `view_*` fields are the claim
under test.

    store  candidates.{observed_perturbation,inverse_direction_hypothesis,pathway_hypothesis,
                       opposed,unresolved}_arm_keys        <- ground truth, global, selection-free
    view   candidates.view_arm_keys_by_origin              <- the claim
    ------------------------------------------------------------------------------------
    membership = store_keys  ∩  selection.selected_arms    (EXACT full-string equality)

Each refusal names a distinct way the claim can be false:

  FOREIGN membership   the view places a candidate on an arm the STORE never put it on. It ADDS
                       evidence — the direction that makes a drug look better than its data.
  DROPPED membership   the store puts it on a selected arm and the view omits it. SILENT: the row
                       still renders, just with less evidence than it has.
  SWAPPED binding      the row is bound to a different selection / condition / view. Every field can
                       be internally consistent and still describe another question.
  PREFIX / NAME match  `direct|P|decrease|Rest` is not `direct|P|decrease|Rest48`, and a display name
                       is never an identity. Stage 3 states this rule; Stage 4 enforces it.
  UNREDERIVABLE        membership Stage 4 cannot rebuild from the store. Refused BY NAME — never
                       displayed, never silently dropped.

Membership is CONTENT-ADDRESSED (`membership_sha256`) over the FULL selection identity, so a
projection cannot be re-pointed at another selection while keeping its rows.

PINS: this module opens NOTHING. `stage3_v2_seam` stays unpinned and `admit_v2()` still refuses —
Stage 4 cannot admit a v2 bundle until W16 publishes its exact commit and schema-set hash. See
`W16_PIN_DEPENDENCIES` at the foot of this file.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional

from .arm_key_codec import MembershipError, arm_key_list
from .membership_records import (
    EXACT_MATCH_RULE,
    MEMBERSHIP_CONTRACT,
    Membership,
    SelectionBinding,
)
from .selection_roles import role_arms



# Stage 3 v2's ACTUAL typed arm-key columns on `candidates` (read from the emitted bundle, not
# guessed from the v1 names). The v1 projection read `*_arms`; the v2 store writes `*_arm_keys`, and
# a projection that silently found neither would have matched NOTHING and shown an empty view rather
# than failing — which is why these are enumerated and their absence is a refusal.
STORE_ARM_KEY_COLUMNS: tuple[str, ...] = (
    "observed_perturbation_arm_keys",
    "inverse_direction_hypothesis_arm_keys",
    "pathway_hypothesis_arm_keys",
    "opposed_arm_keys",
    "unresolved_arm_keys",
)

# The union column the store also carries. Cross-checked against the typed lists: a candidate whose
# `arm_keys` disagrees with its own typed lists is a row that contradicts itself, and Stage 4 will
# not pick whichever of the two it prefers.
STORE_ARM_KEY_UNION_COLUMN = "arm_keys"

# The view's claim.
VIEW_ARM_KEYS_BY_ORIGIN = "view_arm_keys_by_origin"

# The two kinds of row Stage 4 is handed, and they are NOT interchangeable. A global STORE row makes
# no membership claim (Stage 4 computes the intersection itself); a row emitted BY a selection VIEW
# exists precisely to make one. So a missing claim is legitimate on the first and a defect on the
# second — and a checker that cannot tell them apart must treat "no claim" as "nothing to check",
# which is how an emitted view row escapes the only check there is on it.
STORE_ROW = "store"
VIEW_ROW = "view"




# --------------------------------------------------------------------------- reading the selection

def binding_from_selection_view(view: Mapping[str, Any]) -> SelectionBinding:
    """Stage 3's selection view -> the binding Stage 4 will hold every row to.

    Read, never inferred. A view that cannot state its question, its selection hash, its mode, its
    conditions, its selected arms and its own content hash is not a selection Stage 4 can display —
    it is a set of rows with no question attached, and a row with no question cannot be checked
    against one.
    """
    selection = view.get("selection") or {}
    selected = view.get("selected_arms") or {}

    # Stage 3 declares the exact-match guarantee. If a view ever ships without it, Stage 4 does NOT
    # quietly fall back to its own matching: a projection whose matching rule is unstated cannot be
    # audited, and prefix matching is precisely the failure this seam exists to catch.
    if selected.get(EXACT_MATCH_RULE) is not True:
        raise MembershipError(
            "stage3_view_does_not_declare_exact_arm_key_matching",
            f"the selection view does not declare {EXACT_MATCH_RULE!r}. Stage 4 matches arm keys by "
            "exact full-string equality and will not display a view whose matching rule is "
            "unstated — `direct|P|decrease|Rest` is not `direct|P|decrease|Rest48`, and a rule "
            "nobody wrote down is a rule nobody enforced.",
        )

    # The ordered per-role arms, cross-checked against selection.roles / poles / conditions and
    # against each arm's own canonical key.
    arms = role_arms(view)
    arm_keys = _selected_arm_keys(selected)
    if not arm_keys:
        raise MembershipError(
            "stage3_selection_selected_no_arms",
            "the selection view selects no arms. A selection that selected nothing is not a "
            "selection, and every candidate would be 'out of view' for reasons nobody could check.",
        )

    missing = [
        f for f, v in (
            ("selection.selection_id", selection.get("selection_id")),
            ("selection.selection_full_sha256", selection.get("selection_full_sha256")),
            ("selection.full_contract_content_sha256",
             selection.get("full_contract_content_sha256")),
            ("selection.question_id", selection.get("question_id")),
            ("selection.canonical_content_sha256", selection.get("canonical_content_sha256")),
            ("selection.analysis_mode", selection.get("analysis_mode")),
            ("view_id", view.get("view_id")),
            ("view_content_sha256", view.get("view_content_sha256")),
        ) if not v
    ]
    if missing:
        raise MembershipError(
            "stage3_selection_view_cannot_state_its_identity",
            f"the selection view is missing {missing}. Stage 4 binds every displayed row to the "
            "question it answers; a view that cannot name its own question, selection or content "
            "hash cannot be bound to, and an unbindable view is indistinguishable from a swapped "
            "one.",
        )

    return SelectionBinding(
        selection_id=str(selection["selection_id"]),
        selection_full_sha256=str(selection["selection_full_sha256"]),
        full_contract_content_sha256=str(selection["full_contract_content_sha256"]),
        question_id=str(selection["question_id"]),
        selection_canonical_sha256=str(selection["canonical_content_sha256"]),
        analysis_mode=str(selection["analysis_mode"]),
        conditions=tuple(str(c) for c in (selection.get("conditions") or ())),
        selected_arm_keys=frozenset(arm_keys),
        role_arms=arms,
        view_id=str(view["view_id"]),
        view_content_sha256=str(view["view_content_sha256"]),
    )


def _selected_arm_keys(selected: Mapping[str, Any]) -> set[str]:
    """The EXACT arm keys the selection selected — from the per-role arms AND the gene arm keys.

    Both are read. `arms` names the poles (role -> one arm key); `gene_arm_keys` is the full set. If
    the two disagree, the view contradicts itself about what it selected, and Stage 4 refuses rather
    than choosing whichever is more convenient.
    """
    from_arms = {
        str(a["arm_key"]) for a in (selected.get("arms") or {}).values()
        if isinstance(a, Mapping) and a.get("arm_key")
    }
    from_genes = set(arm_key_list(selected.get("gene_arm_keys"),
                                  where="selection view `selected_arms.gene_arm_keys`"))

    if from_arms and from_genes and not from_arms <= from_genes:
        orphan = sorted(from_arms - from_genes)
        raise MembershipError(
            "stage3_selection_contradicts_itself_about_its_arms",
            f"the selection view names role arm(s) {orphan} that are absent from its own "
            "`gene_arm_keys`. The view disagrees with itself about which arms it selected; one of "
            "the two was edited and the other was not.",
        )
    return from_arms | from_genes


# ------------------------------------------------------------------------- re-deriving a candidate

def rederive(candidate: Mapping[str, Any], binding: SelectionBinding) -> Membership:
    """Rebuild ONE candidate's membership FROM THE STORE. The view's claim is not consulted here.

    This is the whole point: the view is checked against this, not merged into it.
    """
    candidate_id = str(candidate.get("candidate_id") or "")
    if not candidate_id:
        raise MembershipError(
            "stage3_candidate_without_an_id",
            "a candidate row carries no candidate_id, so nothing it claims can be bound to it.",
        )

    store: dict[str, tuple[str, ...]] = {}
    for column in STORE_ARM_KEY_COLUMNS:
        if column not in candidate:
            raise MembershipError(
                "stage3_candidate_missing_an_arm_key_column",
                f"candidate {candidate_id!r} has no {column!r}. Stage 4 re-derives membership from "
                f"the typed store columns {list(STORE_ARM_KEY_COLUMNS)}; a column that is absent is "
                "not an empty column — it is a column nobody can check, and a candidate whose "
                "membership cannot be re-derived is refused rather than shown.",
            )
        store[column] = arm_key_list(candidate.get(column),
                                     where=f"candidate {candidate_id!r} column {column!r}")

    _assert_union_agrees(candidate_id, candidate, store)

    # THE INTERSECTION. Exact, full-string, per typed column. No prefix, no normalisation, no
    # case-folding, no display name — a key either IS one of the selected arms or it is not.
    selected = binding.selected_arm_keys
    hit = {col: tuple(sorted(k for k in keys if k in selected)) for col, keys in store.items()}
    return Membership(
        candidate_id=candidate_id,
        selection=binding,
        arm_keys_by_column=hit,
        in_view=any(hit.values()),
    )


def _assert_union_agrees(candidate_id: str, candidate: Mapping[str, Any],
                         store: Mapping[str, tuple[str, ...]]) -> None:
    """`arm_keys` IS the union of the five typed lists — EXACT equality, both directions.

    This is not an assumption. Measured against W16's real bundle (19/19 candidates):
    `arm_keys == union(typed)` for every row, with zero typed-not-in-union and zero
    union-not-in-typed. So the union column is a redundant restatement, and the only thing a
    disagreement can mean is that one of the two was edited and the other was not.

    Both directions are refused, and they are DIFFERENT failures:
      * typed minus union — the row holds evidence on an arm its own summary column denies.
      * union minus typed — the row claims an arm that NO evidence class supports. If Stage 3 ever
        introduces a sixth evidence class, this fires immediately rather than letting a whole class
        of evidence pass through Stage 4 uncounted and unhashed. That is the intended behaviour: a
        new class must be added to STORE_ARM_KEY_COLUMNS deliberately, not discovered silently.
    """
    if STORE_ARM_KEY_UNION_COLUMN not in candidate:
        return
    union = set(arm_key_list(candidate.get(STORE_ARM_KEY_UNION_COLUMN),
                             where=f"candidate {candidate_id!r} column "
                                   f"{STORE_ARM_KEY_UNION_COLUMN!r}"))
    typed: set[str] = set()
    for keys in store.values():
        typed.update(keys)

    if typed - union:
        orphan = sorted(typed - union)
        raise MembershipError(
            "stage3_candidate_contradicts_itself_about_its_arms",
            f"candidate {candidate_id!r} carries arm key(s) {orphan[:5]} in its typed evidence "
            f"columns that are absent from its own {STORE_ARM_KEY_UNION_COLUMN!r}. The row "
            "disagrees with itself about which arms it is on, so one of the two was edited and the "
            "other was not — and Stage 4 will not pick the one it prefers.",
        )
    if union - typed:
        orphan = sorted(union - typed)
        raise MembershipError(
            "stage3_candidate_arm_is_supported_by_no_evidence_class",
            f"candidate {candidate_id!r} lists arm key(s) {orphan[:5]} in "
            f"{STORE_ARM_KEY_UNION_COLUMN!r} that appear in NONE of the typed evidence columns "
            f"{list(STORE_ARM_KEY_COLUMNS)}. In the real bundle `arm_keys` is exactly their union "
            "(19/19 candidates). Either the row is corrupt, or Stage 3 has added a sixth evidence "
            "class — and a class Stage 4 does not know about is a class it would carry uncounted "
            "and unhashed. Add it here deliberately; do not discover it silently.",
        )


# -------------------------------------------------------------------- checking the view's claim

def verify_view_claim(candidate: Mapping[str, Any], membership: Membership,
                      row_kind: str = STORE_ROW) -> None:
    """The view's `view_arm_keys_by_origin` must equal what Stage 4 re-derived. Exactly.

    FOREIGN keys ADD evidence the store never supported. DROPPED keys quietly REMOVE evidence the
    store does support, and a row with less evidence than it has still renders perfectly. Both are
    refused, and each is named for what it is — "the view disagrees" is not actionable.

    `row_kind` is the distinction that makes the absence of a claim meaningful:

      STORE_ROW  a global store row. It makes NO view claim, and is not supposed to — Stage 4
                 computes the intersection itself. Nothing to check.
      VIEW_ROW   a row EMITTED BY a selection view. Its whole purpose is to state which selected
                 arms the candidate sits on. A view row that omits `view_arm_keys_by_origin` is
                 REFUSED, not waved through: treating a missing claim as "no claim to check" would
                 let an emitted view escape the only check that exists on it — and a view row with
                 no claim is indistinguishable from a store row only if you do not know which one
                 you are holding.
    """
    if row_kind not in (STORE_ROW, VIEW_ROW):
        raise MembershipError(
            "stage4_unknown_row_kind",
            f"row_kind={row_kind!r}. A row is either a global STORE row or an emitted VIEW row, and "
            "the difference decides whether a missing claim is legitimate or a defect.",
        )

    if VIEW_ARM_KEYS_BY_ORIGIN not in candidate:
        if row_kind == VIEW_ROW:
            raise MembershipError(
                "stage4_view_row_states_no_membership_claim",
                f"candidate {membership.candidate_id!r} is a row emitted BY a selection view and it "
                f"carries no {VIEW_ARM_KEYS_BY_ORIGIN!r}. Stating which selected arms the candidate "
                "sits on is the entire job of a view row; one that states nothing cannot be checked "
                "against the store, and an unchecked view row is exactly what this seam exists to "
                "prevent.",
                {"candidate_id": membership.candidate_id},
            )
        return  # a global store row makes no view claim, and is not supposed to.

    claimed: set[str] = set()
    by_origin = candidate.get(VIEW_ARM_KEYS_BY_ORIGIN)
    where = f"candidate {membership.candidate_id!r} {VIEW_ARM_KEYS_BY_ORIGIN!r}"

    # The view writes this as a JSON string too, and it may be a per-origin MAP or a flat list.
    if isinstance(by_origin, str) and by_origin.strip():
        try:
            by_origin = json.loads(by_origin)
        except json.JSONDecodeError as exc:
            raise MembershipError(
                "stage3_arm_key_column_is_not_a_list",
                f"{where} is the bare string {by_origin[:40]!r} and cannot be read as a claim.",
            ) from exc

    if isinstance(by_origin, Mapping):
        for origin, keys in by_origin.items():
            claimed.update(arm_key_list(keys, where=f"{where} origin {origin!r}"))
    else:
        claimed.update(arm_key_list(by_origin, where=where))

    derived = set(membership.all_arm_keys)

    foreign = sorted(claimed - derived)
    if foreign:
        raise MembershipError(
            "stage4_view_claims_membership_the_store_does_not_support",
            f"candidate {membership.candidate_id!r}: the view places it on arm(s) {foreign[:5]} "
            "that Stage 4 cannot re-derive from the store's typed arm-key columns for this "
            "selection. A view that adds a candidate to an arm the store never put it on is "
            "inventing evidence, and it is the one direction that makes a drug look better than "
            "its data.",
            {"candidate_id": membership.candidate_id, "foreign_arm_keys": foreign[:10]},
        )

    dropped = sorted(derived - claimed)
    if dropped:
        raise MembershipError(
            "stage4_view_dropped_membership_the_store_does_support",
            f"candidate {membership.candidate_id!r}: the store places it on arm(s) {dropped[:5]} "
            "that this selection selected, and the view omits them. This failure is SILENT — the "
            "row still renders, just with less evidence than it actually has, and nothing about it "
            "looks wrong.",
            {"candidate_id": membership.candidate_id, "dropped_arm_keys": dropped[:10]},
        )


def assert_bound_to(membership: Membership, expected: SelectionBinding,
                    declared_membership_sha256: Optional[str] = None) -> None:
    """A row displayed under a selection must be BOUND to that selection.

    Every field of a swapped binding can be internally consistent and still describe another
    question. The content hash is what makes a swap detectable: change the question, the selection,
    the mode, a condition, the view, or one arm key, and it moves.
    """
    if membership.selection != expected:
        mine, theirs = membership.selection.identity(), expected.identity()
        differ = sorted(k for k in mine if mine[k] != theirs[k])
        raise MembershipError(
            "stage4_candidate_bound_to_a_different_selection",
            f"candidate {membership.candidate_id!r} is bound to a selection differing in {differ}. "
            "A row can be internally consistent in every field and still answer another question; "
            "displaying it here would attach evidence to a question it was never derived for.",
            {"candidate_id": membership.candidate_id, "fields": differ},
        )

    if declared_membership_sha256 is not None:
        actual = membership.membership_sha256()
        if declared_membership_sha256 != actual:
            raise MembershipError(
                "stage4_membership_hash_does_not_recompute",
                f"candidate {membership.candidate_id!r} declares membership "
                f"{declared_membership_sha256[:16]}… and Stage 4 recomputes {actual[:16]}… from the "
                "store. A hash the row asserts about itself proves only that the row can hash.",
                {"candidate_id": membership.candidate_id},
            )


# --------------------------------------------------------------------------------- the projection

def project(candidates: Iterable[Mapping[str, Any]], view: Mapping[str, Any],
            row_kind: str = STORE_ROW) -> dict[str, Any]:
    """The browser/display projection: deterministically FILTER and FLAG by verified membership.

    The store stays GLOBAL and is not filtered — this returns a projection OF it. Every row that is
    displayed carries the membership hash it was displayed under, so the projection cannot later be
    re-pointed at another selection while keeping its rows.

    A candidate that is out of view is REPORTED as out of view, with its (empty) membership, rather
    than vanishing: a row that disappears and a row that was never there look identical, and only
    one of them is a bug.
    """
    binding = binding_from_selection_view(view)

    displayed: list[dict[str, Any]] = []
    out_of_view: list[dict[str, Any]] = []
    for candidate in candidates:
        membership = rederive(candidate, binding)
        verify_view_claim(candidate, membership, row_kind)
        assert_bound_to(membership, binding,
                        candidate.get("membership_sha256"))

        row = {
            "candidate_id": membership.candidate_id,
            "arm_keys_by_column": {k: list(v) for k, v in membership.arm_keys_by_column.items()},
            "membership_sha256": membership.membership_sha256(),
        }
        (displayed if membership.in_view else out_of_view).append(row)

    return {
        "contract": MEMBERSHIP_CONTRACT,
        "selection": binding.identity(),
        "row_kind": row_kind,
        "exact_match_rule": EXACT_MATCH_RULE,
        "displayed": sorted(displayed, key=lambda r: r["candidate_id"]),
        "out_of_view": sorted(out_of_view, key=lambda r: r["candidate_id"]),
        "counts": {"n_displayed": len(displayed), "n_out_of_view": len(out_of_view)},
        "store_is_global_and_was_not_filtered": True,
        "note": (
            "membership was RE-DERIVED from the store's typed arm-key columns and the view's claim "
            "was checked against it, never merged into it. Out-of-view candidates are reported, "
            "not dropped: a row that vanishes and a row that never existed look identical."
        ),
    }


# ------------------------------------------------------------------------------------------ pins

# STILL OWED BY W16. Stage 4 does not guess any of these, and native v2 admission stays CLOSED until
# they are published from a clean, exact Stage-3 commit:
#
#   1. `method.schemas_sha256`  — the v2 schema-SET identity, from the committed producer. Stage 4
#      will NOT substitute a hash of document+manifest instances and call that a schema-set id.
#   2. the v2 verifier entry point (`verifier.verify_stage3_v2`) and its exact required inputs, run
#      OUT OF PROCESS. Gate 2 is not Stage-4's to implement.
#   3. an `artifact_class=analysis` bundle. Every bundle on this host is `fixture`, and Stage 4
#      refuses those BY NAME (`stage3_bundle_is_a_fixture`).
#   4. a selection view emitted WITH the bundle: the current fixture carries
#      `selection_roles_assigned: false`, so no view exists to bind against in the real chain.
#   5. the canonicalization RULE behind `content_sha256`, still unpublished — without it Stage 4
#      cross-checks the per-table canonical hash but cannot independently recompute it.
W16_PIN_DEPENDENCIES: tuple[str, ...] = (
    "method.schemas_sha256 (v2 schema-set identity, from a clean committed producer)",
    "verifier.verify_stage3_v2 entry point + exact required inputs (gate 2, out-of-process)",
    "an artifact_class=analysis bundle (every bundle here is a fixture and is refused by name)",
    "a selection view emitted with the bundle (current fixture: selection_roles_assigned=false)",
    "the canonicalization rule behind content_sha256 (else canonical hashes are cross-checked only)",
)
