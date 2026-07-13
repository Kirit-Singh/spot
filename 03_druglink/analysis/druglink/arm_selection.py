"""FROM THE QUESTION TO THE ARMS: which arms a verified selection names, and whether they exist.

The KEY ALGEBRA — the frozen role x pole -> desired_change map, the key builder, the parser, the
sibling lookup — lives in :mod:`druglink.arm_keys` and is RE-EXPORTED here, so a consumer binds
ONE module (the front-door idiom ``candidates_v2`` already uses for ``edges_v2``).

WHAT THIS MODULE ADDS
---------------------
* the two GENE arms a selection names, one per ROLE, derived from the poles — never guessed,
  never pattern-matched, never hardcoded;
* the role-matched PATHWAY CONTEXT arms;
* the cross-checks, each a NAMED refusal:
    - the aggregate's OWN published role x pole map must equal the one Stage 3 derives;
    - Stage-1's OWN ``arms`` block must name the same arm keys Stage 3 derives;
    - every named arm must EXIST in the admitted aggregate, matched by EXACT key.

WHICH ARMS A MODE READS (frozen; see :mod:`druglink.join_semantics`)
-------------------------------------------------------------------
    within_condition          GENE arms:    the two DIRECT arms, both at the one condition
                              PATHWAY ctx:  condition-matched, at that same condition
    temporal_cross_condition  GENE arms:    the two TEMPORAL DiD arms of the ORDERED pair —
                                            never same-time Direct ranks
                              PATHWAY ctx:  the ENDPOINT panels — role A at from_condition,
                                            role B at to_condition. Two WITHIN-condition
                                            readings side by side; never a statistic across time.

ONE ARM MAY CARRY BOTH ROLES, AND IT IS NOT A DEGENERATE QUESTION
-----------------------------------------------------------------
``away_from_A(high)`` and ``toward_B(low)`` are BOTH ``decrease``. So a selection naming ONE
program with OPPOSITE poles resolves both roles onto a SINGLE reusable arm — and Stage 1 admits
exactly that selection: its only self-comparison refusal is same program + same direction *in
within-condition mode* (``emit_selection_contract.build_contract``, error
``objective_incompatible_same_pole``; same program + same direction at DIFFERENT times is
explicitly a VALID temporal comparison, because the condition disambiguates the poles).

Refusing the shared arm would reject a question Stage 1 calls ready — a gate that fails in the
direction that merely LOOKS safe, which is still a gate that is wrong. The arm is shared, both
roles are stated on it, and nothing is double-counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import join_semantics as js
from . import selection_v3 as s3
from . import stage2_aggregate as sa
from .arm_keys import (  # noqa: F401  (the one front door: re-exported for consumers)
    ARM_KEY_RULE_ID,
    CONTEXT_ARITY,
    DESIRED_CHANGE_BY_ROLE_AND_POLE,
    GATE_ARM_KEY_MISSING,
    GATE_ARM_NOT_IN_AGGREGATE,
    GATE_BOGUS_ARM_KEY,
    GATE_PRODUCER_MAP_ABSENT,
    GATE_PRODUCER_MAP_DISAGREES,
    GATE_STAGE1_ARMS_DISAGREE,
    GATE_UNKNOWN_ROLE_OR_POLE,
    GENE_LANE_FOR_MODE,
    MAPPING_RULE_ID,
    PATHWAY_CONTEXT_LABEL,
    ArmSelectionError,
    _refuse,
    arm_key,
    desired_change,
    parse_arm_key,
    sibling_arm_keys,
)
from .hashing import content_hash


@dataclass(frozen=True)
class SelectedArm:
    """ONE arm, and the role THIS question gives it. The role lives here, never in the store."""
    role: str
    pole: str                       # `high|low` — selection metadata, never part of the key
    program_id: str
    desired_change: str
    lane: str
    context: dict[str, Any]
    arm_key: str

    def binding(self) -> dict[str, Any]:
        return {"role": self.role, "pole": self.pole, "program_id": self.program_id,
                "desired_change": self.desired_change, "lane": self.lane,
                "context": dict(self.context), "arm_key": self.arm_key}


@dataclass(frozen=True)
class SelectedArms:
    """The gene arms this question names — ONE PER ROLE — plus the pathway CONTEXT arms.

    ONE REUSABLE ARM MAY CARRY BOTH ROLES, AND THAT IS NOT A DEGENERATE QUESTION.

    ``away_from_A(high)`` and ``toward_B(low)`` are both ``decrease``. So a selection naming ONE
    program with OPPOSITE poles — which Stage-1 ADMITS (it refuses only same program + same
    direction *within-condition*: ``emit_selection_contract.build_contract``,
    ``objective_incompatible_same_pole``) — resolves both roles onto a SINGLE arm.

    That is the reusable-arm design working, not breaking. A role is a property of the SELECTION,
    assigned at join time; an arm that serves as A here and B there is the whole point. Refusing
    it would reject a question Stage-1 says is valid — a gate that fails in the direction that
    merely LOOKS safe, which is still a defect.

    So the arm keys are DISTINCT (``gene_arm_keys`` is a set, and may hold one key or two), the
    ROLES are always two, and :meth:`roles_of` returns EVERY role an arm carries — so a consumer
    can neither double-count the shared arm nor mistake it for a single-role one.
    """
    analysis_mode: str
    a: SelectedArm
    b: SelectedArm
    pathway_context_label: str
    pathway_arms: dict[str, tuple[SelectedArm, ...]]     # role -> its context arms

    @property
    def gene_arm_keys(self) -> tuple[str, ...]:
        """The DISTINCT gene arms. One key when a single reusable arm carries both roles."""
        return tuple(sorted({self.a.arm_key, self.b.arm_key}))

    @property
    def one_arm_carries_both_roles(self) -> bool:
        return self.a.arm_key == self.b.arm_key

    def roles_of(self, key: str) -> list[str]:
        """EVERY role THIS question gives an arm key. Never just the first one found."""
        roles = [arm.role for arm in (self.a, self.b) if arm.arm_key == key]
        roles += [role for role, arms in sorted(self.pathway_arms.items())
                  if any(arm.arm_key == key for arm in arms)]
        return sorted(set(roles))

    @property
    def pathway_arm_keys(self) -> tuple[str, ...]:
        return tuple(sorted({arm.arm_key
                             for arms in self.pathway_arms.values() for arm in arms}))

    @property
    def all_arm_keys(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.gene_arm_keys) | set(self.pathway_arm_keys)))

    def binding(self) -> dict[str, Any]:
        return {
            "analysis_mode": self.analysis_mode,
            "gene_arm_lane": self.a.lane,
            "gene_arm_keys": list(self.gene_arm_keys),
            "arms": {"A": self.a.binding(), "B": self.b.binding()},
            # STATED, so a consumer cannot silently double-count a shared arm — or read a
            # one-arm question as a one-role one.
            "one_arm_carries_both_roles": self.one_arm_carries_both_roles,
            "pathway_context_label": self.pathway_context_label,
            "pathway_context_arm_keys": {
                role: sorted({arm.arm_key for arm in arms})
                for role, arms in sorted(self.pathway_arms.items())},
            "arm_key_rule_id": ARM_KEY_RULE_ID,
            "role_and_pole_map_rule_id": MAPPING_RULE_ID,
            "arm_keys_are_matched_by_exact_string_equality_never_by_prefix": True,
            "gene_arm_keys_sha256": content_hash(sorted(self.gene_arm_keys)),
        }


def _gene_context(selection: s3.VerifiedSelection) -> dict[str, Any]:
    """The GENE arms' context. Both roles read the same one: one condition, or one ORDERED pair."""
    if selection.is_temporal:
        # ORDERED. Rest->Stim48hr is not Stim48hr->Rest: the DiD changes sign.
        return {"from_condition": selection.from_condition,
                "to_condition": selection.to_condition}
    return {"condition": selection.conditions[0]}


def _pathway_condition(selection: s3.VerifiedSelection, role: str) -> str:
    """WHERE a role's pathway panel is read: AT ITS OWN POLE'S CONDITION.

    The pole already carries it — A at ``conditions[0]``, B at ``conditions[-1]`` — so this reads
    the pole rather than re-deriving the endpoint, and the two can never disagree.

    Within-condition: both poles sit at the one condition, so both panels do.
    Cross-time: the ENDPOINTS — A at the from condition, B at the to condition. They are two
    WITHIN-condition readings shown side by side, and never a statistic computed across time:
    nothing was measured across time, so no longitudinal pathway statistic exists to report, and
    naming one would invent it.
    """
    return selection.pole(role)["condition"]


def derive_arm(selection: s3.VerifiedSelection, role: str, *, lane: str,
               context: Mapping[str, Any]) -> SelectedArm:
    """ONE arm, DERIVED from the selection. Never guessed, never pattern-matched."""
    pole = selection.pole(role)
    change = desired_change(role, pole["direction"])
    return SelectedArm(
        role=role, pole=pole["direction"], program_id=pole["program_id"],
        desired_change=change, lane=lane, context=dict(context),
        arm_key=arm_key(lane, pole["program_id"], change, context))


def derive(selection: s3.VerifiedSelection, *,
           pathway_sources: Sequence[str] = sa.PATHWAY_SOURCES) -> SelectedArms:
    """The two gene arms + the role-matched pathway context arms. A pure function of the
    selection: it touches no store and reads no bytes."""
    js.require_mode(selection.analysis_mode)
    lane = GENE_LANE_FOR_MODE[selection.analysis_mode]
    context = _gene_context(selection)
    arms = {role: derive_arm(selection, role, lane=lane, context=context)
            for role in s3.ROLES}

    pathway: dict[str, tuple[SelectedArm, ...]] = {}
    for role in s3.ROLES:
        condition = _pathway_condition(selection, role)
        pathway[role] = tuple(
            derive_arm(selection, role, lane=sa.LANE_PATHWAY,
                       context={"condition": condition, "pathway_source": source})
            for source in sorted(pathway_sources))

    return SelectedArms(
        analysis_mode=selection.analysis_mode, a=arms[s3.ROLE_A], b=arms[s3.ROLE_B],
        pathway_context_label=PATHWAY_CONTEXT_LABEL[selection.analysis_mode],
        pathway_arms=pathway)


# --------------------------------------------------------------------------- #
# 3. Resolution against the ADMITTED aggregate. Every refusal is named.
# --------------------------------------------------------------------------- #
def check_manifest_agrees(manifest: Mapping[str, Any]) -> None:
    """The producer PUBLISHES its role x pole map. Stage-3's independent restatement must agree.

    REQUIRED, not merely checked-if-present. This used to return SILENTLY when the manifest
    published no map — a claim the prose made and the code did not keep, which is worse than no
    claim at all, because a reader trusts it. The whole value of the check is that TWO lanes
    computed the same table with different hands; with nothing to check against, Stage-3's arm
    keys are an unverified opinion, and a sign error in them is invisible.

    Stage 3 never READS the map (that would make the check circular). It derives its own and
    requires the producer's published one to be identical. A divergence means one of us is keying
    arms to the OPPOSITE perturbation — every drug direction in every view would follow the wrong
    one, and both sides would look green.
    """
    published = manifest.get("desired_change_by_role_and_pole")
    if not isinstance(published, Mapping) or not published:
        _refuse(GATE_PRODUCER_MAP_ABSENT,
                "the aggregate manifest publishes no `desired_change_by_role_and_pole`. Stage 3 "
                "derives that map independently, and can only be shown right by agreeing with a "
                "producer that published its own. A release Stage 3 cannot check itself against "
                "is one whose arm keys nobody has checked.")
    ours = {f"{role}|{pole}": change
            for (role, pole), change in DESIRED_CHANGE_BY_ROLE_AND_POLE.items()}
    theirs = {str(k): str(v) for k, v in published.items()}
    if theirs != ours:
        _refuse(GATE_PRODUCER_MAP_DISAGREES,
                f"the aggregate publishes desired_change_by_role_and_pole={theirs} but Stage 3 "
                f"independently derives {ours}. One of us is keying arms to the opposite "
                "perturbation — every drug direction in every view would follow the wrong one, "
                "and both sides would look green.")


# WHICH arm key Stage-1's own `arms` block publishes for each mode. Stage 1 emits all three
# (`direct_arm_key`, `temporal_arm_key`, `pathway_arm_key_base`); the mode decides which one is
# the GENE arm, and this table is the only place that decides.
STAGE1_GENE_ARM_FIELD = {
    s3.MODE_WITHIN: "direct_arm_key",
    s3.MODE_TEMPORAL: "temporal_arm_key",
}
STAGE1_PATHWAY_BASE_FIELD = "pathway_arm_key_base"


def check_declared_arms(selection: s3.VerifiedSelection, selected: SelectedArms) -> None:
    """Stage-1 EMITS the arm keys it believes this question names. Ours must be the same keys.

    This is the one check no amount of internal consistency can fake: Stage 1 computed these keys
    from its own poles with its own code, and Stage 3 derived them again from the role x pole map
    it restates independently. If the two disagree, one lane is keying the question to the wrong
    perturbation — and a resealed contract cannot make the disagreement go away, because the
    forger would have to be right about the biology to pass.

    A contract that emits no `arms` block is not refused here (the block is Stage-1's, and older
    contracts predate it); the arms are then Stage-3's derivation alone, and the aggregate
    existence gate still stands.
    """
    declared = selection.declared_arms
    if not declared:
        return
    field = STAGE1_GENE_ARM_FIELD[selection.analysis_mode]
    for role, arm in ((s3.ROLE_A, selected.a), (s3.ROLE_B, selected.b)):
        block = declared.get(role) or {}
        theirs = block.get(field)
        if theirs is None:
            continue
        if str(theirs) != arm.arm_key:
            _refuse(GATE_STAGE1_ARMS_DISAGREE,
                    f"the selection declares {role}.{field}={theirs!r}, but Stage 3 derives "
                    f"{arm.arm_key!r} from the same poles under the frozen role x pole map. Two "
                    "lanes computed the same key with different hands and got different answers: "
                    "one of them is asking about the opposite perturbation, and every drug in the "
                    "view would follow it.")
        # The DESIRED CHANGE too, not merely the key it lands in. A key that matched while the
        # change disagreed would mean the two lanes agree by coincidence of spelling.
        if block.get("desired_change") and str(block["desired_change"]) != arm.desired_change:
            _refuse(GATE_STAGE1_ARMS_DISAGREE,
                    f"the selection declares {role}.desired_change={block['desired_change']!r} "
                    f"but Stage 3 derives {arm.desired_change!r} for pole {arm.pole!r}.")
        # ...and the pole's own CONDITION: A at the first, B at the last.
        if block.get("condition") and str(block["condition"]) != \
                selection.pole(role)["condition"]:
            _refuse(GATE_STAGE1_ARMS_DISAGREE,
                    f"the selection declares {role}.condition={block['condition']!r} but its "
                    f"conditions place this pole at {selection.pole(role)['condition']!r}.")

    for role, arms in selected.pathway_arms.items():
        base = (declared.get(role) or {}).get(STAGE1_PATHWAY_BASE_FIELD)
        if not base:
            continue
        for arm in arms:
            if not arm.arm_key.startswith(f"{base}|"):
                _refuse(GATE_STAGE1_ARMS_DISAGREE,
                        f"the selection declares {role}.{STAGE1_PATHWAY_BASE_FIELD}={base!r}, "
                        f"but Stage 3 derives the pathway context arm {arm.arm_key!r}. Under a "
                        "cross-time question the panels are the ENDPOINTS — A at the from "
                        "condition, B at the to condition — and a mismatch means one lane is "
                        "reading the wrong endpoint's pathway panel.")


def resolve(selection: s3.VerifiedSelection, aggregate: sa.AdmittedAggregate, *,
            manifest: Mapping[str, Any]) -> SelectedArms:
    """The selection's arms, PROVED to exist in the admitted aggregate. Fail closed, by name.

    ``manifest`` is REQUIRED: it carries the producer's own role x pole map, and Stage 3 will not
    key a question against a release it cannot check its own derivation against.

    NOTE WHAT IS *NOT* REFUSED HERE: the two roles landing on ONE reusable arm. Stage 1 admits
    that selection, and one arm carrying both roles is the reusable-arm design working — not a
    degenerate question. See :class:`SelectedArms`.
    """
    check_manifest_agrees(manifest)

    sources = sorted({b.pathway_source for b in aggregate.bundles
                      if b.lane == sa.LANE_PATHWAY and b.pathway_source})
    selected = derive(selection, pathway_sources=sources or sa.PATHWAY_SOURCES)

    for arm in (selected.a, selected.b):
        if not arm.arm_key:
            _refuse(GATE_ARM_KEY_MISSING,
                    f"role {arm.role!r} resolves no arm key. A role with no arm is not half a "
                    "question — it is no question, and a view built from one arm would show one "
                    "pole's drugs under the authority of a pair.")
        parse_arm_key(arm.arm_key)               # BOGUS keys refuse here

    # STAGE-1'S OWN ANSWER, against ours. Two hands, one key, or a refusal.
    check_declared_arms(selection, selected)

    known = {a.arm_key for a in aggregate.arms}
    for arm in (selected.a, selected.b):
        if arm.arm_key not in known:
            siblings = sibling_arm_keys(aggregate, arm.arm_key)
            _refuse(GATE_ARM_NOT_IN_AGGREGATE,
                    f"role {arm.role!r} names arm {arm.arm_key!r}, which the admitted aggregate "
                    f"does not have. It holds {len(known)} arms; "
                    f"{len(siblings)} share this key's lane|program|desired_change prefix "
                    f"({siblings[:3]}). Stage 3 matches an arm by EXACT key and never falls back "
                    "to one of those — a near-miss arm answers a question about a different "
                    "context and looks exactly like the right answer.")
    return selected


def vocabularies() -> dict[str, Any]:
    """The arm-selection vocabulary, hashed into the view's method block."""
    return {
        "arm_key_rule_id": ARM_KEY_RULE_ID,
        "role_and_pole_map_rule_id": MAPPING_RULE_ID,
        "desired_change_by_role_and_pole": {
            f"{role}|{pole}": change
            for (role, pole), change in sorted(DESIRED_CHANGE_BY_ROLE_AND_POLE.items())},
        "gene_lane_for_mode": dict(sorted(GENE_LANE_FOR_MODE.items())),
        "pathway_context_for_mode": dict(sorted(PATHWAY_CONTEXT_LABEL.items())),
        "arm_key_carries_pole_or_role": False,
        "arm_keys_are_matched_by_exact_string_equality_never_by_prefix": True,
        "the_context_is_part_of_the_key": True,
        "roles_are_assigned_at_join_time": True,
    }
