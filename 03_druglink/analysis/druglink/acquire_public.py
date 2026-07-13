"""Bounded, real UniProt + ChEMBL 37 acquisition.

    PYTHONPATH=analysis python -m druglink.acquire_public \\
      --artifact-class analysis \\
      --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT" \\
      --top-per-arm 25 --sources uniprot,chembl --chembl-release CHEMBL_37 \\
      --cache-root "$STAGE3_CACHE"

The order of operations is the whole point:

  1. Admit the Direct run (Direct's own standalone verifier runs and must pass).
  2. Expand both arms, take the top N per arm INDEPENDENTLY by that arm's own rank.
  3. FREEZE that queue and the policy, bind them into ``acquisition_id``, and write
     them to the cache -- **before a single HTTP response has been seen**.
  4. Only then fetch.

So the queue cannot be tuned to the answers. There is no adaptive expansion, no
"stop when enough drugs are found", and no retry with a wider net: ZERO candidates
is a valid, successful result. Every page of every response is retained verbatim
with the headers, release, counts and pagination the source actually returned.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from . import armlever, artifact_class as ac, direct_run, http_public as hp
from .acq_manifest import (CHEMBL_ATTRIBUTION, CHEMBL_DATA, CHEMBL_LICENSE,
                           CHEMBL_LIMIT, UNIPROT_ATTRIBUTION, UNIPROT_ENDPOINT,
                           UNIPROT_FIELDS, UNIPROT_LICENSE, UNIPROT_PAGE_SIZE,
                           UNIPROT_SEARCH, build_manifest)
from .hashing import canonical_json, content_hash, sha256_hex, short_id

ACQUISITION_POLICY_VERSION = "stage3-acquire-public-v1"
QUEUE_FILE = "target_queue.json"
MANIFEST_FILE = "acquisition_manifest.json"
ACQUIRED_BY = "druglink.acquire_public/" + ACQUISITION_POLICY_VERSION

# The source identities, the manifest assembly and the manifest content hash live in
# `acq_manifest`; they are re-exported here because they are part of this module's
# published surface (the tests and the offline verifier read them from both).
MOLECULE_CHUNK_SIZE = 20            # ids per molecule_chembl_id__in request

SINGLE_PROTEIN = "SINGLE PROTEIN"
HUMAN_TAXON = "9606"

# Lanes this release does NOT acquire. They are declared, not omitted: an absent
# lane must read as "not evaluated", never as "no evidence".
DEFERRED = {
    "open_targets": "open_targets_known_drugs",
    "pubchem": "pubchem_property",
    "rxnorm": "rxnorm_allrelated",
    "lincs": "lincs_signature_support",
    "gbm_atlas": "gbm_patient_summary",
}
DEFERRED_NO_ADAPTER = ("depmap",)   # no adapter exists at all: a lane, not a source
DEFERRED_REASON = ("deferred lane: not acquired in the bounded UniProt+ChEMBL "
                   "research release; state is not_evaluated, not absence of evidence")
ACTIVITY_NOT_ACQUIRED = (
    "ChEMBL activity/potency was not acquired in this release; potency state is "
    "not_evaluated. It is not zero and not an absence of activity.")


class AcquireError(RuntimeError):
    """The acquisition cannot proceed honestly, so it does not proceed at all."""


# --------------------------------------------------------------------------- #
# 1. freeze                                                                     #
# --------------------------------------------------------------------------- #

def freeze_queue(direct: direct_run.DirectRun, *, top_per_arm: int,
                 sources: tuple[str, ...], chembl_release: str,
                 artifact_class: str) -> dict[str, Any]:
    """The frozen queue + policy, bound into an ID before any response exists."""
    expansion = armlever.expand(direct.screen, direct_run_id=direct.run_id)
    queue = armlever.select_acquisition_targets(expansion["arm_levers"],
                                                top_per_arm=top_per_arm)
    genes = armlever.query_genes(queue)
    policy = {
        "acquisition_policy_version": ACQUISITION_POLICY_VERSION,
        "artifact_class": artifact_class,
        "top_per_arm": top_per_arm,
        "selection_rule": "top_n_per_arm_independently_by_that_arms_own_direct_rank",
        "union_rule": "union_is_for_network_efficiency_only_arm_and_rank_retained",
        "adaptive_expansion_permitted": False,
        "stop_when_enough_drugs_found": False,
        "zero_candidates_is_a_valid_result": True,
        "sources": list(sources),
        "chembl_release_declared": chembl_release,
        "uniprot_query_template": "xref:ensembl-<ENSG> AND organism_id:9606",
        "uniprot_fields": UNIPROT_FIELDS,
        "uniprot_page_size": UNIPROT_PAGE_SIZE,
        "chembl_limit": CHEMBL_LIMIT,
        "molecule_chunk_size": MOLECULE_CHUNK_SIZE,
        "direct_gene_lane_rule": (
            "only_an_exact_SINGLE_PROTEIN_chembl_target_carrying_the_mapped_"
            "accession_enters_the_direct_gene_lane"),
        "activity_acquired": False,
        "potency_state_when_absent": "not_evaluated",
    }
    frozen = {
        "policy": policy,
        "direct_binding": direct.binding,
        "target_queue": queue,
        "query_genes": genes,
        "per_arm_counts": {arm: sum(1 for t in queue if t["desired_arm"] == arm)
                           for arm in armlever.ARMS},
    }
    frozen["target_queue_sha256"] = content_hash(queue)
    frozen["acquisition_id"] = short_id(frozen, 32)
    return frozen


def write_queue(cache_root: str, frozen: dict[str, Any]) -> str:
    """Write the frozen queue FIRST. The cache records the question before answers."""
    os.makedirs(cache_root, exist_ok=True)
    path = os.path.join(cache_root, QUEUE_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(frozen))
    return path


# --------------------------------------------------------------------------- #
# 2. read the bytes back, exactly                                              #
# --------------------------------------------------------------------------- #

def ensembl_accessions(pages: list[hp.Page], ensg: str) -> list[str]:
    """Accessions whose entry carries an EXACT Ensembl GeneId xref for this gene.

    Every match is kept: one-to-many is real and is never reduced to one accession.
    A gene-symbol resemblance is not a cross-reference and maps nothing.
    """
    found: set[str] = set()
    for page in pages:
        for rec in page.body_json.get("results") or []:
            acc = rec.get("primaryAccession")
            if not acc:
                continue
            for xref in rec.get("uniProtKBCrossReferences") or []:
                if xref.get("database") != "Ensembl":
                    continue
                for prop in xref.get("properties") or []:
                    if (prop.get("key") == "GeneId"
                            and str(prop.get("value") or "").split(".")[0] == ensg):
                        found.add(acc)
    return sorted(found)


def single_protein_targets(pages: list[hp.Page], accession: str) -> list[str]:
    """ChEMBL target IDs eligible for the direct-gene lane.

    A PROTEIN FAMILY / COMPLEX / PROTEIN-PROTEIN INTERACTION target that merely
    CONTAINS this accession is NOT translated into the gene: its components are
    other genes too, and no frozen rule assigns the effect to one of them.
    """
    out: set[str] = set()
    for page in pages:
        for tgt in page.body_json.get("targets") or []:
            if tgt.get("target_type") != SINGLE_PROTEIN:
                continue
            accs = {c.get("accession") for c in tgt.get("target_components") or []}
            if accession in accs and tgt.get("target_chembl_id"):
                out.add(tgt["target_chembl_id"])
    return sorted(out)


def molecule_ids(pages: list[hp.Page]) -> list[str]:
    ids: set[str] = set()
    for page in pages:
        for mech in page.body_json.get("mechanisms") or []:
            if mech.get("molecule_chembl_id"):
                ids.add(mech["molecule_chembl_id"])
    return sorted(ids)


def chunks(ids: list[str], size: int) -> list[list[str]]:
    """Sorted, frozen chunks. The chunking is fixed before any molecule is fetched."""
    ordered = sorted(set(ids))
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


# --------------------------------------------------------------------------- #
# 3. fetch + record                                                            #
# --------------------------------------------------------------------------- #

def _group_id(source: str, adapter: str, endpoint: str, query: dict[str, str],
              context: dict[str, Any]) -> str:
    return short_id({"source": source, "adapter": adapter, "endpoint": endpoint,
                     "query": query, "context": context}, 32)


def _write_raw(cache_root: str, rel: str, data: bytes) -> None:
    path = os.path.join(cache_root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def fetch_pages(transport: hp.Transport, base: str, query: dict[str, str], *,
                adapter: str, origin: str) -> list[hp.Page]:
    """Every page of one logical query. Fetched exactly once."""
    return hp.paginate(transport, hp.canonical_url(base, query), adapter=adapter,
                       origin=origin)


def record_group(pages: list[hp.Page], *, cache_root: str, source: str,
                 adapter: str, endpoint: str, query: dict[str, str],
                 context: dict[str, Any], release: str,
                 release_date: Optional[str], license_: str,
                 attribution: str) -> list[dict[str, Any]]:
    """One manifest entry per page: bytes, headers, release, place in the chain."""
    gid = _group_id(source, adapter, endpoint, query, context)
    entries: list[dict[str, Any]] = []
    for i, page in enumerate(pages):
        rel = f"raw/{source}/{adapter}/{gid}_p{i:03d}.json"
        _write_raw(cache_root, rel, page.response.body)
        entries.append({
            "source": source,
            "adapter": adapter,
            "source_release": release,
            "source_release_date": release_date,
            "source_endpoint": endpoint,
            "retrieval_url": page.url,
            "query": dict(query),
            "request_group_id": gid,
            "page_index": i,
            "request_context": context,
            "license": license_,
            "attribution": attribution,
            "acquisition_status": "acquired_public",
            "not_acquired_reason": None,
            "raw_file": rel,                       # RELATIVE: no machine-local path
            "raw_sha256": sha256_hex(page.response.body),
            "raw_bytes": len(page.response.body),
            "raw_media_type": page.response.header("content-type"),
            "response_headers": hp.observed_headers(page),
            "pagination": hp.pagination_record(pages, i),
            "access_record": hp.access_record(page, acquired_by=ACQUIRED_BY),
        })
    return entries


def _uniprot_query(ensg: str) -> dict[str, str]:
    return {"query": f"xref:ensembl-{ensg} AND organism_id:{HUMAN_TAXON}",
            "format": "json", "fields": UNIPROT_FIELDS, "size": UNIPROT_PAGE_SIZE}


def _uniprot_release(pages: list[hp.Page]) -> tuple[str, Optional[str]]:
    """The release the RESPONSE reported. Never a value copied from a document."""
    releases = {p.response.header("x-uniprot-release") for p in pages}
    if len(releases) != 1 or None in releases:
        raise AcquireError(
            f"UniProt pages did not agree on one release: {sorted(map(str, releases))}")
    dates = {p.response.header("x-uniprot-release-date") for p in pages}
    return releases.pop(), (dates.pop() if len(dates) == 1 else None)


def _chembl_release(transport: hp.Transport, cache_root: str,
                    declared: str) -> dict[str, Any]:
    """Pin ChEMBL's own current-release record alongside the API responses."""
    url = hp.canonical_url(CHEMBL_DATA + "/status.json", {})
    page = hp.fetch_page(transport, url, adapter="chembl_status", index=0,
                         origin=hp.CHEMBL_ORIGIN)
    actual = page.body_json.get("chembl_db_version")
    if not actual:
        raise AcquireError("ChEMBL status.json carries no chembl_db_version")
    if str(actual).upper() != declared.upper():
        raise AcquireError(
            f"ChEMBL is serving {actual!r} but the run declared {declared!r}; "
            "refusing to label a response with a release it did not come from")
    rel = "raw/chembl/chembl_status/status.json"
    _write_raw(cache_root, rel, page.response.body)
    return {
        # VERBATIM from the response, including its capitalisation.
        "source_release": str(actual),
        "release_declared": declared,
        "release_date": page.body_json.get("chembl_release_date"),
        "source_endpoint": "/chembl/api/data/status",
        "retrieval_url": url,
        "raw_file": rel,
        "raw_sha256": sha256_hex(page.response.body),
        "raw_bytes": len(page.response.body),
        "license": CHEMBL_LICENSE,
        "attribution": CHEMBL_ATTRIBUTION,
        "access_record": hp.access_record(page, acquired_by=ACQUIRED_BY),
    }


def _deferred_entries() -> list[dict[str, Any]]:
    entries = [{
        "source": source, "adapter": adapter,
        "source_release": "not_acquired", "source_endpoint": "not_acquired",
        "retrieval_url": None, "query": {}, "license": "not_acquired",
        "attribution": None, "acquisition_status": "not_acquired",
        "not_acquired_reason": DEFERRED_REASON,
        "raw_file": None, "raw_sha256": None, "raw_bytes": None,
        "raw_media_type": None, "access_record": None,
    } for source, adapter in sorted(DEFERRED.items())]
    entries.append({
        "source": "chembl", "adapter": "chembl_activity",
        "source_release": "not_acquired",
        "source_endpoint": "/chembl/api/data/activity",
        "retrieval_url": None, "query": {}, "license": CHEMBL_LICENSE,
        "attribution": CHEMBL_ATTRIBUTION, "acquisition_status": "not_acquired",
        "not_acquired_reason": ACTIVITY_NOT_ACQUIRED,
        "raw_file": None, "raw_sha256": None, "raw_bytes": None,
        "raw_media_type": None, "access_record": None,
    })
    return entries


def acquire(*, cache_root: str, artifact_class: str, direct: direct_run.DirectRun,
            top_per_arm: int, sources: tuple[str, ...], chembl_release: str,
            transport: hp.Transport) -> dict[str, Any]:
    """Freeze, then fetch. Never the other way round."""
    ac.require(artifact_class)
    if "uniprot" not in sources:
        raise AcquireError("uniprot is required: ChEMBL is queried by accession")

    frozen = freeze_queue(direct, top_per_arm=top_per_arm, sources=sources,
                          chembl_release=chembl_release, artifact_class=artifact_class)
    write_queue(cache_root, frozen)          # ---- the question, before any answer

    entries: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    uni_pages: list[hp.Page] = []

    def group(pages: list[hp.Page], rows: list[dict[str, Any]],
              kind: str, ctx: dict[str, Any]) -> None:
        groups.append({
            "request_group_id": rows[0]["request_group_id"],
            "kind": kind, "source": rows[0]["source"], "adapter": rows[0]["adapter"],
            "source_endpoint": rows[0]["source_endpoint"], "query": rows[0]["query"],
            "request_context": ctx, "n_pages": len(pages),
            "expected_total_count": pages[0].total_count,
            "observed_total_count": sum(p.n_records for p in pages),
            "page_sha256": [r["raw_sha256"] for r in rows],
        })
        entries.extend(rows)

    release_chembl = (_chembl_release(transport, cache_root, chembl_release)
                      if "chembl" in sources else None)

    gene_map: dict[str, list[str]] = {}
    for ensg in frozen["query_genes"]:
        query = _uniprot_query(ensg)
        pages = fetch_pages(transport, UNIPROT_SEARCH, query,
                            adapter="uniprot_search", origin=hp.UNIPROT_ORIGIN)
        uni_pages.extend(pages)
        # One run, one release. A release that changes mid-run means the pages are
        # not one snapshot, and a mixed snapshot is not a result.
        release, date = _uniprot_release(uni_pages)
        ctx = {"target_ensembl": ensg}
        rows = record_group(pages, cache_root=cache_root, source="uniprot",
                            adapter="uniprot_search", endpoint=UNIPROT_ENDPOINT,
                            query=query, context=ctx, release=release,
                            release_date=date, license_=UNIPROT_LICENSE,
                            attribution=UNIPROT_ATTRIBUTION)
        group(pages, rows, "uniprot_gene_to_accession", ctx)
        gene_map[ensg] = ensembl_accessions(pages, ensg)

    accessions = sorted({a for accs in gene_map.values() for a in accs})
    target_ids: list[str] = []
    if release_chembl:
        chembl_rel = release_chembl["source_release"]
        chembl_date = release_chembl["release_date"]

        def chembl_group(kind: str, adapter: str, endpoint: str, path: str,
                         query: dict[str, str], ctx: dict[str, Any]) -> list[hp.Page]:
            pages = fetch_pages(transport, CHEMBL_DATA + path, query,
                                adapter=adapter, origin=hp.CHEMBL_ORIGIN)
            rows = record_group(pages, cache_root=cache_root, source="chembl",
                                adapter=adapter, endpoint=endpoint, query=query,
                                context=ctx, release=chembl_rel,
                                release_date=chembl_date, license_=CHEMBL_LICENSE,
                                attribution=CHEMBL_ATTRIBUTION)
            group(pages, rows, kind, ctx)
            return pages

        # Every mapped accession is queried -- one-to-many is never reduced to one.
        for acc in accessions:
            pages = chembl_group(
                "chembl_accession_to_target", "chembl_target",
                "/chembl/api/data/target", "/target.json",
                {"target_components__accession": acc, "limit": CHEMBL_LIMIT},
                {"uniprot_accession": acc})
            target_ids.extend(single_protein_targets(pages, acc))

        molecules: list[str] = []
        for tid in sorted(set(target_ids)):
            pages = chembl_group(
                "chembl_target_to_mechanism", "chembl_mechanism",
                "/chembl/api/data/mechanism", "/mechanism.json",
                {"target_chembl_id": tid, "limit": CHEMBL_LIMIT},
                {"target_chembl_id": tid})
            molecules.extend(molecule_ids(pages))

        # Sorted and frozen BEFORE retrieval: the chunk boundaries cannot depend on
        # what any molecule response turns out to say.
        for n, chunk in enumerate(chunks(molecules, MOLECULE_CHUNK_SIZE)):
            chembl_group(
                "chembl_molecule_chunk", "chembl_molecule",
                "/chembl/api/data/molecule", "/molecule.json",
                {"molecule_chembl_id__in": ",".join(chunk), "limit": CHEMBL_LIMIT},
                {"molecule_chunk_index": n, "molecule_chembl_ids": chunk})

    entries.extend(_deferred_entries())
    manifest = build_manifest(
        artifact_class=artifact_class, frozen=frozen, entries=entries, groups=groups,
        uniprot_release=(_uniprot_release(uni_pages) if uni_pages else (None, None)),
        chembl_release=release_chembl, gene_map=gene_map, accessions=accessions,
        target_ids=sorted(set(target_ids)))

    path = os.path.join(cache_root, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(manifest))
    return {"manifest": manifest, "frozen": frozen, "cache_root": cache_root}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="bounded, real UniProt + ChEMBL public acquisition")
    ap.add_argument("--artifact_class", required=True, choices=list(ac.ARTIFACT_CLASSES))
    ap.add_argument("--direct-run", required=True)
    ap.add_argument("--direct-inputs-root", required=True)
    ap.add_argument("--top-per-arm", type=int, required=True)
    ap.add_argument("--sources", default="uniprot,chembl")
    ap.add_argument("--chembl-release", default="CHEMBL_37")
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--direct-analysis", default=None)
    args = ap.parse_args(argv)

    sources = tuple(sorted(s.strip() for s in args.sources.split(",") if s.strip()))
    unknown = [s for s in sources if s not in ("uniprot", "chembl")]
    if unknown:
        print(f"REFUSED: unknown source(s) {unknown}; this release acquires only "
              "uniprot and chembl")
        return 2
    try:
        direct = direct_run.load(args.direct_run, args.direct_inputs_root,
                                 artifact_class=args.artifact_class,
                                 direct_analysis=args.direct_analysis)
        out = acquire(cache_root=args.cache_root, artifact_class=args.artifact_class,
                      direct=direct, top_per_arm=args.top_per_arm, sources=sources,
                      chembl_release=args.chembl_release,
                      transport=hp.default_transport())
    except (direct_run.DirectRunError, armlever.ArmLeverError, AcquireError,
            hp.HttpError, ac.ArtifactClassError) as exc:
        print(f"REFUSED [{args.artifact_class}]: {exc}")
        return 2

    m = out["manifest"]
    print(f"acquisition_id   {m['acquisition_id']}")
    print(f"direct_run       {m['acquisition_binding']['direct_run_id']}")
    print(f"top_per_arm      {m['acquisition_binding']['policy']['top_per_arm']}")
    print(f"target_queue     {m['counts']['n_query_targets']} rows "
          f"({m['acquisition_binding']['per_arm_counts']}), "
          f"{m['counts']['n_query_genes']} gene(s)")
    print(f"releases         {json.dumps({k: v.get('source_release') for k, v in m['releases'].items()})}")
    print(f"pages            {m['counts']['n_pages']} in "
          f"{m['counts']['n_request_groups']} request group(s)")
    print(f"accessions       {m['counts']['n_uniprot_accessions']}, "
          f"single-protein targets {m['counts']['n_single_protein_targets']}")
    print(f"content_sha256   {m['content_sha256']}")
    print("zero candidates is a valid result; run druglink.verify_acquisition next")
    return 0


if __name__ == "__main__":
    sys.exit(main())
