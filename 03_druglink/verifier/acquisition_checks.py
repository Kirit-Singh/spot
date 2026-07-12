"""Checks that re-derive the evidence from the RAW acquisition bytes.

Split out of :mod:`verifier.checks` to keep both modules small. Everything here opens
the cache itself, hashes the bytes itself, re-parses them with the verifier's OWN
parsers, and rebuilds identity / mechanisms / edges / candidates from the result. The
bundle's own tables are only ever the thing being COMPARED against — never the source.
"""
from __future__ import annotations

from typing import Any, Optional

from . import policy, rebuild, sources
from .report import Report


# --------------------------------------------------------------------------- #
# 6. The RAW acquisition bytes: read, hashed and re-parsed by the verifier itself.
# --------------------------------------------------------------------------- #
def check_acquisition(rep: Report, *, doc: dict[str, Any],
                      cache_root: Optional[str],
                      source_records: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Open the cache, hash every page, and bind it to the bundle. Or refuse.

    A nonexistent cache is NOT an empty cache: a bundle whose evidence cannot be
    re-read is unverifiable, and unverifiable is a failure.
    """
    try:
        manifest = sources.load_cache(cache_root)
    except sources.CacheError as exc:
        rep.check("the acquisition cache is present and readable", False, str(exc))
        return None
    rep.check("the acquisition cache is present and readable", True)

    read = sources.read_pages(cache_root, manifest)
    rep.check("every acquired page's RAW BYTES are present and hash to the manifest",
              not read["failures"], "; ".join(read["failures"][:4]))

    # Real runs must keep the moment they were actually retrieved.
    missing = sources.retrieval_timestamps(manifest)
    rep.check("every acquired page records its ACTUAL retrieval timestamp and a 200",
              not missing, "; ".join(missing[:4]))

    # The bundle must be bound to THIS cache, not to some other acquisition.
    acquisition = doc.get("acquisition") or {}
    declared = acquisition.get("acquisition_manifest_sha256")
    rep.check("the bundle binds the acquisition manifest it actually consumed",
              declared == manifest.get("content_sha256"),
              f"bundle bound {str(declared)[:12]}, cache is "
              f"{str(manifest.get('content_sha256'))[:12]}")
    rep.check("the acquisition was independently VERIFIED before the bundle was built",
              bool(acquisition.get("verification", {}).get("all_pass")),
              "the bundle carries no passing acquisition-verification gate")

    # Every source record in the bundle must correspond to a real cached page.
    cached = {p["raw_sha256"] for p in read["pages"]}
    public = [s for s in source_records
              if s.get("acquisition_status") == "acquired_public"]
    orphans = [s["source_record_id"] for s in public
               if s.get("raw_sha256") not in cached]
    rep.check("every acquired source record in the bundle has bytes in the cache",
              not orphans, f"{len(orphans)} source record(s) with no cached bytes")

    return {"manifest": manifest, "pages": read["pages"],
            "records": sources.reparse(read["pages"])}


def check_reconstruction(rep: Report, *, acquired: Optional[dict[str, Any]],
                         arm_levers: list[dict[str, Any]],
                         pathway_nodes: list[dict[str, Any]],
                         assertions: list[dict[str, Any]],
                         entities: list[dict[str, Any]],
                         edges: list[dict[str, Any]],
                         candidates: list[dict[str, Any]]) -> None:
    """Rebuild identity/mechanism/edges/candidates from the BYTES and compare."""
    if acquired is None:
        rep.check("the emitted tables reconstruct from the raw source bytes", False,
                  "the cache could not be read, so nothing could be reconstructed")
        return

    records = acquired["records"]
    forms = rebuild.build_forms(records["molecule"])
    rebuilt_entities = rebuild.build_entities(records["target_entity"],
                                              records["gene_map"])

    # --- mechanisms: 1:1 with the raw bytes, action_type VERBATIM ---------------
    raw_mechs = {(m["source_molecule_id"], m["source_target_id"],
                  str(m["action_type_source"])) for m in records["mechanism"]}
    emitted = {(a["source_molecule_id"],
                _entity_source_id(a["target_entity_id"], entities),
                str(a["action_type_source"])) for a in assertions}
    invented = sorted(emitted - raw_mechs)
    rep.check("no mechanism assertion exists that the raw bytes do not state",
              not invented, f"{len(invented)} invented: {invented[:2]}")

    # --- target entities: class comes from the bytes, not from the bundle -------
    by_source = {e["source_target_id"]: e for e in entities}
    bad = []
    for source_id, want in sorted(rebuilt_entities.items()):
        got = by_source.get(source_id)
        if got is None:
            continue
        if bool(got["direct_gene_lane_eligible"]) != want["is_single_protein"]:
            bad.append(f"{source_id}: bundle says gene-lane="
                       f"{got['direct_gene_lane_eligible']}, bytes say "
                       f"{want['target_type']}")
    rep.check("a complex/family is never promoted into the direct-gene lane",
              not bad, "; ".join(bad[:3]))

    # --- edges: re-derived from bytes + arm levers ------------------------------
    rebuilt_edges = rebuild.build_edges(
        mechanisms=records["mechanism"], forms=forms, entities=rebuilt_entities,
        arm_levers=arm_levers + pathway_nodes)

    def key(edge, source_id=None):
        return (edge["desired_arm"], edge["origin_type"], edge["target_ensembl"],
                edge["form_id"], edge["action_type_normalized"])

    want_edges = {key(e): e for e in rebuilt_edges}
    got_edges = {key(e): e for e in edges}

    missing = sorted(set(want_edges) - set(got_edges))
    extra = sorted(set(got_edges) - set(want_edges))
    rep.check("the emitted edge set is exactly the set the raw bytes imply",
              not missing and not extra,
              f"missing={len(missing)} extra={len(extra)} "
              f"{(missing[:1] + extra[:1])}")

    mismatched = [f"{k}: bundle={got_edges[k]['directional_evidence_status']} "
                  f"bytes={want_edges[k]['directional_evidence_status']}"
                  for k in sorted(set(want_edges) & set(got_edges))
                  if got_edges[k]["directional_evidence_status"]
                  != want_edges[k]["directional_evidence_status"]]
    rep.check("every edge's directional_evidence_status re-derives from the RAW source "
              "action and that arm's own Direct modulation", not mismatched,
              "; ".join(mismatched[:3]))

    # --- candidates: per-arm state and PK eligibility ---------------------------
    rebuilt_cands = rebuild.build_candidates(rebuilt_edges, forms)
    cand_bad, pk_bad = [], []
    for cand in candidates:
        want = rebuilt_cands.get(cand["candidate_id"])
        if want is None:
            continue
        arms = {(a["desired_arm"], a["origin_type"]): a["arm_evidence_state"]
                for a in cand["arm_evidence_states"]}
        for akey, state in want["arm_states"].items():
            if arms.get(akey) != state:
                cand_bad.append(f"{cand['candidate_id']}/{akey}: "
                                f"{arms.get(akey)} != {state}")
        if cand["stage4_assessment_status"] != want["stage4_assessment_status"]:
            pk_bad.append(cand["candidate_id"])
        # A COMPLETED review is judged by whether its evidence resolves (see
        # check_science_registry), not by re-derivation — the verdict comes from Claude
        # Science, not from the raw bytes. Everything NOT completed must reconstruct.
        if (cand["disease_context_review_status"] != policy.REVIEW_COMPLETED
                and cand["disease_context_review_status"]
                != want["baseline_review_status"]):
            pk_bad.append(f"{cand['candidate_id']}:review")
    rep.check("every candidate's per-arm state reconstructs from the raw bytes",
              not cand_bad, "; ".join(cand_bad[:3]))
    rep.check("every candidate's stage4_assessment_status reconstructs from the raw "
              "bytes", not pk_bad, f"{len(pk_bad)} candidate(s)")


def _entity_source_id(entity_id: str, entities: list[dict[str, Any]]) -> Optional[str]:
    for entity in entities:
        if entity["target_entity_id"] == entity_id:
            return entity["source_target_id"]
    return None
