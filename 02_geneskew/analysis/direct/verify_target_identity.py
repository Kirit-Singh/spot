"""THE per-target IDENTITY / ASSAY artifact — W10's independent verification.

A Direct condition bundle ships `target_identity.json` (producer 5e9902a): a records array,
one row per `target_id`, with `target_id_namespace`, `target_symbol`, `target_ensembl`
(nullable) and `observed_perturbation_modality = CRISPRi_knockdown`, plus recount fields and a
binding block bound into `arm_bundle_run_id`. W3 joins it to `arms.parquet` for typed target
evidence — Direct production contract, not a fixture comment.

INDEPENDENCE RULE (test-enforced): imports nothing from the PRODUCER — not its
`target_identity` module, not its `build`/`verify`. The artifact's FORMAT is restated here as
literals; its VALUES are RE-DERIVED from the released source via W10's own identity rule
(`verify_rules.target_identity`), never read back from the artifact and trusted, never
string-parsed from `released_estimate_id`. Both hashes the run bound are re-computed over the
shipped bytes.

TWO SCOPES:
  * PER BUNDLE — exactly this condition's own arm target set (Rest is not Stim8hr; no global
    count hard-coded). Uniqueness, completeness against arms, exact modality, a namespace /
    symbol / ensembl that re-derive from the source, the declared recounts, and both bound
    hashes.
  * ACROSS THE RELEASE — the UNION of the three bundles is the mixed target universe: 11,522
    ensembl + 4 gene_symbol = 11,526. A release check, not a per-bundle one.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_rules as R  # noqa: E402  (W10's own identity rule + H5AD reader)
from verify_arm_recompute import read_pooled_meta  # noqa: E402
from verify_arm_rules import content_sha256, sha256_file  # noqa: E402

# THE ARTIFACT FORMAT, restated as literals (the producer is authoritative; a checker that
# imported the producer's constants would be checking the producer against itself).
TARGET_IDENTITY_FILE = "target_identity.json"
SCHEMA_VERSION = "spot.stage02_target_identity.v1"
MODALITY = "CRISPRi_knockdown"
MODALITY_RULE_ID = "spot.stage02.target_identity.observed_modality.crispri_knockdown.v1"
NAMESPACE_ENSEMBL = R.ENSEMBL_GENE_ID          # "ensembl_gene_id"
NAMESPACE_SYMBOL = R.GENE_SYMBOL               # "gene_symbol"
COLUMNS = ("target_id", "target_id_namespace", "target_symbol", "target_ensembl",
           "observed_perturbation_modality")

RELEASE_UNION_TOTAL = 11526
RELEASE_UNION_ENSEMBL = 11522
RELEASE_UNION_SYMBOL = 4

REFUSE_TI_MISSING = "the_target_identity_artifact_is_absent"
REFUSE_TI_UNREADABLE = "the_target_identity_artifact_is_not_readable"
REFUSE_TI_SCHEMA = "the_target_identity_schema_or_columns_are_not_the_pinned_contract"
REFUSE_TI_DUPLICATE = "a_target_id_appears_more_than_once_in_target_identity"
REFUSE_TI_INCOMPLETE = "the_target_identity_rows_are_not_exactly_the_arm_target_set"
REFUSE_TI_MODALITY = "an_observed_perturbation_modality_is_not_exactly_crispri_knockdown"
REFUSE_TI_NAMESPACE = "a_target_id_namespace_does_not_re_derive_from_the_source"
REFUSE_TI_IDENTITY = "a_target_symbol_or_ensembl_disagrees_with_the_source_identity"
REFUSE_TI_RECOUNT = "the_declared_namespace_counts_do_not_recount_from_the_rows"
REFUSE_TI_UNBOUND = "the_target_identity_hash_is_not_bound_into_the_run_identity"
REFUSE_TI_UNION = "the_release_target_universe_is_not_the_expected_mixed_namespace_union"


# --------------------------------------------------------------------------- #
# THE REFERENCE DERIVATION — the truth the verifier compares against, from the source.
# --------------------------------------------------------------------------- #
def derive_identity_rows(de_main: str, condition: str,
                         identity_map: Optional[dict] = None) -> list[dict[str, Any]]:
    """One canonical identity row per target in THIS condition, RE-DERIVED from the source."""
    _genes, meta, _sel = read_pooled_meta(de_main, condition)
    rows: list[dict[str, Any]] = []
    for i in range(len(meta["target_contrast"])):
        ident = R.target_identity(meta["released_estimate_id"][i],
                                  meta["target_contrast"][i],
                                  meta["target_contrast_gene_name"][i], identity_map)
        rows.append({
            "target_id": str(ident["target_id"]),
            "target_id_namespace": ident["target_id_namespace"],
            "target_symbol": None if ident["target_symbol"] is None
            else str(ident["target_symbol"]),
            "target_ensembl": None if ident["target_ensembl"] is None
            else str(ident["target_ensembl"]),
            "observed_perturbation_modality": MODALITY,
        })
    return rows


def read_doc(bundle_dir: str) -> Optional[dict[str, Any]]:
    """Reopen the shipped target_identity.json. None if absent."""
    path = os.path.join(bundle_dir, TARGET_IDENTITY_FILE)
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# THE BUNDLE GATE.
# --------------------------------------------------------------------------- #
def gate_bundle(bundle_dir: str, de_main: str, condition: str, arm_target_ids: set,
                binding: dict, rep) -> Optional[list[dict[str, Any]]]:
    """Verify one condition's target_identity artifact. Returns its records (for the union)."""
    doc = read_doc(bundle_dir)
    if doc is None:
        rep.gate("the bundle ships a target_identity artifact", False,
                 f"{TARGET_IDENTITY_FILE} is absent — a Direct bundle must carry one row per "
                 "target for W3's typed target join")
        return None
    rep.gate("the bundle ships a target_identity artifact", True)

    rep.gate("the target_identity schema and columns are the pinned contract",
             doc.get("schema_version") == SCHEMA_VERSION
             and tuple(doc.get("columns") or ()) == COLUMNS,
             f"schema={doc.get('schema_version')!r} columns={doc.get('columns')!r}")

    records = doc.get("records") or []
    ids = [str(r.get("target_id")) for r in records]
    rep.gate("every target_id appears exactly once", len(ids) == len(set(ids)),
             f"{len(ids)} rows, {len(set(ids))} distinct")
    rep.gate("the target_identity rows are EXACTLY this bundle's arm target set — no "
             "missing, no extra, and no global universe hard-coded into a condition",
             set(ids) == set(map(str, arm_target_ids)),
             f"missing={sorted(set(map(str, arm_target_ids)) - set(ids))[:3]} "
             f"extra={sorted(set(ids) - set(map(str, arm_target_ids)))[:3]}")

    bad_mod = [r.get("target_id") for r in records
               if r.get("observed_perturbation_modality") != MODALITY]
    rep.gate("every observed_perturbation_modality is EXACTLY CRISPRi_knockdown — a missing, "
             "altered or defaulted modality refuses",
             not bad_mod and doc.get("observed_perturbation_modality") == MODALITY
             and doc.get("modality_rule_id") == MODALITY_RULE_ID,
             f"{len(bad_mod)} bad row(s); doc modality="
             f"{doc.get('observed_perturbation_modality')!r}")

    # RE-DERIVE the identity from the source and compare — never trust the artifact's own
    # namespace / symbol / ensembl.
    truth = {str(r["target_id"]): r for r in derive_identity_rows(de_main, condition)}
    bad_ns, bad_id = [], []
    for r in records:
        tid = str(r.get("target_id"))
        t = truth.get(tid)
        if t is None:
            continue
        ns = r.get("target_id_namespace")
        if ns not in (NAMESPACE_ENSEMBL, NAMESPACE_SYMBOL) or ns != t["target_id_namespace"]:
            bad_ns.append(tid)
            continue
        sym = None if r.get("target_symbol") is None else str(r.get("target_symbol"))
        ens = None if r.get("target_ensembl") is None else str(r.get("target_ensembl"))
        if sym != t["target_symbol"] or ens != t["target_ensembl"]:
            bad_id.append(tid)
    rep.gate("every target_id_namespace RE-DERIVES from the source (ensembl_gene_id / "
             "gene_symbol) — a defaulted or altered namespace refuses",
             not bad_ns, f"{len(bad_ns)} bad, first: {bad_ns[:2]}")
    rep.gate("every target_symbol and target_ensembl agrees with the re-derived source "
             "identity (gene_symbol => null ensembl; ensembl => its own accession)",
             not bad_id, f"{len(bad_id)} bad, first: {bad_id[:2]}")

    # THE DECLARED COUNTS RECOUNT from the rows — a mixed universe stated, not assumed.
    n_ens = sum(1 for r in records if r.get("target_id_namespace") == NAMESPACE_ENSEMBL)
    n_sym = sum(1 for r in records if r.get("target_id_namespace") == NAMESPACE_SYMBOL)
    rep.gate("the declared namespace counts recount from the rows",
             doc.get("n_targets") == len(records)
             and doc.get("n_ensembl_gene_id") == n_ens
             and doc.get("n_gene_symbol") == n_sym,
             f"declared n={doc.get('n_targets')}/ens={doc.get('n_ensembl_gene_id')}/"
             f"sym={doc.get('n_gene_symbol')} recount n={len(records)}/ens={n_ens}/sym={n_sym}")

    # BOTH bound hashes RE-DERIVE from the shipped bytes.
    bound = binding.get("target_identity") or {}
    canonical = content_sha256(doc)
    rep.gate("the target_identity canonical hash is bound into the run identity and "
             "RE-DERIVES from the shipped document",
             bound.get("canonical_sha256") == canonical,
             f"bound={bound.get('canonical_sha256')!r} derived={canonical!r}")
    raw = sha256_file(os.path.join(bundle_dir, TARGET_IDENTITY_FILE))
    rep.gate("the target_identity raw bytes are bound into the run identity",
             bound.get("raw_sha256") == raw,
             f"bound={bound.get('raw_sha256')!r} actual={raw!r}")
    return records


# --------------------------------------------------------------------------- #
# THE RELEASE UNION GATE.
# --------------------------------------------------------------------------- #
def gate_release_union(per_bundle_records: list[list[dict[str, Any]]], rep,
                       expect_production_universe: bool = False) -> None:
    """The UNION across the release's bundles is the mixed-namespace target universe."""
    union: dict[str, str] = {}
    conflicts = []
    for records in per_bundle_records:
        for r in records:
            tid, ns = str(r.get("target_id")), r.get("target_id_namespace")
            if tid in union and union[tid] != ns:
                conflicts.append(tid)
            union[tid] = ns
    rep.gate("a target's namespace is the same in every condition it appears in",
             not conflicts, f"{conflicts[:3]}")

    n_ens = sum(1 for ns in union.values() if ns == NAMESPACE_ENSEMBL)
    n_sym = sum(1 for ns in union.values() if ns == NAMESPACE_SYMBOL)
    rep.gate("the release target universe is a MIXED namespace union (both ensembl and "
             "gene_symbol targets are present)",
             n_ens > 0 and n_sym > 0, f"ensembl={n_ens} symbol={n_sym}")

    if expect_production_universe:
        rep.gate("the release target universe is EXACTLY 11,522 ensembl + 4 gene_symbol "
                 "= 11,526",
                 n_ens == RELEASE_UNION_ENSEMBL and n_sym == RELEASE_UNION_SYMBOL
                 and len(union) == RELEASE_UNION_TOTAL,
                 f"ensembl={n_ens} symbol={n_sym} total={len(union)}")


# --------------------------------------------------------------------------- #
# THE REFERENCE EMITTER — byte-identical to the producer's format (restated, not imported),
# so tests exercise the real artifact and W14/W18 can diff their emission against it.
# --------------------------------------------------------------------------- #
def build_doc(de_main: str, condition: str) -> dict[str, Any]:
    """The target_identity document, in the producer's exact shape, from the source."""
    rows = sorted(derive_identity_rows(de_main, condition),
                  key=lambda r: str(r["target_id"]).encode("utf-8"))
    n_ens = sum(1 for r in rows if r["target_id_namespace"] == NAMESPACE_ENSEMBL)
    n_sym = sum(1 for r in rows if r["target_id_namespace"] == NAMESPACE_SYMBOL)
    return {
        "schema_version": SCHEMA_VERSION,
        "condition": condition,
        "columns": list(COLUMNS),
        "observed_perturbation_modality": MODALITY,
        "modality_rule_id": MODALITY_RULE_ID,
        "n_targets": len(rows),
        "n_ensembl_gene_id": n_ens,
        "n_gene_symbol": n_sym,
        "records": rows,
    }


def emit_reference_artifact(bundle_dir: str, de_main: str,
                            condition: str) -> dict[str, str]:
    """Write a conformant target_identity.json (producer bytes) and return the binding block."""
    doc = build_doc(de_main, condition)
    identity_bytes = (json.dumps(doc, indent=2, sort_keys=True, default=str)
                      + "\n").encode("utf-8")
    with open(os.path.join(bundle_dir, TARGET_IDENTITY_FILE), "wb") as fh:
        fh.write(identity_bytes)
    import hashlib
    return {
        "path_in_bundle": TARGET_IDENTITY_FILE,
        "schema_version": SCHEMA_VERSION,
        "columns": list(COLUMNS),
        "raw_sha256": hashlib.sha256(identity_bytes).hexdigest(),
        "canonical_sha256": content_sha256(doc),
        "observed_perturbation_modality": MODALITY,
        "modality_rule_id": MODALITY_RULE_ID,
        "n_targets": doc["n_targets"],
        "n_ensembl_gene_id": doc["n_ensembl_gene_id"],
        "n_gene_symbol": doc["n_gene_symbol"],
    }


class _MiniReport:
    """A standalone Report for verifying the gate without the full bundle verifier."""

    def __init__(self):
        self.gates: list[dict[str, Any]] = []

    def gate(self, name: str, ok: bool, detail: str = "") -> bool:
        self.gates.append({"gate": name, "passed": bool(ok), "detail": str(detail)})
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [g["gate"] for g in self.gates if not g["passed"]]
