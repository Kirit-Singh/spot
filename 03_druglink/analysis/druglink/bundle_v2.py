"""The Stage-3 **v2** document: what the bundle id commits to, and what it may never carry.

Audit blocker **B8**. v1 is FROZEN — Stage 4 binds ``spot.stage03_drug_annotation.v1`` by SHA — so
v2 does not widen it: this is a NEW schema id with new table contracts, emitted beside v1.
:mod:`druglink.artifacts_v2` owns the TABLES and the atomic write; this module owns the document,
its bindings, and the two structural refusals.

WHAT THE BUNDLE ID COMMITS TO
-----------------------------
Everything that could change the science, and nothing that could not:

  * the Stage-2 aggregate manifest — RAW and CANONICAL identity, and its own self-hash;
  * the SEPARATE independent aggregate report — raw + canonical, verifier and verdict,
    re-checked here to bind THIS manifest (a report that admits other bytes admits nothing);
  * the W3 STAGE-3 BRIDGE, its SEPARATE report and its RECEIPT — the ONLY source of every
    measured row's target namespace and perturbation modality. A bundle that did not name it
    could be rebuilt from a DIFFERENT admitted bridge and come out byte-identical;
  * every consumed lane artifact — all 15, by raw AND canonical hash;
  * the Stage-1 release the aggregate was computed against;
  * the admitted universe store — its id, the typed universe it was extracted FOR, and the
    exact content hashes of the source artifacts it stands on, with their licences;
  * the direction, workflow and candidate vocabularies, by digest;
  * the code tree, the schema set and the environment lock;
  * every scientific table's content hash, and the candidates themselves.

**Paths and timestamps stay OUT** — the document carries no clock (``created_at`` lives in the
manifest, outside its identity). A bundle re-run from the same inputs on another host, in another
directory, at another hour is the same bundle.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

from . import artifact_class as ac
from . import candidates_v2 as cv2
from . import direction as dr
from . import modality_v2 as mv2
from . import pathway_context_v2 as pc2
from . import env
from . import schemas
from . import stage2_aggregate as sa
from . import universe_rows as ur
from . import workflow as wf
from .canonical_number import rule_block
from .hashing import content_hash, sha256_hex, without

V2_SCHEMA = "spot.stage03_drug_annotation.v2"
V2_MANIFEST_SCHEMA = "spot.stage03_manifest.v2"
V2_METHOD_VERSION = "stage3-druglink-v2-reusable-arms-typed-origins"

# THE DOCUMENT FILENAME IS PART OF THE CONTRACT, not a convention. Stage 4 opens this file BY
# NAME, and a producer/consumer that disagree about the spelling do not fail loudly — the reader
# simply finds nothing, and "no candidates" is indistinguishable from "no file". So the name is
# published in the schema, carried INSIDE the document, echoed in the manifest, and the verifier
# refuses a bundle whose document is not named what the contract says.
V2_DOC = {ac.ANALYSIS: "drug_annotation.v2.json",
          ac.FIXTURE: "fixture_drug_annotation.v2.json"}

# Lanes this release deliberately does not evaluate. An absent lane is recorded as absent —
# never as a favourable result, and never as a zero.
DEFERRED_LANES = {
    "open_targets": "not_evaluated",
    "pubchem": "not_evaluated",
    "rxnorm": "not_evaluated",
    "lincs": "not_evaluated",
    "depmap": "not_evaluated",
    "gbm_context": "not_evaluated",
    "potency": "not_evaluated",
    "disease_context_review": "not_evaluated",
}

# The only fields a document's identity cannot cover: the id derived FROM it, the hash OF it,
# and the clock (which lives in the manifest, not here). Everything else is content.
DOC_IDENTITY_EXCLUDED = ("bundle_id", "canonical_content_sha256", "document_sha256",
                         "created_at")

PROVENANCE_COLUMNS: tuple[str, ...] = (
    "provenance_id", "kind", "subject", "raw_sha256", "canonical_sha256",
    "verifier_id", "verdict", "detail",
)
PROVENANCE_KEY: tuple[str, ...] = ("provenance_id",)

# --------------------------------------------------------------------------- #
# The two vocabularies this bundle may not contain, at ANY depth. Structural, not a single
# boolean: a revived combined objective arrives as ONE new field, nested, in a later writer.
# --------------------------------------------------------------------------- #
OBJECTIVE_TOKENS = ("combined", "balanced", "weighted", "overall", "headline", "composite",
                    "best_of", "winner", "score")
# The NEGATIVE declarations. They say the thing is forbidden; they are not the thing.
OBJECTIVE_ALLOWED = frozenset({"combined_objective_permitted", "headline_arm_permitted",
                               "candidate_rank_permitted"})

INFERENCE_EXACT = frozenset({"p", "q", "pval", "qval", "p_val", "q_val", "padj", "qadj",
                             "alpha", "significance", "significant"})
INFERENCE_TOKENS = ("p_value", "pvalue", "q_value", "qvalue", "fdr", "p_adj", "q_adj",
                    "adj_p", "adjusted_p", "bonferroni", "benjamini", "holm")
INFERENCE_ALLOWED = frozenset({"p_q_fdr_permitted"})

GATE_COMBINED_OBJECTIVE = "the_bundle_carries_a_combined_or_weighted_objective"
GATE_PQ_FDR = "the_bundle_carries_a_p_value_q_value_or_fdr"
GATE_REPORT_BINDS_ANOTHER_MANIFEST = "the_independent_report_admits_a_different_manifest"
GATE_STORE_NOT_ADMITTED = "the_universe_store_is_not_bound_to_its_source_artifacts"


class ArtifactV2Error(ValueError):
    """A named, fail-closed refusal. The bundle is not written."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


# --------------------------------------------------------------------------- #
# 1. The two structural refusals.
# --------------------------------------------------------------------------- #
def _keys(node: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key), f"{path}.{key}"
            yield from _keys(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _keys(value, f"{path}[{i}]")


def check_no_combined_objective(obj: Any) -> None:
    """No combined / balanced / weighted / overall / headline / composite score, at any depth.

    This bundle holds reusable arms and three typed origins that answer DIFFERENT questions. A
    number that pools them has no unit, no estimand, and no way back to its evidence.
    """
    for key, path in _keys(obj):
        low = key.lower()
        if low in OBJECTIVE_ALLOWED:
            continue
        hit = next((t for t in OBJECTIVE_TOKENS if t in low), None)
        if hit:
            raise ArtifactV2Error(
                GATE_COMBINED_OBJECTIVE,
                f"{path} carries {key!r} (token {hit!r}). There is no field for a combined, "
                "balanced, weighted, headline or composite objective, and one that appeared "
                "would silently pool a measured effect, a cross-time DiD and an inference")


def check_no_pq_fdr(obj: Any) -> None:
    """No p, q, FDR or adjusted-p, at any depth. ``inference_status`` is ``not_calibrated``.

    Nothing in Stage 3 is calibrated: no null distribution behind a target->drug edge, no
    multiple-testing frame over reusable arms. A p-value here would have the FORM of a calibrated
    statistic and none of the meaning — and a reader would be right to trust it.
    """
    for key, path in _keys(obj):
        low = key.lower()
        if low in INFERENCE_ALLOWED:
            continue
        if low in INFERENCE_EXACT or any(t in low for t in INFERENCE_TOKENS):
            raise ArtifactV2Error(
                GATE_PQ_FDR,
                f"{path} carries {key!r}. Stage 3 is inference_status=not_calibrated: it has "
                "no null distribution and no multiple-testing frame, so a p/q/FDR field would "
                "have the form of a calibrated statistic and none of its meaning")


def check_contract(document: Mapping[str, Any],
                   tables: Mapping[str, list[dict[str, Any]]]) -> None:
    """Every structural refusal, over the DOCUMENT and over every table row."""
    for payload in (document, *tables.values()):
        ac.check_no_retired_keys({"payload": payload})
        check_no_combined_objective(payload)
        check_no_pq_fdr(payload)
    cv2.check_edges(tables.get("target_drug_edges", []))
    cv2.check_candidate_identity(tables)
    # EVERY edge SAYS it is a putative phenocopy and never claims equivalence. A bundle whose
    # edges lack the label is refused: Stage 4 reads FIELDS, and an unlabelled edge is one a
    # consumer may read as "this drug IS the knockdown".
    mv2.check_edges(tables.get("target_drug_edges", []))
    pc2.check_edges_are_all_measured(tables.get("target_drug_edges", []), dr.INFERRED_ORIGINS)
    # AT ANY DEPTH, over the document AND every table: nothing that fails to phenocopy its
    # declared modality wears supported evidence. An agonist reaches a consumer through a
    # summary or a nested block, not through the builder that already has a gate.
    for payload in (document, *tables.values()):
        mv2.check_no_agonist_supported(payload)
    for candidate in tables.get("candidates", []):
        if candidate.get("evidence_is_equivalence") is not False:
            raise ArtifactV2Error(
                mv2.GATE_CLAIMS_EQUIVALENCE,
                f"candidate {candidate.get('candidate_id')!r} declares "
                "evidence_is_equivalence; a drug acting on the protein is never equivalent to "
                "silencing the transcript that was measured")


# --------------------------------------------------------------------------- #
# 2. Upstream bindings. Every one is re-derived from bytes, never copied from a claim.
# --------------------------------------------------------------------------- #
def bind_report(report_path: str, aggregate: sa.AdmittedAggregate) -> dict[str, Any]:
    """The aggregate report's OWN identity, and proof it admits THIS manifest. NATIVE semantics.

    THE RETIRED `admits{}` BLOCK IS GONE. This used to read ``report["admits"]`` — a block Stage
    2 has NEVER emitted. ``report.get("admits") or {}`` yields ``{}`` against the real bytes, so
    both comparisons below became ``None != <sha>`` and the binding... refused? No: it refused
    only because the fixture that fed it was written to the same fiction. Against real bytes it
    was a check on a field that does not exist, which is not a check.

    The real report binds the manifest TOP-LEVEL, with ``manifest_sha256`` and its own
    ``manifest_sha256_recomputed``. Both must equal the SEMANTIC SELF-HASH Stage 3 recomputed
    from the manifest bytes on disk (``aggregate.manifest_self_hash`` — re-derived by the
    loader, never read out of the document). So a report about some OTHER manifest, and a
    manifest edited after it was judged, are the same refusal — and neither the manifest's claim
    about itself nor the report's claim about the manifest is ever taken on trust.
    """
    with open(report_path, "rb") as fh:
        raw = fh.read()
    report = json.loads(raw.decode("utf-8"))
    claimed = report.get(sa.SELF_HASH_FIELD)
    recomputed = report.get("manifest_sha256_recomputed")
    ours = aggregate.manifest_self_hash
    if claimed != ours or recomputed != ours:
        raise ArtifactV2Error(
            GATE_REPORT_BINDS_ANOTHER_MANIFEST,
            f"the report at {os.path.basename(report_path)!r} admits manifest "
            f"{str(claimed)[:16]}… (it recomputed {str(recomputed)[:16]}…), but the manifest "
            f"Stage 3 admitted semantically hashes to {ours[:16]}…. An ADMIT that names other "
            "bytes is an opinion about some other artifact")
    return {"raw_sha256": sha256_hex(raw), "canonical_sha256": content_hash(report),
            "verifier_id": aggregate.verifier_id, "verdict": aggregate.verdict,
            "manifest_sha256": claimed, "manifest_sha256_recomputed": recomputed}


def aggregate_binding(aggregate: sa.AdmittedAggregate,
                      report: Mapping[str, Any]) -> dict[str, Any]:
    """The whole Stage-2 admission chain, as the bundle id will commit to it."""
    return {
        "manifest_raw_sha256": aggregate.manifest_raw_sha256,
        "manifest_canonical_sha256": aggregate.manifest_canonical_sha256,
        "manifest_self_hash": aggregate.manifest_self_hash,
        "independent_report": dict(report),
        "stage1_release_sha256": aggregate.stage1_release_sha256,
        # WHICH BRIDGE TYPED THESE ARMS. See the header: it is in the bundle id.
        "stage3_bridge": dict(aggregate.bridge_binding),
        # Every consumed lane artifact, by BOTH hashes. A bundle nobody can address is a bundle
        # nobody admitted.
        "lane_artifacts": sorted(
            ({"bundle_key": b.bundle_key, "lane": b.lane, "raw_sha256": b.raw_sha256,
              "canonical_sha256": b.canonical_sha256} for b in aggregate.bundles),
            key=lambda b: b["bundle_key"]),
        "n_bundles": len(aggregate.bundles),
        "n_arm_slots": len(aggregate.arms),
        "program_ids": list(aggregate.program_ids),
        "topology_is_derived_not_declared": True,
        "pair_roles_assigned": False,
    }


def store_binding(store: ur.AdmittedStore, *, artifact_class: str) -> dict[str, Any]:
    """The admitted universe store: its identity, its typed universe, and its source bytes."""
    extraction = store.manifest.get("extraction") or {}
    releases = store.releases
    chembl = releases.get("chembl") or {}
    uniprot = releases.get("uniprot") or {}
    binding: dict[str, Any] = {
        "store_id": store.store_id,
        "typed_universe_sha256": store.typed_universe_sha256,
        "n_typed_targets": len(store.typed_universe),
        "admission": dict(store.store_binding),
        "source_artifacts": [{"artifact": name, "content_sha256": extraction.get(pin)}
                             for name, pin in sorted(ur.ARTIFACT_PINS.items())],
        "chembl_release": chembl.get("source_release"),
        "chembl_source_sha256": chembl.get("source_sha256"),
        "chembl_license": chembl.get("license"),
        "chembl_required_attribution": chembl.get("attribution"),
        "uniprot_release": uniprot.get("source_release"),
        "uniprot_source_sha256": uniprot.get("source_sha256"),
        "uniprot_license": uniprot.get("license"),
        # The cache preserves action_type VERBATIM and decides no direction. Stated, so nothing
        # downstream has to assume it.
        "direction_decided_in_cache": False,
    }
    if artifact_class == ac.ANALYSIS:
        missing = [a["artifact"] for a in binding["source_artifacts"]
                   if not a["content_sha256"]]
        if missing or not binding["admission"] or not binding["store_id"]:
            raise ArtifactV2Error(
                GATE_STORE_NOT_ADMITTED,
                "an analysis bundle must bind the store's admitted identity and the exact "
                f"hashes of the source artifacts it stands on; missing: "
                f"{missing or ['store_id/admission']}. A store nobody can address is a store "
                "nobody admitted, and there is no fixture fallback")
    return binding


def method_block(store: ur.AdmittedStore) -> dict[str, Any]:
    """Code, schemas, env lock, and every vocabulary digest this build was computed under."""
    return {
        **env.method_block(),
        "stage3_method_version": V2_METHOD_VERSION,
        "candidates_v2_policy_version": cv2.CANDIDATES_V2_POLICY_VERSION,
        "universe_rows_policy_version": ur.UNIVERSE_ROWS_POLICY_VERSION,
        # WHICH vocabulary every edge was classified under. Move an action type between sets
        # and the digest moves, instead of a drug quietly starting to rank.
        "direction_vocabulary_digest": dr.vocabulary_digest(),
        # The DECLARED direction contract: the modality->modulation map, the compatible
        # mechanism set DERIVED from the engine, and the phenocopy label.
        "modality_vocabulary_digest": content_hash(mv2.vocabularies()),
        "modality_vocabulary": mv2.vocabularies(),
        # The pathway CONTEXTUALIZES a measured edge and never sources one. Bound by digest so
        # reviving a pathway-sourced drug claim moves every downstream identifier.
        "pathway_context_vocabulary_digest": content_hash(pc2.vocabularies()),
        "pathway_context_vocabulary": pc2.vocabularies(),
        "workflow_vocabulary_digest": content_hash(wf.vocabularies()),
        "candidates_v2_vocabulary_digest": content_hash(cv2.vocabularies()),
        "v2_origin_vocabulary": dr.v2_origin_vocabulary(),
        "candidates_v2_vocabulary": cv2.vocabularies(),
        "stage2_topology": {"n_bundles": sa.N_BUNDLES, "n_arm_slots": sa.N_ARM_SLOTS,
                            "lanes": list(sa.LANES),
                            "desired_changes": list(sa.DESIRED_CHANGES)},
        "universe_store_id": store.store_id,
    }


def provenance_rows(*, aggregate: sa.AdmittedAggregate, store: ur.AdmittedStore,
                    report: Mapping[str, Any],
                    method: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per artifact this bundle stands on. A binding a reader cannot enumerate is a
    binding a reader cannot check."""
    rows: list[dict[str, Any]] = [
        {"kind": "stage2_aggregate_manifest", "subject": "aggregate_run_manifest",
         "raw_sha256": aggregate.manifest_raw_sha256,
         "canonical_sha256": aggregate.manifest_canonical_sha256,
         "verifier_id": aggregate.verifier_id, "verdict": aggregate.verdict,
         "detail": f"self_hash={aggregate.manifest_self_hash}"},
        {"kind": "stage2_independent_report", "subject": "aggregate_verification_report",
         "raw_sha256": report.get("raw_sha256"),
         "canonical_sha256": report.get("canonical_sha256"),
         "verifier_id": report.get("verifier_id"), "verdict": report.get("verdict"),
         "detail": "a separate artifact from a separate verifier; it binds the manifest by "
                   "raw AND canonical hash"},
        {"kind": "stage1_release", "subject": "stage1_release",
         "raw_sha256": aggregate.stage1_release_sha256, "canonical_sha256": None,
         "verifier_id": None, "verdict": None,
         "detail": "the release the aggregate was computed against"},
        # THE BRIDGE, ENUMERABLE — the bridge, the SEPARATE report that admitted it, and the
        # RECEIPT that joins it to the aggregate. It is the only source of target identity and
        # perturbation modality here, so a reader must be able to reopen the exact bytes.
        *sa.bridge_provenance_rows(aggregate.bridge_binding),
        {"kind": "universe_store", "subject": store.store_id, "raw_sha256": None,
         "canonical_sha256": store.typed_universe_sha256,
         "verifier_id": str((store.store_binding or {}).get("admitted_by") or ""),
         "verdict": None, "detail": f"{len(store.typed_universe)} typed targets"},
    ]
    rows += [{"kind": "stage2_lane_artifact", "subject": b.bundle_key,
              "raw_sha256": b.raw_sha256, "canonical_sha256": b.canonical_sha256,
              "verifier_id": aggregate.verifier_id, "verdict": aggregate.verdict,
              "detail": f"lane={b.lane}"}
             for b in aggregate.bundles]
    extraction = store.manifest.get("extraction") or {}
    rows += [{"kind": "universe_store_artifact", "subject": name, "raw_sha256": None,
              "canonical_sha256": extraction.get(pin), "verifier_id": None, "verdict": None,
              "detail": "content hash pinned by the store manifest"}
             for name, pin in sorted(ur.ARTIFACT_PINS.items())]
    rows += [{"kind": "vocabulary", "subject": name, "raw_sha256": None,
              "canonical_sha256": method.get(key), "verifier_id": None, "verdict": None,
              "detail": "the vocabulary every row in this bundle was computed under"}
             for name, key in (("direction", "direction_vocabulary_digest"),
                               ("workflow", "workflow_vocabulary_digest"),
                               ("candidates_v2", "candidates_v2_vocabulary_digest"))]
    rows += [{"kind": "code_identity", "subject": name, "raw_sha256": None,
              "canonical_sha256": method.get(key), "verifier_id": None, "verdict": None,
              "detail": "bound into the bundle id"}
             for name, key in (("code_tree", "code_tree_sha256"),
                               ("schema_set", "schemas_sha256"),
                               ("env_lock", "env_lock_sha256"))]
    for row in rows:
        row["provenance_id"] = content_hash(row)[:16]
    return sorted(rows, key=lambda r: (r["kind"], str(r["subject"])))


# --------------------------------------------------------------------------- #
# 3. The document. Content-addressed; no paths, no timestamps.
# --------------------------------------------------------------------------- #
def canonical_content(*, artifact_class: str, aggregate: Mapping[str, Any],
                      universe: Mapping[str, Any], method: Mapping[str, Any],
                      table_hashes: Mapping[str, str],
                      candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Everything the bundle id commits to. No timestamps, no paths, no labels."""
    return {
        "schema_version": V2_SCHEMA,
        "artifact_class": artifact_class,
        # The file this document IS. Stage 4 opens it by name, so the name is content, not
        # convention — and it moves the bundle id if it ever changes.
        "document_file": V2_DOC[artifact_class],
        "stage2_aggregate": dict(aggregate),
        "universe_store": dict(universe),
        "method": dict(method),
        "origin_types": list(cv2.V2_ORIGINS),
        "lanes": list(sa.LANES),
        "desired_changes": list(sa.DESIRED_CHANGES),
        "reusable_arm_identity": list(cv2.ARM_IDENTITY_COLUMNS),
        "deferred_lanes": dict(sorted(DEFERRED_LANES.items())),
        "table_hashes": dict(sorted(table_hashes.items())),
        # Sorted by content id. A LIST is ordered, so embedding the candidates in whatever
        # order the builder happened to assemble them would make the bundle id depend on row
        # order — the very thing content addressing exists to rule out. This is not a rank:
        # candidate_id is a content hash.
        "candidates": sorted((dict(sorted(c.items())) for c in candidates),
                             key=lambda c: str(c["candidate_id"])),
    }


def build_document(*, artifact_class: str, aggregate: sa.AdmittedAggregate,
                   store: ur.AdmittedStore, report: Mapping[str, Any],
                   table_hashes: Mapping[str, str],
                   tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    ac.require(artifact_class)
    if artifact_class == ac.ANALYSIS:
        sa.require_analysis(aggregate)         # a fixture aggregate never becomes an analysis

    method = method_block(store)
    content = canonical_content(
        artifact_class=artifact_class,
        aggregate=aggregate_binding(aggregate, report),
        universe=store_binding(store, artifact_class=artifact_class),
        method=method, table_hashes=table_hashes,
        candidates=list(tables.get("candidates", [])))

    doc: dict[str, Any] = {
        **content,
        **rule_block(),
        # THE THREE TYPED ORIGINS, and what each may carry. Two are measured and are DISTINCT
        # estimands; one is inferred and was never perturbed.
        "measured_origins": sorted(dr.MEASURED_ORIGINS & set(cv2.V2_ORIGINS)),
        "inferred_origins": sorted(dr.INFERRED_ORIGINS & set(cv2.V2_ORIGINS)),
        "direct_and_temporal_are_distinct_estimands_never_fused": True,
        "gene_and_pathway_evidence_are_never_merged": True,
        "inferred_origin_can_never_carry_observed_support": True,
        "pathway_direction_is_never_inherited_from_set_membership": True,
        # A ROLE is what a SELECTION gives an arm at join time. This bundle holds REUSABLE
        # arms; it assigns none.
        "selection_roles_assigned": False,
        "arms_are_independent": True,
        # Named negatively and bound into the id: reviving any of them moves every downstream
        # identifier, instead of quietly changing what a number means.
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "candidate_rank_permitted": False,
        "p_q_fdr_permitted": False,
        "inference_status": "not_calibrated",
        "stage3_never_alters_stage2_ranks_or_tiers": True,
        # THE SIGN RULE, declared in the document and bound into the bundle id. Reviving the
        # modality-fixed rule moves every downstream identifier instead of silently inverting
        # what a recommendation means.
        "the_target_modulation_is_never_derived_from_the_modality_alone": True,
        "an_agonist_is_never_promoted_to_supported_evidence_by_sign_inversion": True,
        "a_pathway_enrichment_record_never_sources_a_drug_edge": True,
        "pathway_lane_admitted": pc2.PATHWAY_LANE_ADMITTED,
        "directional_evidence_statuses": list(wf.DIRECTIONAL_EVIDENCE_STATUSES),
        "stage3_evidence_classes": list(wf.EVIDENCE_CLASSES),
        "evidence_classes_are_unordered": True,
        "stage4_assessment_statuses": list(wf.STAGE4_ASSESSMENT_STATUSES),
        "stage4_assessment_note": wf.STAGE4_ASSESSMENT_NOTE,
        "stage4_admission_permitted": ac.stage4_queue_permitted(artifact_class),
        "data_status": ("synthetic_fixture_only" if artifact_class == ac.FIXTURE
                        else "admitted_stage2_aggregate_and_universe_store"),
        "counts": {f"n_{name}": len(rows) for name, rows in sorted(tables.items())},
    }
    # THE IDENTITY IS THE WHOLE DOCUMENT, minus only the three fields that cannot cover
    # themselves. NOTHING semantic is excluded — so a field added by a later writer MOVES the
    # bundle id instead of riding along outside it. Hashing a hand-picked "core" subset would
    # leave every other field unaddressed, and an unaddressed field is one a writer can change
    # without anyone downstream noticing.
    #
    # NO created_at. "When" lives in the manifest, outside its identity: a clock in the
    # DOCUMENT would make two runs of identical science differ byte for byte, and the second
    # would be refused as a collision. A refusal that says "different content" about content
    # that is identical teaches the next reader to weaken the check.
    content_sha = content_hash(without(doc, DOC_IDENTITY_EXCLUDED))
    doc_id = ac.bundle_id(artifact_class, content_sha)
    doc["bundle_id"] = doc_id
    doc["canonical_content_sha256"] = content_sha
    doc["document_sha256"] = content_hash(without(doc, ("document_sha256",)))

    ac.check_bundle_id(artifact_class, doc_id)
    check_contract(doc, tables)
    schemas.validate(doc, V2_SCHEMA, context=f"{artifact_class}_drug_annotation_v2")
    return doc
