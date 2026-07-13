"""Independent, OFFLINE verification of a public acquisition cache.

    PYTHONPATH=analysis:. python -m druglink.verify_acquisition \\
      --cache-root "$STAGE3_CACHE" \\
      --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT"

It opens NO socket. Everything it asserts, it re-derives: from the retained raw
bytes, from the recorded response headers, and from the Direct run itself. It
never trusts a number the manifest declares about itself when that number can be
recomputed from the bytes.

It fails on:

  * a dropped middle page -- the chain is checked link-by-link in both directions
    AND the observed record counts must add up to the total the SOURCE declared;
  * one changed byte, total count, next link, release, query, license or target;
  * a frozen target queue that is not what this Direct run produces;
  * an ``acquired_public`` entry whose bytes are fixture bytes;
  * a UniProt release that differs across pages of one run.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

from . import armlever, artifact_class as ac, direct_run
from .acquisition import MANIFEST_FILE, QUEUE_FILE
from .verify_acq_pages import (Report, _body, _content_sha256, _read_json,
                               check_bytes, check_chains, check_releases)
from .hashing import (content_hash, contains_local_path, short_id, without)
from .schemas import ACQUISITION, SchemaError, validate

DEFERRED_LANES = ("open_targets", "pubchem", "rxnorm", "lincs")



def check_queue(rep: Report, cache_root: str, manifest: dict[str, Any], *,
                run_dir: Optional[str], inputs_root: Optional[str],
                direct_analysis: Optional[str],
                direct: Optional[direct_run.DirectRun] = None) -> None:
    """Re-derive the frozen queue from the Direct run. It must be the same queue.

    ``direct`` is an explicit TEST seam: it lets the offline acquisition tests supply
    an in-memory Direct stand-in instead of a run directory. It is recorded as such,
    so a pass that skipped Direct's own verifier can never be mistaken for one that
    ran it. The CLI never passes it — it always supplies ``--direct-run`` and
    re-loads, which re-executes Direct's standalone verifier.
    """
    queue_path = os.path.join(cache_root, QUEUE_FILE)
    if not rep.check("frozen_target_queue_is_present", os.path.exists(queue_path)):
        return
    queue = _read_json(queue_path)
    binding = manifest.get("acquisition_binding") or {}
    policy = queue.get("policy") or {}

    rep.check("acquisition_id_binds_the_frozen_queue_and_policy",
              short_id(without(queue, ["acquisition_id"]), 32)
              == queue.get("acquisition_id")
              == manifest.get("acquisition_id"),
              f"queue {queue.get('acquisition_id')!r} vs manifest "
              f"{manifest.get('acquisition_id')!r}")
    rep.check("frozen_queue_hash_matches_the_manifest",
              content_hash(queue["target_queue"]) == binding.get("target_queue_sha256")
              == content_hash(binding.get("target_queue") or []))
    rep.check("acquisition_forbids_adaptive_expansion",
              policy.get("adaptive_expansion_permitted") is False
              and policy.get("stop_when_enough_drugs_found") is False)

    if direct is None:
        direct = direct_run.load(run_dir, inputs_root,
                                 artifact_class=manifest["artifact_class"],
                                 direct_analysis=direct_analysis)
        rep.check("direct_run_was_independently_reverified", True)
    else:
        rep.check("direct_run_was_independently_reverified", True,
                  "test seam: an in-memory Direct stand-in was supplied, so Direct's "
                  "standalone verifier did not re-run in THIS pass")
    expansion = armlever.expand(direct.screen, direct_run_id=direct.run_id)
    rederived = armlever.select_acquisition_targets(
        expansion["arm_levers"], top_per_arm=policy["top_per_arm"])

    rep.check("frozen_queue_is_what_this_direct_run_produces",
              rederived == queue["target_queue"],
              f"re-derived {len(rederived)} target(s), cache froze "
              f"{len(queue['target_queue'])}")
    rep.check("query_genes_are_the_queues_own_union",
              armlever.query_genes(rederived) == queue.get("query_genes"))
    rep.check("cache_is_bound_to_this_direct_run",
              binding.get("direct_run_id") == direct.run_id
              and content_hash(binding.get("direct_binding") or {})
              == direct.binding_sha256,
              f"cache froze {binding.get('direct_run_id')!r}, verified "
              f"{direct.run_id!r}")
    rep.check("top_per_arm_policy_is_bound",
              policy.get("top_per_arm")
              == (binding.get("policy") or {}).get("top_per_arm"))

    per_arm = {arm: sum(1 for t in rederived if t["desired_arm"] == arm)
               for arm in armlever.ARMS}
    rep.check("each_arm_was_selected_independently",
              per_arm == {k: v for k, v in (binding.get("per_arm_counts")
                                            or {}).items()},
              f"re-derived {per_arm}")


def check_graph(rep: Report, cache_root: str, manifest: dict[str, Any],
                entries: list[dict[str, Any]]) -> None:
    """The request graph must follow from the BYTES, not from the manifest's claims."""
    queue = _read_json(os.path.join(cache_root, QUEUE_FILE))
    genes = set(queue.get("query_genes") or [])
    by_adapter: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e["acquisition_status"] == "acquired_public":
            by_adapter.setdefault(e["adapter"], []).append(e)

    asked = {(e.get("request_context") or {}).get("target_ensembl")
             for e in by_adapter.get("uniprot_search", [])}
    rep.check("every_frozen_gene_was_queried_and_no_other",
              asked == genes if genes else asked <= genes,
              f"queried {len(asked)} of {len(genes)} frozen gene(s)")

    accessions: set[str] = set()
    for e in by_adapter.get("uniprot_search", []):
        ensg = (e.get("request_context") or {}).get("target_ensembl")
        for rec in _body(cache_root, e).get("results") or []:
            for xref in rec.get("uniProtKBCrossReferences") or []:
                if xref.get("database") != "Ensembl":
                    continue
                for prop in xref.get("properties") or []:
                    if (prop.get("key") == "GeneId" and rec.get("primaryAccession")
                            and str(prop.get("value") or "").split(".")[0] == ensg):
                        accessions.add(rec["primaryAccession"])

    if not by_adapter.get("chembl_target") and not accessions:
        rep.check("one_to_many_mappings_are_all_carried_into_chembl", True,
                  "no accession mapped; zero candidates is a valid result")
        return

    queried = {(e.get("request_context") or {}).get("uniprot_accession")
               for e in by_adapter.get("chembl_target", [])}
    rep.check("one_to_many_mappings_are_all_carried_into_chembl",
              queried == accessions,
              f"bytes map {len(accessions)} accession(s); {len(queried)} queried "
              f"(missing {sorted(accessions - queried)})")

    single: set[str] = set()
    non_single: set[str] = set()
    for e in by_adapter.get("chembl_target", []):
        acc = (e.get("request_context") or {}).get("uniprot_accession")
        for tgt in _body(cache_root, e).get("targets") or []:
            accs = {c.get("accession") for c in tgt.get("target_components") or []}
            tid = tgt.get("target_chembl_id")
            if tgt.get("target_type") == "SINGLE PROTEIN" and acc in accs:
                single.add(tid)
            else:
                non_single.add(tid)

    mech = {(e.get("request_context") or {}).get("target_chembl_id")
            for e in by_adapter.get("chembl_mechanism", [])}
    rep.check("only_single_protein_targets_entered_the_direct_gene_lane",
              not (mech & (non_single - single)),
              f"family/complex target(s) followed: {sorted(mech & non_single)}")
    rep.check("every_single_protein_target_was_followed", mech == single,
              f"single-protein {sorted(single)}, mechanisms fetched {sorted(mech)}")

    molecules: set[str] = set()
    for e in by_adapter.get("chembl_mechanism", []):
        for m in _body(cache_root, e).get("mechanisms") or []:
            if m.get("molecule_chembl_id"):
                molecules.add(m["molecule_chembl_id"])
    chunked: list[str] = []
    sorted_ok = True
    for e in sorted(by_adapter.get("chembl_molecule", []),
                    key=lambda r: (r.get("request_context") or {}).get(
                        "molecule_chunk_index", 0)):
        chunk = (e.get("request_context") or {}).get("molecule_chembl_ids") or []
        if list(chunk) != sorted(chunk):
            sorted_ok = False
        if e["query"].get("molecule_chembl_id__in") != ",".join(chunk):
            sorted_ok = False
        chunked.extend(chunk)
    rep.check("molecule_chunks_are_sorted_and_frozen", sorted_ok)
    rep.check("molecule_chunks_cover_exactly_the_mechanism_molecules",
              sorted(set(chunked)) == sorted(molecules) and len(chunked)
              == len(set(chunked)),
              f"{len(molecules)} molecule(s) in the bytes, {len(set(chunked))} chunked")


def verify(cache_root: str, *, run_dir: Optional[str], inputs_root: Optional[str],
           direct_analysis: Optional[str] = None,
           artifact_class: Optional[str] = None,
           direct: Optional[direct_run.DirectRun] = None) -> Report:
    """Offline. No network request is made anywhere in this module.

    ``direct`` is the test seam described on :func:`check_queue`; the CLI passes
    ``run_dir``/``inputs_root`` and therefore always re-runs Direct's own verifier.
    """
    rep = Report()
    path = os.path.join(cache_root, MANIFEST_FILE)
    if not rep.check("acquisition_manifest_is_present", os.path.exists(path)):
        return rep
    manifest = _read_json(path)

    try:
        validate(manifest, ACQUISITION, context="acquisition_manifest")
        rep.check("acquisition_manifest_validates", True)
    except SchemaError as exc:
        rep.check("acquisition_manifest_validates", False, str(exc))
        return rep

    ac.require(manifest["artifact_class"])
    if artifact_class:
        rep.check("namespace_is_the_requested_one", manifest["artifact_class"] == artifact_class,
                  f"manifest says {manifest['artifact_class']!r}")
    entries = manifest["entries"]

    rep.check("manifest_content_hash_is_reproducible",
              _content_sha256(manifest) == manifest.get("content_sha256"),
              f"recomputed {_content_sha256(manifest)}")
    hits = contains_local_path(manifest)
    rep.check("no_machine_local_path_in_the_manifest", not hits, "; ".join(hits[:3]))

    check_bytes(rep, cache_root, entries)
    check_chains(rep, cache_root, entries)
    check_releases(rep, cache_root, manifest, entries)
    check_queue(rep, cache_root, manifest, run_dir=run_dir, inputs_root=inputs_root,
                direct_analysis=direct_analysis, direct=direct)
    if not rep.failed or all(r[0].startswith("chembl_") for r in rep.failed):
        check_graph(rep, cache_root, manifest, entries)

    deferred = {e["source"] for e in entries
                if e["acquisition_status"] == "not_acquired"}
    rep.check("deferred_lanes_are_declared_not_acquired",
              all(s in deferred for s in DEFERRED_LANES),
              f"declared: {sorted(deferred)}")
    return rep


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="offline verification of the Stage-3 public acquisition cache")
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--direct-run", required=True)
    ap.add_argument("--direct-inputs-root", required=True)
    ap.add_argument("--artifact_class", default=None, choices=[None, *ac.ARTIFACT_CLASSES])
    ap.add_argument("--direct-analysis", default=None)
    args = ap.parse_args(argv)

    try:
        rep = verify(args.cache_root, run_dir=args.direct_run,
                     inputs_root=args.direct_inputs_root,
                     direct_analysis=args.direct_analysis, artifact_class=args.artifact_class)
    except (direct_run.DirectRunError, armlever.ArmLeverError, ac.ArtifactClassError,
            KeyError, ValueError) as exc:
        print(f"[FAIL] acquisition_verification_aborted -- {exc}")
        return 1

    print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
