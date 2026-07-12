"""The contributor-evidence bundle, built in the ONE order the contract allows.

The record id binds the completeness proof (``record_id.py``), so the evidence can
only be constructed in one direction:

    raw source  ->  the kept offsets + row names it actually holds
                ->  source records carrying that proof
                ->  the record ids DERIVED from it
                ->  the manifest citations that name those ids

Nothing here may run backwards. A manifest row cannot mint its own citation: its
payload does not hold the offset proof, and the proof is what the id is a hash of.
That is the whole point of the rule, and a fixture that could shortcut it would be
testing a rule the runtime does not have.

The evidence domain is GLOBAL POOLED-MAIN ONLY (``domain.py``). No guide-slot and no
donor-pair rows are emitted here: they carry no contributor evidence in this pass, and
a support row inside a pooled-main manifest is a claim with no method behind it.

ATTACK HOOKS. Each forges one artifact and then pins the forgery HONESTLY, so a
refusal has to come from the content and never from a hash mismatch:

    source_rows_fn  the RAW SOURCE, after the records were built against the pristine
                    rows — the records' proof goes stale and only a replay can see it
    records_fn      the source-record TABLE
    replay_fn       the replay REPORT
    manifest_rows_fn  the manifest ROWS, before records are built — so the forgery is
                    carried consistently all the way through the table and the ids
                    (the honest-producer attack), and only the raw source refuses it
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from fixtures_spec import CONDITION, TargetSpec

# The literal public evidence: GWCD4i.pseudobulk_merged.h5ad obs.guide_id.
IDENTITY_METHOD = "released_per_guide_identity_column"
SOURCE_CLASS = "marson_gwcd4i_public_release"
PINNED_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"

SOURCE_NAME = "GWCD4i.pseudobulk_merged.h5ad"
RECORD_TABLE_NAME = "stage02_source_records.json"
REPLAY_REPORT_NAME = "stage02_source_replay.json"
MANIFEST_NAME = "contributing_guides.manifest.json"
REGISTRY_NAME = "source_registry.json"

# Two kept pseudobulk rows per contributor, with a DROPPED row wedged between them.
# So an offset proof is a genuine, non-contiguous, multi-row array: an implementation
# that assumed one row per contributor, or that took a contiguous span, or that forgot
# to filter on keep_for_DE, produces a different proof and fails.
KEPT_SAMPLES = ("d1", "d2")
TARGETING = "targeting"
NON_TARGETING = "non_targeting"
# Non-targeting controls live under their own pseudo-target, exactly as a control does:
# they are kept for the fit but belong to no perturbation scope, so no released scope's
# contributor set contains them. Citing one is the attack that must be caught.
NON_TARGETING_TARGET = "NON_TARGETING"
NON_TARGETING_GUIDES = ("g-NT-1", "g-NT-2")


def contributing_guides(spec: TargetSpec) -> list[str]:
    """The guides that actually contributed to the POOLED estimate.

    ``manifest_main`` when the spec names one (the library may hold guides that never
    contributed), else the whole library. The released guide SLOTS are not consulted:
    a slot name is not evidence of which guide contributed, and support is out of
    domain in this pass.
    """
    guides = spec.manifest_main if spec.manifest_main is not None else spec.lib_guides
    return sorted(g for g in guides if g)


def main_ambiguous(spec: TargetSpec) -> bool:
    """Is the pooled identity UNPROVEN — the six-style ambiguous scope?

    An ambiguous scope proves no guide, so it holds no contributor rows in the raw
    source, mints no record, and cites nothing.
    """
    return "main" in spec.ambiguous_estimates or not spec.lib_guides


# --------------------------------------------------------------------------- #
# 1. THE RAW SOURCE — pinned FIRST. Everything downstream is derived from it.
# --------------------------------------------------------------------------- #
def raw_source_rows(specs: list[TargetSpec],
                    conditions: Sequence[str] = (CONDITION,)) -> list[dict[str, Any]]:
    """The rows the SOURCE itself holds, structurally faithful to the release.

    obs.guide_id is the literal per-guide identity column, obs.perturbed_gene_id names
    the target in ITS OWN namespace, obs.culture_condition / obs.keep_for_DE /
    obs.guide_type are the release's own columns, and the obs index NAMES each row.

    A contributor set is per (target, CONDITION): the release fits each condition
    separately, so a multi-condition source holds the contributor rows once per
    condition and the offset proof is condition-scoped.
    """
    rows: list[dict[str, Any]] = []

    def emit(target, guide, cond, keep, sample, gtype=TARGETING):
        rows.append({
            "pseudobulk_id": f"{target}|{guide}|{cond}|{sample}",
            "guide_id": guide, "perturbed_gene_id": target,
            "culture_condition": cond, "keep_for_DE": keep,
            "guide_type": gtype})

    for cond in conditions:
        for spec in sorted(specs, key=lambda s: s.target):
            if main_ambiguous(spec):
                continue                  # an unproven scope shows no contributor rows
            for guide in contributing_guides(spec):
                emit(spec.target, guide, cond, True, KEPT_SAMPLES[0])
                # NOT kept for DE. It sits INSIDE the contributor's row span, so the
                # proof is [i, i+2] — an offset array only a keep_for_DE filter produces.
                emit(spec.target, guide, cond, False, "dropped")
                emit(spec.target, guide, cond, True, KEPT_SAMPLES[1])

        for guide in NON_TARGETING_GUIDES:   # controls: kept, but never a contributor
            emit(NON_TARGETING_TARGET, guide, cond, True, KEPT_SAMPLES[0],
                 NON_TARGETING)
    return rows


def kept_proof(raw: list[dict[str, Any]]) -> dict[tuple, dict[str, list]]:
    """(target, condition, guide) -> the EXACT kept offsets and row names.

    Derived here, independently of the code under test, so the fixture never asks the
    verifier what the truth is. This is the same grouping ``replay.derive_from_source``
    makes; the two agreeing is the test, not the assumption.
    """
    proof: dict[tuple, dict[str, list]] = {}
    for i, row in enumerate(raw):
        if not row["keep_for_DE"]:
            continue
        key = (row["perturbed_gene_id"], row["culture_condition"], row["guide_id"])
        entry = proof.setdefault(key, {"offsets": [], "rows": []})
        entry["offsets"].append(i)
        entry["rows"].append(row["pseudobulk_id"])
    return proof


def write_source_file(d: str, specs: list[TargetSpec], source_rows_fn=None,
                      conditions: Sequence[str] = (CONDITION,)
                      ) -> tuple[str, str, dict[tuple, dict]]:
    """Write the pinned raw source; return its path, its sha256 and the TRUE proof.

    ``source_rows_fn`` tampers with the source AFTER the proof has been fixed, then the
    tampered bytes are pinned honestly. The records still claim the offsets the pristine
    source had; the source no longer agrees. Only a replay can notice.
    """
    import h5py
    import numpy as np
    from direct.hashing import file_sha256
    from fixtures_io import _write_categorical

    raw = raw_source_rows(specs, conditions)
    proof = kept_proof(raw)                       # from the PRISTINE rows
    if source_rows_fn is not None:
        raw = source_rows_fn(raw)

    path = os.path.join(d, SOURCE_NAME)
    with h5py.File(path, "w") as fh:
        obs = fh.create_group("obs")
        obs.attrs["_index"] = "pseudobulk_id"
        obs.create_dataset("pseudobulk_id", data=np.array(
            [r["pseudobulk_id"] for r in raw], dtype="S96"))
        for col in ("guide_id", "perturbed_gene_id", "culture_condition",
                    "guide_type"):
            _write_categorical(obs, col, [r[col] for r in raw])
        obs.create_dataset("keep_for_DE", data=np.array(
            [bool(r["keep_for_DE"]) for r in raw], dtype=bool))
    return path, file_sha256(path), proof


# --------------------------------------------------------------------------- #
# 2. THE MANIFEST ROWS — pooled-main scopes only, citations not yet minted.
# --------------------------------------------------------------------------- #
def manifest_rows(specs: list[TargetSpec], source_sha: str = "a" * 64,
                  conditions: Sequence[str] = (CONDITION,)) -> list[dict[str, Any]]:
    """One pooled-main scope per (target, CONDITION): the GLOBAL evidence domain.

    The domain is all-condition by construction (``domain.py``), so a multi-condition
    release ships one pooled-main scope per condition and the manifest must cover every
    one of them — a manifest that covered only the analysis condition would not match
    the universe it is checked against.

    A determined row leaves ``source_record_id`` null until ``link_citations`` mints it
    — the id is a hash of a proof this row does not hold.

    An AMBIGUOUS row is the release's own six-style scope: it proves no guide, so it
    carries no guide, no citation and no proof fields at all. It still carries the full
    released target identity, because it is still a real target.
    """
    rows: list[dict[str, Any]] = []
    for cond in conditions:
        for spec in specs:
            base = {"estimate_type": "main", "estimate_id": "main",
                    **spec.identity_at(cond),
                    "condition": cond, "donor_pair": None,
                    "n_guides": spec.n_guides, "n_cells": spec.n_cells,
                    "included": True}
            if main_ambiguous(spec):
                rows.append(dict(base, guide_id=None, evidence_state="ambiguous",
                                 source_record_id=None))
                continue
            for guide in contributing_guides(spec):
                rows.append(dict(base, guide_id=guide, evidence_state="determined",
                                 identity_method=IDENTITY_METHOD,
                                 source_id=SOURCE_NAME,
                                 source_sha256=source_sha, source_record_id=None))
    return rows


# --------------------------------------------------------------------------- #
# 3. THE SOURCE RECORDS — the proof, then the id that binds it.
# --------------------------------------------------------------------------- #
def _fabricated_proof(proof: dict[tuple, dict], key: tuple) -> dict[str, list]:
    """The proof a FABRICATING producer would ship for a contributor with no rows.

    A forged guide has no kept rows in the source, so no honest proof exists for it.
    Rather than refuse to build (which would test nothing), the fixture does what the
    adversary does: it borrows a well-formed proof from elsewhere. The table then loads,
    the citation resolves, and the RAW SOURCE is the only thing left that can refuse it
    — which is exactly the property under test.
    """
    same_scope = [k for k in sorted(proof) if k[:2] == key[:2]]
    donor = proof.get(same_scope[0]) if same_scope else (
        proof[sorted(proof)[0]] if proof else None)
    if donor is None:
        return {"offsets": [0], "rows": ["fabricated"]}
    return {"offsets": list(donor["offsets"]), "rows": list(donor["rows"])}


def source_records(rows: list[dict[str, Any]], proof: dict[tuple, dict]
                   ) -> list[dict[str, Any]]:
    """One record per determined manifest row, carrying the COMPLETE offset proof.

    The id is derived only once the proof is on the record — the rule hashes it, so a
    record built without it has no id to mint. An EXCLUDED determined row still gets a
    record: an excluded row that cites evidence is still making a claim, and an
    unchecked citation is exactly where a fabrication would hide.
    """
    from direct.record_id import derive_record_id

    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("evidence_state")) != "determined" or not row.get("guide_id"):
            continue
        key = (str(row["target_id"]), str(row["condition"]), str(row["guide_id"]))
        p = proof.get(key) or _fabricated_proof(proof, key)
        rec = {
            "estimate_type": row["estimate_type"], "estimate_id": row["estimate_id"],
            "released_estimate_id": row["released_estimate_id"],
            "target_id": row["target_id"],
            "target_id_namespace": row["target_id_namespace"],
            "target_symbol": row["target_symbol"],
            "target_ensembl": row["target_ensembl"],
            "condition": row["condition"], "donor_pair": row["donor_pair"],
            "guide_id": row["guide_id"],
            "identity_method": row.get("identity_method"),
            "source_id": row.get("source_id"),
            "source_sha256": row.get("source_sha256"),
            # THE COMPLETE PROOF: every kept raw row for this contributor, in order,
            # with the names the source gives them. The locator is one OF them.
            "pseudobulk_source_offsets": list(p["offsets"]),
            "pseudobulk_source_rows": list(p["rows"]),
            "source_row_index": p["offsets"][0],
        }
        rec["source_record_id"] = derive_record_id(rec)     # only NOW is it derivable
        out.append(rec)
    # canonically ordered: the table's bytes must not depend on the order the manifest
    # happened to list its rows in
    return sorted(out, key=lambda r: r["source_record_id"])


def _citation_key(rec: dict[str, Any]) -> tuple:
    from direct.sources import ESTIMATE_KEY
    return tuple(None if rec.get(f) is None else str(rec.get(f))
                 for f in ESTIMATE_KEY) + (str(rec.get("guide_id")),)


def link_citations(rows: list[dict[str, Any]], records: list[dict[str, Any]]
                   ) -> list[dict[str, Any]]:
    """Write each minted record id back into the determined row that claims it.

    This is the ONLY direction a citation can be established in: the row names an id it
    could never have computed, and resolution then checks that the record it names
    matches the row's entire released scope key and guide.
    """
    by_key = {_citation_key(r): r["source_record_id"] for r in records}
    for row in rows:
        if str(row.get("evidence_state")) == "determined" and row.get("guide_id"):
            row["source_record_id"] = by_key.get(_citation_key(row))
    return rows


def source_record_doc(records: list[dict[str, Any]], records_fn=None) -> dict:
    """The v2 table: the compiled identity rule, declared, plus the records.

    An honest producer implements the rule it declares, so the declaration IS the
    compiled rule. A table that states one rule while minting ids under another is
    refused before a record is indexed — and ``records_fn`` is how a test builds one.
    """
    from direct.record_id import RULE_METADATA, RULE_METADATA_KEY
    from direct.sources import SCHEMA_VERSION

    if records_fn is not None:
        records = records_fn(records)
    return {"schema_version": SCHEMA_VERSION,
            RULE_METADATA_KEY: json.loads(json.dumps(RULE_METADATA)),
            "records": records}


# --------------------------------------------------------------------------- #
# 4. THE MANIFEST DOCUMENT + the replay report + the trust anchor.
# --------------------------------------------------------------------------- #
def manifest_doc(rows: list[dict[str, Any]], sources: list[dict],
                 source_record_table: str = RECORD_TABLE_NAME,
                 source_replay_report: str = REPLAY_REPORT_NAME) -> dict:
    from direct.manifest_schema import SCHEMA_VERSION, SOURCE_RECORD_TABLE_SCHEMA
    return {
        "schema_version": SCHEMA_VERSION,
        "source_record_table_schema_version": SOURCE_RECORD_TABLE_SCHEMA,
        "identity_method": IDENTITY_METHOD,
        "source_class": SOURCE_CLASS,
        "source_record_table": source_record_table,
        "source_replay_report": source_replay_report,
        "sources": sources,
        "rows": rows,
    }


def _dump(path: str, doc: dict) -> str:
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return path


def write_replay_report(d: str, table_path: str, manifest_path: str,
                        source_path: str, replay_fn=None) -> str:
    """Replay the records against the RAW source, prove completeness, pin the verdict.

    The report hashes the table and the source but NOT the manifest — the manifest has
    to pin this report among its sources, so a report that hashed the manifest back
    would be a cycle no honest pair could ever satisfy.
    """
    from direct.replay import build_report
    report = build_report(table_path=table_path, manifest_path=manifest_path,
                          source_path=source_path, source_id=SOURCE_NAME)
    if replay_fn is not None:
        report = replay_fn(report)
    return _dump(os.path.join(d, REPLAY_REPORT_NAME), report)


def _pins(d: str, shas: dict[str, str]) -> tuple[str, list[dict]]:
    pins = {name: {"path": name, "sha256": sha, "revision": PINNED_REVISION}
            for name, sha in shas.items()}
    path = _dump(os.path.join(d, REGISTRY_NAME), {"sources": pins})
    sources = [{"name": n, "sha256": p["sha256"], "revision": PINNED_REVISION}
               for n, p in sorted(pins.items())]
    return path, sources


@dataclass
class Evidence:
    """Everything the lane needs to stand a contributor claim up — or to attack one."""
    manifest_path: str
    registry_path: str
    table_path: str
    replay_path: str
    source_path: str
    source_sha256: str
    rows: list[dict]
    records: list[dict]
    proof: dict[tuple, dict]
    sources: list[dict]


def write_evidence(d: str, specs: list[TargetSpec], *, manifest_rows_fn=None,
                   manifest_final_fn=None, records_fn=None, recite=False,
                   replay_fn=None, source_rows_fn=None,
                   manifest_sources=None, source_record_table=None,
                   source_replay_report=None,
                   conditions: Sequence[str] = (CONDITION,)) -> Evidence:
    """Build the whole bundle in the one order the identity rule permits.

    THE TWO MANIFEST HOOKS run on either side of the citation minting, and which one a
    test wants depends on what it is attacking:

      * ``manifest_rows_fn``  — BEFORE the records are built. The forged claim is then
        carried consistently into the records and the ids, so the manifest and table
        agree and the refusal must come from a RULE or from the raw source.
      * ``manifest_final_fn`` — AFTER the citations are minted. Use this to attack the
        citation itself (drop it, point it elsewhere): a pre-link edit would simply be
        overwritten by the minting, which is the honest producer doing its job.

    ``recite`` decides WHICH forger ``records_fn`` is, and the distinction is the whole
    value of binding the proof into the id:

      * ``recite=False`` — a SLOPPY forger. It edits the table and leaves the manifest
        citing the ids the records used to have. Re-keying is automatic (the id is a
        hash of the payload), so the citation goes stale and the run dies on the ID,
        without the source being consulted at all.
      * ``recite=True``  — a CONSISTENT forger. It edits the table and then re-cites
        its own forgery, so every id derives, every citation resolves, and the manifest
        and table agree perfectly. Nothing generated can refute it. Only the RAW SOURCE
        can — which is the property strict replay exists to have.

    The manifest is written TWICE, and that is not a wart: the replay report must be
    built from the manifest's rows, and the manifest must then pin the report's bytes
    among its sources. Writing the rows, replaying them, then re-writing the same rows
    with the report pinned is how that is done without a hash cycle. The rows are
    identical across both writes, so the report describes exactly the manifest that
    ships.
    """
    from direct.hashing import file_sha256

    source_path, source_sha, proof = write_source_file(d, specs, source_rows_fn,
                                                       conditions)

    rows = manifest_rows(specs, source_sha, conditions)
    if manifest_rows_fn is not None:
        rows = manifest_rows_fn(rows)          # forge the CLAIM, before it is minted
    records = source_records(rows, proof)
    link_citations(rows, records)

    if records_fn is not None:
        records = records_fn(records)          # forge the EVIDENCE
        if recite:
            link_citations(rows, records)      # ...and stand behind it
    if manifest_final_fn is not None:
        rows = manifest_final_fn(rows)         # forge the CITATION, after it is minted

    table_path = _dump(os.path.join(d, RECORD_TABLE_NAME),
                       source_record_doc(records))
    manifest_path = os.path.join(d, MANIFEST_NAME)

    # pass 1: the rows, so the replay has a manifest to prove completeness against
    _dump(manifest_path, manifest_doc(rows, []))
    replay_path = write_replay_report(d, table_path, manifest_path, source_path,
                                      replay_fn)

    registry_path, sources = _pins(d, {
        SOURCE_NAME: source_sha,
        RECORD_TABLE_NAME: file_sha256(table_path),
        REPLAY_REPORT_NAME: file_sha256(replay_path),
    })

    # pass 2: the same rows, now with every source pinned
    _dump(manifest_path, manifest_doc(
        rows, sources if manifest_sources is None else manifest_sources,
        source_record_table or RECORD_TABLE_NAME,
        REPLAY_REPORT_NAME if source_replay_report is None else source_replay_report))

    return Evidence(manifest_path=manifest_path, registry_path=registry_path,
                    table_path=table_path, replay_path=replay_path,
                    source_path=source_path, source_sha256=source_sha,
                    rows=rows, records=records, proof=proof, sources=sources)
