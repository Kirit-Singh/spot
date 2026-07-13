"""A sealed, **NON-PRODUCTION** Stage-3 v2 world: aggregate + store + emitted bundle.

NOTHING HERE IS A SCIENTIFIC FINDING. Every program is ``FIXTURE_PROG_*``, every target
``FIXTURE_TGT_*``, every molecule ``FIXTURE_CHEMBL_*``, and every artifact declares
``artifact_class="fixture"``. The universe is not the admitted universe and the store is
not the admitted store — the verifier's analysis-path pins refuse these bytes by name.

This module stands in for the **producer** the independent verifier judges, so it must not
borrow the verifier's derivations: it computes direction with the REAL Stage-3 engine
(``druglink.direction``) and content-addresses with the REAL hasher (``druglink.hashing``).
The verifier restates both from the contract. If the two ever disagree, verification fails
— which is the point of writing them with different hands.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from druglink.hashing import content_hash, file_sha256

from verifier import v2_contract as C

PROGRAMS = tuple(f"FIXTURE_PROG_{i:02d}" for i in range(C.N_PROGRAMS))
INDEPENDENT = "spot.stage02.aggregate.independent_verifier.v1"
AGG_MANIFEST_SCHEMA = "spot.stage02_aggregate_run_manifest.v1"
AGG_REPORT_SCHEMA = "spot.stage02_aggregate_verification.v1"
CODE_SHA = "c0de" + "0" * 60
ENV_SHA = "e11f" + "0" * 60

# ns, target_id, chembl target, store disposition, uniprot accession
TARGETS = (
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_00", "FIXTURE_CHEMBL_T0", C.DISP_DRUG_EVIDENCE,
     "FIXTUREACC0"),
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_01", "FIXTURE_CHEMBL_T1", C.DISP_DRUG_EVIDENCE,
     "FIXTUREACC1"),
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_02", "FIXTURE_CHEMBL_T2", C.DISP_AMBIGUOUS_IDENTITY,
     "FIXTUREACC2"),
    (C.NS_SYMBOL, "FIXTURE_TGT_SYM", "FIXTURE_CHEMBL_TS", C.DISP_UNSUPPORTED_NAMESPACE,
     "FIXTUREACCS"),
)
# Referenced by every arm, absent from the store: it must land in `dispositions` as
# target_not_in_admitted_typed_universe — which is NOT "no drug evidence".
OFF_UNIVERSE = (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_OFF")

# STAGE-2's OWN per-target modulation vocabulary, consumed verbatim. Stage 3 translates these
# terms and REFUSES any other: reading an unknown term as "no direction" would make a
# vocabulary drift look exactly like a target that was examined and found directionless.
SUPPORTS_INHIBITION = "supports_target_inhibition"        # -> the arm wants a DECREASE
NEEDS_ACTIVATION = "opposed_would_require_target_activation"   # -> it wants an INCREASE

# Each measured record states its OWN desired modulation. Nothing is inherited.
ARM_RECORDS = (
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_00", SUPPORTS_INHIBITION, True, 1),
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_01", NEEDS_ACTIVATION, True, 2),
    (C.NS_ENSEMBL_GENE, "FIXTURE_TGT_02", SUPPORTS_INHIBITION, True, 3),
    (C.NS_SYMBOL, "FIXTURE_TGT_SYM", SUPPORTS_INHIBITION, False, None),
    (OFF_UNIVERSE[0], OFF_UNIVERSE[1], SUPPORTS_INHIBITION, True, 4),
)


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The sealed 15-bundle / 300-arm Stage-2 aggregate.
# --------------------------------------------------------------------------- #
def _contexts() -> list[tuple[str, str, dict]]:
    out = [(f"{C.LANE_DIRECT}|{c}", C.LANE_DIRECT, {"condition": c})
           for c in C.CONDITIONS]
    out += [(f"{C.LANE_TEMPORAL}|{a}|{b}", C.LANE_TEMPORAL,
             {"from_condition": a, "to_condition": b})
            for a, b in C.ordered_condition_pairs()]
    out += [(f"{C.LANE_PATHWAY}|{c}|{s}", C.LANE_PATHWAY,
             {"condition": c, "pathway_source": s})
            for c in C.CONDITIONS for s in C.PATHWAY_SOURCES]
    return out


def _bundle_doc(key: str, lane: str, ctx: dict) -> dict:
    pathway = lane == C.LANE_PATHWAY
    bases = [{"base_key": f"{p}|{t}", "program_id": p, "target_id": t,
              "target_id_namespace": ns, "target_symbol": f"SYM_{t[-2:]}",
              "released_estimate_id": f"{t}|est"}
             for p in PROGRAMS for ns, t, _m, _e, _r in ARM_RECORDS]
    arms = []
    for prog in PROGRAMS:
        for change in C.DESIRED_CHANGES:
            arm_key = f"{key}|{prog}|{change}"
            records = []
            for ns, tgt, mod, evaluable, rank in ARM_RECORDS:
                rec = {"target_id": tgt, "target_id_namespace": ns,
                       "desired_target_modulation": mod, "evaluable": evaluable,
                       # An INFERRED node was never perturbed: null rank stays null.
                       "rank": None if pathway else rank}
                if pathway:
                    rec["set_id"] = f"{ctx['pathway_source']}:FIXTURE_SET"
                else:
                    rec["base_key"] = f"{prog}|{tgt}"
                records.append(rec)
            arms.append({"arm_key": arm_key, "program_id": prog,
                         "desired_change": change,
                         "ranking": {"path": f"rankings/{prog}__{change}.json",
                                     "raw_sha256": _hex(f"raw|{arm_key}"),
                                     "canonical_sha256": _hex(f"canon|{arm_key}")},
                         "records": records})
    doc = {"schema_version": f"spot.stage02_{lane}_arm_bundle.v1",
           "artifact_class": "fixture", "bundle_key": key, "lane": lane,
           "context": dict(ctx), "arms": arms}
    if not pathway:
        doc["base_records"] = bases
    return doc


def write_aggregate(root: str, *, mutate_bundles=None, mutate_inventory=None,
                    mutate_manifest=None, mutate_report=None, mutate_after_seal=None,
                    artifact_class: str = "fixture") -> dict[str, str]:
    bundles_root = os.path.join(root, "bundles")
    docs = {key: _bundle_doc(key, lane, ctx) for key, lane, ctx in _contexts()}
    if mutate_bundles:
        mutate_bundles(docs)

    inventory = []
    for key, lane, ctx in _contexts():
        rel = os.path.join(lane, key.replace("|", "__") + ".json")
        full = os.path.join(bundles_root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        payload = json.dumps(docs[key], sort_keys=True, separators=(",", ":"))
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(payload)
        inventory.append({"bundle_key": key, "lane": lane, "path": rel,
                          "raw_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                          "canonical_sha256": content_hash(docs[key]), **ctx})
    if mutate_inventory:
        mutate_inventory(inventory)

    stage1 = os.path.join(root, "stage1_release.json")
    with open(stage1, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"release_id": "fixture_stage1_v3",
                             "programs": list(PROGRAMS)}, sort_keys=True))

    manifest = {"schema_version": AGG_MANIFEST_SCHEMA, "artifact_class": artifact_class,
                "generated_at": "2026-07-13T00:00:00+00:00",
                "stage1_release": {"release_id": "fixture_stage1_v3",
                                   "raw_sha256": file_sha256(stage1)},
                "inventory": inventory}
    if mutate_manifest:
        mutate_manifest(manifest)
    manifest["manifest_sha256"] = content_hash(
        {k: v for k, v in manifest.items()
         if k not in ("manifest_sha256", *C.NON_SEMANTIC_FIELDS)})

    manifest_path = os.path.join(root, "aggregate_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")))

    report = {"schema_version": AGG_REPORT_SCHEMA, "verifier_id": INDEPENDENT,
              "verdict": "admit",
              "admits": {"manifest_raw_sha256": file_sha256(manifest_path),
                         "manifest_canonical_sha256": content_hash(manifest)}}
    if mutate_report:
        mutate_report(report, manifest, manifest_path)
    report_path = os.path.join(root, "aggregate_verification.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True, separators=(",", ":")))

    if mutate_after_seal:
        mutate_after_seal(bundles_root, manifest_path, report_path)

    return {"manifest": manifest_path, "report": report_path,
            "bundles_root": bundles_root, "stage1_release": stage1}


# --------------------------------------------------------------------------- #
# The sealed universe store.
# --------------------------------------------------------------------------- #
def _assertion(mec: int, mol: str, chembl_target: str, action: str, *,
               rankable: bool, variant: Optional[int] = None) -> dict:
    a = {"source_row_id": mec, "molecule_chembl_id": mol,
         "target_chembl_id": chembl_target, "action_type_source": action,
         "general_gene_rankable": rankable,
         "mechanism_of_action": f"{action.lower()} of {chembl_target}",
         "mechanism_refs": [], "max_phase_source": "4"}
    if variant is not None:
        a["variant_id"] = variant
        a["variant_specific"] = True
    return a


def _store_rows() -> list[dict]:
    """Rows in the ADMITTED store's own shape: a typed identity, a disposition, the UniProt
    accessions and ChEMBL targets it resolved through, and its three assertion lanes.

    Tuned so that every directional status actually OCCURS. A suite that never produces an
    `opposed` cannot prove an opposed sourced action is preserved rather than dropped, and one
    that never produces an `unresolved` cannot prove an unknown action fails CLOSED.
    """
    rows = []
    for ns, tgt, chembl, disp, acc in TARGETS:
        row: dict[str, Any] = {
            "target_id": tgt, "target_id_namespace": ns, "disposition": disp,
            "identity": {"accessions": [acc], "targets": [chembl],
                         "identity_status": ("ambiguous"
                                             if disp == C.DISP_AMBIGUOUS_IDENTITY
                                             else "resolved"),
                         "shared_accession_genes": {}},
            "no_evidence_reason": None,
            "drugs": [], "variant_specific_assertions": [],
            "ambiguous_source_assertions": []}
        if tgt == "FIXTURE_TGT_00":
            # The arm wants this target DOWN: an inhibitor/degrader RUNS WITH the tested
            # direction; a BINDER states no enumerated effect and must fail CLOSED.
            row["drugs"] = [
                _assertion(9001, "FIXTURE_CHEMBL_M1", chembl, "INHIBITOR", rankable=True),
                _assertion(9002, "FIXTURE_CHEMBL_M2", chembl, "DEGRADER", rankable=True),
                _assertion(9007, "FIXTURE_CHEMBL_M6", chembl, "BINDER", rankable=True)]
        elif tgt == "FIXTURE_TGT_01":
            # The knockdown moved this arm the UNDESIRED way, so the arm wants an INCREASE: a
            # sourced AGONIST is the inverse-direction HYPOTHESIS, and an INHIBITOR is OPPOSED.
            row["drugs"] = [
                _assertion(9003, "FIXTURE_CHEMBL_M3", chembl, "AGONIST", rankable=True),
                _assertion(9008, "FIXTURE_CHEMBL_M7", chembl, "INHIBITOR", rankable=True)]
            row["variant_specific_assertions"] = [
                _assertion(9004, "FIXTURE_CHEMBL_M4", chembl, "INHIBITOR",
                           rankable=False, variant=C.VARIANT_UNDEFINED_MUTATION)]
        elif tgt == "FIXTURE_TGT_02":
            row["ambiguous_source_assertions"] = [
                _assertion(9005, "FIXTURE_CHEMBL_M1", chembl, "INHIBITOR",
                           rankable=False),
                _assertion(9006, "FIXTURE_CHEMBL_M5", chembl, "ANTAGONIST",
                           rankable=False)]
        rows.append(row)
    return rows


# The frozen predicates, as the store's own artifact states them.
ELIGIBILITY_SQL = ("td.target_type = 'SINGLE PROTEIN' AND td.tax_id = 9606 AND "
                   "td.species_group_flag = 0 AND cs.component_type = 'PROTEIN' AND "
                   "cs.tax_id = 9606 AND tc.homologue = 0")


def _eligibility(rows: list[dict]) -> dict:
    """The store's eligibility EVIDENCE: the predicate INPUTS, not merely the verdict.

    An unfalsifiable 'eligible' is a promise about a computation nobody kept the inputs to —
    so every input the predicate was applied to travels with the record, and the verifier
    re-derives the verdict from them rather than reading it.
    """
    records = []
    for _ns, tgt, chembl, _disp, acc in TARGETS:
        # A NON-HUMAN taxon, deliberately: a store with no rejections looks identical to one
        # whose rejections were dropped, and the second is a missing gate.
        rejected = tgt == "FIXTURE_TGT_02"
        tax = 10090 if rejected else 9606
        records.append({
            "target_chembl_id": chembl, "accession": acc,
            "target_type": "SINGLE PROTEIN", "tax_id": tax, "species_group_flag": 0,
            "n_components": 1,
            "components": [{"accession": acc, "component_type": "PROTEIN",
                            "tax_id": 9606, "homologue": 0}],
            "eligible": not rejected,
            "disposition": ("reject_nonhuman_target_taxon" if rejected
                            else "eligible_human_single_protein")})
    return {
        "schema": "spot.stage03_target_eligibility_evidence.v1",
        "eligibility_policy_version": "stage3-universe-target-eligibility-v1",
        "eligible_single_protein_sql": ELIGIBILITY_SQL,
        "counts": {"n_total": len(records),
                   "n_eligible": sum(1 for r in records if r["eligible"]),
                   "n_rejected": sum(1 for r in records if not r["eligible"])},
        "records": records}


def _provenance() -> list[dict]:
    return [
        {"name": "uniprot", "release": "2026_02", "release_date": "10-Jun-2026",
         "publisher_md5": "7ef6a677d4db949397c3b352c466e499", "size_bytes": 37842957,
         "acquired_sha256": _hex("fixture-uniprot"),
         "accessed_at_utc": "2026-07-01T00:00:00Z",
         "release_metadata_url": "https://ftp.uniprot.org/RELEASE.metalink",
         "relnotes_url": "https://ftp.uniprot.org/relnotes.txt",
         "url_is_mutable": True,
         "mutability_note": "current_release is mutable; the release is bound instead"},
        {"name": "chembl", "release": "CHEMBL_37",
         "publisher_sha256": _hex("fixture-chembl-pub"),
         "acquired_sha256": _hex("fixture-chembl"),
         "accessed_at_utc": "2026-07-01T00:00:00Z",
         "release_metadata_url": "https://ftp.ebi.ac.uk/checksums.txt",
         "doi": "10.6019/CHEMBL.database.37"},
    ]


def _store_id(rows: list[dict]) -> str:
    return _hex("fixture-store|" + content_hash(rows))


def write_store(store_dir: str, *, mutate_rows=None, mutate_after_seal=None) -> str:
    os.makedirs(store_dir, exist_ok=True)
    rows = _store_rows()
    if mutate_rows:
        mutate_rows(rows)
    evidence = _eligibility(rows)
    provenance = _provenance()

    typed = sorted(({"target_id": r["target_id"],
                     "target_id_namespace": r["target_id_namespace"]} for r in rows),
                   key=lambda r: (r["target_id_namespace"], r["target_id"]))
    manifest = {
        "schema_version": "spot.stage03_universe_store.v1",
        "store_id": _store_id(rows),
        "universe_binding": {"universe_targets_sha256": content_hash(typed),
                             "n_targets_total": len(rows)},
        "extraction": {"extraction_query_sha256": _hex("fixture-query"),
                       "store_rows_sha256": content_hash(rows),
                       "eligibility_evidence_sha256": content_hash(evidence),
                       "public_source_provenance_sha256": content_hash(provenance)},
        "releases": {
            "chembl": {"source_release": "CHEMBL_37", "license": "CC BY-SA 3.0",
                       "attribution": "preserve ChEMBL IDs; display release and URL",
                       "source_sha256": _hex("fixture-chembl"),
                       "doi": "10.6019/CHEMBL.database.37"},
            "uniprot": {"source_release": "2026_02", "license": "CC BY 4.0",
                        "attribution": "UniProt Consortium",
                        "source_sha256": _hex("fixture-uniprot")}},
    }
    for name, doc in ((C.STORE_MANIFEST_NAME, manifest), (C.STORE_ROWS_NAME, rows),
                      (C.STORE_ELIGIBILITY_NAME, evidence),
                      (C.STORE_PROVENANCE_NAME, provenance)):
        with open(os.path.join(store_dir, name), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, sort_keys=True, separators=(",", ":")))
    for name, text in ((C.STORE_LICENSE_NAME, "CC BY-SA 3.0 Unported\n"),
                       (C.STORE_ATTRIBUTION_NAME, "ChEMBL 37; preserve ChEMBL IDs\n")):
        with open(os.path.join(store_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    if mutate_after_seal:
        mutate_after_seal(store_dir)
    return store_dir


def load_fixture_store(store_dir: str):
    """The sealed store, as an ``AdmittedStore`` the REAL producer can consume.

    Constructed from the store's own bytes rather than through ``universe_rows.load_store``,
    because that path is GATED: it pins the exact store_id an independent verifier admitted
    (625c921f…), and a synthetic store can never satisfy it. That gate is the point of it —
    so a fixture is built here, declares itself a fixture, and is refused by the analysis path.
    """
    from druglink import universe_rows as ur

    def _read(name):
        with open(os.path.join(store_dir, name), "r", encoding="utf-8") as fh:
            return json.load(fh)

    manifest = _read(C.STORE_MANIFEST_NAME)
    rows = _read(C.STORE_ROWS_NAME)
    typed = ur.derive_typed_universe(rows)
    return ur.AdmittedStore(
        store_dir=store_dir, manifest=manifest, rows=rows,
        eligibility_evidence=_read(C.STORE_ELIGIBILITY_NAME),
        source_provenance=_read(C.STORE_PROVENANCE_NAME),
        licences={C.STORE_LICENSE_NAME: "fixture", C.STORE_ATTRIBUTION_NAME: "fixture"},
        typed_universe=typed, typed_universe_sha256=ur.typed_universe_sha256(typed),
        store_binding={"schema_version": "spot.stage03_universe_binding.v1",
                       "store_id": manifest["store_id"],
                       "admitted_store_id": manifest["store_id"],
                       "admitted_producer_commit": "fixture",
                       "admission_report_sha256": "fixture",
                       "admitted_by": "independent_verifier",
                       "producer_admits_store": False,
                       "verified_from_disk": True},
        _index={(r["target_id_namespace"], r["target_id"]): r for r in rows})
