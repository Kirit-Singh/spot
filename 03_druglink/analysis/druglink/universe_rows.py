"""Read the ADMITTED universe store's ROWS, and join them to targets by TYPED identity.

This module exists because of audit blocker **B6**: the store is on disk, every hash in it
verifies — and its **2,227 general drug assertions never reach Stage-3 candidate
generation**, because the v2 CLI hands ``admitted_universe.bind`` an **EMPTY** typed
universe::

    []                    -> 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945
    the store's universe  -> 5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af

An empty list is not "no universe supplied". It is a **different universe** — one that covers
nothing — and the only reason it does not already produce silent zero-coverage answers is that
the store's binding gate refuses it. The fix is therefore not to relax that gate: it is to
DERIVE the real 11,526-row typed universe from the store's own rows and prove it hashes to
what the store bound. Copying the claimed hash across would prove exactly nothing.

THE JOIN IS TYPED, OR IT IS MIS-ATTRIBUTION
-------------------------------------------
Edges are joined to targets by **exact typed identity** — ``(target_id,
target_id_namespace)`` — and never by gene symbol. A symbol join looks identical on the day it
is written and silently re-attributes every edge the first time a gene is renamed or a symbol
is reused across namespaces. A query that cannot be answered by an exact typed match REFUSES;
it never degrades to a name match, and it never crosses a namespace to find something.

WHAT A SYMBOL-ONLY TARGET MEANS
-------------------------------
Four released targets (MTRNR2L1/L4/L8, OCLM) carry a gene symbol and no Ensembl id. Stage-3's
acquisition route resolves targets by UniProt Ensembl cross-reference, so the ROUTE cannot
reach them. They are **RETAINED** with an ``unsupported_namespace`` disposition, answer with
zero edges, and that is never an absence of drug evidence — an absence nobody recorded is
indistinguishable from a target nobody measured.

The assertion-level semantics (ambiguous identity, variant containment, the ``-1`` UNDEFINED
MUTATION sentinel, max_phase-is-context) live one layer down in
:mod:`druglink.universe_edges`, and are enforced at EMIT time.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from . import admitted_universe as au
from . import universe_verify as uv
from .hashing import content_hash
from .universe_edges import (
    DISP_AMBIGUOUS_IDENTITY,
    GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
    GATE_CACHE_CARRIES_A_DIRECTION_VERDICT,
    GATE_MAX_PHASE_IS_NOT_A_RANK,
    GATE_MISSING_SOURCE_IDENTITY,
    GATE_VARIANT_IN_GENERAL_LANE,
    LANE_AMBIGUOUS,
    LANE_CONTAINERS,
    LANE_GENERAL,
    LANE_VARIANT,
    MAX_PHASE_KEYS,
    RANKABLE_LANES,
    VARIANT_UNDEFINED_MUTATION,
    DrugEdgeError,
    UniverseRowsError,
    build_edge,
    gate_row,
    is_variant_assertion,
    order_edges,
    rankable_edges,
)

UNIVERSE_ROWS_POLICY_VERSION = "stage3-universe-rows-v1"

# The one front door: the edge-layer names are re-exported so a consumer binds ONE module.
__all__ = [
    "UNIVERSE_ROWS_POLICY_VERSION", "ADMITTED_TYPED_UNIVERSE_SHA256",
    "EMPTY_TYPED_UNIVERSE_SHA256", "MANIFEST_NAME", "ROWS_NAME", "ELIGIBILITY_NAME",
    "PROVENANCE_NAME", "LICENSE_NAME", "ATTRIBUTION_NAME", "JSON_ARTIFACTS",
    "LICENSE_ARTIFACTS", "ARTIFACT_PINS", "NS_ENSEMBL_GENE", "NS_SYMBOL", "STORE_NAMESPACES",
    "DISP_DRUG_EVIDENCE", "DISP_NO_DRUG_EVIDENCE", "DISP_AMBIGUOUS_IDENTITY",
    "DISP_UNSUPPORTED_NAMESPACE", "DISPOSITIONS", "LANE_GENERAL", "LANE_VARIANT",
    "LANE_AMBIGUOUS", "LANE_CONTAINERS", "RANKABLE_LANES", "MAX_PHASE_KEYS",
    "VARIANT_UNDEFINED_MUTATION",
    "GATE_EMPTY_TYPED_UNIVERSE", "GATE_MALFORMED_STORE_ROW", "GATE_DUPLICATE_TYPED_IDENTITY",
    "GATE_TYPED_UNIVERSE_HASH_MISMATCH", "GATE_NOT_THE_ADMITTED_UNIVERSE",
    "GATE_STORE_NOT_FOUND", "GATE_MISSING_ARTIFACT", "GATE_ARTIFACT_HASH_DRIFT",
    "GATE_LICENSE_BINDING_MISSING", "GATE_STORE_DID_NOT_VERIFY",
    "GATE_UNTYPED_TARGET_QUERY", "GATE_NAMESPACE_CROSS_JOIN",
    "GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE", "GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE",
    "GATE_VARIANT_IN_GENERAL_LANE", "GATE_CACHE_CARRIES_A_DIRECTION_VERDICT",
    "GATE_MISSING_SOURCE_IDENTITY", "GATE_MAX_PHASE_IS_NOT_A_RANK",
    "UniverseRowsError", "TypedUniverseError", "AdmittedStoreError", "DrugEdgeError",
    "AdmittedStore", "derive_typed_universe", "typed_universe_sha256", "load_store",
    "drug_edges_for_targets", "rankable_edges", "order_edges", "is_variant_assertion",
]

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

# Each JSON artifact, and the manifest key that pins its bytes.
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
# The hash of []. Named so the B6 defect can be refused BY NAME, not merely fail a compare.
EMPTY_TYPED_UNIVERSE_SHA256 = \
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"

NS_ENSEMBL_GENE = "ensembl_gene"
NS_SYMBOL = "symbol"
STORE_NAMESPACES = (NS_ENSEMBL_GENE, NS_SYMBOL)

DISP_DRUG_EVIDENCE = "drug_evidence"
DISP_NO_DRUG_EVIDENCE = "no_drug_evidence"
DISP_UNSUPPORTED_NAMESPACE = "unsupported_namespace"
DISPOSITIONS = (DISP_DRUG_EVIDENCE, DISP_NO_DRUG_EVIDENCE, DISP_AMBIGUOUS_IDENTITY,
                DISP_UNSUPPORTED_NAMESPACE)

GATE_EMPTY_TYPED_UNIVERSE = "the_typed_universe_is_empty"
GATE_MALFORMED_STORE_ROW = "a_store_row_is_not_a_typed_universe_row"
GATE_DUPLICATE_TYPED_IDENTITY = "two_store_rows_claim_one_typed_identity"
GATE_TYPED_UNIVERSE_HASH_MISMATCH = \
    "the_derived_typed_universe_is_not_the_one_the_store_binds"
GATE_NOT_THE_ADMITTED_UNIVERSE = "this_is_not_the_typed_universe_that_was_admitted"
GATE_STORE_NOT_FOUND = "the_universe_store_is_not_on_disk"
GATE_MISSING_ARTIFACT = "a_required_store_artifact_is_missing"
GATE_ARTIFACT_HASH_DRIFT = "a_store_artifact_no_longer_hashes_to_its_manifest_pin"
GATE_LICENSE_BINDING_MISSING = "the_store_does_not_carry_its_source_licence_and_attribution"
GATE_STORE_DID_NOT_VERIFY = "the_universe_store_did_not_verify_from_its_own_bytes"
GATE_UNTYPED_TARGET_QUERY = "a_drug_edge_query_must_carry_an_exact_typed_target_identity"
GATE_NAMESPACE_CROSS_JOIN = "a_target_id_may_not_be_joined_across_namespaces"
GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE = "the_target_is_not_in_the_admitted_typed_universe"


class TypedUniverseError(UniverseRowsError):
    """The typed target universe could not be derived, or is not the admitted one."""


class AdmittedStoreError(UniverseRowsError):
    """The store on disk could not be loaded and proved."""


# --------------------------------------------------------------------------- #
# 1. The typed universe
# --------------------------------------------------------------------------- #
def derive_typed_universe(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The exact typed target universe, DERIVED from the store's own rows.

    One row per target: its id, the namespace it actually arrived in, and the store's
    disposition. Sorted in the store's canonical order — ``(namespace, target_id)`` — so two
    derivations of one universe are byte-identical.

    The disposition rides along for the consumer's benefit and is deliberately NOT hashed (see
    :func:`typed_universe_sha256`): the binding is over target IDENTITY, which is what the
    store was extracted FOR. Folding the store's own verdicts into the universe it was built
    against would make the binding circular.
    """
    typed: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        tid, ns, disp = (row.get("target_id"), row.get("target_id_namespace"),
                         row.get("disposition"))
        if not tid or not ns or not disp:
            raise TypedUniverseError(
                GATE_MALFORMED_STORE_ROW,
                f"row {tid!r} carries namespace={ns!r} disposition={disp!r}. A universe row "
                "without a typed identity and a disposition can be neither joined nor "
                "accounted for, and a target nobody accounted for is indistinguishable from a "
                "target nobody measured")
        if disp not in DISPOSITIONS:
            raise TypedUniverseError(
                GATE_MALFORMED_STORE_ROW,
                f"row {tid!r} carries an unknown disposition {disp!r}; known: {DISPOSITIONS}")
        key = (str(ns), str(tid))
        if key in seen:
            raise TypedUniverseError(
                GATE_DUPLICATE_TYPED_IDENTITY,
                f"{ns}:{tid} appears twice. A duplicated identity double-counts every drug "
                "edge that lands on it")
        seen.add(key)
        typed.append({"target_id": str(tid), "target_id_namespace": str(ns),
                      "disposition": str(disp)})

    if not typed:
        raise TypedUniverseError(
            GATE_EMPTY_TYPED_UNIVERSE,
            "an empty typed universe is not 'no universe supplied' — it is a universe that "
            f"covers nothing. It hashes to {EMPTY_TYPED_UNIVERSE_SHA256[:8]}…, which can never "
            "be the universe the store was extracted for")

    typed.sort(key=lambda r: (r["target_id_namespace"], r["target_id"]))
    return typed


def typed_universe_sha256(typed_universe: Iterable[Mapping[str, str]]) -> str:
    """The store's OWN universe hash, recomputed — never copied out of the manifest.

    Delegates to the store verifier's projection (the identity pair, canonically sorted, then
    content-hashed) so Stage 3 holds exactly ONE implementation of this hash: a second
    implementation is a second chance to disagree with the store about what it bound.
    """
    typed = list(typed_universe)
    if not typed:
        raise TypedUniverseError(
            GATE_EMPTY_TYPED_UNIVERSE,
            "refusing to hash an empty typed universe; see derive_typed_universe")
    return uv._typed_universe_hash(typed)


def _check_universe_is_the_admitted_one(typed_universe: Iterable[Mapping[str, str]],
                                        manifest: Mapping[str, Any]) -> str:
    typed = list(typed_universe)
    derived = typed_universe_sha256(typed)
    bound = (manifest.get("universe_binding") or {}).get("universe_targets_sha256")
    if derived != bound:
        raise TypedUniverseError(
            GATE_TYPED_UNIVERSE_HASH_MISMATCH,
            f"the universe derived from these rows hashes to {derived[:16]}…, and the store "
            f"binds {str(bound)[:16]}…. The store was extracted FOR a particular universe; "
            "serving a run a store built against a different one answers questions about "
            "targets it never covered, and calls the silence coverage")
    if derived != ADMITTED_TYPED_UNIVERSE_SHA256:
        raise TypedUniverseError(
            GATE_NOT_THE_ADMITTED_UNIVERSE,
            f"this universe is {derived[:16]}… and the admitted universe is "
            f"{ADMITTED_TYPED_UNIVERSE_SHA256[:16]}…. A store can be perfectly consistent with "
            "a universe nobody admitted — that is what a forgery is — so re-admitting is a "
            "deliberate code change here, not a command-line flag")
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
        """The one row with EXACTLY this typed identity, or None. Never a symbol match."""
        return self._index.get((str(namespace), str(target_id)))


def _read_json(store_dir: str, name: str) -> Any:
    path = os.path.join(store_dir, name)
    if not os.path.exists(path):
        raise AdmittedStoreError(
            GATE_MISSING_ARTIFACT,
            f"{name} is not in the store. A deleted artifact refuses BY NAME: an earlier "
            "producer shipped the provenance gate's REPORT rather than the gate, and returned "
            "ok=True on a deleted provenance file")
    with open(path) as fh:
        return json.load(fh)


def _read_text(store_dir: str, name: str) -> str:
    path = os.path.join(store_dir, name)
    if not os.path.exists(path):
        raise AdmittedStoreError(
            GATE_MISSING_ARTIFACT,
            f"{name} is not in the store. ChEMBL is CC BY-SA 3.0 and its attribution is "
            "REQUIRED: a derived layer travelling without its licence is a licence breach, not "
            "a missing nicety")
    with open(path) as fh:
        return fh.read()


def _check_licence_bindings(manifest: Mapping[str, Any],
                            licences: Mapping[str, str]) -> None:
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

    The order matters, and every step is a named refusal:

      1. the manifest is present — there is no fixture fallback;
      2. every artifact (rows, eligibility, provenance, licence, attribution) is present;
      3. every artifact's ACTUAL bytes still hash to the manifest's pin — a mutated file fails
         here even though the manifest is untouched;
      4. the typed universe derived from the rows is the universe the store bound, and is the
         universe that was ADMITTED;
      5. ``admitted_universe.bind`` re-runs the producer's full gate over the same bytes and
         pins the exact admitted ``store_id``. This module never admits anything — a generator
         that admits its own inputs is one process asserting twice.
    """
    manifest_path = os.path.join(store_dir, MANIFEST_NAME)
    if not os.path.isdir(store_dir) or not os.path.exists(manifest_path):
        raise AdmittedStoreError(
            GATE_STORE_NOT_FOUND,
            f"no {MANIFEST_NAME} under {store_dir!r}. A Stage-3 run without its admitted "
            "universe store does not quietly become a Stage-3 run with a synthetic one")
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
                f"{name} hashes to {got[:16]}… and the manifest pins {str(want)[:16]}…. The "
                "manifest is untouched, so this is the artifact that moved")

    _check_licence_bindings(manifest, licences)

    rows = loaded[ROWS_NAME]
    typed = derive_typed_universe(rows)
    universe_sha = _check_universe_is_the_admitted_one(typed, manifest)

    # The producer's full gate, over the ACTUAL bytes, plus the admitted store_id pin. The
    # verdict is not this module's — it is the one an independent verifier already issued.
    try:
        binding = au.bind(store_dir=store_dir, universe_targets=typed)
    except au.AdmittedUniverseError as exc:
        raise AdmittedStoreError(GATE_STORE_DID_NOT_VERIFY, str(exc)) from exc

    return AdmittedStore(
        store_dir=store_dir, manifest=manifest, rows=rows,
        eligibility_evidence=loaded[ELIGIBILITY_NAME],
        source_provenance=loaded[PROVENANCE_NAME], licences=licences,
        typed_universe=typed, typed_universe_sha256=universe_sha, store_binding=binding,
        _index={(r["target_id_namespace"], r["target_id"]): r for r in rows})


# --------------------------------------------------------------------------- #
# 3. The adapter: typed target identity -> source drug assertions
# --------------------------------------------------------------------------- #
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


def _typed_key(query: Any) -> tuple[str, str]:
    """A query is a TYPED identity, or it is refused. A bare id is a symbol join waiting."""
    if isinstance(query, Mapping):
        tid, ns = query.get("target_id"), query.get("target_id_namespace")
    elif isinstance(query, (tuple, list)) and len(query) == 2:
        tid, ns = query
    else:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"{query!r} is not a typed target identity. The store is joined ONLY by exact "
            "(target_id, target_id_namespace). Joining by a bare id — a gene SYMBOL above all "
            "— looks identical the day it is written, and silently re-attributes every edge "
            "the first time a gene is renamed or a symbol is reused")
    if not tid or not ns:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"target_id={tid!r} target_id_namespace={ns!r}: both halves of the typed identity "
            "are required. A namespace-less id is a name, and names are not identities")
    return str(ns), str(tid)


def drug_edges_for_targets(store: AdmittedStore,
                           target_ids: Iterable[Any]) -> list[dict[str, Any]]:
    """Every SOURCE drug assertion held for these targets, joined by exact typed identity.

    ``target_ids`` are TYPED identities: ``{"target_id": …, "target_id_namespace": …}`` or a
    ``(target_id, namespace)`` pair. A bare string is refused — see :func:`_typed_key`.

    Every assertion is emitted — general, variant-specific, and ambiguous-identity copies
    alike — each typed by its lane and carrying its own rankability disposition. Only
    ``lane == general_gene_rankable`` may rank a gene (:func:`rankable_edges`). The
    non-rankable lanes travel with the result deliberately: an assertion that is silently
    dropped is indistinguishable from a drug nobody found, and the store's entire point is
    that those two are different things.

    A symbol-only target answers with ZERO edges and its ``unsupported_namespace``
    disposition — which means "this acquisition ROUTE cannot reach it", and never "no drug
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
                    f"{tid} is in the admitted universe under namespace {other[0]!r}, and you "
                    f"asked under {ns!r}. A namespace-crossing match is silent "
                    "mis-attribution, so the join refuses rather than guessing which one you "
                    "meant")
            raise DrugEdgeError(
                GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE,
                f"{ns}:{tid} is not one of the {len(store.typed_universe)} targets in the "
                "admitted typed universe. The join is by exact typed identity and never "
                "degrades to a symbol match, so this refuses rather than answering about some "
                "other gene")
        gate_row(row)
        for lane, container in LANE_CONTAINERS:
            for assertion in (row.get(container) or []):
                edges.append(build_edge(row, assertion, lane, binding))

    edges.sort(key=lambda e: (e["target_id_namespace"], e["target_id"], e["lane"],
                              str(e["source_row_id"])))
    return edges
