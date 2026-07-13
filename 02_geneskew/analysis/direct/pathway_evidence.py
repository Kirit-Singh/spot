"""The BYTES a pathway count can be recounted from.

THE GAP an independent audit found (W0, A3 follow-on). The pathway provenance bound the
gene-set bundle, both universes, the input files and the records — but NOT the ranking the
counts were taken from. ``n_hits_in_ranking`` is computed inside ``enrichment.enrich_one``
against a ranked list that lives only in memory and is never written. So the verifier could
only re-derive the coverage arithmetic FROM THE RECORD'S OWN DECLARED COUNTS: it checked
that the declared numbers were consistent with each other.

They always are, if you forge them together. Alter the declared member counts so a
zero-coverage pathway becomes headline-rankable in BOTH arms, reseal ``records_sha256``
honestly, and the artifact ADMITS with zero failed checks. Internal consistency is not
provenance. A count nobody can recount is a claim.

So the bundle now CARRIES the evidence the counts are taken from:

  * the FULL MAPPED MEMBERSHIP of each set, in BOTH namespaces, BEFORE this run's universes
    intersected it — plus the number of source symbols the published set had. The
    intersections the producer used ship beside it, explicitly labelled as its DECLARED
    OUTPUTS, so a verifier can re-derive them instead of adopting them;
  * the perturbation-TARGET universe — the ranked population membership is tested in;
  * each ARM's RANKING — the ordered target ids, their canonical scores and their ranks.
    This is the arm-evaluable universe, and it is exactly what ``n_hits_in_ranking`` counts
    against;
  * the MASKED SIGNATURES and the DE-READOUT universe the convergence claim is computed
    from, so a cosine can be recomputed rather than read.

This module is the PRODUCER half, and only that. It emits the bytes and binds them into the
run identity (raw sha256 AND canonical sha256, plus a logical path inside the bundle). An
INDEPENDENT verifier — which may not import this module, and does not — loads them, recounts,
and decides whether the declared counts survive. Generator is not verifier: a producer that
also wrote the check that its counts were honest would be marking its own homework.
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Optional

from . import config, enrichment
from .hashing import canonical_num, content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_pathway_evidence.v1"
EVIDENCE_FILE = "pathway_evidence.json"
SIGNATURES_FILE = "pathway_signatures.parquet"
GENE_SETS_FILE = "gene_sets.source.json"
EVIDENCE_KEY = "pathway_evidence"
SIGNATURES_KEY = "masked_signatures"
GENE_SETS_KEY = "gene_set_source"
SIGNATURE_COLUMNS = ("target_id", "gene_id", "value")

# WHAT each count is recounted against. Named, so the verifier and the producer are talking
# about the same universes rather than two things that share a word.
COUNT_RULE_ID = "spot.stage02.pathway.member_counts_are_recounted_from_the_bound_bytes.v1"
COUNT_RULE = (
    "n_genes_in_target_universe = |FULL mapped genes_target INTERSECT the bound target "
    "universe| ; n_hits_in_ranking = |FULL mapped genes_target INTERSECT that arm's ranked "
    "targets| ; n_ranked = |that arm's ranked targets| — recounted from the PRE-INTERSECTION "
    "membership, never from the producer's already-intersected output")


def arm_rankings(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Each arm's RANKING, as the enrichment actually walked it.

    The same ``enrichment.rank_targets`` the producer enriches with — so what is written is
    the ranking that was used, not a reconstruction of it that could differ. (The VERIFIER
    may not import this module, and does not: it recounts against these bytes.)
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for arm in config.ARMS:
        ranked = enrichment.rank_targets(rows, arm)
        out[arm] = [{"target_id": t, "score": canonical_num(v), "rank": i}
                    for i, (t, v) in enumerate(ranked, start=1)]
    return out


def membership(bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The FULL mapped membership of each set — BEFORE any universe intersection.

    The first cut of this emitted ``genes_in_target_universe`` (the ALREADY-INTERSECTED set)
    under the name ``genes_target``, which made the recount circular: intersecting an
    already-intersected set with the same universe returns itself, so
    ``n_genes_in_target_universe`` would have "re-derived" to agree with ANY declared value.
    A check that cannot fail is not a check.

    So what ships is the full mapped membership in each namespace — the crosswalk's output,
    before this run's universes touched it. An independent verifier intersects THESE against
    the bound target and readout universes and gets a number the producer did not choose.

    The intersections the producer actually used ship too, as DECLARED OUTPUTS — clearly
    named as such. They are the producer's answer, not the evidence for it.
    """
    if bundle is None:
        return {}
    return {
        set_id: {
            # THE EVIDENCE: full, mapped, pre-intersection.
            "genes_target": sorted(str(g) for g in s["genes_target"]),
            "genes_readout": sorted(str(g) for g in s["genes_readout"]),
            "n_genes_target": s["n_genes_target"],
            "n_genes_readout": s["n_genes_readout"],
            "n_source_symbols": s["n_source_symbols"],
            # THE PRODUCER'S DECLARED OUTPUTS: what it says the intersections came to.
            # Re-derivable from the evidence above; never a substitute for it.
            "declared_genes_in_target_universe": sorted(
                str(g) for g in s["genes_in_target_universe"]),
            "declared_n_genes_in_target_universe": s["n_genes_in_target_universe"],
            "declared_genes_in_readout_universe": sorted(
                str(g) for g in s["genes_in_universe"]),
            "declared_n_genes_in_readout_universe": s["n_genes_in_universe"],
        }
        for set_id, s in sorted(bundle["sets"].items())
    }


def build(rows: list[dict[str, Any]], bundle: Optional[dict[str, Any]],
          target_universe: dict[str, Any],
          readout_universe: dict[str, Any]) -> dict[str, Any]:
    """The whole evidence document. Ids, counts and canonical numbers — no prose."""
    return {
        "schema_version": SCHEMA_VERSION,
        "count_rule_id": COUNT_RULE_ID,
        "count_rule": COUNT_RULE,
        "arms": list(config.ARMS),
        # the ranked POPULATION — what membership is tested in
        "target_universe": sorted(str(t) for t in target_universe["target_ids"]),
        "target_universe_sha256": target_universe["sha256"],
        # the SIGNATURE VECTOR SPACE — what convergence is computed in. A different
        # universe, and collapsing the two was the B1 scientific bug.
        "readout_universe": [str(g) for g in readout_universe["gene_ids"]],
        "readout_universe_sha256": readout_universe["sha256"],
        "membership": membership(bundle),
        "arm_rankings": arm_rankings(rows),
    }


def signature_rows(signatures: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """The masked signatures, LONG. One row per (target, gene) that survived the mask.

    Long and columnar because a release signature matrix is signature-targets x ~10k readout
    genes: a nested JSON of it would be gigabytes, and an artifact too big to write is an
    artifact nobody binds.
    """
    return [{"target_id": str(t), "gene_id": str(g), "value": canonical_num(v)}
            for t, vec in sorted(signatures.items())
            for g, v in sorted(vec.items())]


def gene_set_source_block(source_path: str,
                          bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """WHICH gene-set bundle this run stood on — by CONTENT, and by a BUNDLE-RELATIVE path.

    The provenance named the gene-set release and its hashes, but the FILE lived wherever the
    operator happened to keep it. A verifier could therefore check that the run's gene sets
    hashed to X, but could not obtain X: it had to be handed the same file out of band, and
    an artifact whose evidence only exists on the machine that made it is not independently
    checkable.

    So the exact input JSON is copied into the bundle, BYTE FOR BYTE, and named by a path
    relative to the bundle — never an absolute machine path, which would be unusable to
    anyone else and would leak the producer's filesystem into a published artifact.
    """
    with open(source_path) as fh:
        doc = json.load(fh)
    block = {
        "logical_name": GENE_SETS_FILE,
        "path_in_bundle": GENE_SETS_FILE,
        "copied_byte_for_byte": True,
        # the bytes as supplied, and the content independent of their formatting
        "raw_sha256": file_sha256(source_path),
        "canonical_sha256": content_hash(doc),
        "schema_version": doc.get("schema_version"),
        "n_sets_in_source": len(doc.get("sets") or []),
    }
    if bundle is not None:
        block.update({
            "gene_set_release": bundle["gene_set_release"],
            "gene_set_license": bundle["gene_set_license"],
            "gene_set_license_reference": bundle["gene_set_license_reference"],
            "gene_id_namespace": bundle["gene_id_namespace"],
        })
    return block


def write(doc: dict[str, Any], sig_rows: list[dict[str, Any]], out_dir: str, *,
          gene_sets_source: Optional[str] = None) -> dict[str, str]:
    """Write the evidence artifacts INTO the bundle. Returns their paths."""
    from . import emit
    evidence_path = os.path.join(out_dir, EVIDENCE_FILE)
    emit.write_json(evidence_path, doc)
    signatures_path = os.path.join(out_dir, SIGNATURES_FILE)
    emit.write_parquet(sig_rows, signatures_path, sort_by=["target_id", "gene_id"])

    paths = {"evidence": evidence_path, "signatures": signatures_path}
    if gene_sets_source:
        # BYTE FOR BYTE. Not re-serialised: a re-emitted JSON is a different file that
        # happens to mean the same thing, and its raw hash would not be the hash the run
        # bound. The verifier is entitled to the exact bytes the producer read.
        gene_sets_path = os.path.join(out_dir, GENE_SETS_FILE)
        shutil.copyfile(gene_sets_source, gene_sets_path)
        paths["gene_sets"] = gene_sets_path
    return paths


def binding_block(doc: dict[str, Any], sig_rows: list[dict[str, Any]],
                  gene_sets: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """WHAT evidence this run stands on — bound into the RUN IDENTITY, by CONTENT.

    Canonical hashes only, because this block is hashed INTO the run id and the run id names
    the directory the files are written to: a raw byte hash cannot exist yet. The canonical
    hash is the stronger of the two anyway — it is over the CONTENT, so an independent
    verifier recomputing it from the shipped bytes catches any change to what the evidence
    SAYS, whatever the file looks like. The raw byte hashes are recorded beside the files
    once they exist (``written_block``).

    The parquet's canonical hash is taken over the ROWS, never the file: parquet bytes are
    not byte-stable across writers, and a hash that changes when nothing changed is a hash
    people learn to ignore.
    """
    return {
        "count_rule_id": doc["count_rule_id"],
        "count_rule": doc["count_rule"],
        EVIDENCE_KEY: {
            "logical_name": EVIDENCE_FILE,
            "path_in_bundle": EVIDENCE_FILE,
            "schema_version": doc["schema_version"],
            "canonical_sha256": content_hash(doc),
            "n_target_universe": len(doc["target_universe"]),
            "n_readout_universe": len(doc["readout_universe"]),
            "n_sets": len(doc["membership"]),
            "n_ranked_by_arm": {arm: len(r) for arm, r in doc["arm_rankings"].items()},
        },
        **({GENE_SETS_KEY: gene_sets} if gene_sets else {}),
        SIGNATURES_KEY: {
            "logical_name": SIGNATURES_FILE,
            "path_in_bundle": SIGNATURES_FILE,
            "columns": list(SIGNATURE_COLUMNS),
            "canonical_sha256": content_hash(sig_rows),
            "n_rows": len(sig_rows),
            "n_signature_targets": len({r["target_id"] for r in sig_rows}),
            "readout_universe_sha256": doc["readout_universe_sha256"],
        },
    }


def written_block(binding: dict[str, Any], paths: dict[str, str]) -> dict[str, Any]:
    """The identity block, plus the RAW byte hash of each file as it was actually written.

    The canonical hash proves WHAT the evidence says; the raw hash pins the exact bytes that
    say it. A verifier wants both: one that checked only the canonical hash would not notice
    it had been handed different bytes than the ones that were hashed.
    """
    out = {k: v for k, v in binding.items()
           if k not in (EVIDENCE_KEY, SIGNATURES_KEY, GENE_SETS_KEY)}
    for key, path_key in ((EVIDENCE_KEY, "evidence"), (SIGNATURES_KEY, "signatures")):
        out[key] = dict(binding[key], raw_sha256=file_sha256(paths[path_key]))

    if GENE_SETS_KEY in binding:
        block = dict(binding[GENE_SETS_KEY])
        copied = file_sha256(paths["gene_sets"])
        # The copy IS the source, or the artifact does not ship. A "byte-for-byte" copy
        # nobody checked is a claim, and this one is cheap to make true.
        if copied != block["raw_sha256"]:
            raise ValueError(
                f"the gene-set bundle copied into the artifact hashes to {copied!r}, but "
                f"the source it was read from hashes to {block['raw_sha256']!r}; the copy "
                "is not the file the run stood on")
        out[GENE_SETS_KEY] = dict(block, copy_verified=True)
    return out
