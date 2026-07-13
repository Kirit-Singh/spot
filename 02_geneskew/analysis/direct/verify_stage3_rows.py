"""THE INDEPENDENT CHECK ON THE STAGE-2 -> STAGE-3 ROW. It does not import the contract.

``stage3_rows`` DECIDES a row's direction and namespace. This module DECIDES THEM AGAIN,
from the row's own signed value and the release's own target universe, and refuses if the
two answers differ. It deliberately re-states the sign rule, the enum and the Ensembl rule
rather than importing them: a verifier that imports the producer's constant cannot catch the
producer changing it, and a verifier that imports the producer's arithmetic reproduces the
producer's bug faithfully and then calls it agreement.

WHAT IT IS ACTUALLY DEFENDING
-----------------------------
One inversion, and one wrong gene:

  * A row whose ``desired_target_modulation`` tracks the PROGRAM direction instead of the
    ORIENTED ARM VALUE. Stage 3 would then hunt for agonists on exactly the targets whose
    knockdown helped. G_DIRECTION re-derives from the value and nothing else, so a row that
    was built from the program axis disagrees with its own number and is refused.

  * A row whose namespace was sniffed from the shape of its id. Three of the four symbol
    targets carry an ENSG-looking release key that belongs to a DIFFERENT GENE, so sniffing
    silently attaches the wrong gene to a drug. G_NAMESPACE requires the namespace to be
    DECLARED and to be a member of the release's own universe.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# RE-STATED, NOT IMPORTED. If the producer's tokens ever drift from these, that disagreement
# is the finding — and it cannot surface if both sides read the same constant.
# --------------------------------------------------------------------------- #
MODALITY = "CRISPRi_knockdown"
SIGN_EPS = 1e-9

MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"

INHIBITION_COMPATIBLE = "inhibition_observed_compatible"
INHIBITOR_OPPOSED = "inhibitor_opposed"
NO_DIRECTIONAL_RESPONSE = "no_directional_response"
NOT_EVALUABLE = "not_evaluable"

CLASS_OF = {
    MOD_DECREASE: INHIBITION_COMPATIBLE,
    MOD_INCREASE: INHIBITOR_OPPOSED,
    MOD_NO_DIRECTION: NO_DIRECTIONAL_RESPONSE,
    MOD_NOT_EVALUATED: NOT_EVALUABLE,
}

ENSEMBL_GENE_ID = "ensembl_gene_id"
GENE_SYMBOL = "gene_symbol"
NAMESPACES = (ENSEMBL_GENE_ID, GENE_SYMBOL)
ENSG_RE = re.compile(r"^ENSG[0-9]+$")

PROGRAM_DIRECTIONS = ("increase", "decrease")

REQUIRED = (
    "schema_version", "arm_key", "program_id", "target_id", "target_id_namespace",
    "observed_perturbation_modality", "perturbation_target_effect",
    "program_effect_direction", "desired_target_modulation", "phenocopy_class",
    "arm_value", "evaluable", "rank",
)

# The gates, named. A failure says WHICH invariant broke, never "invalid row".
G_FIELDS = "stage3_row_carries_every_required_field"
G_MODALITY = "observed_perturbation_modality_is_the_assay_not_a_derived_direction"
G_ORIENTATION = "program_effect_direction_equals_the_arm_keys_desired_change"
G_DIRECTION = "desired_target_modulation_rederives_from_the_oriented_arm_value"
G_PHENOCOPY = "phenocopy_class_follows_the_modulation_and_is_never_equivalence"
G_NO_AGONIST = "a_negative_arm_value_is_never_promoted_to_supported"
G_NAMESPACE = "target_id_namespace_is_declared_in_enum_and_in_the_release_universe"


def _rederive(arm_value: Any, evaluable: Any) -> str:
    """The sign rule, from the VALUE alone. The program direction is not an input here."""
    if not bool(evaluable) or arm_value is None:
        return MOD_NOT_EVALUATED
    try:
        value = float(arm_value)
    except (TypeError, ValueError):
        return MOD_NOT_EVALUATED
    if value > SIGN_EPS:
        return MOD_DECREASE
    if value < -SIGN_EPS:
        return MOD_INCREASE
    return MOD_NO_DIRECTION


def _desired_change_of(arm_key: Any) -> Optional[str]:
    """The PROGRAM direction encoded in the arm key: lane|program_id|desired_change|context."""
    parts = str(arm_key).split("|")
    return parts[2] if len(parts) > 2 and parts[2] in PROGRAM_DIRECTIONS else None


def verify_row(row: dict[str, Any], *, universe: dict[str, str]) -> list[str]:
    """Every way ONE row can be inadmissible. ``universe`` is target_id -> namespace."""
    bad: list[str] = []
    tid = row.get("target_id")

    missing = [f for f in REQUIRED if f not in row]
    if missing:
        bad.append(f"{G_FIELDS}: {tid}: missing {missing}")
        return bad                        # the rest would be checking fields that aren't there

    # (1) WHAT WAS DONE is a property of the assay. It is a constant, and a row whose
    # modality varies with anything at all has derived it from something it should not have.
    if row["observed_perturbation_modality"] != MODALITY:
        bad.append(f"{G_MODALITY}: {tid}: modality "
                   f"{row['observed_perturbation_modality']!r} is not {MODALITY!r}. Every "
                   "number in this release came from one assay; a row that says otherwise is "
                   "describing a perturbation nobody performed")

    # (2) ORIENTATION. The row's program axis must be the arm's own desired_change — if the
    # row were oriented against a different arm, its sign would mean the opposite thing.
    want_dir = _desired_change_of(row["arm_key"])
    if want_dir is None:
        bad.append(f"{G_ORIENTATION}: {tid}: arm_key {row['arm_key']!r} encodes no "
                   "desired_change, so this row's sign is oriented against nothing")
    elif row["program_effect_direction"] != want_dir:
        bad.append(f"{G_ORIENTATION}: {tid}: program_effect_direction "
                   f"{row['program_effect_direction']!r} but the arm_key says {want_dir!r}. "
                   "The arm value is oriented to the ARM's desired change; read against any "
                   "other, its sign means the opposite of what it says")

    # (3) THE INVERSION GATE. Re-derived from the VALUE, independently. A row whose modulation
    # was taken from the program direction fails here, on every row where the two differ.
    want_mod = _rederive(row["arm_value"], row["evaluable"])
    if row["desired_target_modulation"] != want_mod:
        bad.append(
            f"{G_DIRECTION}: {tid}: ships desired_target_modulation "
            f"{row['desired_target_modulation']!r}, but arm_value={row['arm_value']!r} / "
            f"evaluable={row['evaluable']!r} re-derives {want_mod!r}. The implied DRUG "
            "direction comes from the oriented arm value — never from the PROGRAM direction")

    # (4) the class follows the modulation, and the claim is a phenocopy, never an equivalence
    want_class = CLASS_OF.get(want_mod)
    if row["phenocopy_class"] != want_class:
        bad.append(f"{G_PHENOCOPY}: {tid}: phenocopy_class {row['phenocopy_class']!r} does "
                   f"not follow modulation {want_mod!r} (expected {want_class!r})")
    if row.get("claim_is_equivalence") is True:
        bad.append(f"{G_PHENOCOPY}: {tid}: claims EQUIVALENCE. An inhibitor is not a "
                   "knockdown; the strongest claim available here is a putative phenocopy")

    # (5) NO AGONIST FROM A SIGN INVERSION. A negative value OPPOSES an inhibitor. It does not
    # SUPPORT an agonist: no CRISPRa arm was run, so there is no observation to phenocopy.
    try:
        value = float(row["arm_value"]) if row["arm_value"] is not None else None
    except (TypeError, ValueError):
        value = None
    if value is not None and value < -SIGN_EPS:
        if row["phenocopy_class"] != INHIBITOR_OPPOSED:
            bad.append(
                f"{G_NO_AGONIST}: {tid}: arm_value {value!r} is negative — the knockdown "
                "moved the program the WRONG way — yet this row is classed "
                f"{row['phenocopy_class']!r}. That observation OPPOSES an inhibitor; it does "
                "not support an agonist. Activation was never tested and may not be ranked "
                "as supported evidence")
        if row.get("supported") is True:
            bad.append(f"{G_NO_AGONIST}: {tid}: a negative arm value marked supported")

    # (6) THE NAMESPACE. Declared, in the enum, and a MEMBER of the release's own universe —
    # never sniffed from the id's shape. (The shape rule is still checked, as a CONSISTENCY
    # check against the declaration; it is never the source of it.)
    ns = row["target_id_namespace"]
    if ns not in NAMESPACES:
        bad.append(f"{G_NAMESPACE}: {tid}: namespace {ns!r} not in {list(NAMESPACES)}")
    else:
        declared = universe.get(str(tid))
        if declared is None:
            bad.append(f"{G_NAMESPACE}: {tid}: not in the release's target universe, so its "
                       "namespace is unresolved. Refuse it — never infer it, and never drop "
                       "it silently: a dropped row and a row that never existed look the same")
        elif declared != ns:
            bad.append(f"{G_NAMESPACE}: {tid}: row declares {ns!r}; the release's universe "
                       f"says {declared!r}")
        looks_ensembl = bool(ENSG_RE.match(str(tid)))
        if ns == ENSEMBL_GENE_ID and not looks_ensembl:
            bad.append(f"{G_NAMESPACE}: {tid}: declared {ENSEMBL_GENE_ID} but is not an "
                       "Ensembl accession")
        if ns == GENE_SYMBOL and looks_ensembl:
            bad.append(f"{G_NAMESPACE}: {tid}: declared {GENE_SYMBOL} but is an Ensembl "
                       "accession")
    return bad


def verify_rows(rows: list[dict[str, Any]], *, universe: dict[str, str]) -> dict[str, Any]:
    """The report over MANY rows. Counts by class, so a reader sees what Stage 3 may act on."""
    failures: list[str] = []
    by_class: dict[str, int] = {}
    for row in rows:
        failures += verify_row(row, universe=universe)
        by_class[str(row.get("phenocopy_class"))] = (
            by_class.get(str(row.get("phenocopy_class")), 0) + 1)
    return {
        "verifier_id": "spot.stage02.stage3_row.independent_verifier.v1",
        "generator_is_not_verifier": True,
        "n_rows": len(rows),
        "n_failed": len(failures),
        "failures": failures[:50],
        "rows_by_phenocopy_class": by_class,
        # what Stage 3 may actually match an inhibitor to — stated, not left to be counted
        "n_inhibition_observed_compatible": by_class.get(INHIBITION_COMPATIBLE, 0),
        "n_inhibitor_opposed": by_class.get(INHIBITOR_OPPOSED, 0),
        "verdict": "admit" if not failures else "reject",
    }
