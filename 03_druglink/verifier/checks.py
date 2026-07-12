"""Every Stage-3 check. Independent reconstruction, never self-consistency.

The gate is: does the bundle agree with what an independent pass derives from the
SOURCES — the verified Direct run, the cached public bytes, and the retained verbatim
source fields? A bundle whose internal hashes all agree with each other has proved
only that one producer was self-consistent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Optional

import pandas as pd

from . import canon, policy, reconstruct
from .acquisition_checks import check_acquisition, check_reconstruction
from .workflow_checks import check_workflow
from . import science_registry as sreg
from .report import Report

EXPECTED_DIRECT_FILES = {
    "axis.json", "input_manifest.json", "gene_universe.json", "provenance.json",
    "verification.json", "screen.parquet", "masks.parquet",
    "contributing_guides.parquet", "guide_support.parquet", "donor_support.parquet",
}

# --------------------------------------------------------------------------- #
# The manifest's OWN identity.
#
# The manifest is the root of trust for the whole bundle: every file hash and the
# document hash are recorded IN it. Verifying those entries while never recomputing the
# manifest's own canonical identity proves only that the manifest agrees with itself —
# a forged `manifest_sha256` sailed through all 60 checks (external review B6).
#
# `manifest_sha256` cannot cover itself, and `created_at` is a non-semantic timestamp
# (the same bundle rebuilt at a different wall-clock time is the same bundle). Both are
# excluded — and NOTHING else is, so no semantic field can hide outside the identity.
# --------------------------------------------------------------------------- #
MANIFEST_IDENTITY_EXCLUDED = ("manifest_sha256", "created_at")

MANIFEST_IDENTITY_GATE = (
    "manifest_sha256 reproduces from the manifest's own canonical content "
    "(excluding manifest_sha256 and the non-semantic created_at)"
)


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _table(bundle: str, name: str) -> list[dict[str, Any]]:
    path = os.path.join(bundle, f"{name}.parquet")
    if not os.path.exists(path):
        return []
    frame = pd.read_parquet(path)
    return [{k: reconstruct.cell(v) if k != "arm_rank" else reconstruct.rank(v)
             for k, v in row.items()}
            for row in frame.to_dict("records")]


# --------------------------------------------------------------------------- #
# 1. The Direct run is verified INDEPENDENTLY, by Direct's own standalone verifier.
# --------------------------------------------------------------------------- #
def check_direct(rep: Report, *, doc: dict[str, Any], direct_run: str,
                 direct_inputs_root: str, direct_analysis: Optional[str]) -> Optional[pd.DataFrame]:
    upstream = doc["upstream"]

    present = {f for f in os.listdir(direct_run) if not f.startswith(".")}
    rep.check("direct run file inventory is exact (no extra, no missing)",
              present == EXPECTED_DIRECT_FILES,
              f"extra={sorted(present - EXPECTED_DIRECT_FILES)} "
              f"missing={sorted(EXPECTED_DIRECT_FILES - present)}")

    analysis = direct_analysis or os.environ.get("SPOT_DIRECT_ANALYSIS")
    if not analysis:
        here = os.path.dirname(os.path.abspath(__file__))
        guess = os.path.normpath(os.path.join(
            here, "..", "..", "..", "spot-stage2-direct", "02_geneskew", "analysis"))
        analysis = guess if os.path.isdir(guess) else None
    if not rep.check("Direct's standalone verifier is available to re-run", analysis):
        return None

    env = dict(os.environ)
    env["PYTHONPATH"] = analysis + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "direct.verify_run", "--run-dir", direct_run,
         "--inputs-root", direct_inputs_root],
        capture_output=True, text=True, env=env, check=False)
    report = proc.stdout + proc.stderr
    rep.check("Direct's standalone verifier RECONSTRUCTS this run from source and "
              "exits 0", proc.returncode == 0,
              f"exit={proc.returncode}; {report.strip()[-400:]}")
    rep.check("the Direct verifier report the bundle bound is the one we just got",
              canon.sha256_hex(report) == upstream["direct_verifier"]["report_sha256"]
              or proc.returncode != 0,
              "the bundle bound a different verifier report than this run produces")

    # Re-hash every consumed Direct file ourselves; compare to the bound hashes.
    bad = []
    for name, declared in sorted(upstream["direct_file_sha256"].items()):
        actual = canon.file_sha256(os.path.join(direct_run, name))
        if actual != declared:
            bad.append(f"{name}: bundle bound {declared[:12]}, actual {actual[:12]}")
    rep.check("every consumed Direct file hashes to what the bundle bound", not bad,
              "; ".join(bad))

    prov = _read_json(os.path.join(direct_run, "provenance.json"))
    rep.check("the bundle binds THIS Direct run_id",
              prov["run_id"] == upstream["direct_run_id"],
              f"{prov['run_id']} != {upstream['direct_run_id']}")
    ctx = upstream["upstream_gate_context"]
    rep.check("upstream gate fields are preserved verbatim as CONTEXT (Stage 3 gates "
              "on none of them)",
              ctx["direct_lane"] == prov.get("namespace")
              and ctx["stage1_gate_passed"] == prov.get("production_gate_passed"),
              str(ctx))
    return pd.read_parquet(os.path.join(direct_run, "screen.parquet"))


# --------------------------------------------------------------------------- #
# 2. The two arms, re-expanded from the screen.
# --------------------------------------------------------------------------- #
def check_arms(rep: Report, *, doc: dict[str, Any], screen: pd.DataFrame,
               arm_levers: list[dict[str, Any]]) -> None:
    run_id = doc["upstream"]["direct_run_id"]
    expected = reconstruct.expand_arms(screen, run_id)

    rep.check("exactly two arm rows per Direct screen row",
              len(arm_levers) == 2 * len(screen) == len(expected),
              f"{len(arm_levers)} arm rows for {len(screen)} screen rows")

    keys = [reconstruct.key_of(r) for r in arm_levers]
    rep.check("every immutable arm-lever key is unique (no last-row-wins collapse)",
              len(set(keys)) == len(keys),
              f"{len(keys) - len(set(keys))} duplicate key(s)")

    by_key = {reconstruct.key_of(r): r for r in arm_levers}
    mismatches: list[str] = []
    for want in expected:
        got = by_key.get(reconstruct.key_of(want))
        if got is None:
            mismatches.append(f"missing {reconstruct.key_of(want)}")
            continue
        for field in reconstruct.ARM_FACT_FIELDS:
            if got.get(field) != want[field]:
                mismatches.append(
                    f"{want['target_id']}/{want['desired_arm']}.{field}: "
                    f"emitted {got.get(field)!r}, screen says {want[field]!r}")
    rep.check("each arm row reproduces ITS OWN pole's fields from the Direct screen "
              "(an A row never carries a B value)", not mismatches,
              "; ".join(mismatches[:4]))

    nulls_ok = all(r["arm_rank"] is None or isinstance(r["arm_rank"], int)
                   for r in arm_levers)
    rep.check("a null arm rank stays NULL (never coerced to 0, -1 or NaN)", nulls_ok)

    for arm in policy.ARMS:
        rows = [r for r in arm_levers if r["desired_arm"] == arm]
        rep.check(f"{arm}: every screen row is present, evaluable or not",
                  len(rows) == len(screen), f"{len(rows)} != {len(screen)}")

    unmapped = [r for r in arm_levers
                if r["target_identity_state"] != "ensembl_mapped"]
    rep.check("no unmapped symbol-artifact_class target is permitted a gene-drug edge",
              all(not r["gene_target_drug_edge_permitted"] for r in unmapped),
              f"{len(unmapped)} unmapped row(s)")

    rep.check("arm_direction_measured is re-derived from the ARM's own screen fields",
              all(bool(r["arm_direction_measured"])
                  == reconstruct.arm_direction_measured(r)
                  for r in arm_levers))


# --------------------------------------------------------------------------- #
# 3. Direction: re-derived from the verbatim source action, never from the label.
# --------------------------------------------------------------------------- #
def check_direction(rep: Report, *, edges: list[dict[str, Any]],
                    assertions: list[dict[str, Any]],
                    entities: list[dict[str, Any]]) -> None:
    single = {e["target_entity_id"]: bool(e["direct_gene_lane_eligible"])
              for e in entities}

    eff_bad, cls_bad, sup_bad = [], [], []
    for a in assertions:
        want = policy.intervention_effect(a["action_type_source"])
        if a["intervention_effect"] != want:
            eff_bad.append(f"{a['assertion_id']}: {a['action_type_source']!r} -> "
                           f"emitted {a['intervention_effect']}, want {want}")
    rep.check("every assertion's intervention_effect re-derives from its VERBATIM "
              "source action_type", not eff_bad, "; ".join(eff_bad[:3]))

    for e in edges:
        want = reconstruct.edge_status(
            e, single.get(e["target_entity_id"], False))
        if e["directional_evidence_status"] != want["directional_evidence_status"]:
            cls_bad.append(f"{e['edge_id']}: emitted "
                           f"{e['directional_evidence_status']}, want "
                           f"{want['directional_evidence_status']}")
        if bool(e["observed_perturbation_support"]) != want[
                "observed_perturbation_support"]:
            sup_bad.append(e["edge_id"])
    rep.check("every edge's directional_evidence_status re-derives from (arm "
              "modulation, intervention effect, entity class, conflict, origin)",
              not cls_bad, "; ".join(cls_bad[:3]))
    rep.check("ONLY a measured direct target carries observed_perturbation_support (an "
              "inverse-direction hypothesis and a pathway node never do)", not sup_bad,
              f"{len(sup_bad)} edge(s)")

    # The inverse-direction hypothesis is a DISTINCT state: never folded into
    # unresolved, never folded into observed support, never the same evidence class.
    inverse = [e for e in edges
               if e["directional_evidence_status"]
               == policy.INVERSE_DIRECTION_HYPOTHESIS]
    rep.check("every inverse-direction hypothesis is a REAL sourced activation on the "
              "undesired-direction arm, is NOT observed gain of function, and does not "
              "share an evidence class with a measurement",
              all(e["directional_evidence_reason"] == policy.REASON_INVERSE_ACTIVATION
                  and e["observed_perturbation_support"] is False
                  and e["stage3_evidence_class"] == policy.CLASS_INVERSE
                  and e["intervention_effect"] == policy.FUNCTIONAL_ACTIVATION
                  and e["arm_desired_target_modulation"] == policy.MOD_INCREASE
                  and e["origin_type"] == policy.ORIGIN_DIRECT_TARGET
                  for e in inverse),
              f"{len(inverse)} inverse-direction edge(s)")
    rep.check("no edge is filed under a measurement's evidence class unless it IS a "
              "measured perturbation",
              all((e["stage3_evidence_class"] == policy.CLASS_MEASURED)
                  == (e["directional_evidence_status"]
                      == policy.OBSERVED_PERTURBATION
                      and e["origin_type"] == policy.ORIGIN_DIRECT_TARGET)
                  for e in edges))

    # The load-bearing semantic guard from the audit.
    liars = [e["edge_id"] for e in edges
             if e["intervention_effect"] == policy.FUNCTIONAL_INHIBITION
             and "abundance" in str(e.get("intervention_effect_reason", "")).lower()]
    rep.check("no functional inhibitor is serialized as an abundance reduction",
              not liars, f"{len(liars)} edge(s)")




# --------------------------------------------------------------------------- #
# 5. Content integrity, banned objectives, hygiene.
# --------------------------------------------------------------------------- #
def check_integrity(rep: Report, *, bundle: str, doc: dict[str, Any],
                    manifest: dict[str, Any]) -> None:
    # FIRST: the manifest must prove its own identity. Every check below reads the
    # manifest's recorded hashes, so a manifest that has not proved itself is not a
    # trustworthy source for any of them. A missing manifest_sha256 fails here too —
    # `declared` is then None, which no hash equals.
    declared = manifest.get("manifest_sha256")
    recomputed = canon.chash(canon.without(manifest, MANIFEST_IDENTITY_EXCLUDED))
    rep.check(MANIFEST_IDENTITY_GATE, recomputed == declared,
              f"manifest declares {str(declared)[:12]}…, but its own canonical content "
              f"hashes to {recomputed[:12]}…")

    rep.check("document_sha256 reproduces from the document's own content",
              canon.chash(canon.without(doc, ("document_sha256",)))
              == doc["document_sha256"])

    files = {f["file"]: f for f in manifest["files"]}
    bad = []
    for name, entry in sorted(files.items()):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            bad.append(f"{name}: missing")
            continue
        actual = canon.file_sha256(path)
        if actual != entry["file_sha256"]:
            bad.append(f"{name}: file hash {actual[:12]} != {entry['file_sha256'][:12]}")
    rep.check("every bundle file hashes to its manifest entry", not bad,
              "; ".join(bad[:3]))

    present = {f for f in os.listdir(bundle) if not f.startswith(".")}
    # verification.json is THIS verifier's own output, so it is permitted but never
    # required — and it is never an input to any check above.
    expected = set(files) | {"manifest.json"}
    extra = sorted(present - expected - {"verification.json"})
    rep.check("bundle inventory is exact (no extra or stale file)",
              not extra and not (expected - present),
              f"extra={extra} missing={sorted(expected - present)}")

    rep.check("no production pointer FILE exists in the bundle",
              not [f for f in policy.PRODUCTION_POINTER_FILES
                   if os.path.exists(os.path.join(bundle, f))])

    banned = policy.banned_keys_in(doc)
    rep.check("the document carries no combined/headline objective key",
              not banned, str(banned[:5]))

    col_hits: list[str] = []
    for name in sorted(files):
        if not name.endswith(".parquet"):
            continue
        cols = set(pd.read_parquet(os.path.join(bundle, name)).columns)
        hit = policy.BANNED_KEYS.intersection(cols)
        col_hits += [f"{name}:{c}" for c in sorted(hit)]
    rep.check("no table carries a combined/headline objective COLUMN", not col_hits,
              str(col_hits[:5]))

    local = policy.contains_local_path(doc)
    rep.check("the document leaks no machine-local path", not local, str(local[:3]))
    local_m = policy.contains_local_path(canon.without(manifest, ("files",)))
    rep.check("the manifest leaks no machine-local path", not local_m, str(local_m[:3]))


def check_dispositions(rep: Report, *, arm_levers: list[dict[str, Any]],
                       candidates: list[dict[str, Any]],
                       dispositions: list[dict[str, Any]]) -> None:
    subjects = {(d["subject_kind"], d["subject_id"], d["state"])
                for d in dispositions}

    unmapped = {r["target_id"] for r in arm_levers
                if r["target_identity_state"] != "ensembl_mapped"}
    missing = [t for t in unmapped
               if ("arm_lever_target", t, "unmapped_released_symbol_namespace")
               not in subjects]
    rep.check("every unmapped symbol target has an explicit disposition (none is "
              "silently dropped)", not missing, f"{len(missing)} missing")

    not_sent = {c["candidate_id"] for c in candidates
                if c["stage4_assessment_status"] == policy.NOT_QUEUED}
    gone = [c for c in not_sent
            if ("candidate", c, policy.NOT_QUEUED) not in subjects]
    rep.check("every candidate NOT queued for Stage 4 stays visible as a disposition",
              not gone, f"{len(gone)} missing")


def check_science_registry(rep: Report, *, doc: dict[str, Any],
                           science_registry_root: Optional[str],
                           pathway_nodes: list[dict[str, Any]],
                           pathways_rows: list[dict[str, Any]],
                           candidates: list[dict[str, Any]]) -> None:
    """FINDING 1: resolve EVERY referenced Science record and RE-HASH its bytes.

    Independent implementation (``verifier/science_registry.py``): it imports nothing
    from ``druglink``, restates the canonical-number rule, and re-derives every hash from
    the bytes on disk. A resolver that reused the writer's hashing would prove only that
    the writer was self-consistent.
    """
    refs = (sreg.collect_refs(pathway_nodes) + sreg.collect_refs(pathways_rows)
            + sreg.collect_refs(candidates, "disease_context_review_evidence_refs"))

    declared = (doc.get("science_evidence_registry") or {}).get("science_registry")
    if not refs:
        rep.check("no Science record is referenced, and none is claimed", True)
        return

    rep.check("a Science registry is bound whenever Science records are referenced",
              declared == "provided" and science_registry_root,
              f"{len(refs)} reference(s) but registry={declared!r}")

    fails = sreg.verify_refs(science_registry_root, refs)
    rep.check("every referenced Science record RESOLVES in the registry and its bytes "
              "RE-HASH to what the reference binds (a missing or altered record fails "
              "closed)", not fails, "; ".join(fails[:4]))

    # FINDING 5: a substantive verdict must be paid for with resolvable evidence.
    substantive = {"supportive", "contradictory", "mixed"}
    unpaid = [c["candidate_id"] for c in candidates
              if c.get("disease_context_review_result") in substantive
              and not (c.get("disease_context_review_evidence_refs") or [])]
    rep.check("no substantive disease-context review (supportive/contradictory/mixed) "
              "is emitted without resolvable evidence bindings", not unpaid,
              f"{len(unpaid)} candidate(s)")

    # A pending review can never carry a result.
    drifted = [c["candidate_id"] for c in candidates
               if c.get("disease_context_review_status") != "completed"
               and c.get("disease_context_review_result") is not None]
    rep.check("a pending review carries NO result and can never become favourable",
              not drifted, f"{len(drifted)} candidate(s)")


def run_checks(*, bundle: str, cache_root: str, direct_run: str,
               direct_inputs_root: str, artifact_class: str,
               direct_analysis: Optional[str] = None,
               science_registry_root: Optional[str] = None) -> Report:
    rep = Report()
    manifest = _read_json(os.path.join(bundle, "manifest.json"))
    doc = _read_json(os.path.join(bundle, manifest["document_file"]))

    rep.check("the bundle declares the artifact_class it was verified as",
              doc["artifact_class"] == artifact_class == manifest["artifact_class"],
              f"doc={doc['artifact_class']} manifest={manifest['artifact_class']} "
              f"asked={artifact_class}")

    screen = check_direct(rep, doc=doc, direct_run=direct_run,
                          direct_inputs_root=direct_inputs_root,
                          direct_analysis=direct_analysis)

    arm_levers = _table(bundle, "arm_levers")
    edges = _table(bundle, "target_drug_edges")
    assertions = _table(bundle, "mechanism_assertions")
    entities = _table(bundle, "target_entities")
    moieties = _table(bundle, "active_moieties")
    cands = _table(bundle, "candidates")
    disps = _table(bundle, "dispositions")
    source_records = _table(bundle, "source_records")
    pathway_nodes = _table(bundle, "pathway_nodes")
    pathways_rows = _table(bundle, "pathways")

    check_pathways(rep, doc=doc, screen=screen, pathway_nodes=pathway_nodes,
                   pathways_rows=pathways_rows)
    check_science_registry(rep, doc=doc, science_registry_root=science_registry_root,
                           pathway_nodes=pathway_nodes, pathways_rows=pathways_rows,
                           candidates=cands)

    if screen is not None:
        check_arms(rep, doc=doc, screen=screen, arm_levers=arm_levers)
    check_direction(rep, edges=edges, assertions=assertions, entities=entities)
    check_workflow(rep, doc=doc, artifact_class=artifact_class,
                   candidates=cands, edges=edges, moieties=moieties)
    check_integrity(rep, bundle=bundle, doc=doc, manifest=manifest)
    check_dispositions(rep, arm_levers=arm_levers, candidates=cands,
                       dispositions=disps)

    acquired = check_acquisition(rep, doc=doc, cache_root=cache_root,
                                 source_records=source_records)
    check_reconstruction(rep, acquired=acquired, arm_levers=arm_levers,
                         pathway_nodes=pathway_nodes, assertions=assertions,
                         entities=entities, edges=edges, candidates=cands)
    return rep


def check_pathways(rep: Report, *, doc: dict[str, Any],
                   screen: Optional[pd.DataFrame],
                   pathway_nodes: list[dict[str, Any]],
                   pathways_rows: list[dict[str, Any]]) -> None:
    """The pathway-node lane: inferred, never measured, never merged."""
    lane = (doc.get("pathway_hypotheses") or {}).get("pathway_lane")
    rep.check("the pathway lane is explicitly declared (evaluated or not_evaluated)",
              lane in ("evaluated", "not_evaluated"), f"got {lane!r}")

    if lane == "not_evaluated":
        rep.check("an unevaluated pathway lane emits NO pathway nodes (an absent lane "
                  "is never a silent zero)", not pathway_nodes,
                  f"{len(pathway_nodes)} node(s)")
        return

    rep.check("every pathway node states its OWN desired direction (never inherited "
              "from its pathway)",
              all(n.get("arm_desired_target_modulation") for n in pathway_nodes))
    rep.check("no pathway node claims a measured Direct rank, value or tier",
              all(n.get("arm_rank") is None
                  and n.get("arm_value_source_string") is None
                  and n.get("arm_evidence_tier") == "not_evaluated"
                  for n in pathway_nodes))
    rep.check("no pathway node is research_direction_evaluable (it was never "
              "perturbed)",
              all(not n.get("research_direction_evaluable") for n in pathway_nodes))
    rep.check("every pathway node carries origin_type=pathway_node",
              all(n.get("origin_type") == policy.ORIGIN_PATHWAY_NODE
                  for n in pathway_nodes))

    # FINDING 2: the FULL typed triple travels downstream. An id alone is not a binding.
    triple = ("science_evidence_id", "science_evidence_sha256", "record_type")
    bad_refs = [n["target_ensembl"] for n in pathway_nodes
                for r in (n.get("science_evidence_refs") or [])
                if not all(r.get(f) for f in triple)]
    rep.check("every emitted Science reference carries the FULL typed triple "
              "{science_evidence_id, sha256, record_type} — never the id alone",
              not bad_refs, f"{len(bad_refs)} reference(s)")

    # FINDING 3: every node binds a HASH-BOUND parent enrichment. No dangling parents.
    binding_fields = ("pathway_record_id", "gene_set_release_id", "gene_set_sha256",
                      "universe_id", "universe_sha256")
    dangling = [n["target_ensembl"] for n in pathway_nodes
                if not all(n.get(f) for f in binding_fields)]
    rep.check("every pathway node binds a hash-bound parent enrichment "
              "(pathway_record_id + gene-set + universe hashes)", not dangling,
              f"{len(dangling)} node(s) with a dangling parent enrichment")

    parents = {p["pathway_record_id"] for p in pathways_rows}
    orphaned = [n["target_ensembl"] for n in pathway_nodes
                if n.get("pathway_record_id") not in parents]
    rep.check("every node's parent enrichment record resolves to an emitted pathway",
              not orphaned, f"{len(orphaned)} node(s)")

    # Every node admitted to a drug edge must cite a perturbation this screen contains.
    if screen is None:
        return
    measured = set(screen["target_ensembl"].dropna().astype(str))
    orphan = [n["target_ensembl"] for n in pathway_nodes
              if n.get("gene_target_drug_edge_permitted")
              and not (n.get("n_contributing_perturbations") or 0)]
    rep.check("every drug-eligible pathway node cites at least one contributing "
              "measured perturbation", not orphan, f"{len(orphan)} node(s)")
    cited_unknown = [n["target_ensembl"] for n in pathway_nodes
                     for c in (n.get("contributing_perturbations") or [])
                     if c.get("perturbed_target_ensembl") not in measured]
    rep.check("every cited contributing perturbation exists in THIS Direct screen",
              not cited_unknown, f"{len(cited_unknown)} citation(s)")
