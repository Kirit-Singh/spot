"""A sealed, NON-PRODUCTION Stage-2 aggregate + universe store for the v2 producer tests.

NOTHING HERE IS A SCIENTIFIC FINDING. Every program is ``FIXTURE_PROG_*``, every target
``FIXTURE_TGT_*``, every molecule ``FIXTURE_MOL_*``, and every release declares
``artifact_class="fixture"`` — so :func:`druglink.stage2_aggregate.require_analysis` and the
v2 writer's own store firewall refuse these inputs by name on the analysis path. A fixture
cannot be laundered into an analysis, and no biological candidate is invented anywhere here.

What IS real is the shape: the complete 15-bundle / 300-arm topology the admission gate
derives from the conditions and sources, and a store whose rows carry the rankability lanes
the real store paid for. The action types are the source vocabulary's own terms (INHIBITOR /
AGONIST) because the direction engine reads them verbatim — a token, not a claim.

The fixture is tuned so that ALL FIVE directional statuses actually occur. A suite that never
produces an ``inverse_direction_hypothesis`` cannot prove one is kept apart from a
measurement, and a suite that never produces a ``pathway_hypothesis`` cannot prove an inferred
node is kept out of the measured lane.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from druglink import stage2_aggregate as sa
from druglink import universe_rows as ur
from druglink.hashing import content_hash

PROGRAMS = tuple(f"FIXTURE_PROG_{i:02d}" for i in range(sa.N_PROGRAMS))
NS = "fixture"
INDEPENDENT = "spot.stage02.aggregate.independent_verifier.v1"
AGG_MANIFEST_SCHEMA = "spot.stage02_aggregate_run_manifest.v1"
AGG_REPORT_SCHEMA = "spot.stage02_aggregate_verification.v1"

# Five typed targets, each exercising a different disposition.
TGT_DECREASE = "FIXTURE_TGT_00"       # in the store; the arm wants this target DOWN
TGT_INCREASE = "FIXTURE_TGT_01"       # knockdown moved the arm the UNDESIRED way
TGT_NO_DRUGS = "FIXTURE_TGT_02"       # in the store; no source assertion at all
TGT_UNSUPPORTED = "FIXTURE_TGT_03"    # in the store; namespace unreachable by this route
TGT_OFF_UNIVERSE = "FIXTURE_TGT_04"   # NOT in the admitted typed universe
MEASURED_TARGETS = (TGT_DECREASE, TGT_INCREASE, TGT_NO_DRUGS, TGT_UNSUPPORTED,
                    TGT_OFF_UNIVERSE)

SUPPORTS_INHIBITION = "supports_target_inhibition"
NEEDS_ACTIVATION = "opposed_would_require_target_activation"

# Stage-2's per-target modulation, and the rank it arrived with. TGT_INCREASE is deliberately
# UNRANKED: a null rank is a STATE, and it must reach an edge as null — never as 0, never last.
MEASURED_RECORDS: dict[str, dict[str, Any]] = {
    TGT_DECREASE: {"modulation": SUPPORTS_INHIBITION, "rank": 1},
    TGT_INCREASE: {"modulation": NEEDS_ACTIVATION, "rank": None},
    TGT_NO_DRUGS: {"modulation": SUPPORTS_INHIBITION, "rank": 2},
    TGT_UNSUPPORTED: {"modulation": SUPPORTS_INHIBITION, "rank": 3},
    TGT_OFF_UNIVERSE: {"modulation": SUPPORTS_INHIBITION, "rank": 4},
}

MOL_INHIBITOR = "FIXTURE_MOL_1"
MOL_AGONIST = "FIXTURE_MOL_2"
MOL_VARIANT_ONLY = "FIXTURE_MOL_3"
MEC_INHIBIT_DECREASE, MEC_AGONIST_DECREASE = 9001, 9002
MEC_INHIBIT_INCREASE, MEC_AGONIST_INCREASE = 9003, 9004
MEC_VARIANT = 9005


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The Stage-2 aggregate: 15 physical bundles, 300 reusable arm slots.
# --------------------------------------------------------------------------- #
def default_targets() -> tuple[tuple[str, str], ...]:
    """(target_id, namespace) pairs. Synthetic, and in no admitted universe."""
    return tuple((t, NS) for t in MEASURED_TARGETS)


def _modulation(i: int, tgt: str) -> str:
    """Stage-2's per-target modulation, consumed verbatim.

    For the SYNTHETIC targets the fixture states one per target. For CALLER-SUPPLIED targets
    (the admitted store's own identities) it CYCLES the vocabulary, so that every branch of the
    frozen direction engine is exercised. The assignment is PLUMBING: it asserts nothing
    biological about any gene, and no count derived from it is a scientific result.
    """
    if tgt in MEASURED_RECORDS:
        return MEASURED_RECORDS[tgt]["modulation"]
    return (SUPPORTS_INHIBITION, NEEDS_ACTIVATION,
            "no_directional_response")[i % 3]


def _rank(i: int, tgt: str) -> Optional[int]:
    if tgt in MEASURED_RECORDS:
        return MEASURED_RECORDS[tgt]["rank"]
    # Every third target is UNRANKED: a null rank is a STATE, and it must reach an edge as
    # null — never as 0, never last.
    return None if i % 3 == 2 else i + 1


def _base_records(lane: str, targets: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    out = []
    for prog in PROGRAMS:
        for tgt, ns in targets:
            base = {"base_key": f"{prog}|{tgt}", "program_id": prog, "target_id": tgt,
                    "target_id_namespace": ns, "target_symbol": f"SYM_{tgt[-2:]}",
                    "target_ensembl": f"ENSGFIXTURE{tgt[-2:]}", "evaluable": True}
            if lane == sa.LANE_TEMPORAL:
                base["from_released_estimate_id"] = f"{tgt}|from"
                base["to_released_estimate_id"] = f"{tgt}|to"
            else:
                base["released_estimate_id"] = f"{tgt}|est"
            out.append(base)
    return out


def _records(lane: str, prog: str, source: Optional[str],
             targets: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    if lane == sa.LANE_PATHWAY:
        # INFERRED nodes: nobody perturbed them, so no value and NO rank. The LAST node states
        # no direction of its OWN — only a set membership — and must stay INERT rather than
        # inheriting the direction of the set it happens to belong to.
        return [{"target_id": tgt, "target_id_namespace": ns,
                 "set_id": f"{source}:FIXTURE_SET_{i}", "arm_value": None, "rank": None,
                 "evaluable": True,
                 **({} if i == len(targets) - 1
                    else {"desired_target_modulation": _modulation(i, tgt)})}
                for i, (tgt, ns) in enumerate(targets)]
    return [{"base_key": f"{prog}|{tgt}", "target_id": tgt,
             "arm_value": 0.5 + i / 10,                       # a float, on the wire
             "rank": _rank(i, tgt), "evaluable": True,
             "desired_target_modulation": _modulation(i, tgt)}
            for i, (tgt, _ns) in enumerate(targets)]


def _bundle_doc(key: str, lane: str, ctx: dict[str, Any],
                targets: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    arms = []
    for prog in PROGRAMS:
        for change in sa.DESIRED_CHANGES:
            arm_key = f"{key}|{prog}|{change}"
            arms.append({
                "arm_key": arm_key, "program_id": prog, "desired_change": change,
                "ranking": {"path": f"rankings/{prog}__{change}.json",
                            "raw_sha256": _hex(f"raw|{arm_key}"),
                            "canonical_sha256": _hex(f"canon|{arm_key}")},
                "records": _records(lane, prog, ctx.get("pathway_source"), targets)})
    doc = {"schema_version": f"spot.stage02_{lane}_arm_bundle.v1",
           "artifact_class": "fixture", "bundle_key": key, "lane": lane,
           "context": dict(ctx), "arms": arms}
    if lane != sa.LANE_PATHWAY:
        doc["base_records"] = _base_records(lane, targets)
    return doc


def contexts() -> list[tuple[str, str, dict[str, Any]]]:
    out = [(f"{sa.LANE_DIRECT}|{c}", sa.LANE_DIRECT, {"condition": c})
           for c in sa.CONDITIONS]
    out += [(f"{sa.LANE_TEMPORAL}|{a}|{b}", sa.LANE_TEMPORAL,
             {"from_condition": a, "to_condition": b})
            for a, b in sa.ordered_condition_pairs()]
    out += [(f"{sa.LANE_PATHWAY}|{c}|{s}", sa.LANE_PATHWAY,
             {"condition": c, "pathway_source": s})
            for c in sa.CONDITIONS for s in sa.PATHWAY_SOURCES]
    return out


def build_release(root: Any, *, mutate_bundles=None, artifact_class: str = "fixture",
                  generated_at: str = "2026-07-13T00:00:00Z",
                  targets: Any = None) -> dict[str, str]:
    """Write a sealed NON-PRODUCTION release; return the four admission paths.

    ``targets`` are the typed identities the arms carry: ``[(target_id, namespace), …]``. Pass
    the ADMITTED store's OWN identities to exercise the arm->target join against real source
    assertions without inventing a single one of them. The release remains a FIXTURE: it
    declares ``artifact_class="fixture"``, ``require_analysis`` refuses it by name, and no
    count it produces is a scientific result.
    """
    root = str(root)
    targets = tuple(default_targets() if targets is None
                    else (tuple(t) for t in targets))
    bundles_root = os.path.join(root, "bundles")
    docs = {key: _bundle_doc(key, lane, ctx, targets) for key, lane, ctx in contexts()}
    if mutate_bundles:
        mutate_bundles(docs)

    inventory = []
    for key, lane, ctx in contexts():
        rel = os.path.join(lane, key.replace("|", "__") + ".json")
        full = os.path.join(bundles_root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        payload = json.dumps(docs[key], sort_keys=True, separators=(",", ":"))
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(payload)
        inventory.append({
            "bundle_key": key, "lane": lane, "path": rel,
            "raw_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            # Declared by Stage 2, carried and never recomputed here: its arm values are
            # floats on the wire, and Stage-3's canonical rule deliberately refuses floats.
            "canonical_sha256": _hex(f"stage2_canonical|{payload}"),
            **ctx})

    stage1_path = os.path.join(root, "stage1_release.json")
    with open(stage1_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"release_id": "fixture_stage1_v3",
                             "programs": list(PROGRAMS)}, sort_keys=True))
    with open(stage1_path, "rb") as fh:
        stage1_sha = hashlib.sha256(fh.read()).hexdigest()

    manifest: dict[str, Any] = {
        "schema_version": AGG_MANIFEST_SCHEMA,
        "artifact_class": artifact_class,
        "generated_at": generated_at,
        "stage1_release": {"release_id": "fixture_stage1_v3", "raw_sha256": stage1_sha},
        "inventory": inventory,
    }
    manifest[sa.SELF_HASH_FIELD] = sa.manifest_self_hash(manifest)
    manifest_path = os.path.join(root, "aggregate_run_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    with open(manifest_path, "rb") as fh:
        manifest_raw = hashlib.sha256(fh.read()).hexdigest()

    report = {"schema_version": AGG_REPORT_SCHEMA,
              "verifier_id": INDEPENDENT, "verdict": sa.ADMIT,
              "admits": {"manifest_raw_sha256": manifest_raw,
                         "manifest_canonical_sha256": content_hash(manifest)}}
    report_path = os.path.join(root, "independent_aggregate_verification.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True, separators=(",", ":")))

    return {"manifest_path": manifest_path, "report_path": report_path,
            "bundles_root": bundles_root, "stage1_release_path": stage1_path}


def admit(root: Any, **kwargs: Any) -> tuple[sa.AdmittedAggregate, dict[str, str]]:
    """The sealed release, through the REAL disk-backed admission gate."""
    paths = build_release(root, **kwargs)
    return sa.admit_aggregate(**paths), paths


# --------------------------------------------------------------------------- #
# THE REAL ADMITTED UNIVERSE STORE.
#
# There is NO admitted Stage-2 aggregate anywhere — so none is invented. The Stage-2 side stays
# the sealed PLUMBING release above; what is real here is the STORE, and the arm targets are
# the store's OWN typed identities, so the join is exercised against real ChEMBL assertions.
#
# The slice below is a DETERMINISTIC code-path-coverage rule over the store's own canonical
# order — the first row carrying each disposition, the first carrying a variant assertion, the
# first carrying an ambiguous one, and one identity the store does not cover at all. No gene is
# chosen for any biological reason, and no count derived from it is a scientific result.
# --------------------------------------------------------------------------- #
REAL_STORE = "/home/tcelab/.cache/spot-stage3-universe-w3tokens/store"
NOT_IN_UNIVERSE = ("ENSG00000000000", ur.NS_ENSEMBL_GENE)


def real_store_targets(store: ur.AdmittedStore) -> list[tuple[str, str]]:
    rows = sorted(store.rows,
                  key=lambda r: (r["target_id_namespace"], r["target_id"]))
    picked: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for want in (
            lambda r: r["disposition"] == ur.DISP_DRUG_EVIDENCE,
            lambda r: r["disposition"] == ur.DISP_NO_DRUG_EVIDENCE,
            lambda r: r["disposition"] == ur.DISP_AMBIGUOUS_IDENTITY,
            lambda r: r["disposition"] == ur.DISP_UNSUPPORTED_NAMESPACE,
            lambda r: bool(r.get("variant_specific_assertions")),
            lambda r: bool(r.get("ambiguous_source_assertions")),
            lambda r: len(r.get("drugs") or []) > 1,
    ):
        row = next((r for r in rows if want(r)
                    and (r["target_id"], r["target_id_namespace"]) not in seen), None)
        if row is not None:
            key = (row["target_id"], row["target_id_namespace"])
            seen.add(key)
            picked.append(key)
    # A typed identity the admitted store does NOT cover. It must land in `dispositions` as
    # target_not_in_admitted_typed_universe — which is never an absence of drug evidence.
    picked.append(NOT_IN_UNIVERSE)
    return picked


def universe_counts(store: ur.AdmittedStore) -> dict[str, int]:
    """What the store HOLDS, recomputed from its own rows. Never quoted from a memo."""
    rows = store.rows
    general = [a for r in rows for a in (r.get("drugs") or [])]
    variant = [a for r in rows for a in (r.get("variant_specific_assertions") or [])]
    ambiguous = [a for r in rows for a in (r.get("ambiguous_source_assertions") or [])]
    return {
        "n_typed_targets": len(store.typed_universe),
        "n_source_assertions": len(general) + len(variant) + len(ambiguous),
        "n_rankable_assertions": len(general),
        "n_variant_non_rankable": len(variant),
        "n_ambiguous_non_rankable": len(ambiguous),
        "n_targets_with_drug_evidence": sum(1 for r in rows if r.get("drugs")),
        "n_molecules": len({a["molecule_chembl_id"] for a in general
                            if a.get("molecule_chembl_id")}),
    }


# --------------------------------------------------------------------------- #
# The universe store. Constructed directly: ``load_store`` is the GATED path and pins the
# REAL admitted store id — which is exactly what stops a synthetic store entering an analysis.
# --------------------------------------------------------------------------- #
def _assertion(**over: Any) -> dict[str, Any]:
    row = {"molecule_chembl_id": MOL_INHIBITOR, "target_chembl_id": "FIXTURE_CHEMBL_TGT",
           "pref_name": "FIXTURE COMPOUND 1", "molecule_type": "Small molecule",
           "inchikey": "FIXTUREKEYAAAAAAAAAAAAAAAAA-N", "source_row_id": MEC_INHIBIT_DECREASE,
           "action_type_source": "INHIBITOR", "mechanism_of_action": "fixture inhibitor",
           "mechanism_refs": ["FIXTURE_REF"], "selectivity_comment": None,
           "direct_interaction": True, "molecular_mechanism": True, "disease_efficacy": True,
           "max_phase_source": "4", "max_phase_canonical": "4E+0", "variant_id": None,
           "variant_specific": False, "general_gene_rankable": True,
           "cross_ref_provenance": {}}
    row.update(over)
    return row


def _agonist(**over: Any) -> dict[str, Any]:
    return _assertion(molecule_chembl_id=MOL_AGONIST, pref_name="FIXTURE COMPOUND 2",
                      inchikey="FIXTUREKEYBBBBBBBBBBBBBBBBB-N", action_type_source="AGONIST",
                      mechanism_of_action="fixture agonist", **over)


def store_rows() -> list[dict[str, Any]]:
    return [
        {"target_id": TGT_DECREASE, "target_id_namespace": NS,
         "disposition": ur.DISP_DRUG_EVIDENCE,
         "drugs": [_assertion(source_row_id=MEC_INHIBIT_DECREASE),
                   _agonist(source_row_id=MEC_AGONIST_DECREASE)],
         "variant_specific_assertions": []},
        {"target_id": TGT_INCREASE, "target_id_namespace": NS,
         "disposition": ur.DISP_DRUG_EVIDENCE,
         "drugs": [_assertion(source_row_id=MEC_INHIBIT_INCREASE),
                   _agonist(source_row_id=MEC_AGONIST_INCREASE)],
         # The UNDEFINED MUTATION sentinel: NOT null, NOT wild-type, and never rankable.
         "variant_specific_assertions": [
             _assertion(source_row_id=MEC_VARIANT, molecule_chembl_id=MOL_VARIANT_ONLY,
                        inchikey="FIXTUREKEYCCCCCCCCCCCCCCCCC-N", variant_id=-1,
                        variant_specific=True, general_gene_rankable=False,
                        variant_disposition="variant_specific_non_rankable")]},
        {"target_id": TGT_NO_DRUGS, "target_id_namespace": NS,
         "disposition": ur.DISP_NO_DRUG_EVIDENCE, "drugs": [],
         "variant_specific_assertions": []},
        {"target_id": TGT_UNSUPPORTED, "target_id_namespace": NS,
         "disposition": ur.DISP_UNSUPPORTED_NAMESPACE, "drugs": [],
         "variant_specific_assertions": []},
    ]


def store(rows: Optional[list[dict[str, Any]]] = None) -> ur.AdmittedStore:
    rows = store_rows() if rows is None else rows
    eligibility: dict[str, Any] = {"fixture": True}
    provenance: list[Any] = [{"source": "fixture", "note": "no public bytes were read"}]
    manifest = {
        "store_id": "fixture_store_" + _hex("candidates_v2_fixture_store")[:32],
        "extraction": {ur.ARTIFACT_PINS[ur.ROWS_NAME]: content_hash(rows),
                       ur.ARTIFACT_PINS[ur.ELIGIBILITY_NAME]: content_hash(eligibility),
                       ur.ARTIFACT_PINS[ur.PROVENANCE_NAME]: content_hash(provenance)},
        "releases": {
            "chembl": {"source_release": "FIXTURE_CHEMBL", "license": "CC BY-SA 3.0",
                       "attribution": "fixture; no source bytes were used",
                       "source_sha256": _hex("fixture_chembl")},
            "uniprot": {"source_release": "FIXTURE_UNIPROT", "license": "CC BY 4.0",
                        "attribution": "fixture; no source bytes were used",
                        "source_sha256": _hex("fixture_uniprot")}},
    }
    typed = ur.derive_typed_universe(rows)
    return ur.AdmittedStore(
        store_dir="/fixture-store-not-on-disk", manifest=manifest, rows=rows,
        eligibility_evidence=eligibility, source_provenance=provenance,
        licences={ur.LICENSE_NAME: "fixture", ur.ATTRIBUTION_NAME: "fixture"},
        typed_universe=typed, typed_universe_sha256=ur.typed_universe_sha256(typed),
        store_binding={"schema_version": "spot.stage03_universe_binding.v1",
                       "store_id": manifest["store_id"],
                       "admitted_by": "independent_verifier", "verified_from_disk": True},
        _index={(r["target_id_namespace"], r["target_id"]): r for r in rows})
