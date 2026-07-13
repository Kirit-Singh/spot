"""A PREFETCH-ONLY drug-candidate manifest. It is a WORK LIST, not a result.

W8 needs to know which public-source records to fetch before the pathway lane lands. This emits
exactly that: the Direct display projection's target ids, intersected with the ADMITTED universe
store, resolved to their typed identity and their public-source lookup keys.

WHAT THIS IS NOT, AND CANNOT BECOME
-----------------------------------
``artifact_class`` is ``prefetch_only`` — a value Stage-3's own ``artifact_class.require()``
REFUSES. There are two Stage-3 classes, ``analysis`` and ``fixture``, and this is neither. So the
artifact cannot be admitted as a Stage-3 analysis by construction rather than by convention: any
code path that tries raises ``ArtifactClassError`` before it reads a single row.

It carries NO score, NO rank ordering across arms, NO combined objective, and NO candidate
selection. It says "these public-source records exist for these targets" and nothing else. A
prefetch list that quietly acquired an ordering would be a ranking wearing a work-list's clothes,
and the first consumer to sort by it would be reading a claim nobody made.

IDENTITY IS RESOLVED BY THE STORE, NEVER INFERRED
-------------------------------------------------
The projection's rows carry ``target_id`` and ``target_symbol`` — and NO namespace. Stage 3 does
not guess one from the id's shape: the admitted universe holds 11,522 Ensembl ids AND 4 gene
symbols, so a shape guess types most rows right, mistypes the rest, and a mistyped row fails the
exact-identity join by simply finding no drug — indistinguishable from a target that genuinely
has none.

Instead each id is looked up in the ADMITTED STORE, which is the authority on typed identity. A
target that resolves to MORE THAN ONE typed identity is REFUSED for the prefetch list and reported
as ambiguous, never silently resolved to one of them.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping

from . import assertions_v2 as av2
from .hashing import canonical_json, content_hash, file_sha256
from .universe_rows import AdmittedStore

MANIFEST_SCHEMA = "spot.stage03_prefetch_manifest.v1"
METHOD_ID = "spot.stage03.prefetch_manifest.v1"
ARTIFACT_CLASS = "prefetch_only"          # NOT a Stage-3 artifact class. Deliberately.
DIRECT_LANE_PREFIX = "direct|"

PROJECTION_SCHEMA = "spot.stage02_display_projection.v2"

# A lookup key is STATED or it is explicitly NOT AVAILABLE. It is never a null wearing a key's
# name — the first version of this manifest emitted source_locator=None on all 455 rows while the
# handoff claimed every row carried an exact public-source lookup key.
LOOKUP_KEY_STATED = "stated"
LOOKUP_KEY_NOT_AVAILABLE = "not_available"


class PrefetchError(ValueError):
    """The prefetch manifest cannot be built from these bytes. Refuse; never repair."""


def _refuse(gate: str, message: str) -> None:
    raise PrefetchError(f"[{gate}] {message}")


def _upstream_hash(obj: Any) -> str:
    """Hash UPSTREAM bytes under UPSTREAM's canonicalisation — a plain sha256 over canonical JSON.

    NOT `hashing.content_hash`. That enforces Stage-3's canonical-number rule (exact decimal
    strings, never floats) because it addresses Stage-3's own SCIENTIFIC CONTENT. W3's projection
    carries float `arm_value`s and computed `projection_sha256` under its own rule, so hashing it
    our way would refuse an honest artifact for speaking its own language.

    We are binding THEIR bytes, floats and all. Our number rule governs what WE emit — never how
    we identify what someone else emitted.
    """
    import hashlib
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_projection(path: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Open W3's display projection and BIND it by its own bytes.

    Its ``projection_sha256`` is RECOMPUTED, never read: a self-hash a consumer copies rather than
    checks names whatever bytes it is handed.
    """
    if not os.path.exists(path):
        _refuse("the_display_projection_is_not_on_disk", f"no projection at {path!r}")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    if doc.get("schema_version") != PROJECTION_SCHEMA:
        _refuse("the_display_projection_is_not_the_native_schema",
                f"the projection declares schema_version={doc.get('schema_version')!r}; the "
                f"native contract is {PROJECTION_SCHEMA!r}")

    claimed = doc.get("projection_sha256")
    recomputed = _upstream_hash({k: v for k, v in doc.items() if k != "projection_sha256"})
    if claimed != recomputed:
        _refuse("the_projection_does_not_hash_to_the_identity_it_publishes",
                f"the projection publishes {str(claimed)[:16]}… but its own content hashes to "
                f"{recomputed[:16]}…. It was edited after it was addressed.")

    # The projection must be SELECTION-INDEPENDENT and carry no cross-arm ordering. If it did, a
    # prefetch list drawn from it would inherit a ranking nobody in Stage 3 computed.
    if doc.get("selection_independent") is not True:
        _refuse("the_projection_is_not_selection_independent",
                "a prefetch list drawn from a selection-specific projection would answer ONE "
                "question while claiming to be the global work list")
    for field in ("combined_objective", "cross_arm_score_or_order"):
        if doc.get(field) not in (None, False):
            _refuse("the_projection_carries_a_cross_arm_ordering",
                    f"the projection declares {field}={doc.get(field)!r}; a prefetch list must "
                    "inherit no score and no cross-arm order")

    binding = {
        "path": os.path.basename(path),
        "raw_sha256": file_sha256(path),
        "canonical_sha256": _upstream_hash(doc),
        "projection_self_sha256": recomputed,
        "schema_version": PROJECTION_SCHEMA,
        "method_version": str(doc.get("method_version") or ""),
    }
    return doc, binding


def direct_target_ids(projection: Mapping[str, Any]) -> list[str]:
    """The UNION of the target ids in every DIRECT arm's prefix.

    The projection's rows are a capped PREFIX (``is_a_prefix``), which is exactly what a work list
    wants: it is the set of targets a Direct arm actually surfaced. The union is taken across arms
    and DEDUPLICATED — a target appearing in six arms is one record to fetch, not six. No arm's
    ordering survives the union, and none should: this is a set.
    """
    arms = projection.get("arms") or {}
    if not isinstance(arms, dict) or not arms:
        _refuse("the_projection_carries_no_arms", "a projection of nothing projects nothing")

    ids: set[str] = set()
    n_direct = 0
    for arm_key, arm in arms.items():
        if not str(arm_key).startswith(DIRECT_LANE_PREFIX):
            continue
        n_direct += 1
        for row in arm.get("rows") or []:
            tid = row.get("target_id")
            if tid:
                ids.add(str(tid))
    if not n_direct:
        _refuse("the_projection_has_no_direct_arms",
                f"no arm key begins {DIRECT_LANE_PREFIX!r}; there is nothing to prefetch")
    if not ids:
        _refuse("the_direct_arms_name_no_targets",
                f"{n_direct} direct arm(s), and not one target id between them")
    return sorted(ids)


def _resolve(store: AdmittedStore, target_id: str) -> list[dict[str, str]]:
    """The typed identities the ADMITTED STORE gives this id. Never a guess."""
    return [dict(r) for r in store.typed_universe if r["target_id"] == target_id]


def build(*, projection_path: str, store: AdmittedStore, created_at: str) -> dict[str, Any]:
    """The prefetch manifest: the public-source records W8 must fetch, and nothing else."""
    from . import universe_rows as ur

    projection, projection_binding = load_projection(projection_path)
    wanted = direct_target_ids(projection)

    records: list[dict[str, Any]] = []
    resolved: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    not_in_universe: list[str] = []

    for tid in wanted:
        hits = _resolve(store, tid)
        if not hits:
            not_in_universe.append(tid)
            continue
        if len(hits) > 1:
            # Two typed identities for one id. Resolving it would be picking which is true.
            ambiguous.append({"target_id": tid,
                              "namespaces": sorted(h["target_id_namespace"] for h in hits),
                              "reason": "one_target_id_resolves_to_more_than_one_typed_identity"})
            continue
        resolved.append(tid)

    typed = [(t, _resolve(store, t)[0]["target_id_namespace"]) for t in resolved]
    edges = ur.rankable_edges(ur.drug_edges_for_targets(store, typed))

    binding = store.release_binding if hasattr(store, "release_binding") else {}
    if not binding:
        from . import universe_edges as ue
        binding = ue._release_binding(store) if hasattr(ue, "_release_binding") else {}

    n_no_locator = 0
    for e in edges:
        # THE LOOKUP KEY, TRUTHFULLY. `assertions_v2.source_locator` builds
        # `chembl:<release>:drug_mechanism/<mec_id>` from the store's OWN bound provenance, and
        # REFUSES rather than emitting a locator that resolves to nothing. If it cannot be built,
        # we say so — `lookup_key_status: not_available` — and W8 falls back to the
        # molecule_chembl_id, which IS an exact machine lookup key. A null is never dressed as a
        # key: the first version of this manifest emitted source_locator=None on all 455 rows
        # while the handoff claimed every row carried an exact lookup key. It did not.
        try:
            locator = av2.source_locator(e, binding)
            status = LOOKUP_KEY_STATED
        except av2.AssertionV2Error:
            locator = None
            status = LOOKUP_KEY_NOT_AVAILABLE
            n_no_locator += 1

        records.append({
            # typed target identity — resolved BY THE STORE
            "target_id": e["target_id"],
            "target_id_namespace": e["target_id_namespace"],
            # source record identity
            "source_record_id": e.get("edge_id"),
            "mec_id": e.get("source_row_id"),
            "assertion_lane": e.get("lane"),
            # drug identity — molecule_chembl_id is the EXACT MACHINE LOOKUP KEY
            "molecule_chembl_id": e.get("molecule_chembl_id"),
            "target_chembl_id": e.get("target_chembl_id"),
            "molecule_pref_name": e.get("pref_name"),          # SOURCE-VERBATIM name
            "molecule_type": e.get("molecule_type"),
            "inchikey": e.get("inchikey"),
            # the public-source coordinates, or an explicit statement that there are none
            "source_locator": locator,
            "lookup_key_status": status,
            "machine_lookup_key": e.get("molecule_chembl_id"),
            "machine_lookup_key_kind": "molecule_chembl_id",
            "source_release": binding.get("chembl_release"),
            "mechanism_refs": list(e.get("mechanism_refs") or []),
            "cross_ref_provenance": dict(e.get("cross_ref_provenance") or {}),
            # verbatim, uninterpreted. This manifest asserts no direction.
            "action_type_source": e.get("action_type_source"),
            "mechanism_of_action": e.get("mechanism_of_action"),
        })

    # DETERMINISTIC ORDER, and an order that carries NO CLAIM: by identity, not by any value.
    records.sort(key=lambda r: (str(r["target_id_namespace"]), str(r["target_id"]),
                                str(r["source_record_id"])))

    doc: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_class": ARTIFACT_CLASS,
        "method_id": METHOD_ID,
        "created_at": created_at,
        "is_a_work_list_not_a_result": True,
        "carries_no_score_or_rank": True,
        "combined_objective_permitted": False,
        "cross_arm_ordering_permitted": False,
        "may_be_admitted_as_a_stage3_analysis": False,
        "record_order_is_by_identity_and_carries_no_claim": True,
        "stage2_display_projection": projection_binding,
        "universe_store": {
            "store_id": store.store_id,
            "typed_universe_sha256": store.typed_universe_sha256,
        },
        "counts": {
            "n_direct_arms": sum(1 for k in (projection.get("arms") or {})
                                 if str(k).startswith(DIRECT_LANE_PREFIX)),
            "n_target_ids_in_direct_prefixes": len(wanted),
            "n_resolved_in_admitted_universe": len(resolved),
            "n_not_in_admitted_universe": len(not_in_universe),
            "n_ambiguous_identity": len(ambiguous),
            "n_prefetch_records": len(records),
            # The number W8 actually schedules against: how many of the resolved targets carry
            # any public-source record at all. The rest resolve fine and simply have no drug —
            # which is a FINDING, not a gap, and is why it is counted rather than inferred from
            # the difference between two other numbers.
            "n_targets_with_prefetch_records": len({(r["target_id_namespace"], r["target_id"])
                                                    for r in records}),
            "n_targets_with_no_qualifying_drug_evidence_in_the_bound_store":
                len(resolved) - len({r["target_id"] for r in records}),
            "n_distinct_molecules": len({r["molecule_chembl_id"] for r in records}),
            "n_records_with_a_stated_source_locator":
                sum(1 for r in records if r["lookup_key_status"] == LOOKUP_KEY_STATED),
            "n_records_with_no_source_locator": n_no_locator,
        },
        # ABSENCE IS STATED, never a silent drop: a target nobody can fetch is reported, not lost.
        # PHRASING MATTERS. "no qualifying drug evidence in the bound store" — NOT "has no drug".
        # The store is ChEMBL 37 filtered to the general-gene rankable lane; a target absent from
        # it may still have a drug in a source this store does not bind, in a lane it excludes, or
        # in a later release. Saying "has no drug" would state a fact about the WORLD when we only
        # have a fact about THIS STORE, and a reader would stop looking.
        "absence_means": ("no QUALIFYING drug evidence in the BOUND store "
                          "(ChEMBL 37, general-gene rankable lane) — NOT 'this target has no "
                          "drug'. A target may carry evidence in a source this store does not "
                          "bind, in a lane it excludes, or in a later release."),
        "targets_with_no_qualifying_drug_evidence_in_the_bound_store": len(resolved) - len(
            {r["target_id"] for r in records}),
        "not_in_admitted_universe": sorted(not_in_universe),
        "ambiguous_identity": sorted(ambiguous, key=lambda a: str(a["target_id"])),
        "records": records,
    }
    doc["manifest_sha256"] = content_hash({k: v for k, v in doc.items()
                                           if k not in ("manifest_sha256", "created_at")})
    doc["manifest_id"] = doc["manifest_sha256"][:16]
    return doc


def write(doc: Mapping[str, Any], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"prefetch_manifest.{doc['manifest_id']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(doc))
    return path
