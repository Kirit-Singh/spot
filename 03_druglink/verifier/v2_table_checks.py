"""The SIGN and TABLE checks, over the bytes the producer actually EMITTED.

Split from :mod:`verifier.v2_checks` (identity, schema, hygiene, upstream bindings) at the
500-line gate. Imports NOTHING from ``druglink``.

Three things live here, and they are the three a consumer would be hurt by:

  * the SIGN CONTRACT the bundle was built under is RECOMPUTED from the vocabulary the bundle
    publishes, and its semantic tables are required to be the ones this verifier restates;
  * the SIGN GATES are re-asserted on every emitted edge — a reconstruction mismatch refuses
    every inversion under ONE name, and these say WHICH;
  * the TABLES are compared, row for row, against an independent rebuild.
"""
from __future__ import annotations

from typing import Any, Optional

from . import canon, policy
from . import v2_admission as v2
from . import v2_contract as C
from . import v2_tables as T
from .report import Report


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def _content_hash(name: str, rows: list[dict[str, Any]]) -> str:
    """The hash the BUNDLE binds: display columns excluded, row order irrelevant."""
    return T.content_hash(name, rows)


def check_modality_vocabulary(rep: Report, *, doc: dict[str, Any]) -> Optional[str]:
    """The SIGN CONTRACT the bundle was built under — recomputed, then AGREED WITH or refused.

    Two separate things, and both must hold:

      1. the digest the bundle DECLARES is the content address of the vocabulary block it
         PUBLISHES (so the digest cannot name a contract nobody can read); and
      2. that block's SEMANTIC TABLES — which modality performs which target action, which drug
         mechanisms phenocopy it, and which (modality, sign) pair yields which modulation token —
         are EXACTLY the ones this verifier restates for itself.

    The prose in the block is the producer's; the tables that decide a direction are checked. A
    verifier that took the block on trust would let the producer redefine what "phenocopy" means
    and then grade itself against the new meaning.
    """
    method = doc.get("method") or {}
    published = method.get("modality_vocabulary")
    if not isinstance(published, dict) or not published:
        _gate(rep, C.GATE_MODALITY_VOCABULARY_DIVERGENCE,
              "the bundle PUBLISHES the sign contract it classified every edge under (a digest "
              "with no readable vocabulary behind it is an address for a document nobody has)",
              False, f"modality_vocabulary={type(published).__name__}")
        return None

    recomputed = canon.chash(published)
    _gate(rep, C.GATE_MODALITY_VOCABULARY_DIVERGENCE,
          "the modality-vocabulary digest the bundle binds is the content hash of the vocabulary "
          "it actually publishes (recomputed here from the block itself, never copied from the "
          "digest beside it)",
          method.get("modality_vocabulary_digest") == recomputed,
          f"declares {str(method.get('modality_vocabulary_digest'))[:16]}…, the block hashes to "
          f"{recomputed[:16]}…")

    mine = C.semantic_vocabulary()
    drift = sorted(k for k, v in mine.items() if published.get(k) != v)
    _gate(rep, C.GATE_MODALITY_VOCABULARY_DIVERGENCE,
          "the bundle's sign contract IS the one this verifier restates: the same SIGN_EPS "
          f"({C.SIGN_EPS!r}, bound from Stage-2 Direct and never retuned), the same sign states, "
          "the same modality->action table, the same phenocopying-mechanism set DERIVED from it "
          "for EACH modality, and the same (modality, sign)->modulation map. A producer free to "
          "redefine what phenocopies a knockdown could grade itself against the new meaning",
          not drift, f"divergent: {drift[:4]}")
    return recomputed if not drift else None


def check_sign_rule(rep: Report, *, doc: dict[str, Any],
                    emitted: dict[str, list[dict[str, Any]]]) -> None:
    """THE SIGN GATES, RE-ASSERTED ON THE EMITTED BYTES — not merely inside a reconstruction.

    A reconstruction mismatch already refuses any of these, but it refuses them all under ONE
    name. These say WHICH inversion was attempted, and they hold even where a table is not
    rebuilt row-for-row.
    """
    edges = emitted.get("target_drug_edges") or []
    refusals = [r for e in edges for r in C.edge_refusals(e)]
    _gate(rep, C.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
          "EVERY emitted edge re-derives its own direction: the sign it declares IS the sign of "
          "the arm_value it carries; its desired_target_modulation IS what that sign plus its "
          "DECLARED modality yield; its phenocopy flag IS what the restated engine says of its "
          "verbatim action_type; and no edge claims support without a mechanism that actually "
          "phenocopies what was tested, on a sign that actually supported the desired change",
          not refusals and bool(edges),
          f"{len(refusals)} refusal(s): {'; '.join(refusals[:2])}"
          if refusals else f"{len(edges)} edge(s)")

    # AT ANY DEPTH, over the document AND every table. An agonist reaches a consumer through a
    # summary, a count map or a candidate field a later writer added — not through the edge
    # builder that already has a gate.
    deep = C.agonists_in_supported_evidence([doc, emitted])
    _gate(rep, C.GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
          "NO AGONIST REACHES SUPPORTED EVIDENCE BY SIGN INVERSION — checked at ANY DEPTH, "
          "across the document and every table. An agonist never phenocopies a knockdown: on an "
          "opposing row it is the UNTESTED INVERSE of a deleterious result, an experiment nobody "
          "ran, and presenting it as observed support is the worst thing this lane could emit",
          not deep, "; ".join(deep[:3]))

    # THE INHIBITOR-OPPOSED ROW. It is KEPT, it is NAMED, and it never ranks — the row the
    # retired modality-fixed rule would have filed as supported evidence.
    opposing = [e for e in edges
                if e.get("observed_sign_state") == C.SIGN_OPPOSES_DESIRED_CHANGE]
    leaked = [e.get("edge_id") for e in opposing
              if e.get("directional_evidence_status") == policy.OBSERVED_PERTURBATION
              or bool(e.get("observed_perturbation_support"))]
    _gate(rep, C.GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN,
          "on a row whose knockdown moved the program the WRONG way, NOTHING is supported: an "
          "inhibitor phenocopies the UNDESIRED effect and is flagged OPPOSED (kept, named, never "
          "ranked), and an agonist is an untested inverse hypothesis. Neither is a measurement",
          not leaked, f"{len(leaked)} of {len(opposing)} opposing row(s): {leaked[:3]}")


def check_tables(rep: Report, *, emitted: dict[str, list[dict[str, Any]]],
                 rebuilt: dict[str, Any], doc: dict[str, Any],
                 manifest: dict[str, Any]) -> None:
    """RE-DERIVE every table hash, then compare the emitted rows to an independent rebuild."""
    n_edges = len(rebuilt["target_drug_edges"])
    _gate(rep, C.GATE_EMPTY_EVIDENCE,
          "the independent reconstruction is NON-VACUOUS: the admitted store's source "
          "assertions actually REACH the Stage-2 arms. Zero reachable evidence is silent "
          "zero-coverage wearing a green check — the exact shape of the B6 defect",
          n_edges > 0 and bool(rebuilt["source_records"]),
          f"{n_edges} edge(s), {len(rebuilt['source_records'])} source record(s)")

    # EVERY arm slot, including the ones nothing reached. An arm that no drug evidence found
    # is emitted with n_edges=0 and NAMES the absence; a missing row would make it
    # indistinguishable from an arm that never ran.
    slots = emitted.get("arm_slots") or []
    silent = [s for s in slots if s.get("n_edges") == 0]
    _gate(rep, C.GATE_ARM_SLOTS_INCOMPLETE,
          f"the bundle emits ALL {C.N_ARM_SLOTS} arm slots the release resolved — including "
          "any that no drug evidence reached, each carrying n_edges and an evidence state "
          "that NAMES the absence. Without them, 'this arm had no drug evidence' and 'this "
          "arm never ran' are the same silence",
          len(slots) == C.N_ARM_SLOTS == len(rebuilt["arm_slots"])
          and all(s.get("arm_evidence_state") == T.NO_DRUG_EVIDENCE for s in silent),
          f"{len(slots)} slot(s), {len(silent)} with zero evidence")

    # A COUNT OF ROWS IS NOT A COUNT OF RANKS. Stage 2 RETAINS every unrankable target with a
    # null rank, so a hit count taken from rows inflates by exactly the targets the arm could
    # not evaluate — the ones least entitled to support a claim.
    inflated = [s.get("arm_slot_id") for s in slots
                if s.get("n_ranked") is None or int(s.get("n_ranked")) > int(s.get("n_records"))]
    _gate(rep, C.GATE_HIT_COUNT_COUNTED_ROWS_NOT_RANKS,
          "every arm slot reports n_ranked (NON-NULL RANKS) and n_records (ROWS) as the "
          "different numbers they are, and no arm claims more ranks than it has rows",
          not inflated and bool(slots), f"{len(inflated)}: {inflated[:3]}")

    # A NULL RANK NEVER BECAME A ZERO. A 0 sorts, and it sorts as BEST.
    coerced = [e.get("edge_id") for e in (emitted.get("target_drug_edges") or [])
               if e.get("arm_rank") == 0
               or (e.get("arm_rank") is None and e.get("arm_rank_status") == T.RANKED)]
    _gate(rep, C.GATE_NULL_RANK_COERCED_TO_ZERO,
          "no null rank was coerced to a 0 (Stage-2 ranks start at 1; a 0 here is a null someone "
          "coerced — and it sorts as first place for a target nobody ranked)",
          not coerced, f"{len(coerced)}: {coerced[:3]}")

    # THE UNADMITTED PATHWAY LANE CONTRIBUTED EXACTLY ZERO — by name, not by omission.
    pathway_edges = [e.get("edge_id") for e in (emitted.get("target_drug_edges") or [])
                     if e.get("origin_type") in v2.INFERRED_ORIGINS
                     or e.get("lane") == C.LANE_PATHWAY]
    context_rows = emitted.get("pathway_context") or []
    _gate(rep, C.GATE_PATHWAY_LANE_CONTRIBUTED,
          "the PATHWAY lane contributed NOTHING: not one edge in target_drug_edges carries a "
          "pathway origin, and the pathway_context table is EMPTY. Its verifier fails open — "
          "bytes admitted by a fail-open gate are unadmitted bytes with a certificate stapled to "
          "them — and a pathway record is a gene-set ENRICHMENT with no CRISPRi sign to give a "
          "drug a direction. ZERO is the honest output, and it is checked rather than assumed",
          not pathway_edges and not context_rows,
          f"{len(pathway_edges)} pathway edge(s), {len(context_rows)} context row(s)")

    # AN ENRICHMENT VALUE NEVER SOURCED AN EDGE, and a gene-set id never became a target.
    set_level = [e.get("edge_id") for e in (emitted.get("target_drug_edges") or [])
                 if any(e.get(f) not in (None, "")
                        for f in ("enrichment_value", "coverage", "convergence"))]
    _gate(rep, C.GATE_ENRICHMENT_SOURCED_AN_EDGE,
          "no drug edge was sourced from a SET-LEVEL statistic (nobody knocked down a set: an "
          "enrichment value has no sign, and sourcing an edge from one would hand a set-level "
          "number a direction it never had — guilt by association wearing the costume of a "
          "measurement)",
          not set_level, f"{len(set_level)}: {set_level[:3]}")

    mismatched, hashed = [], {}
    for name in sorted(C.TABLES):
        got = emitted.get(name)
        if got is None:
            mismatched.append(f"{name}: table absent from the bundle")
            continue
        # `provenance` binds the producer's own code/vocabulary digests, so it is checked
        # against what this verifier re-admitted (check_provenance) rather than rebuilt.
        want = rebuilt.get(name) if name in C.RECONSTRUCTED_TABLES else got
        if want is None:
            # A table the reconstruction did not produce is a NAMED refusal, never a traceback:
            # a crash is not a verdict, and a verifier that dies is one nobody can read.
            mismatched.append(f"{name}: the independent reconstruction produced no such table")
            continue
        hashed[name] = _content_hash(name, want)
        # EVERY column, display included: the bundle id need not cover a label, but an
        # independent reconstruction still has to reproduce one.
        if T.full_hash(name, got) != T.full_hash(name, want):
            mismatched.append(
                f"{name}: emitted {len(got)} row(s), reconstruction {len(want)}")

    _gate(rep, C.GATE_RECONSTRUCTION_MISMATCH,
          "every emitted table reproduces EXACTLY what an independent pass reconstructs from "
          "the Stage-2 bundles and the admitted store — arm slots, target-drug edges, arm "
          "summaries, candidates, source records and dispositions. Direction is re-translated "
          "from the verbatim action_type_source; the bundle's own intervention_effect is "
          "never read",
          not mismatched, "; ".join(mismatched[:4]))

    declared = doc.get("table_hashes") or {}
    drift = sorted(k for k, v in hashed.items() if declared.get(k) != v)
    _gate(rep, C.GATE_TABLE_HASH_DRIFT,
          "every table hash the document and the manifest bind is the hash of the table this "
          "verifier rebuilt (row-order invariant, so permuting rows cannot change an id)",
          not drift and (manifest.get("table_hashes") or {}) == declared
          and set(declared) == set(C.TABLES),
          f"drift={drift}")

    want = sorted((dict(sorted(c.items())) for c in rebuilt["candidates"]),
                  key=lambda c: str(c["candidate_id"]))
    got = doc.get("candidates") or []
    _gate(rep, C.GATE_RECONSTRUCTION_MISMATCH,
          "the document's candidate block IS the reconstructed candidate set, in stable "
          "content-id order (there is no candidate-level winner, no combined objective and "
          "no rank, so the order carries no claim — and a permuted table must not move the "
          "bundle id)",
          canon.cjson(got) == canon.cjson(want),
          f"document carries {len(got)} candidate(s), reconstruction {len(want)}")
