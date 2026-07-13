"""Read the ADMITTED universe store's ROWS, and turn them into typed target/drug edges.

This module exists because of audit blocker **B6**: the store is on disk, every hash in it
verifies — and its **2,227 general drug assertions never reach Stage-3 candidate
generation**. The v2 CLI hands ``admitted_universe.bind`` an **EMPTY** typed universe, whose
hash is::

    []                     -> 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945
    the store's universe    -> 5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af

An empty list is not "no universe supplied"; it is a **different universe** — one covering
nothing — and the only reason it does not already produce silent zero-coverage answers is
that the store's binding gate refuses it. So the fix is not to relax the gate: it is to
DERIVE the real 11,526-row typed universe from the store's own rows and prove it hashes to
what the store bound. Copying the claimed hash across would prove nothing at all.

THE JOIN IS TYPED, OR IT IS MIS-ATTRIBUTION
-------------------------------------------
Drug edges are joined to targets by **exact typed identity** — ``(target_id,
target_id_namespace)`` — and never by gene symbol. A symbol join looks identical on the day
it is written and silently re-attributes every edge the first time a gene is renamed or a
symbol is reused across namespaces. A query that cannot be answered by an exact typed match
REFUSES; it never degrades to a name match.

WHAT THE CACHE MAY NOT CARRY
----------------------------
``action_type`` is preserved **verbatim** (``INHIBITOR``, ``AGONIST``, …). The cache carries
no Stage-3 compatibility verdict, no direction, no intervention effect: direction is
recomputed at build time from the frozen Stage-3 vocabulary against the arm's own desired
change. A cached verdict is a verdict nobody can re-derive, and it survives the vocabulary
that produced it.

THREE SEMANTICS THAT WERE PAID FOR ONCE ALREADY
-----------------------------------------------
1. **ambiguous_identity rows carry no rankable drug evidence** (86 rows). The row says
   ``drugs: []`` — but six source assertions are preserved one level down, under
   ``ambiguous_source_assertions``, and a consumer that flattens reads the ASSERTION, not
   the row. So non-rankability is enforced **recursively, at any depth, in any container**.
2. **All 29 variant assertions are excluded from general-gene ranking** — including the 10
   whose ``variant_id`` is ``-1``, ChEMBL's UNDEFINED MUTATION sentinel. ``-1`` is *not*
   null: it means "there is a mutation and we do not know which one", and reading it as
   wild-type is the most dangerous interpretation available.
3. **Symbol-only targets are RETAINED** with an ``unsupported_namespace`` disposition. They
   were perturbed; the acquisition ROUTE cannot reach them. That is never an absence of
   drug evidence, and nothing may read it as one.

And ``max_phase`` is **context only**. It is preserved exactly (source + canonical) and may
never gate or rank: :func:`order_edges` refuses it as a sort key by name.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from . import admitted_universe as au
from . import universe_verify as uv
from .hashing import content_hash, short_id

UNIVERSE_ROWS_POLICY_VERSION = "stage3-universe-rows-v1"

# --------------------------------------------------------------------------- #
# The store's on-disk layout. The PRODUCER's names are the contract, not ours.
# --------------------------------------------------------------------------- #
MANIFEST_NAME = au.MANIFEST_NAME
ROWS_NAME = "universe_store.rows.json"
ELIGIBILITY_NAME = "target_eligibility_evidence.json"
PROVENANCE_NAME = "source_provenance.public.json"
LICENSE_NAME = "CHEMBL_LICENSE"
ATTRIBUTION_NAME = "CHEMBL_REQUIRED_ATTRIBUTION"
JSON_ARTIFACTS = (ROWS_NAME, ELIGIBILITY_NAME, PROVENANCE_NAME)
LICENSE_ARTIFACTS = (LICENSE_NAME, ATTRIBUTION_NAME)

# Each JSON artifact and the manifest key that pins its bytes.
ARTIFACT_PINS = {
    ROWS_NAME: "store_rows_sha256",
    ELIGIBILITY_NAME: "eligibility_evidence_sha256",
    PROVENANCE_NAME: "public_source_provenance_sha256",
}

# --------------------------------------------------------------------------- #
# The audited universe, pinned. A pin computed from the thing it pins is not a pin.
# --------------------------------------------------------------------------- #
ADMITTED_TYPED_UNIVERSE_SHA256 = \
    "5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af"
# The hash of []. Named so it can be refused BY NAME rather than merely failing a compare.
EMPTY_TYPED_UNIVERSE_SHA256 = \
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"

NS_ENSEMBL_GENE = "ensembl_gene"
NS_SYMBOL = "symbol"
STORE_NAMESPACES = (NS_ENSEMBL_GENE, NS_SYMBOL)

DISP_DRUG_EVIDENCE = "drug_evidence"
DISP_NO_DRUG_EVIDENCE = "no_drug_evidence"
DISP_AMBIGUOUS_IDENTITY = "ambiguous_identity"
DISP_UNSUPPORTED_NAMESPACE = "unsupported_namespace"
DISPOSITIONS = (DISP_DRUG_EVIDENCE, DISP_NO_DRUG_EVIDENCE, DISP_AMBIGUOUS_IDENTITY,
                DISP_UNSUPPORTED_NAMESPACE)

# The three lanes an assertion may occupy. Exactly one is rankable.
LANE_GENERAL = "general_gene_rankable"
LANE_VARIANT = "variant_specific_non_rankable"
LANE_AMBIGUOUS = "ambiguous_identity_non_rankable"
RANKABLE_LANES = frozenset({LANE_GENERAL})

# Where each lane's assertions live in a store row.
LANE_CONTAINERS = ((LANE_GENERAL, "drugs"),
                   (LANE_VARIANT, "variant_specific_assertions"),
                   (LANE_AMBIGUOUS, "ambiguous_source_assertions"))

# ChEMBL's UNDEFINED MUTATION sentinel. NOT null. NOT wild-type.
VARIANT_UNDEFINED_MUTATION = -1

# max_phase is CONTEXT. Any of these as a sort/gate key is a refusal.
MAX_PHASE_KEYS = frozenset({"max_phase", "max_phase_source", "max_phase_canonical",
                            "max_phase_rank", "phase", "development_phase"})

# --------------------------------------------------------------------------- #
# Named gates. Every refusal below says which one fired.
# --------------------------------------------------------------------------- #
GATE_EMPTY_TYPED_UNIVERSE = "the_typed_universe_is_empty"
GATE_MALFORMED_STORE_ROW = "a_store_row_is_not_a_typed_universe_row"
GATE_DUPLICATE_TYPED_IDENTITY = "two_store_rows_claim_one_typed_identity"
GATE_TYPED_UNIVERSE_HASH_MISMATCH = "the_derived_typed_universe_is_not_the_one_the_store_binds"
GATE_NOT_THE_ADMITTED_UNIVERSE = "this_is_not_the_typed_universe_that_was_admitted"
GATE_STORE_NOT_FOUND = "the_universe_store_is_not_on_disk"
GATE_MISSING_ARTIFACT = "a_required_store_artifact_is_missing"
GATE_ARTIFACT_HASH_DRIFT = "a_store_artifact_no_longer_hashes_to_its_manifest_pin"
GATE_LICENSE_BINDING_MISSING = "the_store_does_not_carry_its_source_licence_and_attribution"
GATE_STORE_DID_NOT_VERIFY = "the_universe_store_did_not_verify_from_its_own_bytes"
GATE_UNTYPED_TARGET_QUERY = "a_drug_edge_query_must_carry_an_exact_typed_target_identity"
GATE_NAMESPACE_CROSS_JOIN = "a_target_id_may_not_be_joined_across_namespaces"
GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE = "the_target_is_not_in_the_admitted_typed_universe"
GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE = \
    "an_ambiguous_identity_row_carries_rankable_drug_evidence"
GATE_VARIANT_IN_GENERAL_LANE = "a_variant_assertion_reached_the_general_gene_lane"
GATE_CACHE_CARRIES_A_DIRECTION_VERDICT = \
    "the_cache_carries_a_stage3_direction_or_ranking_verdict"
GATE_MISSING_SOURCE_IDENTITY = "a_source_assertion_lost_its_source_identity"
GATE_MAX_PHASE_IS_NOT_A_RANK = "max_phase_is_context_and_may_never_gate_or_rank"


class UniverseRowsError(ValueError):
    """A named, fail-closed refusal. Never fall back to a fixture or a partial answer."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


class TypedUniverseError(UniverseRowsError):
    """The typed target universe could not be derived, or is not the admitted one."""


class AdmittedStoreError(UniverseRowsError):
    """The store on disk could not be loaded and proved."""


class DrugEdgeError(UniverseRowsError):
    """A drug edge could not be emitted without violating a store semantic."""


# --------------------------------------------------------------------------- #
# 1. The typed universe
# --------------------------------------------------------------------------- #
def derive_typed_universe(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The exact typed target universe, DERIVED from the store's own rows.

    One row per target: its id, the namespace it actually arrived in, and the store's
    disposition. Sorted in the store's canonical order — ``(namespace, target_id)`` — so
    two derivations of the same universe are byte-identical.

    The disposition rides along for the consumer's benefit and is deliberately NOT hashed
    (see :func:`typed_universe_sha256`): the binding is over target IDENTITY, which is what
    the store was extracted FOR. Hashing the store's own verdicts into the universe it was
    built against would make the binding circular.
    """
    typed: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        tid = row.get("target_id")
        ns = row.get("target_id_namespace")
        disp = row.get("disposition")
        if not tid or not ns or not disp:
            raise TypedUniverseError(
                GATE_MALFORMED_STORE_ROW,
                f"row {tid!r} carries namespace={ns!r} disposition={disp!r}; a universe row "
                "without a typed identity and a disposition cannot be joined or accounted "
                "for, and a target nobody accounted for is indistinguishable from a target "
                "nobody measured")
        if disp not in DISPOSITIONS:
            raise TypedUniverseError(
                GATE_MALFORMED_STORE_ROW,
                f"row {tid!r} carries an unknown disposition {disp!r}; known: {DISPOSITIONS}")
        key = (str(ns), str(tid))
        if key in seen:
            raise TypedUniverseError(
                GATE_DUPLICATE_TYPED_IDENTITY,
                f"{ns}:{tid} appears twice; a duplicated identity double-counts every drug "
                "edge that lands on it")
        seen.add(key)
        typed.append({"target_id": str(tid), "target_id_namespace": str(ns),
                      "disposition": str(disp)})

    if not typed:
        raise TypedUniverseError(
            GATE_EMPTY_TYPED_UNIVERSE,
            "an empty typed universe is not 'no universe supplied' — it is a universe that "
            f"covers nothing, and it hashes to {EMPTY_TYPED_UNIVERSE_SHA256[:8]}…, which can "
            "never be the universe the store was extracted for")

    typed.sort(key=lambda r: (r["target_id_namespace"], r["target_id"]))
    return typed


def typed_universe_sha256(typed_universe: Sequence[Mapping[str, str]]) -> str:
    """The store's OWN universe hash, recomputed — never copied from the manifest.

    Delegates to the store verifier's projection (identity pair, canonically sorted,
    content-hashed) so there is exactly one implementation of this hash in Stage 3: a second
    implementation is a second chance to disagree with the store about what it bound.
    """
    if not typed_universe:
        raise TypedUniverseError(
            GATE_EMPTY_TYPED_UNIVERSE,
            "refusing to hash an empty typed universe; see derive_typed_universe")
    return uv._typed_universe_hash(list(typed_universe))


def _check_universe_is_the_admitted_one(typed_universe: Sequence[Mapping[str, str]],
                                        manifest: Mapping[str, Any]) -> str:
    derived = typed_universe_sha256(typed_universe)
    bound = (manifest.get("universe_binding") or {}).get("universe_targets_sha256")
    if derived != bound:
        raise TypedUniverseError(
            GATE_TYPED_UNIVERSE_HASH_MISMATCH,
            f"the universe derived from these rows hashes to {derived[:16]}…, and the store "
            f"binds {str(bound)[:16]}…. The store was extracted FOR a particular universe; "
            "serving a run a store built against a different one answers questions about "
            "targets it never covered")
    if derived != ADMITTED_TYPED_UNIVERSE_SHA256:
        raise TypedUniverseError(
            GATE_NOT_THE_ADMITTED_UNIVERSE,
            f"this universe is {derived[:16]}… and the admitted universe is "
            f"{ADMITTED_TYPED_UNIVERSE_SHA256[:16]}…. A store may be internally consistent "
            "with a universe nobody admitted; re-admitting is a deliberate code change here")
    return derived


# --------------------------------------------------------------------------- #
# 2. The store, loaded and proved from its own bytes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AdmittedStore:
    """The store's real bytes, proved against the manifest's pins and the admitted pins."""

    store_dir: str
    manifest: dict[str, Any]
    rows: list[dict[str, Any]]
    eligibility_evidence: dict[str, Any]
    source_provenance: Any
    licences: dict[str, str]
    typed_universe: list[dict[str, str]]
    typed_universe_sha256: str
    store_binding: dict[str, Any]
    _index: dict[tuple[str, str], dict[str, Any]] = field(repr=False, default_factory=dict)

    @property
    def store_id(self) -> str:
        return str(self.manifest.get("store_id", ""))

    @property
    def releases(self) -> dict[str, Any]:
        return dict(self.manifest.get("releases") or {})

    def row_for(self, target_id: str, namespace: str) -> dict[str, Any] | None:
        return self._index.get((str(namespace), str(target_id)))


def _read_json(store_dir: str, name: str) -> Any:
    path = os.path.join(store_dir, name)
    if not os.path.exists(path):
        raise AdmittedStoreError(
            GATE_MISSING_ARTIFACT,
            f"{name} is not in the store. A deleted artifact must refuse BY NAME — an "
            "earlier producer shipped the provenance gate's REPORT rather than the gate and "
            "returned ok=True on a deleted file")
    with open(path) as fh:
        return json.load(fh)


def _read_text(store_dir: str, name: str) -> str:
    path = os.path.join(store_dir, name)
    if not os.path.exists(path):
        raise AdmittedStoreError(
            GATE_MISSING_ARTIFACT,
            f"{name} is not in the store. ChEMBL is CC BY-SA 3.0 and its attribution is "
            "REQUIRED: a derived layer that travels without its licence is a licence breach, "
            "not a missing nicety")
    with open(path) as fh:
        return fh.read()


def _check_licence_bindings(manifest: Mapping[str, Any], licences: Mapping[str, str]) -> None:
    rel = manifest.get("releases") or {}
    chembl = rel.get("chembl") or {}
    uniprot = rel.get("uniprot") or {}
    missing = [name for name, text in licences.items() if not text.strip()]
    if chembl.get("license") != "CC BY-SA 3.0":
        missing.append("releases.chembl.license != CC BY-SA 3.0")
    if uniprot.get("license") != "CC BY 4.0":
        missing.append("releases.uniprot.license != CC BY 4.0")
    if not chembl.get("attribution"):
        missing.append("releases.chembl.attribution")
    if not chembl.get("source_release"):
        missing.append("releases.chembl.source_release")
    if missing:
        raise AdmittedStoreError(
            GATE_LICENSE_BINDING_MISSING,
            f"the store does not carry its source licence/attribution bindings: {missing}")


def load_store(store_dir: str) -> AdmittedStore:
    """Open the store FROM DISK, re-hash every artifact against the manifest, then bind it.

    Order matters, and each step is a named refusal:

      1. the manifest is present;
      2. every artifact (rows, eligibility, provenance, licence, attribution) is present;
      3. every artifact's ACTUAL bytes still hash to the manifest's pin — a mutated file
         fails here even though the manifest is untouched;
      4. the typed universe derived from the rows is the universe the store bound, and is
         the universe that was ADMITTED;
      5. ``admitted_universe.bind`` re-runs the full store gate over the same bytes and pins
         the exact admitted ``store_id``. This module never admits anything.
    """
    manifest_path = os.path.join(store_dir, MANIFEST_NAME)
    if not os.path.isdir(store_dir) or not os.path.exists(manifest_path):
        raise AdmittedStoreError(
            GATE_STORE_NOT_FOUND,
            f"no {MANIFEST_NAME} under {store_dir!r}. There is no fixture fallback: a Stage-3 "
            "run without its admitted universe store does not quietly become a Stage-3 run "
            "with a synthetic one")
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    loaded = {name: _read_json(store_dir, name) for name in JSON_ARTIFACTS}
    licences = {name: _read_text(store_dir, name) for name in LICENSE_ARTIFACTS}

    extraction = manifest.get("extraction") or {}
    for name, pin_key in ARTIFACT_PINS.items():
        got = content_hash(loaded[name])
        want = extraction.get(pin_key)
        if got != want:
            raise AdmittedStoreError(
                GATE_ARTIFACT_HASH_DRIFT,
                f"{name} hashes to {got[:16]}… and the manifest pins {str(want)[:16]}…; the "
                "manifest is untouched, so this is the artifact that moved")

    _check_licence_bindings(manifest, licences)

    rows = loaded[ROWS_NAME]
    typed = derive_typed_universe(rows)
    universe_sha = _check_universe_is_the_admitted_one(typed, manifest)

    # The producer's full gate, over the ACTUAL bytes, plus the admitted store_id pin. It is
    # not this module's verdict — it is the one an independent verifier already issued.
    try:
        binding = au.bind(store_dir=store_dir, universe_targets=typed)
    except au.AdmittedUniverseError as exc:
        raise AdmittedStoreError(GATE_STORE_DID_NOT_VERIFY, str(exc)) from exc

    index = {(r["target_id_namespace"], r["target_id"]): r for r in rows}
    return AdmittedStore(
        store_dir=store_dir, manifest=manifest, rows=rows,
        eligibility_evidence=loaded[ELIGIBILITY_NAME],
        source_provenance=loaded[PROVENANCE_NAME], licences=licences,
        typed_universe=typed, typed_universe_sha256=universe_sha,
        store_binding=binding, _index=index)


# --------------------------------------------------------------------------- #
# 3. The adapter: typed target identity -> source drug assertions
# --------------------------------------------------------------------------- #
def _rankability_nodes(node: Any, path: str = "$"):
    """Every dict at ANY depth that makes a rankability claim. Container-agnostic.

    The row saying ``drugs: []`` is not enough. Six ambiguous assertions live one level down
    under ``ambiguous_source_assertions``, and a consumer that flattens reads the assertion,
    not the row — flattening being the obvious thing to do.
    """
    if isinstance(node, Mapping):
        if "general_gene_rankable" in node:
            yield path, node
        for key, value in node.items():
            yield from _rankability_nodes(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            yield from _rankability_nodes(item, f"{path}[{i}]")


def is_variant_assertion(assertion: Mapping[str, Any]) -> bool:
    """``variant_id`` of ANY value — including the ``-1`` sentinel — is a variant assertion."""
    return assertion.get("variant_id") not in (None, "")


def _gate_row(row: Mapping[str, Any]) -> None:
    """The three store semantics, enforced at EMIT time — not merely at load time."""
    tid = row.get("target_id")

    if row.get("disposition") == DISP_AMBIGUOUS_IDENTITY:
        if row.get("drugs"):
            raise DrugEdgeError(
                GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
                f"{tid} has a shared UniProt accession and still carries {len(row['drugs'])} "
                "rankable drug assertion(s): one mechanism would become independent-looking "
                "evidence for every gene the accession maps to")
        for node_path, node in _rankability_nodes(row):
            if node.get("general_gene_rankable") is not False:
                raise DrugEdgeError(
                    GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
                    f"{tid}{node_path[1:]} (mec {node.get('source_row_id')}) claims "
                    f"general_gene_rankable={node.get('general_gene_rankable')!r} inside an "
                    "ambiguous_identity row; non-rankability holds at ANY depth, in ANY "
                    "container, however honestly that container is named")

    for assertion in (row.get("drugs") or []):
        if is_variant_assertion(assertion):
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: mec {assertion.get('source_row_id')} carries "
                f"variant_id={assertion.get('variant_id')!r} in the GENERAL lane. A V617F "
                "inhibitor is evidence about V617F, not about wild-type JAK2 — and variant_id "
                f"{VARIANT_UNDEFINED_MUTATION} is ChEMBL's UNDEFINED MUTATION sentinel, which "
                "is emphatically not 'no variant'")
        if assertion.get("general_gene_rankable") is False:
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: mec {assertion.get('source_row_id')} sits in the general lane while "
                "declaring itself non-rankable; the lane and the flag must agree")

    for assertion in (row.get("variant_specific_assertions") or []):
        if assertion.get("general_gene_rankable") is not False:
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: variant mec {assertion.get('source_row_id')} must be EXPLICITLY "
                "general_gene_rankable=false. An absent field is not a denial, and that is "
                "how 29 variant assertions reached general-gene ranking")


def _release_binding(store: AdmittedStore) -> dict[str, Any]:
    rel = store.releases
    chembl = rel.get("chembl") or {}
    uniprot = rel.get("uniprot") or {}
    return {
        "store_id": store.store_id,
        "typed_universe_sha256": store.typed_universe_sha256,
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


def _edge(row: Mapping[str, Any], assertion: Mapping[str, Any], lane: str,
          binding: Mapping[str, Any]) -> dict[str, Any]:
    """One source assertion, preserved VERBATIM and typed by its lane.

    Nothing here is derived: no direction, no intervention effect, no phase gate, no score.
    ``action_type_source`` travels exactly as ChEMBL wrote it, and the frozen Stage-3
    direction vocabulary reads it at build time against the arm's own desired change.
    """
    forbidden = uv.FORBIDDEN_DRUG_KEYS & set(assertion.keys())
    if forbidden:
        raise DrugEdgeError(
            GATE_CACHE_CARRIES_A_DIRECTION_VERDICT,
            f"{row.get('target_id')}: mec {assertion.get('source_row_id')} carries "
            f"{sorted(forbidden)}. The cache may hold only source-faithful fields; a cached "
            "direction is a verdict nobody can re-derive and it outlives the vocabulary that "
            "produced it")
    required = ("source_row_id", "molecule_chembl_id", "target_chembl_id",
                "action_type_source")
    if any(assertion.get(k) in (None, "") for k in required):
        raise DrugEdgeError(
            GATE_MISSING_SOURCE_IDENTITY,
            f"{row.get('target_id')}: an assertion is missing its mec_id / molecule / target "
            "/ action_type; ChEMBL's REQUIRED.ATTRIBUTION is to preserve the ChEMBL IDs, and "
            "an edge that cannot name its source row cannot be checked against the source")

    rankable = (lane == LANE_GENERAL
                and assertion.get("general_gene_rankable") is True)
    edge = {
        "target_id": row["target_id"],
        "target_id_namespace": row["target_id_namespace"],
        "target_disposition": row["disposition"],
        "lane": lane,
        "general_gene_rankable": rankable,
        # ChEMBL identities, verbatim.
        "molecule_chembl_id": assertion.get("molecule_chembl_id"),
        "target_chembl_id": assertion.get("target_chembl_id"),
        "pref_name": assertion.get("pref_name"),
        "molecule_type": assertion.get("molecule_type"),
        "inchikey": assertion.get("inchikey"),
        "source_row_id": assertion.get("source_row_id"),          # = mec_id
        # The mechanism, verbatim. action_type carries NO Stage-3 verdict.
        "action_type_source": assertion.get("action_type_source"),
        "mechanism_of_action": assertion.get("mechanism_of_action"),
        "mechanism_refs": list(assertion.get("mechanism_refs") or []),
        "selectivity_comment": assertion.get("selectivity_comment"),
        "direct_interaction": assertion.get("direct_interaction"),
        "molecular_mechanism": assertion.get("molecular_mechanism"),
        "disease_efficacy": assertion.get("disease_efficacy"),
        # Context only. Never a gate, never a rank.
        "max_phase_source": assertion.get("max_phase_source"),
        "max_phase_canonical": assertion.get("max_phase_canonical"),
        "max_phase_is_context_only": True,
        # Rankability dispositions, verbatim (-1 is preserved, never nulled).
        "variant_id": assertion.get("variant_id"),
        "variant_specific": assertion.get("variant_specific"),
        "variant_disposition": assertion.get("variant_disposition"),
        "ambiguity_disposition": assertion.get("ambiguity_disposition"),
        "cross_ref_provenance": dict(assertion.get("cross_ref_provenance") or {}),
        # Provenance / licence bindings.
        "release_binding": dict(binding),
        # Stated, so nothing downstream has to assume it.
        "direction_decided_in_cache": False,
        "universe_rows_policy_version": UNIVERSE_ROWS_POLICY_VERSION,
    }
    edge["edge_id"] = short_id(edge)
    return edge


def _typed_key(query: Any) -> tuple[str, str]:
    """A query is a TYPED identity or it is refused. A bare id is a symbol join waiting."""
    if isinstance(query, Mapping):
        tid, ns = query.get("target_id"), query.get("target_id_namespace")
    elif isinstance(query, (tuple, list)) and len(query) == 2:
        tid, ns = query
    else:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"{query!r} is not a typed target identity. The store is joined ONLY by exact "
            "(target_id, target_id_namespace); joining by a bare id — a gene SYMBOL above all "
            "— looks identical the day it is written and silently re-attributes every edge "
            "the first time a gene is renamed or a symbol is reused")
    if not tid or not ns:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"target_id={tid!r} target_id_namespace={ns!r}: both halves of the typed identity "
            "are required; a namespace-less id is a name, and names are not identities")
    return str(ns), str(tid)


def drug_edges_for_targets(store: AdmittedStore,
                           target_ids: Iterable[Any]) -> list[dict[str, Any]]:
    """Every SOURCE drug assertion held for these targets, joined by exact typed identity.

    Every assertion is emitted — general, variant-specific and ambiguous-identity copies
    alike — each typed by its lane and carrying its own rankability disposition. Only
    ``lane == general_gene_rankable`` may rank a gene. The non-rankable lanes travel with the
    result deliberately: an assertion that is silently dropped is indistinguishable from a
    drug nobody found, and the store's whole point is that the two are different.

    A symbol-only target answers with ZERO edges and its ``unsupported_namespace``
    disposition — which means "this acquisition route cannot reach it", and never "no drug
    evidence exists".
    """
    binding = _release_binding(store)
    edges: list[dict[str, Any]] = []
    for query in target_ids:
        ns, tid = _typed_key(query)
        row = store.row_for(tid, ns)
        if row is None:
            other = [n for n in STORE_NAMESPACES if store.row_for(tid, n) is not None]
            if other:
                raise DrugEdgeError(
                    GATE_NAMESPACE_CROSS_JOIN,
                    f"{tid} exists in the admitted universe under namespace {other[0]!r}, and "
                    f"you asked under {ns!r}. A namespace-crossing match is silent "
                    "mis-attribution, so the join refuses rather than guessing")
            raise DrugEdgeError(
                GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE,
                f"{ns}:{tid} is not one of the {len(store.typed_universe)} targets in the "
                "admitted typed universe. The join is by exact typed identity and never "
                "degrades to a symbol match, so this refuses instead of answering about some "
                "other gene")
        _gate_row(row)
        for lane, container in LANE_CONTAINERS:
            for assertion in (row.get(container) or []):
                edges.append(_edge(row, assertion, lane, binding))

    edges.sort(key=lambda e: (e["target_id_namespace"], e["target_id"], e["lane"],
                              str(e["source_row_id"])))
    return edges


def rankable_edges(edges: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The general-gene lane, and nothing else. Variant and ambiguous copies never rank."""
    return [dict(e) for e in edges
            if e.get("lane") in RANKABLE_LANES and e.get("general_gene_rankable") is True]


def order_edges(edges: Iterable[Mapping[str, Any]], *,
                by: Sequence[str]) -> list[dict[str, Any]]:
    """Deterministic ordering — and the ONE place max_phase is refused as a key.

    ``max_phase`` is regulatory CONTEXT about a molecule, not evidence about a target. An
    approved drug for another disease is not better evidence than a phase-1 drug for this
    one; sorting by it turns a context field into a silent objective.
    """
    bad = [k for k in by if k in MAX_PHASE_KEYS]
    if bad:
        raise DrugEdgeError(
            GATE_MAX_PHASE_IS_NOT_A_RANK,
            f"{bad} cannot order drug edges. max_phase is CONTEXT: it is preserved exactly "
            "(source + canonical) and may never gate or rank — an approved drug for another "
            "disease is not stronger evidence about this target than a phase-1 drug")
    rows = [dict(e) for e in edges]
    rows.sort(key=lambda e: tuple(content_hash(e.get(k)) for k in by))
    return rows
