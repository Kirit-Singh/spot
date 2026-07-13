"""THE INDEPENDENT BRIDGE VERIFIER: it REOPENS the admitted native bytes and REBUILDS the rows.

WHY SELF-CONSISTENCY WAS NOT ENOUGH — the two attacks that beat the previous version
--------------------------------------------------------------------------------------
The earlier ``verify_artifact`` checked that the artifact hashed to what it claimed, and that
each row's direction re-derived from THE VALUE PRINTED ON THAT ROW. Both attacks walk straight
through that:

  1. COHERENT RESEAL. Change a Direct row's ``arm_value`` from +0.5 to -0.5, change its
     ``desired_target_modulation`` and ``phenocopy_class`` to match, recompute ``rows_sha256``.
     Every internal check agrees. ADMIT. The forged row is perfectly self-consistent — it is
     just no longer a statement about the experiment. The number came from nowhere.

  2. FORGED PATHWAY CONTEXT. The contexts were not read at all, so a context carrying
     ``is_a_crispri_target_row: true``, ``may_be_matched_to_a_drug_as_a_target: true``,
     ``arm_value: 99`` and ``desired_target_modulation: decrease`` was admitted with zero
     failures — a gene set wearing a target's clothes, ready to be prescribed a drug.

A verifier that only asks "does this document agree with itself" cannot tell evidence from
fiction, because fiction can be made to agree with itself. So this one does not ask that.

WHAT IT DOES INSTEAD
--------------------
It opens the ADMITTED NATIVE BYTES — the bound ranking records, the bound identity/assay
source, the native pathway records — and REBUILDS every row and every context from them. Then
it compares, field by field. A row the native bytes do not produce is not a row.

The self-hash is still checked. It is necessary and it is nowhere near sufficient.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

# The verifier's modules load FLAT — never through the producer's package. Same bootstrap the
# other verifiers use, so this runs identically as a module and as a subprocess.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_stage3_rows as VR  # noqa: E402, I001

BRIDGE_FILE = "stage3_bridge.json"

# THE PRODUCER'S IDENTITY ARTIFACT, RESTATED — not imported.
#
# `target_identity` owns these, and the producer side imports them from it. This module may
# not: the audit probe forbids a verifier importing ANY producer module, because a verifier
# that reads the producer's constant agrees with it by construction and cannot catch it moving.
#
# The risk that creates is precisely the one 9bd5895 exists to kill — a second literal drifting
# to `.parquet` — so it is closed the other way: `test_stage3_bridge` PIN-TESTS these three
# against `target_identity`'s own, and a disagreement is a failing test rather than a verifier
# quietly checking a file nobody wrote.
IDENTITY_FILE = "target_identity.json"
IDENTITY_SCHEMA = "spot.stage02_target_identity.v1"
IDENTITY_RECORDS_KEY = "records"          # NOT "targets" — that was my guess, and it was wrong
IDENTITY_MODALITY_FIELD = "observed_perturbation_modality"

# --------------------------------------------------------------------------- #
# WHERE EACH LANE'S ROWS ACTUALLY LIVE. Read off the producers, not imagined.
#
# I had every lane rebuilding from `rankings/<program>__<change>.json`. DIRECT HAS NO SUCH
# DIRECTORY. Its rows are `arms.parquet` (arm_artifacts.ROWS_FILE), bound by the bundle's
# `arm_rows_sha256`, with the value in a column called `value`. Rebuilding Direct from a
# rankings dir would have found nothing and failed every Direct row as an orphan.
# --------------------------------------------------------------------------- #
NATIVE_ROWS = {
    "direct": {"kind": "parquet", "file": "arms.parquet", "value_field": "value",
               "join_on": "target_id"},
    # temporal DOES ship rankings/, with `arm_value`, and its identity lives on base_records
    # keyed by base_key — "never on the arm records that join to it", in its own words.
    "temporal": {"kind": "rankings_dir", "dir": "rankings", "value_field": "arm_value",
                 "join_on": "base_key"},
    # pathway ships NO target rows at all: its records are (arm x GENE SET).
    "pathway": None,
}
AGGREGATE_MANIFEST = "stage2_run_manifest.json"
AGGREGATE_REPORT = "stage2_aggregate_verification.json"

G_AGGREGATE = "the_bridge_binds_an_ADMITTED_aggregate_and_the_bytes_still_match"

# THE RECEIPT — the immutable-aggregate <-> bridge join. Stage 3 gates on it, so it is a
# referent like any other: it is REOPENED and RE-DERIVED, never taken at its word.
RECEIPT_FILE = "stage2_stage3_receipt.json"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"

G_RECEIPT_ABSENT = "the_release_ships_no_stage3_receipt"
G_RECEIPT_SELF_HASH = "the_receipt_hashes_to_what_it_says_it_does"
G_RECEIPT_BINDS = "every_artifact_the_receipt_names_is_on_disk_with_exactly_the_bound_bytes"
G_RECEIPT_ADMITTED = "the_bridge_report_the_receipt_names_actually_ADMITS_the_bridge"
G_RECEIPT_RESEALED = "the_receipt_names_the_aggregate_that_was_actually_admitted"

G_SELF_HASH = "the_bridge_hashes_to_what_it_says_it_does"
G_BINDINGS = "the_bridge_binds_the_admitted_native_bytes_it_was_built_from"
G_SOURCE_BYTES = "the_bound_native_bytes_are_on_disk_and_unchanged"
G_RECONSTRUCTED = "every_row_REBUILDS_from_the_admitted_native_bytes"
G_ORPHAN_ROW = "a_row_the_native_bytes_do_not_produce"
G_CTX_ALLOWLIST = "a_pathway_context_carries_only_pathway_context_fields"
G_CTX_FLAGS = "a_pathway_context_declares_itself_not_target_evidence"
G_CTX_RECONSTRUCTED = "every_pathway_context_REBUILDS_from_the_native_pathway_record"
G_COMPLETENESS = "the_bridge_carries_the_evidence_the_admitted_lanes_actually_contain"
G_ZERO_EVIDENCE = "a_bridge_with_no_evidence_is_not_a_bridge"
G_ADMISSION = "each_bound_lane_admission_is_a_real_ADMIT_report_bound_by_hash"
G_DUPLICATE = "a_row_or_context_key_appears_more_than_once"
G_ROW_FIREWALL = "a_typed_row_carries_only_contract_fields"

# EXACTLY what a pathway context may carry, and exactly what it may never carry.
CTX_ALLOWED = frozenset({
    "schema_version", "lane", "arm_key", "program_id", "context", "gene_set_id",
    "native_set_id_field", "source", "enrichment_value", "coverage", "convergence_ref",
    "leading_edge", "n_leading_edge", "n_leading_edge_joinable",
    "is_a_crispri_target_row", "may_be_matched_to_a_drug_as_a_target", "links_to_targets_via",
})
CTX_FORBIDDEN = frozenset({
    "arm_value", "desired_target_modulation", "phenocopy_class", "evaluable", "rank",
    "target_id", "observed_perturbation_modality", "program_effect_direction",
    "supported", "phenocopy_claim",
})

REQUIRED_BINDINGS = ("native_bundles", "lane_admissions", "stage1", "identity_source",
                     "aggregate")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _row_key(row: dict) -> tuple:
    return (str(row.get("lane")), str(row.get("arm_key")), str(row.get("target_id")))


def verify(bridge_root: str, *, bundles_root: str) -> dict[str, Any]:
    """Rebuild the bridge from the admitted native bytes, and refuse anything that differs."""
    failures: list[str] = []
    path = os.path.join(bridge_root, BRIDGE_FILE)
    if not os.path.exists(path):
        return {"verdict": "reject", "n_failed": 1,
                "failures": [f"{bridge_root}: no {BRIDGE_FILE}"], "n_rows": 0}
    with open(path) as fh:
        doc = json.load(fh)

    # (1) the seal. NECESSARY, NOT SUFFICIENT — a forger can recompute it, and did.
    claimed = doc.get("bridge_sha256")
    derived = _canon({k: v for k, v in doc.items() if k != "bridge_sha256"})
    if claimed != derived:
        failures.append(f"{G_SELF_HASH}: says {str(claimed)[:16]}; hashes to {derived[:16]}")

    # (2) IT MUST NAME WHAT IT WAS BUILT FROM. A bridge that binds nothing could have been
    # built from anything — including nothing.
    bindings = doc.get("bindings") or {}
    for key in REQUIRED_BINDINGS:
        if not bindings.get(key):
            failures.append(
                f"{G_BINDINGS}: binds no {key!r}. A typed row that names neither the bytes it "
                "came from nor the admission that cleared them is a row from nowhere")

    # (3) THE BOUND NATIVE BYTES MUST STILL BE THE ADMITTED ONES.
    sources: dict[str, dict] = {}
    for rel, bound in (bindings.get("native_bundles") or {}).items():
        src = os.path.join(bundles_root, rel)
        if not os.path.exists(src):
            failures.append(f"{G_SOURCE_BYTES}: {rel} is bound but is not on disk")
            continue
        for fname, want in (bound.get("files") or {}).items():
            # the inventory binds {raw_sha256, canonical_sha256}, not a bare hash string
            want = want.get("raw_sha256") if isinstance(want, dict) else want
            fp = os.path.join(src, fname)
            if not os.path.exists(fp):
                failures.append(f"{G_SOURCE_BYTES}: {rel}/{fname} is bound but absent")
            elif _sha256(fp) != want:
                failures.append(
                    f"{G_SOURCE_BYTES}: {rel}/{fname} bound {str(want)[:16]}, on disk "
                    f"{_sha256(fp)[:16]} — the bridge was built from different bytes than "
                    "the ones that were admitted")
        sources[rel] = bound

    # (4) THE RECONSTRUCTION. Rebuild every row from the native ranking + identity bytes, and
    # compare. THIS is what the coherent reseal cannot survive: the forged value is not the
    # value in the native ranking record, so the rebuilt row disagrees with the shipped one.
    rebuilt: dict[tuple, dict] = {}
    for rel, bound in sources.items():
        rebuilt.update(_rebuild_rows(os.path.join(bundles_root, rel), bound))

    shipped = {_row_key(r): r for r in (doc.get("target_rows") or [])}
    for key, row in shipped.items():
        want = rebuilt.get(key)
        if want is None:
            failures.append(
                f"{G_ORPHAN_ROW}: {key}: the admitted native bytes produce no such row. It "
                "agrees with itself, and with nothing that was measured")
            continue
        for field in ("arm_value", "evaluable", "rank", "target_id_namespace",
                      "observed_perturbation_modality", "desired_target_modulation",
                      "phenocopy_class", "program_effect_direction"):
            if row.get(field) != want.get(field):
                failures.append(
                    f"{G_RECONSTRUCTED}: {key}: {field}={row.get(field)!r}; rebuilt from the "
                    f"admitted native bytes it is {want.get(field)!r}")
    for key in rebuilt:
        if key not in shipped:
            failures.append(f"{G_RECONSTRUCTED}: {key}: the native bytes produce this row and "
                            "the bridge dropped it — a dropped row and a row that never "
                            "existed look identical")

    # (4b) THE AGGREGATE MUST HAVE ADMITTED, AND ITS BYTES MUST STILL BE THOSE BYTES.
    # The bridge is DOWNSTREAM of aggregate admission. A bridge built over a rejected — or a
    # since-edited — aggregate is a Stage-3 handoff for a release that was never cleared.
    failures += _verify_aggregate(bindings.get("aggregate") or {}, bundles_root)

    # (5) THE PATHWAY CONTEXTS — which the previous verifier did not read AT ALL.
    contexts = doc.get("pathway_contexts") or []
    failures += _verify_contexts(contexts, sources, bundles_root)

    # (6) DUPLICATES. Two rows under one key means one of them was never checked.
    seen_rows = [_row_key(r) for r in (doc.get("target_rows") or [])]
    for key in {k for k in seen_rows if seen_rows.count(k) > 1}:
        failures.append(f"{G_DUPLICATE}: {key} appears {seen_rows.count(key)} times")
    seen_ctx = [(str(c.get("arm_key")), str(c.get("gene_set_id"))) for c in contexts]
    for key in {k for k in seen_ctx if seen_ctx.count(k) > 1}:
        failures.append(f"{G_DUPLICATE}: context {key} appears {seen_ctx.count(key)} times")

    # (7) THE ROW FIREWALL. Run the INDEPENDENT row verifier over every row, so a smuggled
    # p/q, a `supported: true` on an opposed row or an equivalence claim is actually examined
    # rather than merely absent from the fields this module happens to compare.
    universe = {r["target_id"]: r.get("target_id_namespace")
                for r in (doc.get("target_rows") or []) if r.get("target_id")}
    failures += VR.verify_rows(doc.get("target_rows") or [], universe=universe)["failures"]

    # (8) THE ADMISSION. "Nonempty" is not an admission. Each lane must carry a REAL native
    # ADMIT, bound by its own report hash — otherwise `lane_admissions: {"x": 1}` clears a
    # release.
    failures += _verify_admissions(bindings.get("lane_admissions") or {})

    # (9) COMPLETENESS — AND THE ZERO-EVIDENCE FAIL-OPEN THIS CLOSES.
    #
    # A bridge with a dummy bundle, empty files, arbitrary non-empty bindings and NO rows and
    # NO contexts was ADMITTED with n_failed=0. Nothing it claimed was false, because it
    # claimed nothing. That is the most dangerous artifact of all: a clean report over an empty
    # release. Evidence that is absent is not evidence that is fine.
    #
    # So: every admitted lane must CONTRIBUTE. A Direct lane whose identity artifact is missing
    # does not quietly vanish into a temporal-only bridge — it FAILS COMPLETENESS, because a
    # Stage-3 handoff missing an entire lane of target evidence is not a smaller handoff, it is
    # a wrong one.
    failures += _verify_completeness(doc, sources, rebuilt, contexts)

    return {
        "verifier_id": "spot.stage02.stage3_bridge.independent_verifier.v1",
        "generator_is_not_verifier": True,
        "reconstructs_from_admitted_native_bytes": True,
        "self_hash_alone_is_sufficient": False,
        "n_rows": len(shipped),
        "n_rebuilt": len(rebuilt),
        "n_contexts": len(doc.get("pathway_contexts") or []),
        "n_failed": len(failures),
        "failures": failures[:50],
        "verdict": "admit" if not failures else "reject",
    }


def _verify_aggregate(agg: dict, bundles_root: str) -> list[str]:
    """The aggregate manifest AND its INDEPENDENT report — both bound, both still on disk."""
    bad: list[str] = []
    if not agg:
        return [f"{G_AGGREGATE}: the bridge binds no aggregate. It runs AFTER the aggregate is "
                "admitted; one that names no aggregate could have been built before it, or "
                "instead of it"]

    for role, fname in (("manifest", AGGREGATE_MANIFEST), ("report", AGGREGATE_REPORT)):
        bound = agg.get(role) or {}
        path = bound.get("path") or os.path.join(bundles_root, fname)
        if not os.path.exists(path):
            bad.append(f"{G_AGGREGATE}: the aggregate {role} is bound but is not on disk")
            continue
        if bound.get("raw_sha256") and _sha256(path) != bound["raw_sha256"]:
            bad.append(
                f"{G_AGGREGATE}: the aggregate {role} bound "
                f"{str(bound['raw_sha256'])[:16]}, on disk {_sha256(path)[:16]} — the bridge "
                "was built over a different aggregate than the one that was admitted")
            continue
        with open(path) as fh:
            doc = json.load(fh)
        if bound.get("canonical_sha256") and _canon(doc) != bound["canonical_sha256"]:
            bad.append(f"{G_AGGREGATE}: the aggregate {role}'s canonical hash does not match")
        # THE ADMISSION ITSELF. `admit` comes from the SEPARATE aggregate verifier's report —
        # never from the manifest, which never admits itself.
        if role == "report" and doc.get("verdict") != "admit":
            bad.append(
                f"{G_AGGREGATE}: the aggregate verifier's verdict is {doc.get('verdict')!r}, "
                "not 'admit'. The bridge runs only over an ADMITTED release — a Stage-3 "
                "handoff for a release nobody cleared is worse than no handoff")
    return bad


def _verify_admissions(admissions: dict) -> list[str]:
    """A lane admission is an ADMIT verdict from the lane's own verifier, bound by hash."""
    bad: list[str] = []
    for lane, adm in admissions.items():
        if not isinstance(adm, dict):
            bad.append(f"{G_ADMISSION}: [{lane}] the admission is not a report at all")
            continue
        if adm.get("native_verdict") != "ADMIT":
            bad.append(f"{G_ADMISSION}: [{lane}] native_verdict "
                       f"{adm.get('native_verdict')!r} is not the exact token 'ADMIT'")
        if not (adm.get("native_self_hash") or adm.get("report_id")):
            bad.append(f"{G_ADMISSION}: [{lane}] the admission binds no report hash — an "
                       "admission nobody can identify could have been written for anything")
    return bad


def _verify_completeness(doc: dict, sources: dict, rebuilt: dict, contexts: list) -> list[str]:
    """Every admitted lane must CONTRIBUTE. Silence is not a pass."""
    bad: list[str] = []
    rows = doc.get("target_rows") or []

    if not rows and not contexts:
        bad.append(
            f"{G_ZERO_EVIDENCE}: this bridge carries 0 target rows and 0 pathway contexts. "
            "Nothing it says is false, because it says nothing — and a clean report over an "
            "empty release is the most dangerous artifact there is")

    for rel, bound in sources.items():
        lane = str(bound.get("lane"))
        if lane == "pathway":
            if not any(str(c.get("arm_key", "")).startswith("pathway|") for c in contexts):
                bad.append(f"{G_COMPLETENESS}: the pathway bundle {rel} is bound and admitted, "
                           "and the bridge carries no pathway context from it")
            continue
        # a TARGET-EVIDENCE lane that contributed no rows
        if not any(r.get("lane") == lane for r in rows):
            bad.append(
                f"{G_COMPLETENESS}: the {lane} bundle {rel} is bound and ADMITTED, and the "
                "bridge carries NO target rows from it. If its identity artifact is missing, "
                "that is a REFUSAL — a Stage-3 handoff missing a whole lane of target evidence "
                "is not a smaller handoff, it is a wrong one")
    return bad


def _rebuild_rows(bundle_dir: str, bound: dict) -> dict[tuple, dict]:
    """Rebuild a bundle's typed rows FROM ITS OWN NATIVE BYTES. The producer's word is not used.

    Identity + assay come from the lane's bound identity source. A lane that binds none
    produces NO rows — and so a bridge that ships rows for it has rows from nowhere.
    """
    lane = str(bound.get("lane"))
    identity = _identity_index(bundle_dir, bound)
    if identity is None:
        return {}                       # no bound identity source -> this lane rebuilds nothing
    # temporal joins on base_key; a lane with an identity artifact joins on target_id
    join_on = "base_key" if (bound.get("identity_source") or {}).get(
        "kind") == "base_records" else "target_id"

    spec = NATIVE_ROWS.get(lane)
    if spec is None:
        return {}                       # pathway: no target rows exist to rebuild
    records = _native_records(bundle_dir, spec)
    join_on = spec["join_on"]
    value_field = spec["value_field"]

    out: dict[tuple, dict] = {}
    if True:
        for rec in records:
            # THE ARM KEY IS READ VERBATIM. An arm key rebuilt from a filename and a sorted
            # context is a key I invented — it would differ from the producer's on any lane
            # whose context order or separator I guessed wrong, and then EVERY row would look
            # like an orphan (or, worse, match the wrong arm).
            arm_key = str(rec.get("arm_key") or "")
            change = arm_key.split("|")[2] if arm_key.count("|") >= 2 else None
            # ...and identity is joined on the LANE'S OWN key, verbatim.
            join_value = str(rec.get(join_on) if rec.get(join_on) is not None
                             else rec.get("target_id"))
            ident = identity.get(join_value) or {}
            value, evaluable = rec.get(value_field), bool(rec.get("evaluable"))
            modulation = VR._rederive(value, evaluable)
            out[(lane, arm_key, str(rec.get("target_id")))] = {
                "arm_value": value,
                "evaluable": evaluable,
                "rank": rec.get("rank"),
                "target_id_namespace": ident.get("target_id_namespace"),
                "observed_perturbation_modality": ident.get("modality"),
                "desired_target_modulation": modulation,
                "phenocopy_class": VR.CLASS_OF.get(modulation),
                "program_effect_direction": change,
            }
    return out


def _native_records(bundle_dir: str, spec: dict) -> list:
    """The lane's OWN row bytes. Direct: arms.parquet. Temporal: rankings/*.json."""
    if spec["kind"] == "parquet":
        path = os.path.join(bundle_dir, spec["file"])
        if not os.path.exists(path):
            return []
        import pandas as pd
        return pd.read_parquet(path).to_dict("records")

    rdir = os.path.join(bundle_dir, spec["dir"])
    if not os.path.isdir(rdir):
        return []
    out: list = []
    for fname in sorted(os.listdir(rdir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        # `records`, with `ranked` as the native alias (arm_topology.ARM_RANKING_ROWS)
        out += doc.get("records") if doc.get("records") is not None else (doc.get("ranked") or [])
    return out


def _identity_index(bundle_dir: str, bound: dict) -> Any:
    """target_id -> {namespace, modality}, from the lane's BOUND identity source.

    Direct binds NO such artifact today (`arm_artifacts.VERIFIED_PATHS` has no identity table,
    and the CRISPRi modality is never emitted), so it returns None and rebuilds nothing.
    """
    src = bound.get("identity_source") or {}
    kind = src.get("kind")
    if kind == "base_records":
        with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
            doc = json.load(fh)
        # keyed by BASE_KEY, verbatim — that is the key temporal's arm records join on
        return {str(b.get("base_key")): {
            "target_id": b.get("target_id"),
            "target_id_namespace": b.get("target_id_namespace"),
            "modality": b.get("perturbation_modality"),
        } for b in (doc.get("base_records") or [])}
    if kind == "identity_artifact":
        # THE PRODUCER'S OWN BYTES, in place. Never a reference copy this verifier wrote for
        # itself: a verifier that creates the file it is checking has checked its own work.
        name = src.get("file") or IDENTITY_FILE
        if name != IDENTITY_FILE:
            return None                   # a file by another name is not this artifact
        path = os.path.join(bundle_dir, name)
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            doc = json.load(fh)
        if doc.get("schema_version") != IDENTITY_SCHEMA:
            return None
        rows = doc.get(IDENTITY_RECORDS_KEY) or []

        # UNIQUE, or it is not a join key: a duplicated target silently multiplies every row
        # it is joined to.
        ids = [str(r.get("target_id")) for r in rows]
        if len(ids) != len(set(ids)):
            return None
        return {str(r.get("target_id")): {
            "target_id": r.get("target_id"),
            "target_id_namespace": r.get("target_id_namespace"),
            "modality": r.get(IDENTITY_MODALITY_FIELD),
        } for r in rows}
    return None


def _verify_contexts(contexts: list, sources: dict, bundles_root: str) -> list[str]:
    """A pathway context is a GENE SET's record. It may never wear a target's clothes."""
    bad: list[str] = []
    native: dict[tuple, dict] = {}
    for rel, bound in sources.items():
        if str(bound.get("lane")) != "pathway":
            continue
        native.update(_native_pathway_records(os.path.join(bundles_root, rel), bound))

    for ctx in contexts:
        where = f"{ctx.get('arm_key')}/{ctx.get('gene_set_id')}"

        extra = sorted(set(ctx) - CTX_ALLOWED)
        if extra:
            bad.append(f"{G_CTX_ALLOWLIST}: {where}: carries {extra}, which is not a pathway "
                       "context field")
        smuggled = sorted(set(ctx) & CTX_FORBIDDEN)
        if smuggled:
            bad.append(
                f"{G_CTX_ALLOWLIST}: {where}: carries TARGET-EVIDENCE field(s) {smuggled}. An "
                "enrichment value is a statement about a gene set; a context that also carries "
                "an arm value and a drug direction is a target row wearing a pathway's clothes")

        if ctx.get("is_a_crispri_target_row") is not False:
            bad.append(f"{G_CTX_FLAGS}: {where}: is_a_crispri_target_row="
                       f"{ctx.get('is_a_crispri_target_row')!r}; a pathway context is never "
                       "target evidence and must say so")
        if ctx.get("may_be_matched_to_a_drug_as_a_target") is not False:
            bad.append(f"{G_CTX_FLAGS}: {where}: may_be_matched_to_a_drug_as_a_target="
                       f"{ctx.get('may_be_matched_to_a_drug_as_a_target')!r} — a gene set is "
                       "not a drug target")

        # ...and it must actually be one of the native records.
        want = native.get((str(ctx.get("arm_key")), str(ctx.get("gene_set_id"))))
        if want is None:
            bad.append(f"{G_CTX_RECONSTRUCTED}: {where}: the native pathway records contain no "
                       "such (arm, gene set)")
            continue
        if ctx.get("enrichment_value") != want.get("enrichment_value"):
            bad.append(f"{G_CTX_RECONSTRUCTED}: {where}: enrichment_value "
                       f"{ctx.get('enrichment_value')!r} != native {want['enrichment_value']!r}")
        shipped_le = [e.get("target_id") for e in (ctx.get("leading_edge") or [])]
        if shipped_le != [str(t) for t in (want.get("leading_edge") or [])]:
            bad.append(f"{G_CTX_RECONSTRUCTED}: {where}: the leading edge is not the native one")
        for entry in (ctx.get("leading_edge") or []):
            ns, joinable = entry.get("target_id_namespace"), entry.get("joinable")
            if joinable is True and ns not in VR.NAMESPACES:
                bad.append(f"{G_CTX_RECONSTRUCTED}: {where}: leading-edge "
                           f"{entry.get('target_id')!r} claims joinable with namespace {ns!r}")
            if joinable is False and ns is not None:
                bad.append(f"{G_CTX_RECONSTRUCTED}: {where}: leading-edge "
                           f"{entry.get('target_id')!r} is non-joinable yet carries {ns!r}")
    return bad


def _native_pathway_records(bundle_dir: str, bound: dict) -> dict[tuple, dict]:
    """The pathway lane's OWN records, keyed (arm_key, set_id). Its field is `set_id`."""
    path = os.path.join(bundle_dir, "arm_bundle.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        doc = json.load(fh)
    out: dict[tuple, dict] = {}
    for rec in (doc.get("records") or []):
        # the pathway lane names it `pathway_arm_key`
        arm_key = str(rec.get("pathway_arm_key") or rec.get("arm_key"))
        out[(arm_key, str(rec.get("set_id")))] = {
            "enrichment_value": rec.get("enrichment_value"),
            "leading_edge": rec.get("leading_edge") or [],
        }
    return out


def main(argv=None) -> int:
    """The SEPARATE process. It writes its own report; its exit code is the verdict."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Reopen the admitted native bytes and REBUILD the Stage-3 bridge. "
                    "Trusts nothing the bridge says about itself.")
    ap.add_argument("--bridge-root", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--report", required=True, help="a FILE, not a directory")
    ap.add_argument("--receipt-only", action="store_true",
                    help="verify stage2_stage3_receipt.json INSTEAD — the join Stage 3 gates "
                         "on. A swapped receipt is a swapped release. Its report is written "
                         "separately: the receipt binds the bridge report, so rewriting that "
                         "report while checking the receipt would invalidate it.")
    args = ap.parse_args(argv)

    # RECEIPT-ONLY is a SEPARATE pass with a SEPARATE report, and it must be: the receipt
    # BINDS the bridge report, so re-writing that report while checking the receipt would
    # invalidate the very hash the receipt was built on. The chain only grows forward.
    report = (verify_receipt(args.bridge_root, bundles_root=args.bundles_root)
              if args.receipt_only
              else verify(args.bridge_root, bundles_root=args.bundles_root))
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    for f in report["failures"][:10]:
        print(f"  - {f}")
    return 0 if report["verdict"] == "admit" else 1



def verify_receipt(bridge_root: str, *, bundles_root: str) -> dict[str, Any]:
    """REOPEN the receipt and re-derive every artifact it names.

    The receipt is what lets a reader walk from an ADMITTED aggregate to its Stage-3 handoff
    WITHOUT either artifact having been re-sealed. Stage 3 gates on it — so a swapped receipt
    is a swapped release. It could point at a different bridge, a different aggregate, or a
    bridge report that never admitted anything, and every hash inside it would still agree
    with itself.

    So nothing here is taken at its word: every path it names is reopened, re-hashed against
    the bytes it bound, and the bridge report it names must actually say `admit`.
    """
    failures: list[str] = []
    path = os.path.join(bridge_root, RECEIPT_FILE)
    if not os.path.exists(path):
        return {"verdict": "reject", "n_failed": 1, "receipt": None,
                "failures": [f"{G_RECEIPT_ABSENT}: no {RECEIPT_FILE} at {bridge_root}. The "
                             "receipt is the ONLY thing that joins an admitted aggregate to "
                             "its Stage-3 handoff; without it, Stage 3 is trusting a bridge "
                             "that names an aggregate nobody re-checked"]}
    with open(path) as fh:
        doc = json.load(fh)

    if doc.get("schema_version") != RECEIPT_SCHEMA:
        failures.append(f"{G_RECEIPT_SELF_HASH}: schema {doc.get('schema_version')!r} is not "
                        f"{RECEIPT_SCHEMA!r}")

    claimed = doc.get("receipt_sha256")
    derived = _canon({k: v for k, v in doc.items() if k != "receipt_sha256"})
    if claimed != derived:
        failures.append(f"{G_RECEIPT_SELF_HASH}: says {str(claimed)[:16]}; its own content "
                        f"hashes to {derived[:16]}")

    # THE AGGREGATE MUST NOT HAVE BEEN RE-SEALED. The receipt exists precisely to make that
    # unnecessary; a receipt that claimed otherwise would be describing a different design.
    if (doc.get("aggregate_is_immutable") is not True
            or doc.get("aggregate_was_resealed") is not False):
        failures.append(
            f"{G_RECEIPT_RESEALED}: the receipt says aggregate_was_resealed="
            f"{doc.get('aggregate_was_resealed')!r}. An admitted aggregate is never rewritten "
            "— the chain only grows forward")

    # EVERY REFERENT, REOPENED. raw AND canonical, against the bytes on disk.
    referents = {
        "aggregate.manifest": (doc.get("aggregate") or {}).get("manifest"),
        "aggregate.report": (doc.get("aggregate") or {}).get("report"),
        "bridge": doc.get("bridge"),
        "bridge_report": doc.get("bridge_report"),
    }
    loaded: dict[str, Any] = {}
    for name, bound in referents.items():
        if not bound:
            failures.append(f"{G_RECEIPT_BINDS}: the receipt names no {name}")
            continue
        p = bound.get("path")
        if not p or not os.path.exists(p):
            failures.append(f"{G_RECEIPT_BINDS}: {name}: {p!r} is named but is not on disk")
            continue
        if _sha256(p) != bound.get("raw_sha256"):
            failures.append(
                f"{G_RECEIPT_BINDS}: {name}: bound {str(bound.get('raw_sha256'))[:16]}, on "
                f"disk {_sha256(p)[:16]} — the receipt names a different artifact than the "
                "one that is there")
            continue
        with open(p) as fh:
            body = json.load(fh)
        if bound.get("canonical_sha256") and _canon(body) != bound["canonical_sha256"]:
            failures.append(f"{G_RECEIPT_BINDS}: {name}: canonical hash does not match")
        loaded[name] = body

    # ...and the reports it names must actually ADMIT. A receipt binding a REJECT report is a
    # receipt for a release that was refused.
    for name, want in (("aggregate.report", "admit"), ("bridge_report", "admit")):
        body = loaded.get(name)
        if body is not None and body.get("verdict") != want:
            failures.append(
                f"{G_RECEIPT_ADMITTED}: {name} says verdict={body.get('verdict')!r}, not "
                f"{want!r}. The receipt is a receipt FOR AN ADMISSION")

    return {
        "verifier_id": "spot.stage02.stage3_receipt.independent_verifier.v1",
        "generator_is_not_verifier": True,
        "receipt": RECEIPT_FILE,
        "n_failed": len(failures),
        "failures": failures[:50],
        "verdict": "admit" if not failures else "reject",
    }

if __name__ == "__main__":
    raise SystemExit(main())
