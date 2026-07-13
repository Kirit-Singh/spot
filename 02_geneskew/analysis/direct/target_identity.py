"""The bound per-target IDENTITY/ASSAY artifact. One row per target, derived — never parsed.

Stage 3 joins typed target evidence to `arms.parquet`, and until now the bundle shipped the arm
VALUES with no bound statement of WHAT each target_id is. A consumer had to infer the namespace
from the shape of the string — which is exactly the inference `identity.py` exists to forbid:
the released key is never inspected, "not even to phrase an error message", because four of this
release's targets are SYMBOLS whose keys look nothing like the other 11,522.

So the rows come from the ALREADY-ADMITTED source identity table (`identity.resolve`), which has
already decided each target's namespace against the release's own bytes. Nothing here re-derives
it, and nothing here reads a target_id to guess what it is.

  target_id                       the released key, verbatim
  target_id_namespace             ensembl_gene_id | gene_symbol — DECIDED upstream
  target_symbol                   required, non-empty
  target_ensembl                  NULLABLE: populated only for an ensembl_gene_id row. A
                                  gene_symbol row's Ensembl id is NULL, and it stays NULL — a
                                  symbol that could be mapped is still a symbol that was
                                  perturbed under its symbol.
  observed_perturbation_modality  CRISPRi_knockdown

SCOPE: A BUNDLE COVERS ITS OWN CONDITION, NOT THE RELEASE
---------------------------------------------------------
Each Direct condition bundle carries EXACTLY the targets that condition scored — no more and no
fewer. The three conditions do not ship the same targets, and the union across the release is a
RELEASE-level fact, not a bundle-level one. Nothing here hard-codes a count: the set is derived
from the condition's own admitted identity table and then checked, in BOTH directions, against
the targets the bundle actually scored.

An identity row for a target the bundle never scored is refused too. It is the quieter of the
two errors: a missing row makes a target vanish from Stage 3's join, and an extra one asserts
that a bundle measured something it did not.

THE MODALITY IS DECLARED, NOT DEFAULTED. It is what the assay DID — a knockdown, not an
overexpression — and every desired-change arm in the bundle is read against it. A bundle that
defaulted it, or shipped it empty, would let a reader assume the perturbation went the other way
and every sign in the release would flip meaning. So it is a pinned constant, bound into the run
identity, and anything other than the pinned value is refused by name.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .hashing import content_hash

SCHEMA_VERSION = "spot.stage02_target_identity.v1"
TARGET_IDENTITY_FILE = "target_identity.json"

# WHAT THE ASSAY DID. Pinned: a modality that can be defaulted is a modality nobody stated.
OBSERVED_PERTURBATION_MODALITY = "CRISPRi_knockdown"
MODALITY_RULE_ID = "spot.stage02.target_identity.observed_modality.crispri_knockdown.v1"

COLUMNS = ("target_id", "target_id_namespace", "target_symbol", "target_ensembl",
           "observed_perturbation_modality")

NAMESPACE_ENSEMBL = "ensembl_gene_id"
NAMESPACE_SYMBOL = "gene_symbol"
NAMESPACES = (NAMESPACE_ENSEMBL, NAMESPACE_SYMBOL)

REFUSE_DUPLICATE_TARGET = "target_identity_has_more_than_one_row_for_a_target"
REFUSE_INCOMPLETE = "target_identity_does_not_cover_every_target_the_bundle_scored"
REFUSE_EXTRANEOUS = "target_identity_carries_a_target_the_bundle_never_scored"
REFUSE_MODALITY = "observed_perturbation_modality_is_not_the_pinned_assay_modality"
REFUSE_NAMESPACE = "target_id_namespace_is_not_a_declared_namespace"
REFUSE_SYMBOL_HAS_ENSEMBL = "a_gene_symbol_row_carries_a_target_ensembl"
REFUSE_ABSENT = "the_bundle_ships_no_target_identity_artifact"


class TargetIdentityError(ValueError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise TargetIdentityError(gate, message)


def rows(identities: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per target, from the admitted identity table. Sorted; deterministic."""
    out = []
    for target_id in sorted(identities, key=lambda t: str(t).encode("utf-8")):
        ident = identities[target_id]
        ns = str(ident.target_id_namespace)
        if ns not in NAMESPACES:
            _refuse(REFUSE_NAMESPACE,
                    f"target {target_id!r} declares namespace {ns!r}; the release's targets are "
                    f"{list(NAMESPACES)} and a namespace nobody declared cannot be joined on")
        ensembl = ident.target_ensembl
        # A gene_symbol row's Ensembl id is NULL and stays NULL. The released key is never
        # inspected to invent one — that is the inference identity.py exists to forbid.
        if ns == NAMESPACE_SYMBOL and ensembl:
            _refuse(REFUSE_SYMBOL_HAS_ENSEMBL,
                    f"target {target_id!r} is a {NAMESPACE_SYMBOL} row carrying "
                    f"target_ensembl={ensembl!r}. It was perturbed under its SYMBOL; promoting "
                    "a key prefix into an accession is exactly the guess this lane refuses")
        out.append({
            "target_id": str(target_id),
            "target_id_namespace": ns,
            "target_symbol": str(ident.target_symbol),
            "target_ensembl": (str(ensembl) if ensembl else None),
            "observed_perturbation_modality": OBSERVED_PERTURBATION_MODALITY,
        })
    return out


def build(identities: dict[str, Any], *, condition: str,
          scored_targets: set) -> dict[str, Any]:
    """The artifact, checked: unique, complete against what the bundle scored, exact modality."""
    records = rows(identities)

    seen = [r["target_id"] for r in records]
    if len(seen) != len(set(seen)):
        dupes = sorted({t for t in seen if seen.count(t) > 1})
        _refuse(REFUSE_DUPLICATE_TARGET,
                f"{len(dupes)} target(s) appear more than once (e.g. {dupes[:3]}). A join key "
                "that is not unique silently multiplies every row it is joined to")

    _check_exact_set(seen, scored_targets)

    bad = [r["target_id"] for r in records
           if r["observed_perturbation_modality"] != OBSERVED_PERTURBATION_MODALITY]
    if bad:
        _refuse(REFUSE_MODALITY,
                f"{len(bad)} row(s) do not declare the pinned assay modality "
                f"{OBSERVED_PERTURBATION_MODALITY!r}. The modality is what the assay DID — a "
                "knockdown, not an overexpression — and every desired-change arm is read "
                "against it; a defaulted one lets a reader assume the perturbation went the "
                "other way, and every sign in the release flips meaning")

    n_ensembl = sum(1 for r in records if r["target_id_namespace"] == NAMESPACE_ENSEMBL)
    n_symbol = sum(1 for r in records if r["target_id_namespace"] == NAMESPACE_SYMBOL)
    return {
        "schema_version": SCHEMA_VERSION,
        "condition": condition,
        "columns": list(COLUMNS),
        "observed_perturbation_modality": OBSERVED_PERTURBATION_MODALITY,
        "modality_rule_id": MODALITY_RULE_ID,
        "n_targets": len(records),
        # the MIXED universe, counted rather than assumed: the release perturbs Ensembl ids AND
        # a handful of bare symbols, and a loader that expected one namespace would drop the
        # other four without noticing.
        "n_ensembl_gene_id": n_ensembl,
        "n_gene_symbol": n_symbol,
        "records": records,
    }


def _check_exact_set(seen: list[str], scored_targets) -> None:
    """The bundle's identity rows are EXACTLY the targets it scored. Both directions."""
    scored = set(map(str, scored_targets))
    have = set(seen)

    missing = sorted(scored - have)
    if missing:
        _refuse(REFUSE_INCOMPLETE,
                f"{len(missing)} target(s) the bundle SCORED have no identity row (e.g. "
                f"{missing[:3]}). Stage 3 joins this to arms.parquet; a scored target with no "
                "identity would drop out of the join and disappear without a trace")

    extra = sorted(have - scored)
    if extra:
        _refuse(REFUSE_EXTRANEOUS,
                f"{len(extra)} identity row(s) name a target the bundle never scored (e.g. "
                f"{extra[:3]}). A condition bundle covers ITS OWN targets: the three conditions "
                "do not ship the same set, and an extra row asserts this bundle measured "
                "something it did not")


def verify(doc: dict[str, Any], *, scored_targets: Optional[set] = None) -> dict[str, Any]:
    """REOPEN a SHIPPED artifact and re-check it. This is the gate that can actually fire.

    `build` checks rows it created itself, so its modality check can never fail — a gate that
    validates its own output is a gate that validates nothing. THIS one runs against the bytes
    somebody else shipped, which is the only place the check means anything. W10 calls it.
    """
    records = doc.get("records") or []
    seen = [str(r.get("target_id")) for r in records]
    if len(seen) != len(set(seen)):
        dupes = sorted({t for t in seen if seen.count(t) > 1})
        _refuse(REFUSE_DUPLICATE_TARGET,
                f"{len(dupes)} duplicated target_id (e.g. {dupes[:3]}); a join key that is not "
                "unique silently multiplies every row it is joined to")

    for r in records:
        ns = str(r.get("target_id_namespace"))
        if ns not in NAMESPACES:
            _refuse(REFUSE_NAMESPACE,
                    f"target {r.get('target_id')!r} declares namespace {ns!r}")
        if ns == NAMESPACE_SYMBOL and r.get("target_ensembl"):
            _refuse(REFUSE_SYMBOL_HAS_ENSEMBL,
                    f"target {r.get('target_id')!r} is a {NAMESPACE_SYMBOL} row carrying "
                    f"target_ensembl={r.get('target_ensembl')!r}")
        if r.get("observed_perturbation_modality") != OBSERVED_PERTURBATION_MODALITY:
            _refuse(REFUSE_MODALITY,
                    f"target {r.get('target_id')!r} declares modality "
                    f"{r.get('observed_perturbation_modality')!r}, not the pinned "
                    f"{OBSERVED_PERTURBATION_MODALITY!r}. The modality is what the assay DID — "
                    "a knockdown read as an overexpression flips the meaning of every sign in "
                    "the release")

    if doc.get("observed_perturbation_modality") != OBSERVED_PERTURBATION_MODALITY:
        _refuse(REFUSE_MODALITY,
                f"the artifact declares modality {doc.get('observed_perturbation_modality')!r}")

    if scored_targets is not None:
        _check_exact_set(seen, scored_targets)

    return {
        "n_targets": len(records),
        "n_ensembl_gene_id": sum(1 for r in records
                                 if r["target_id_namespace"] == NAMESPACE_ENSEMBL),
        "n_gene_symbol": sum(1 for r in records
                             if r["target_id_namespace"] == NAMESPACE_SYMBOL),
        "verified": True,
    }


def load(bundle_dir: str, *, scored_targets: Optional[set] = None) -> dict[str, Any]:
    """THE consumer entry point. Reopen the PRODUCER-EMITTED bytes, verify, return them + hash.

    Every consumer — the independent verifier, P2S, the Stage-3 join — reads the artifact
    THROUGH THIS, off the bundle, in place. Nobody re-derives identity from a mask, and nobody
    reads a target_id to guess what it is: the release perturbs four bare SYMBOLS whose keys look
    nothing like the other 11,522, so a string heuristic is wrong for exactly the rows nobody
    thinks about.

    The producer emits `target_identity.json`. It is the only shape there is: a consumer that
    expected a parquet would either fail to find the artifact or write one of its own, and a
    verifier that creates the file it is supposed to be checking has checked its own work.
    """
    import json

    from .hashing import file_sha256

    path = os.path.join(bundle_dir, TARGET_IDENTITY_FILE)
    if not os.path.exists(path):
        _refuse(REFUSE_ABSENT,
                f"the bundle ships no {TARGET_IDENTITY_FILE!r}. Identity is not something a "
                "consumer may reconstruct from the masks or from the shape of a target_id — it "
                "is a bound artifact, and its absence is a refusal, not a prompt to infer")
    with open(path) as fh:
        doc = json.load(fh)
    verify(doc, scored_targets=scored_targets)
    return {"doc": doc, "raw_sha256": file_sha256(path), "path": path,
            "canonical_sha256": content_hash(doc)}


def binding_block(doc: dict[str, Any], raw_sha256: str) -> dict[str, Any]:
    """What the run identity binds: the path, BOTH hashes, and the counts W10 recounts."""
    return {
        "path_in_bundle": TARGET_IDENTITY_FILE,
        "schema_version": doc["schema_version"],
        "columns": list(COLUMNS),
        "raw_sha256": raw_sha256,
        "canonical_sha256": content_hash(doc),
        "observed_perturbation_modality": doc["observed_perturbation_modality"],
        "modality_rule_id": doc["modality_rule_id"],
        "n_targets": doc["n_targets"],
        "n_ensembl_gene_id": doc["n_ensembl_gene_id"],
        "n_gene_symbol": doc["n_gene_symbol"],
    }
