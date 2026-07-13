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

  * the gene-set MEMBERSHIP actually used (per set: its target-namespace members, and the
    number of source symbols the published set had);
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

import os
from typing import Any, Optional

from . import config, enrichment
from .hashing import canonical_num, content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_pathway_evidence.v1"
EVIDENCE_FILE = "pathway_evidence.json"
SIGNATURES_FILE = "pathway_signatures.parquet"
EVIDENCE_KEY = "pathway_evidence"
SIGNATURES_KEY = "masked_signatures"
SIGNATURE_COLUMNS = ("target_id", "gene_id", "value")

# WHAT each count is recounted against. Named, so the verifier and the producer are talking
# about the same universes rather than two things that share a word.
COUNT_RULE_ID = "spot.stage02.pathway.member_counts_are_recounted_from_the_bound_bytes.v1"
COUNT_RULE = (
    "n_genes_in_target_universe = |set members INTERSECT target universe| ; "
    "n_hits_in_ranking = |set members INTERSECT that arm's ranked targets| ; "
    "n_ranked = |that arm's ranked targets| — every one recounted from the bound evidence, "
    "never read from the record")


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
    """The gene-set membership USED, in the TARGET namespace, per set."""
    if bundle is None:
        return {}
    return {
        set_id: {
            "genes_target": sorted(str(g) for g in s["genes_in_target_universe"]),
            "n_source_symbols": s["n_source_symbols"],
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


def write(doc: dict[str, Any], sig_rows: list[dict[str, Any]],
          out_dir: str) -> dict[str, str]:
    """Write both evidence artifacts INTO the bundle. Returns their paths."""
    from . import emit
    evidence_path = os.path.join(out_dir, EVIDENCE_FILE)
    emit.write_json(evidence_path, doc)
    signatures_path = os.path.join(out_dir, SIGNATURES_FILE)
    emit.write_parquet(sig_rows, signatures_path, sort_by=["target_id", "gene_id"])
    return {"evidence": evidence_path, "signatures": signatures_path}


def binding_block(doc: dict[str, Any],
                  sig_rows: list[dict[str, Any]]) -> dict[str, Any]:
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
    out = {k: v for k, v in binding.items() if k not in (EVIDENCE_KEY, SIGNATURES_KEY)}
    for key, path_key in ((EVIDENCE_KEY, "evidence"), (SIGNATURES_KEY, "signatures")):
        out[key] = dict(binding[key], raw_sha256=file_sha256(paths[path_key]))
    return out
