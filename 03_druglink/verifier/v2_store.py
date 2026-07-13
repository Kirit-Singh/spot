"""The ADMITTED UNIVERSE STORE, re-opened from disk and re-proved from its own bytes.

Imports NOTHING from ``druglink``. The typed universe is DERIVED from the store's own rows,
the eligibility verdicts are REPLAYED from their own predicate inputs, and every source
assertion is rebuilt from the row it lives in — the store's claims are never read as results.

WHY THE ELIGIBILITY REPLAY IS HERE AND NOT READ
-----------------------------------------------
The store ships an ``eligible`` flag per ChEMBL target. A flag is a CLAIM: it asks to be
believed, and a resealed artifact carries a perfectly consistent hash over a mutated taxon.
What survives a reseal is the REPLAY — re-deriving the verdict from the record's own inputs
(target type, taxon, species group, component type, component taxon, homologue, cardinality)
and comparing. The contradiction is then between a record's inputs and its own verdict, and
rehashing cannot remove it.

THE GENERAL LANE IS THE SINGLE-PROTEIN LANE, AND THAT IS CHECKED
----------------------------------------------------------------
The producer classifies every general-gene assertion as a single-protein target without
re-deriving it. That is only sound if the general lane cannot contain a complex, a family or a
non-human target — so this module PROVES it, per assertion, against the replayed evidence. A
general-lane assertion whose target is not an eligible human single protein is a NAMED refusal
here, rather than a direction quietly computed against an entity that is not a gene.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import canon
from . import v2_contract as C
from . import v2_tables as T
from .report import Report

# The six frozen eligibility predicates, restated from the store's own SQL. A target is an
# eligible human single protein iff ALL of them hold, over EXACTLY one component.
SINGLE_PROTEIN = "SINGLE PROTEIN"
COMPONENT_PROTEIN = "PROTEIN"
HUMAN_TAX_ID = 9606
HOMOLOGUE_EXACT = 0
SPECIES_GROUP_NONE = 0

EDGE_POLICY_VERSION = "stage3-universe-edges-v1"


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def _load(rep: Report, path: str, what: str, gate: str) -> Optional[Any]:
    if not path or not os.path.isfile(path):
        _gate(rep, gate,
              f"the {what} is on disk and is opened for admission (there is no fixture "
              "fallback: a Stage-3 run without its admitted store does not quietly become one "
              "with a synthetic store)",
              False, f"not found: {path!r}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        _gate(rep, gate, f"the {what} parses as JSON", False, f"{type(exc).__name__}: {exc}")
        return None


# --------------------------------------------------------------------------- #
# 1. The typed universe, DERIVED from the store's own rows.
# --------------------------------------------------------------------------- #
def derive_typed_universe(rep: Report, rows: Any) -> Optional[list[dict[str, str]]]:
    if not isinstance(rows, list):
        _gate(rep, C.GATE_MALFORMED_STORE_ROW, "the store's rows artifact is a list of rows",
              False, type(rows).__name__)
        return None

    typed: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    malformed, duplicate, unknown_ns = [], [], []
    for row in rows:
        tid, ns, disp = (row.get("target_id"), row.get("target_id_namespace"),
                         row.get("disposition"))
        if not tid or not ns or disp not in C.STORE_DISPOSITIONS:
            malformed.append(f"{tid!r}/{ns!r}/{disp!r}")
            continue
        # An UNKNOWN namespace token is a NAMED refusal — never coerced onto a known one, and
        # never defaulted. The store's own RETIRED tokens land here: Stage 2 serializes
        # `ensembl_gene_id` / `gene_symbol`, and a store still speaking `ensembl_gene` /
        # `symbol` cannot be exact-typed-joined to it. Aliasing between the two would absorb
        # that divergence in silence and let both lanes stay green while they drift apart.
        if str(ns) not in C.STORE_NAMESPACES:
            unknown_ns.append(f"{tid}:{ns}")
            continue
        if (str(ns), str(tid)) in seen:
            duplicate.append(f"{ns}:{tid}")
            continue
        seen.add((str(ns), str(tid)))
        typed.append({"target_id": str(tid), "target_id_namespace": str(ns)})

    _gate(rep, C.GATE_MALFORMED_STORE_ROW,
          "every store row carries a typed identity and a known disposition (a target nobody "
          "accounted for is indistinguishable from a target nobody measured)",
          not malformed, str(malformed[:3]))
    _gate(rep, C.GATE_UNKNOWN_NAMESPACE_TOKEN,
          f"every store row is typed in the admitted vocabulary {list(C.STORE_NAMESPACES)} — an "
          f"unknown token (the RETIRED {list(C.RETIRED_NAMESPACES)} above all) is refused, never "
          "aliased onto a known one",
          not unknown_ns, str(unknown_ns[:3]))
    _gate(rep, C.GATE_DUPLICATE_TYPED_IDENTITY,
          "no two store rows claim one typed identity (a duplicate double-counts every drug "
          "edge that lands on it)",
          not duplicate, str(duplicate[:3]))
    if not _gate(rep, C.GATE_EMPTY_TYPED_UNIVERSE,
                 "the derived typed universe is NOT empty (an empty universe is not 'no "
                 "universe supplied' — it is a universe that covers nothing, it hashes to "
                 f"{C.EMPTY_TYPED_UNIVERSE_SHA256[:8]}…, and the audited CLI passed exactly "
                 "that)",
                 bool(typed), "0 rows"):
        return None
    if malformed or duplicate or unknown_ns:
        return None

    typed.sort(key=lambda r: (r["target_id_namespace"], r["target_id"]))
    return typed


def typed_universe_sha256(typed: list[dict[str, str]]) -> str:
    """The identity PAIR, canonically sorted, then content-hashed. Restated, not imported."""
    return canon.chash(sorted(
        ({"target_id": t["target_id"],
          "target_id_namespace": t["target_id_namespace"]} for t in typed),
        key=lambda r: (r["target_id_namespace"], r["target_id"])))


# --------------------------------------------------------------------------- #
# 2. The eligibility REPLAY. Never the store's own flag.
# --------------------------------------------------------------------------- #
def replay_eligibility(record: dict[str, Any]) -> tuple[bool, str]:
    """Re-derive (eligible, reason) from the record's OWN predicate inputs."""
    components = record.get("components") or []
    if record.get("target_type") != SINGLE_PROTEIN:
        return False, "target_type_is_not_single_protein"
    if record.get("tax_id") != HUMAN_TAX_ID:
        return False, "reject_nonhuman_target_taxon"
    if record.get("species_group_flag") != SPECIES_GROUP_NONE:
        return False, "target_is_a_species_group"
    if record.get("n_components") != 1 or len(components) != 1:
        return False, "target_is_not_exactly_one_component"
    component = components[0]
    if component.get("component_type") != COMPONENT_PROTEIN:
        return False, "component_is_not_a_protein"
    if component.get("tax_id") != HUMAN_TAX_ID:
        return False, "reject_nonhuman_component_taxon"
    if component.get("homologue") != HOMOLOGUE_EXACT:
        return False, "component_is_a_homologue"
    if not component.get("accession"):
        return False, "component_names_no_accession"
    return True, "eligible_human_single_protein"


def check_eligibility(rep: Report, evidence: Any,
                      referenced: set[str]) -> dict[str, bool]:
    """Replay every verdict, and prove the evidence COVERS every target the store references.

    Returns the replayed single-protein map — the producer's claim is never read.
    """
    records = (evidence or {}).get("records") or []
    replayed: dict[str, bool] = {}
    mismatched: list[str] = []
    for record in records:
        eligible, reason = replay_eligibility(record)
        tid = str(record.get("target_chembl_id"))
        replayed[tid] = eligible
        if eligible != bool(record.get("eligible")):
            mismatched.append(f"{tid}: store says eligible={record.get('eligible')!r}, "
                              f"replay says {eligible!r} ({reason})")

    _gate(rep, C.GATE_ELIGIBILITY_REPLAY,
          "every target-eligibility verdict REPLAYS from its own predicate inputs — target "
          "type, taxon, species group, component type, component taxon, homologue and "
          "component cardinality (a resealed artifact hashes perfectly and still contradicts "
          "itself here; the only way to hide a mutated taxon is to flip the verdict too, "
          "which is the honest outcome)",
          not mismatched and bool(records),
          "; ".join(mismatched[:3]) or f"{len(records)} record(s)")

    uncovered = sorted(referenced - set(replayed))
    _gate(rep, C.GATE_ELIGIBILITY_NOT_COVERED,
          "every ChEMBL target the store's rows REFERENCE has an eligibility record — "
          "rejections included. A producer that drops its rejections looks identical to one "
          "that had none, and 'no rejections' from a store holding non-human targets is a "
          "missing gate, not a clean bill of health",
          not uncovered, f"{len(uncovered)} uncovered: {uncovered[:3]}")
    _gate(rep, C.GATE_ELIGIBILITY_REPLAY,
          "the evidence covers REJECTED mappings too",
          any(not v for v in replayed.values()),
          f"{sum(1 for v in replayed.values() if not v)} rejected")
    return replayed


# --------------------------------------------------------------------------- #
# 3. The store's three semantics, and the source assertions it holds.
# --------------------------------------------------------------------------- #
def check_semantics(rep: Report, rows: list[dict[str, Any]],
                    single_protein: dict[str, bool]) -> bool:
    """Container-agnostic and depth-agnostic: a consumer that flattens reads the ASSERTION."""
    ambiguous, variant_in_general, undenied, cached, unnamed, not_single = [], [], [], [], [], []
    for row in rows:
        tid = row.get("target_id")
        if row.get("disposition") == C.DISP_AMBIGUOUS_IDENTITY and row.get("drugs"):
            ambiguous.append(f"{tid} ({len(row['drugs'])} rankable)")
        for a in (row.get("drugs") or []):
            if a.get("variant_id") not in (None, ""):
                variant_in_general.append(f"{tid}/mec {a.get('source_row_id')}")
            if not single_protein.get(str(a.get("target_chembl_id"))):
                not_single.append(f"{tid}/{a.get('target_chembl_id')}")
        for a in (row.get("variant_specific_assertions") or []):
            if a.get("general_gene_rankable") is not False:
                undenied.append(f"{tid}/mec {a.get('source_row_id')}")
        for _lane, container in C.LANE_CONTAINERS:
            for a in (row.get(container) or []):
                forbidden = C.FORBIDDEN_ASSERTION_KEYS & set(a.keys())
                if forbidden:
                    cached.append(f"{tid}/mec {a.get('source_row_id')}: {sorted(forbidden)}")
                if [f for f in C.REQUIRED_ASSERTION_FIELDS if a.get(f) in (None, "")]:
                    unnamed.append(f"{tid}/mec {a.get('source_row_id')}")

    ok = _gate(rep, C.GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
               "no ambiguous-identity row carries rankable drug evidence, at ANY depth and in "
               "ANY container (one mechanism would otherwise become independent-looking "
               "evidence for every gene its shared accession maps to)",
               not ambiguous, str(ambiguous[:3]))
    ok = _gate(rep, C.GATE_VARIANT_IN_GENERAL_LANE,
               "no variant assertion reaches the GENERAL gene lane, and every variant "
               "assertion is EXPLICITLY general_gene_rankable=false. A V617F inhibitor is "
               "evidence about V617F, not wild-type JAK2 — and variant_id "
               f"{C.VARIANT_UNDEFINED_MUTATION} is ChEMBL's UNDEFINED MUTATION sentinel, not "
               "'no variant'. An absent field is not a denial: omission is exactly how 29 "
               "variant assertions reached general-gene ranking",
               not variant_in_general and not undenied,
               str((variant_in_general + undenied)[:3])) and ok
    ok = _gate(rep, C.GATE_CACHE_CARRIES_A_DIRECTION_VERDICT,
               "the store carries no cached Stage-3 direction or ranking verdict (a cached "
               "direction is a verdict nobody can re-derive, and it outlives the vocabulary "
               "that produced it — action_type_source travels VERBATIM and is re-translated "
               "at build time)",
               not cached, str(cached[:3])) and ok
    ok = _gate(rep, C.GATE_MISSING_SOURCE_IDENTITY,
               "every source assertion names its source row and its ChEMBL identities (an "
               "edge that cannot name its source row cannot be checked against the source, and "
               "ChEMBL's REQUIRED attribution is to preserve those ids)",
               not unnamed, str(unnamed[:3])) and ok
    ok = _gate(rep, C.GATE_NOT_SINGLE_PROTEIN_IN_GENERAL_LANE,
               "every GENERAL-gene assertion's target REPLAYS as an eligible human single "
               "protein. The producer classifies direction against that lane without "
               "re-deriving it, so a complex, a family or a non-human target reaching it would "
               "have a direction computed against an entity that is not the gene the screen "
               "perturbed",
               not not_single, str(not_single[:3])) and ok
    return ok


def release_binding(manifest: dict[str, Any], *, store_id: str,
                    universe_sha: str) -> dict[str, Any]:
    """The releases, licences and source hashes — read from the STORE'S OWN manifest.

    Never a constant in this file: a release hardcoded in a verifier is a claim about data the
    verifier has never seen.
    """
    releases = manifest.get("releases") or {}
    chembl = releases.get("chembl") or {}
    uniprot = releases.get("uniprot") or {}
    return {
        "store_id": store_id,
        "typed_universe_sha256": universe_sha,
        "chembl_release": chembl.get("source_release"),
        "chembl_source_sha256": chembl.get("source_sha256"),
        "chembl_doi": chembl.get("doi"),
        "chembl_license": chembl.get("license"),
        "chembl_required_attribution": chembl.get("attribution"),
        "uniprot_release": uniprot.get("source_release"),
        "uniprot_source_sha256": uniprot.get("source_sha256"),
        "uniprot_license": uniprot.get("license"),
        "uniprot_attribution": uniprot.get("attribution"),
    }


def open_store(rep: Report, *, store_dir: str,
               artifact_class: str) -> Optional[dict[str, Any]]:
    """Re-open the admitted universe store FROM DISK and re-prove it against its own bytes."""
    manifest = _load(rep, os.path.join(str(store_dir or ""), C.STORE_MANIFEST_NAME),
                     "universe store manifest", C.GATE_STORE_NOT_FOUND)
    if manifest is None:
        return None

    artifacts: dict[str, Any] = {}
    for name in C.STORE_JSON_ARTIFACTS:
        got = _load(rep, os.path.join(store_dir, name), f"store artifact {name}",
                    C.GATE_STORE_MISSING_ARTIFACT)
        if got is None:
            return None
        artifacts[name] = got

    for name in C.STORE_TEXT_ARTIFACTS:
        path = os.path.join(store_dir, name)
        if not _gate(rep, C.GATE_LICENSE_BINDING_MISSING,
                     f"the store ships {name} (ChEMBL is CC BY-SA 3.0 and its attribution is "
                     "REQUIRED: a derived layer travelling without its licence is a licence "
                     "breach, not a missing nicety)",
                     os.path.isfile(path), f"absent: {path!r}"):
            return None

    extraction = manifest.get("extraction") or {}
    drifted = [f"{name}: on disk {canon.chash(artifacts[name])[:12]}… vs pinned "
               f"{str(extraction.get(pin))[:12]}…"
               for name, pin in C.STORE_ARTIFACT_PINS.items()
               if canon.chash(artifacts[name]) != extraction.get(pin)]
    if not _gate(rep, C.GATE_STORE_ARTIFACT_HASH_DRIFT,
                 "every store artifact ON DISK still hashes to the manifest's pin (the "
                 "manifest is untouched, so a drift here is the artifact that moved — a pin "
                 "nobody checks against the bytes is not a pin)",
                 not drifted, "; ".join(drifted[:3])):
        return None

    rows = artifacts[C.STORE_ROWS_NAME]
    typed = derive_typed_universe(rep, rows)
    if typed is None:
        return None
    derived_sha = typed_universe_sha256(typed)

    _gate(rep, C.GATE_TYPED_UNIVERSE_HASH_MISMATCH,
          "the universe re-derived from the store's rows IS the universe the store binds (the "
          "store was extracted FOR a particular universe; serving a run a store built against "
          "a different one answers questions about targets it never covered, and calls the "
          "silence coverage)",
          derived_sha == (manifest.get("universe_binding") or {}).get(
              "universe_targets_sha256"),
          f"derived {derived_sha[:16]}…")

    if artifact_class == C.ANALYSIS:
        _gate(rep, C.GATE_NOT_THE_ADMITTED_UNIVERSE,
              f"the analysis path stands on the ADMITTED typed universe "
              f"({C.ADMITTED_TYPED_UNIVERSE_SHA256[:16]}…, "
              f"{C.N_ADMITTED_UNIVERSE_TARGETS:,} targets). A store can be perfectly "
              "consistent with a universe nobody admitted — that is what a forgery is",
              derived_sha == C.ADMITTED_TYPED_UNIVERSE_SHA256,
              f"derived {derived_sha[:16]}… over {len(typed)} target(s)")
        _gate(rep, C.GATE_NOT_THE_ADMITTED_STORE,
              f"the analysis path stands on the ADMITTED store_id ({C.ADMITTED_STORE_ID[:16]}…)",
              str(manifest.get("store_id") or "") == C.ADMITTED_STORE_ID,
              f"got {str(manifest.get('store_id'))[:16]}…")

    referenced = {str(a.get("target_chembl_id"))
                  for r in rows
                  for _lane, container in C.LANE_CONTAINERS
                  for a in (r.get(container) or [])}
    referenced |= {str(t) for r in rows
                   for t in ((r.get("identity") or {}).get("targets") or [])}
    single_protein = check_eligibility(rep, artifacts[C.STORE_ELIGIBILITY_NAME], referenced)
    if not check_semantics(rep, rows, single_protein):
        return None

    store_id = str(manifest.get("store_id") or "")
    return {
        "store_dir": store_dir, "manifest": manifest, "rows": rows,
        "store_id": store_id,
        "eligibility": artifacts[C.STORE_ELIGIBILITY_NAME],
        "provenance": artifacts[C.STORE_PROVENANCE_NAME],
        "typed_universe": typed, "typed_universe_sha256": derived_sha,
        "single_protein": single_protein,
        "release_binding": release_binding(manifest, store_id=store_id,
                                           universe_sha=derived_sha),
        "index": {(str(r["target_id_namespace"]), str(r["target_id"])): r for r in rows},
    }


# --------------------------------------------------------------------------- #
# 4. The source assertions the store holds, rebuilt from the rows they live in.
# --------------------------------------------------------------------------- #
def assertions_for(store: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    """Every source assertion on one row — general, variant and ambiguous alike, each typed
    by its lane and carrying its own rankability disposition. Nothing is dropped."""
    binding = store["release_binding"]
    out: list[dict[str, Any]] = []
    for lane, container in C.LANE_CONTAINERS:
        for a in (row.get(container) or []):
            edge = {
                "target_id": row["target_id"],
                "target_id_namespace": row["target_id_namespace"],
                "target_disposition": row["disposition"],
                "lane": lane,
                "general_gene_rankable": (lane == C.LANE_GENERAL
                                          and a.get("general_gene_rankable") is True),
                "molecule_chembl_id": a.get("molecule_chembl_id"),
                "target_chembl_id": a.get("target_chembl_id"),
                "pref_name": a.get("pref_name"),
                "molecule_type": a.get("molecule_type"),
                "inchikey": a.get("inchikey"),
                "source_row_id": a.get("source_row_id"),
                "action_type_source": a.get("action_type_source"),
                "mechanism_of_action": a.get("mechanism_of_action"),
                "mechanism_refs": list(a.get("mechanism_refs") or []),
                "selectivity_comment": a.get("selectivity_comment"),
                "direct_interaction": a.get("direct_interaction"),
                "molecular_mechanism": a.get("molecular_mechanism"),
                "disease_efficacy": a.get("disease_efficacy"),
                "max_phase_source": a.get("max_phase_source"),
                "max_phase_canonical": a.get("max_phase_canonical"),
                "max_phase_is_context_only": True,
                "variant_id": a.get("variant_id"),
                "variant_specific": a.get("variant_specific"),
                "variant_disposition": a.get("variant_disposition"),
                "ambiguity_disposition": a.get("ambiguity_disposition"),
                "cross_ref_provenance": dict(a.get("cross_ref_provenance") or {}),
                "release_binding": dict(binding),
                "direction_decided_in_cache": False,
                "edge_policy_version": EDGE_POLICY_VERSION,
            }
            edge["edge_id"] = canon.short(edge)
            out.append(edge)
    return out


def moiety_id(assertion: dict[str, Any]) -> str:
    """Structure first (InChIKey), registry id second, then a NAMED unresolved identity.

    This IS the candidate_id, and it is derived — never assigned.
    """
    if assertion.get("inchikey"):
        return f"AM:INCHIKEY:{assertion['inchikey']}"
    if assertion.get("molecule_chembl_id"):
        return f"AM:CHEMBL:{assertion['molecule_chembl_id']}"
    return "AM:UNRESOLVED:" + canon.short({"mec_id": assertion.get("source_row_id")})


def identity_status(assertion: dict[str, Any]) -> str:
    if assertion.get("inchikey"):
        return "resolved"
    if assertion.get("molecule_chembl_id"):
        return "chembl_molecule_id_only"
    return "unresolved"


def source_locator(assertion: dict[str, Any], binding: dict[str, Any]) -> str:
    """``chembl:<release>:drug_mechanism/<mec_id>`` — the exact row, in the exact release."""
    return (f"{C.SOURCE_SCHEME_CHEMBL}:{binding.get('chembl_release')}:"
            f"{C.SOURCE_TABLE_DRUG_MECHANISM}/{assertion.get('source_row_id')}")


def source_record(assertion: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    """One VERBATIM source assertion: addressable, release-bound, licence-bound."""
    binding = store["release_binding"]
    mid = moiety_id(assertion)
    row = {c: assertion.get(c) for c in T.SOURCE_RECORD_COLUMNS}
    row.update({
        "source_record_id": assertion.get("edge_id"),
        "mec_id": assertion.get("source_row_id"),
        "candidate_id": mid,
        "active_moiety_id": mid,
        "identity_status": identity_status(assertion),
        "assertion_lane": assertion.get("lane"),
        "inchikey_status": T.STATED if assertion.get("inchikey") else T.NOT_STATED,
        "max_phase_status": (T.STATED if assertion.get("max_phase_source") not in (None, "")
                             else T.NOT_STATED),
        "source_locator": source_locator(assertion, binding),
        "source_scheme": C.SOURCE_SCHEME_CHEMBL,
        "source_release": binding["chembl_release"],
        "source_sha256": binding["chembl_source_sha256"],
        "source_license": binding["chembl_license"],
        "source_required_attribution": binding["chembl_required_attribution"],
        "chembl_release": binding["chembl_release"],
        "chembl_source_sha256": binding["chembl_source_sha256"],
        "chembl_license": binding["chembl_license"],
        "chembl_required_attribution": binding["chembl_required_attribution"],
        "uniprot_release": binding["uniprot_release"],
        "uniprot_source_sha256": binding["uniprot_source_sha256"],
        "uniprot_license": binding["uniprot_license"],
        "universe_store_id": store["store_id"],
        "typed_universe_sha256": store["typed_universe_sha256"],
    })
    return row
