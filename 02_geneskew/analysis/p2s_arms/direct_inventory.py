"""THE ADMITTED DIRECT INVENTORY: masks and eligibility, from the bundle's OWN bytes.

Two things here are scientific, not clerical, and an independent real-input attack found both.

MASKS ARE SELECTED BY THE FULL ESTIMATE IDENTITY — NEVER UNIONED ACROSS SCOPES
-----------------------------------------------------------------------------
The bundle's ``masks.parquet`` carries rows for the MAIN estimate and for the guide-slot and
donor-pair estimates. They are different estimates. Taking their union would mask a gene for a
perturbation that had no reason to mask it, and the reconstruction would then be denied
evidence nothing said to withhold — silently, and with a matrix that still looks fine.

So the main-estimate mask is selected on ``estimate_type == "main" AND estimate_id == "main"``,
and the masked gene comes from ``masked_gene_ensembl`` — the readout namespace the arms are
actually computed in.

ELIGIBILITY IS ARM-SPECIFIC
--------------------------
It is not a property of a target. It is ``evaluable`` on the arm
``direct|program|increase|condition`` — the arm the fit is taken on. And because the two sign
arms are one measurement and a sign, their evaluable inventories MUST be identical; if they
are not, something re-derived one of them, and this refuses rather than picking a side.

A MISSING MASK IS A REFUSAL, NEVER AN EMPTY ONE
----------------------------------------------
An eligible target with no mask row would silently get ``mask = {}`` — i.e. NOTHING masked,
which is the most permissive possible mask and the exact opposite of the safe default.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd
from direct import target_identity as ti

from . import armref, config
from . import disposition as D


def main_estimate_masks(bundle_dir: str) -> dict[str, Any]:
    """The MAIN-estimate mask rows. Scopes are SELECTED, never unioned."""
    df = pd.read_parquet(os.path.join(bundle_dir, "masks.parquet"))

    if config.MASK_GENE_COLUMN not in df.columns:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"the bundle's masks.parquet has no {config.MASK_GENE_COLUMN!r} column (it has "
            f"{sorted(df.columns)}). The masked gene must arrive in the READOUT namespace; "
            "this lane will not re-derive it from a symbol")

    n_all = len(df)
    scoped = df
    for col, want in (("estimate_type", config.MASK_MAIN_ESTIMATE_TYPE),
                      ("estimate_id", config.MASK_MAIN_ESTIMATE_ID)):
        if col not in df.columns:
            raise D.RefusalError(
                D.REFUSE_MASK_SCOPE_UNION,
                f"the bundle's masks.parquet has no {col!r} column, so a MAIN-estimate mask "
                "cannot be told apart from a guide-slot or donor-pair one. Unioning them "
                "would mask genes for perturbations that had no reason to mask them")
        scoped = scoped[scoped[col].astype(str) == want]

    if scoped.empty:
        raise D.RefusalError(
            D.REFUSE_MASK_EMPTY,
            f"the admitted bundle ships {n_all} mask row(s) but NONE for the main estimate "
            f"({config.MASK_MAIN_ESTIMATE_TYPE}/{config.MASK_MAIN_ESTIMATE_ID}). An empty "
            "mask is the most permissive mask there is, and it is never a default")

    rows = (scoped[["target_id", config.MASK_GENE_COLUMN]].astype(str)
            .rename(columns={config.MASK_GENE_COLUMN: "gene_id"})
            .drop_duplicates())
    by_target: dict[str, set] = {}
    for r in rows.itertuples(index=False):
        by_target.setdefault(str(r.target_id), set()).add(str(r.gene_id))

    return {"rows": rows.to_dict("records"), "by_target": by_target,
            "n_rows_all_scopes": int(n_all), "n_rows_main": int(len(rows)),
            "scopes_unioned": config.MASK_SCOPES_MAY_BE_UNIONED,
            "estimate_type": config.MASK_MAIN_ESTIMATE_TYPE,
            "estimate_id": config.MASK_MAIN_ESTIMATE_ID,
            "gene_column": config.MASK_GENE_COLUMN}


def load_target_identity(bundle_dir: str, *, scored_targets: set) -> dict[str, Any]:
    """The bound per-target IDENTITY — through Direct's OWN shared loader. Never inferred.

    ``direct.target_identity.load`` reopens the producer-emitted ``target_identity.json`` in
    place, verifies it (namespace declared, symbol present, a gene_symbol row carries no
    Ensembl id, every scored target covered and no extra), and returns the records plus BOTH
    hashes. Nobody re-derives identity from a mask or from the shape of a target_id: the
    release perturbs four bare SYMBOLS whose keys look nothing like an Ensembl id, so a string
    heuristic is wrong for exactly the rows nobody thinks about.
    """
    loaded = ti.load(bundle_dir, scored_targets=scored_targets)
    ensembl: dict[str, Any] = {}
    namespace: dict[str, str] = {}
    symbol: dict[str, str] = {}
    for r in loaded["doc"]["records"]:
        t = str(r["target_id"])
        ensembl[t] = r["target_ensembl"] and str(r["target_ensembl"])
        namespace[t] = str(r["target_id_namespace"])
        symbol[t] = str(r["target_symbol"])
    return {
        "target_ensembl_by_target": ensembl,
        "namespace_by_target": namespace,
        "symbol_by_target": symbol,
        "raw_sha256": loaded["raw_sha256"],
        "canonical_sha256": loaded["canonical_sha256"],
        "binding": ti.binding_block(loaded["doc"], loaded["raw_sha256"]),
        "n_symbol_targets": loaded["doc"]["n_gene_symbol"],
        "n_ensembl_targets": loaded["doc"]["n_ensembl_gene_id"],
    }


def all_scored_targets(bundle_dir: str) -> set[str]:
    """Every unique ``target_id`` the bundle SCORED — the COMPLETE set identity.json covers.

    Read off ``arms.parquet``, NOT off one arm's evaluable subset. ``target_identity.json`` is a
    property of the whole condition bundle: it carries exactly the targets the condition scored,
    and ``ti.load`` checks that in BOTH directions. Verifying it against a single arm's evaluable
    targets would refuse every real bundle — each non-evaluable scored target would read as an
    "extraneous" identity row.
    """
    arms = pd.read_parquet(os.path.join(bundle_dir, "arms.parquet"))
    if "target_id" not in arms.columns:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            "the bundle's arms.parquet has no target_id column, so the set of targets the "
            "bundle scored — the set target_identity.json must cover — cannot be derived")
    return set(arms["target_id"].astype(str).unique().tolist())


def _self_gene_check(*, targets: list[str], target_ensembl: dict[str, Any],
                     namespace: dict[str, Any], symbol: dict[str, Any],
                     mask_by_target: dict[str, set],
                     readout_crosswalk: dict[str, set] | None):
    """Classify each target's self-gene readout coordinate: masked/absent (ok), or a leak.

    An ensembl_gene_id target's self-gene is its OWN Ensembl id — it must be in the target's
    mask (its positive control). A gene_symbol target has no Ensembl id by contract, so its
    self-gene coordinate is resolved through the DE ``gene_name``/id crosswalk and is one of:

      PRESENT     the symbol names exactly one readout coordinate — which must be masked;
      ABSENT      the symbol names none — proven, and nothing can leak;
      UNRESOLVED  no crosswalk was supplied, or the symbol names MORE THAN ONE coordinate —
                  refuse rather than assume no self-gene can leak. Namespace = gene_symbol
                  alone is NOT that proof.

    Returns ``(leak, unmapped, unresolved)`` — ensembl self-genes left unmasked, symbol
    self-coordinates present-but-unmasked, and symbol self-coordinates that cannot be resolved.
    """
    leak: list = []
    unmapped: list = []
    unresolved: list = []
    for t in targets:
        masked = mask_by_target.get(t, set())
        if namespace.get(t) == ti.NAMESPACE_SYMBOL:
            sym = symbol.get(t)
            if readout_crosswalk is None:
                unresolved.append((t, sym, "no DE gene_name crosswalk supplied"))
                continue
            coords = readout_crosswalk.get(str(sym)) or set()
            if not coords:
                continue                                    # ABSENT — proven; nothing to leak
            if len(coords) > 1:
                unresolved.append((t, sym, f"names {len(coords)} readout coordinates"))
                continue
            (coord,) = tuple(coords)
            if coord not in masked:                         # PRESENT but unmasked
                unmapped.append((t, sym, coord))
        else:
            ens = target_ensembl.get(t)
            if ens and ens not in masked:
                leak.append((t, ens))
    return leak, unmapped, unresolved


def evaluable_targets(bundle_dir: str, *, program_id: str, condition: str) -> dict[str, Any]:
    """The targets EVALUABLE on this program's arm. Arm-specific, and symmetric by proof."""
    arms = pd.read_parquet(os.path.join(bundle_dir, "arms.parquet"))
    inc, dec = armref.both_arms(program_id, condition)

    def inventory(arm_key: str) -> list[str]:
        sub = arms[arms["arm_key"].astype(str) == arm_key]
        ev = sub[sub["evaluable"].astype(bool)]
        return sorted(ev["target_id"].astype(str).unique().tolist())

    inc_targets = inventory(inc.arm_key)
    dec_targets = inventory(dec.arm_key)

    if not inc_targets:
        raise D.RefusalError(
            D.REFUSE_ELIGIBLE_EMPTY,
            f"the admitted bundle ships no EVALUABLE target on {inc.arm_key!r}. Eligibility "
            "is a property of the ARM, not of the target, and an arm with nothing evaluable "
            "has no perturbation matrix to reconstruct from")

    # The two arms are ONE measurement and a sign. Their evaluable inventories must therefore
    # be identical — if they are not, one of them was re-derived, and picking a side would be
    # choosing which of two disagreeing answers to believe.
    if inc_targets != dec_targets:
        only_inc = sorted(set(inc_targets) - set(dec_targets))[:3]
        only_dec = sorted(set(dec_targets) - set(inc_targets))[:3]
        raise D.RefusalError(
            D.REFUSE_ARM_INVENTORY_ASYMMETRY,
            f"the two sign arms of {program_id!r} at {condition!r} do not share one evaluable "
            f"inventory ({len(inc_targets)} vs {len(dec_targets)}; only-increase={only_inc}, "
            f"only-decrease={only_dec}). They are one measurement and a sign; a disagreement "
            "here means something re-derived one of them")

    sub_inc = arms[arms["arm_key"].astype(str) == inc.arm_key]
    states = sub_inc.set_index("target_id")["base_state"].astype(str).to_dict()
    # Direct's ARM_ROW_COLUMNS carries NO target_ensembl — it lives on the MAIN MASK rows.
    # evaluable_targets does not read it here; direct_inventory.bind attaches it from masks.
    return {
        "targets": inc_targets,
        "n_evaluable": len(inc_targets),
        "arm_key": inc.arm_key,
        "sibling_arm_key": dec.arm_key,
        "inventories_are_identical": True,
        "eligibility_is_arm_specific": True,
        "base_state_by_target": {t: states.get(t) for t in inc_targets},
        "qc_pass_states_seen": sorted({states.get(t) for t in inc_targets if states.get(t)}),
    }


def bind(bundle_dir: str, *, program_id: str, condition: str,
         readout_crosswalk: dict[str, set] | None = None) -> dict[str, Any]:
    """Masks + arm-specific eligibility + BOUND identity, cross-checked. A gap is a refusal.

    ``readout_crosswalk`` is the DE ``gene_name`` -> set-of-Ensembl-ids pairing. It is what
    resolves a gene_symbol target's self-gene readout coordinate; without it a symbol target
    cannot be PROVEN free of a self-gene leak, and this refuses rather than exempt it silently.
    """
    masks = main_estimate_masks(bundle_dir)
    elig = evaluable_targets(bundle_dir, program_id=program_id, condition=condition)

    # EVERY eligible target must carry a mask. A target with no mask row would otherwise get
    # the empty mask — nothing withheld at all, the most permissive setting there is.
    unmasked = [t for t in elig["targets"] if t not in masks["by_target"]]
    if unmasked:
        raise D.RefusalError(
            D.REFUSE_MASK_MISSING_FOR_ELIGIBLE,
            f"{len(unmasked)} evaluable target(s) on {elig['arm_key']!r} have NO main-estimate "
            f"mask in the admitted bundle (e.g. {unmasked[:3]}). A missing mask is not an "
            "empty mask: it would withhold nothing, which is the most permissive mask there "
            "is and the exact opposite of the safe default")

    # IDENTITY comes from the bound target_identity.json — through Direct's shared loader,
    # never from a mask or a target_id heuristic. It is loaded and VERIFIED ONCE against the
    # bundle's COMPLETE scored set (every unique arms.parquet target_id), then SUBSET to this
    # arm's eligible columns. Verifying against the eligible subset would refuse every real
    # bundle: the artifact covers the whole condition, so each non-evaluable scored target
    # would read as an extraneous identity row.
    scored = all_scored_targets(bundle_dir)
    identity = load_target_identity(bundle_dir, scored_targets=scored)
    missing_identity = sorted(t for t in elig["targets"]
                              if t not in identity["namespace_by_target"])
    if missing_identity:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"{len(missing_identity)} evaluable target(s) have no target_identity row (e.g. "
            f"{missing_identity[:3]}), though every scored target should. The identity "
            "artifact and the arm rows disagree about what this bundle measured")
    target_ensembl = {t: identity["target_ensembl_by_target"].get(t) for t in elig["targets"]}
    namespace = {t: identity["namespace_by_target"].get(t) for t in elig["targets"]}
    symbol = {t: identity["symbol_by_target"].get(t) for t in elig["targets"]}
    symbol_targets = sorted(t for t in elig["targets"]
                            if namespace[t] == ti.NAMESPACE_SYMBOL)

    # SELF-GENE: every target's self-gene readout coordinate must be MASKED (its positive
    # control) or PROVEN absent. gene_symbol targets are NOT silently exempt — their self-gene
    # is resolved through the DE crosswalk (present -> mask; absent -> ok; unresolved -> refuse).
    leak, symbol_unmapped, unresolved = _self_gene_check(
        targets=elig["targets"], target_ensembl=target_ensembl, namespace=namespace,
        symbol=symbol, mask_by_target=masks["by_target"], readout_crosswalk=readout_crosswalk)
    if leak:
        raise D.RefusalError(
            D.REFUSE_MASK_MISSING_FOR_ELIGIBLE,
            f"{len(leak)} target(s) with a known Ensembl id do not mask their OWN gene (e.g. "
            f"{leak[:3]}). The self-gene is the perturbation's positive control; leaving it "
            "unmasked would let the target reconstruct itself")
    if symbol_unmapped:
        raise D.RefusalError(
            D.REFUSE_TARGET_SYMBOL_PRESENT_UNMAPPED,
            f"{len(symbol_unmapped)} gene_symbol target(s) name a readout coordinate that the "
            f"mask does NOT withhold (e.g. {symbol_unmapped[:3]}). The symbol IS measured in "
            "the readout, so its self-gene must be masked exactly as an Ensembl target's is")
    if unresolved:
        raise D.RefusalError(
            D.REFUSE_SELF_GENE_UNRESOLVED,
            f"{len(unresolved)} gene_symbol target(s) whose self-gene coordinate cannot be "
            f"resolved (e.g. {unresolved[:3]}). A symbol was perturbed but the DE crosswalk "
            "cannot say whether it names a readout coordinate; namespace=gene_symbol alone is "
            "not proof no self-gene can leak, so this refuses rather than assume it")

    return {"masks": masks, "eligible": elig,
            "targets": elig["targets"], "mask_by_target": masks["by_target"],
            "target_ensembl_by_target": target_ensembl,
            "namespace_by_target": namespace,
            "target_identity_binding": identity["binding"],
            "target_identity_raw_sha256": identity["raw_sha256"],
            "target_identity_canonical_sha256": identity["canonical_sha256"],
            "n_scored_targets": len(scored),
            "n_symbol_namespace_targets": len(symbol_targets),
            "symbol_namespace_targets": symbol_targets[:10]}
