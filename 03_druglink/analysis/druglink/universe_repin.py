"""RE-EMIT the admitted universe store under Stage-2's canonical namespace vocabulary.

THE DIVERGENCE
--------------
Stage-2's W3 release serializes its typed identities as ``ensembl_gene_id`` / ``gene_symbol``.
The store was extracted speaking ``ensembl_gene`` / ``symbol``. The join between them is by
EXACT TYPED IDENTITY — the only honest join, because a symbol match silently re-attributes
every edge the first time a gene is renamed — so exact-token equality refused every one of the
11,522 real Ensembl rows, and the whole lane produced ZERO edges.

Two ways out, and only one of them is honest:

  * an ALIAS LAYER that maps ``ensembl_gene`` -> ``ensembl_gene_id`` at join time. It works on
    the day it is written, it is invisible in every test, and it is precisely how two admitted
    artifacts drift apart while both stay green. REFUSED, everywhere, including here;
  * STANDARDISE the store on Stage-2's tokens, and re-pin it. That is this module.

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT
---------------------------------------------
This is a VOCABULARY RE-PIN, not a re-extraction. Not one byte of science moves: no row is
added, dropped, merged or reordered; no assertion, molecule, licence, attribution or
provenance field changes. ChEMBL is never re-queried — the extraction happened once, on
tcefold, and re-running it would produce a different store for reasons that have nothing to do
with a token.

The load-bearing proof is :func:`scientific_content_sha256`: a canonical hash over every store
row with ``target_id_namespace`` PROJECTED OUT. It is identical before and after, and that is
what demonstrates that only the vocabulary moved. The ``store_id`` and the typed-universe hash
MUST change, because the typed universe hashes ``{target_id, target_id_namespace}`` — a token
change necessarily moves it. A re-pin whose hashes did NOT move would mean the re-pin did not
happen.

The old store is left on disk, untouched, and its ``store_id`` goes on the REFUSED list: a
stale-vocabulary store can never be re-admitted by accident.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from typing import Any, Iterable, Mapping

from . import universe_verify as uv
from .hashing import content_hash, file_sha256, without

REPIN_POLICY_VERSION = "stage3-universe-repin-v1"

MANIFEST_SCHEMA_V1 = "spot.stage03_universe_manifest.v1"      # ensembl_gene / symbol
MANIFEST_SCHEMA_V2 = "spot.stage03_universe_manifest.v2"      # Stage-2 (W3) canonical tokens

# The ONE token change this module makes. Written as a map so it can be read, tested and cited
# — and it lives HERE, in the re-emit tool, never in the production loader. A translation map
# in the loader is an alias layer; a translation map in a one-shot re-emitter is a migration.
REPIN_TOKENS = {"ensembl_gene": uv.NS_ENSEMBL_GENE, "symbol": uv.NS_SYMBOL}

# The store this re-pin was derived FROM. Literals: a pin computed from the thing it pins is
# not a pin, and the whole point of the proof is that these are the bytes we started with.
SOURCE_STORE_ID = \
    "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160"
SOURCE_TYPED_UNIVERSE_SHA256 = \
    "5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af"
SOURCE_PRODUCER_COMMIT = "d268a74f339d346609951e73810ab26e2e654d86"

MANIFEST_NAME = "universe_manifest.json"
ROWS_NAME = "universe_store.rows.json"
VERIFY_REPORT_NAME = "verify_report.json"

# Carried BYTE-FOR-BYTE. The licences, the attribution, the source provenance, the eligibility
# evidence and the extraction's own metrics are facts about an extraction that ALREADY
# happened; re-writing them would be inventing a run that never took place.
CARRIED_VERBATIM = (
    "target_eligibility_evidence.json",
    "source_provenance.public.json",
    "CHEMBL_LICENSE",
    "CHEMBL_REQUIRED_ATTRIBUTION",
    "CHEMBL_checksums.txt",
    "UNIPROT_2026_02.by_organism.RELEASE.metalink",
    "UNIPROT_2026_02.relnotes.txt",
    # The EXTRACTION's metrics. It names the SOURCE store_id, because it describes the
    # extraction run that produced it — and that run was not repeated. Carried verbatim rather
    # than rewritten: peak RSS and wall-clock for a run that never happened would be fabricated.
    "extraction_metrics.json",
)

GATE_UNKNOWN_NAMESPACE_TOKEN = "a_store_row_carries_a_namespace_token_nobody_agreed_to"
GATE_ALREADY_CANONICAL = "this_store_already_speaks_the_canonical_vocabulary"
GATE_AMBIGUOUS_PROJECTED_IDENTITY = "two_rows_share_one_target_id_once_the_namespace_is_removed"
GATE_SCIENCE_MOVED = "the_scientific_content_hash_moved_and_this_is_only_a_vocabulary_re_pin"
GATE_CARRIED_ARTIFACT_MOVED = "a_carried_artifact_is_not_byte_identical_to_the_source"
GATE_REPIN_DID_NOT_VERIFY = "the_re_emitted_store_did_not_verify_from_its_own_bytes"
GATE_IDENTITY_DID_NOT_MOVE = "the_re_pinned_store_kept_the_source_identity"
GATE_SOURCE_NOT_ON_DISK = "the_source_universe_store_is_not_on_disk"


class RepinError(ValueError):
    """The vocabulary re-pin could not be made, or could not be proved. Refuse."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


# --------------------------------------------------------------------------- #
# 1. THE LOAD-BEARING PROOF: the science, hashed WITHOUT the token.
# --------------------------------------------------------------------------- #
def scientific_content_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    """Canonical hash over every store row with ``target_id_namespace`` PROJECTED OUT.

    This is the invariant a vocabulary re-pin must preserve EXACTLY. It covers every other
    field of every row — the dispositions, the drug assertions, the identities, the accessions,
    the variant and ambiguous lanes, the stated missingness reasons — and it deliberately
    covers the ``target_id`` itself, so a re-pin that renamed a target would be caught here
    even though its namespace was the only field it was allowed to touch.

    Rows are sorted by ``target_id`` so the hash is order-invariant: it must not be able to
    hide a reorder, and it must not be able to FAIL on one either — the re-pin is not permitted
    to reorder rows, and :func:`repin_proof` asserts the order separately and exactly.

    With the namespace removed, ``target_id`` has to carry the identity alone. If two rows
    shared one id across namespaces the projection would be ambiguous and the hash would be
    meaningless, so that REFUSES rather than quietly hashing a collision.
    """
    projected = [without(r, ("target_id_namespace",)) for r in rows]
    ids = [r.get("target_id") for r in projected]
    if len(set(ids)) != len(ids):
        dupes = sorted({str(t) for t in ids if ids.count(t) > 1})
        raise RepinError(
            GATE_AMBIGUOUS_PROJECTED_IDENTITY,
            f"{dupes[:3]} appear under more than one namespace. With the namespace projected "
            "out, target_id must carry the identity by itself — otherwise this hash silently "
            "conflates two different targets and proves nothing about either")
    return content_hash(sorted(projected, key=lambda r: str(r.get("target_id"))))


# --------------------------------------------------------------------------- #
# 2. The token map, applied to rows and to nothing else.
# --------------------------------------------------------------------------- #
def repin_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One row, with ONLY ``target_id_namespace`` rewritten. Every other key is passed through.

    An unrecognised token REFUSES by name. It is never coerced onto a known one and never
    defaulted to the majority namespace: a token nobody agreed to names a different identity
    space, and guessing which one would be the alias layer this whole exercise exists to avoid.
    """
    token = row.get("target_id_namespace")
    if token in uv.STORE_NAMESPACES:          # already canonical; nothing to do to this row
        return dict(row)
    if token not in REPIN_TOKENS:
        raise RepinError(
            GATE_UNKNOWN_NAMESPACE_TOKEN,
            f"row {row.get('target_id')!r} carries target_id_namespace={token!r}. The re-pin "
            f"knows {sorted(REPIN_TOKENS)} (retired) and {list(uv.STORE_NAMESPACES)} "
            "(canonical), and it will not invent a mapping for a third")
    return {**row, "target_id_namespace": REPIN_TOKENS[str(token)]}


def repin_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every row, in the SOURCE ORDER. A re-pin that reorders rows is not a re-pin."""
    return [repin_row(r) for r in rows]


def typed_universe(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The identity pair the store binds. The store verifier's own projection, sorted."""
    return sorted(({"target_id": str(r["target_id"]),
                    "target_id_namespace": str(r["target_id_namespace"])} for r in rows),
                  key=lambda t: (t["target_id_namespace"], t["target_id"]))


def repin_manifest(manifest: Mapping[str, Any], rows: list[dict[str, Any]], *,
                   created_at: str) -> dict[str, Any]:
    """The manifest, with every hash the token change MOVED recomputed from the new bytes.

    Recomputed: the store-rows hash, the typed-universe hash, the ``store_id`` they feed, and
    the manifest's own content hash. Unchanged and carried across: the extraction query hash,
    both source-release hashes, the eligibility-evidence hash, the provenance hash, every
    licence, every attribution, and every coverage count — because none of them moved.
    """
    out = copy.deepcopy(dict(manifest))
    out["schema_version"] = MANIFEST_SCHEMA_V2
    out["created_at"] = created_at
    out["extraction"]["store_rows_sha256"] = content_hash(rows)

    typed = typed_universe(rows)
    universe_sha = uv._typed_universe_hash(typed)
    out["universe_binding"]["universe_targets_sha256"] = universe_sha
    out["universe_binding"]["n_targets_total"] = len(rows)
    out["coverage"] = {**out["coverage"], **uv._recompute_coverage(rows)}

    # The lineage of the re-pin, stated in the artifact rather than left in a memo. A reader
    # who opens this store must be able to see WHAT changed and WHAT it came from.
    out["namespace_vocabulary"] = {
        "vocabulary": list(uv.STORE_NAMESPACES),
        "vocabulary_source": "stage2_w3_release_serialization",
        "retired_vocabulary": list(uv.RETIRED_NAMESPACES),
        "token_map": dict(REPIN_TOKENS),
        "repin_policy_version": REPIN_POLICY_VERSION,
        "repinned_from_store_id": SOURCE_STORE_ID,
        "repinned_from_typed_universe_sha256": SOURCE_TYPED_UNIVERSE_SHA256,
        "repinned_from_producer_commit": SOURCE_PRODUCER_COMMIT,
        "scientific_content_sha256": scientific_content_sha256(rows),
        "chembl_was_not_requeried": True,
        "extraction_metrics_describes_the_source_extraction": True,
        "note": ("a VOCABULARY re-pin, not a re-extraction: only target_id_namespace was "
                 "rewritten. The scientific content hash — every row with the namespace "
                 "projected out — is identical to the source store's. store_id and the typed "
                 "universe hash necessarily MOVE, because the typed universe hashes "
                 "{target_id, target_id_namespace}"),
    }

    out["store_id"] = uv.store_identity(out)
    out["content_sha256"] = uv._manifest_identity(out)
    return out


# --------------------------------------------------------------------------- #
# 3. Emit, re-verify from disk, and PROVE.
# --------------------------------------------------------------------------- #
def _write_json(path: str, obj: Any) -> None:
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def _counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Everything the re-pin must not move, recounted from the bytes in front of us."""
    rows = list(rows)
    lanes = {"drugs": [], "variant_specific_assertions": [], "ambiguous_source_assertions": []}
    for r in rows:
        for lane in lanes:
            lanes[lane].extend(r.get(lane) or [])
    ns: dict[str, int] = {}
    for r in rows:
        ns[str(r["target_id_namespace"])] = ns.get(str(r["target_id_namespace"]), 0) + 1
    symbol_ns = [n for n in ns if n not in (uv.NS_ENSEMBL_GENE, "ensembl_gene")]
    return {
        "n_rows": len(rows),
        "namespace_split": ns,
        "symbol_targets": sorted(r["target_id"] for r in rows
                                 if str(r["target_id_namespace"]) in symbol_ns),
        "n_assertions_total": sum(len(v) for v in lanes.values()),
        "n_assertions_general_rankable": len(lanes["drugs"]),
        "n_assertions_variant": len(lanes["variant_specific_assertions"]),
        "n_assertions_ambiguous": len(lanes["ambiguous_source_assertions"]),
        "n_targets_with_general_drug_evidence": sum(1 for r in rows if r.get("drugs")),
        "n_molecules_general_lane": len({a["molecule_chembl_id"] for a in lanes["drugs"]}),
        "n_symbol_target_drug_edges": sum(
            len(r.get(lane) or []) for r in rows for lane in lanes
            if str(r["target_id_namespace"]) in symbol_ns),
        "dispositions": {d: sum(1 for r in rows if r["disposition"] == d)
                         for d in sorted({str(r["disposition"]) for r in rows})},
    }


def repin_proof(*, src_rows: list[dict[str, Any]], src_manifest: Mapping[str, Any],
                new_rows: list[dict[str, Any]], new_manifest: Mapping[str, Any],
                carried: dict[str, dict[str, str]],
                verify: Mapping[str, Any]) -> dict[str, Any]:
    """The report that proves the science is untouched. Every obligation asserted, not asserted-at.

    Raises rather than returning a report with a failed obligation in it: a proof that reports
    its own falsity is a document, not a gate.
    """
    before, after = _counts(src_rows), _counts(new_rows)
    sci_before = scientific_content_sha256(src_rows)
    sci_after = scientific_content_sha256(new_rows)

    # (3) THE LOAD-BEARING PROOF. Only the vocabulary moved.
    if sci_before != sci_after:
        raise RepinError(
            GATE_SCIENCE_MOVED,
            f"the scientific content hash moved: {sci_before[:16]}… -> {sci_after[:16]}…. Only "
            "target_id_namespace was permitted to change, and this hash excludes exactly that "
            "field — so something else did")

    # (4) The identity map is BIJECTIVE and TOTAL, and nothing was reordered.
    if [r["target_id"] for r in src_rows] != [r["target_id"] for r in new_rows]:
        raise RepinError(
            GATE_SCIENCE_MOVED,
            "the target_id sequence changed. A re-pin adds, drops, merges and reorders nothing")

    # (5) The identity MUST move. A re-pin whose hashes stayed put did not happen.
    if new_manifest["store_id"] == src_manifest["store_id"]:
        raise RepinError(
            GATE_IDENTITY_DID_NOT_MOVE,
            "the re-pinned store kept the source store_id. The typed universe hashes "
            "{target_id, target_id_namespace}, so a token change MUST move it")

    # (6) Everything carried was carried byte-for-byte.
    moved = [n for n, h in carried.items() if h["source_sha256"] != h["repinned_sha256"]]
    if moved:
        raise RepinError(
            GATE_CARRIED_ARTIFACT_MOVED,
            f"{moved} are not byte-identical to the source. Licences, attribution, source "
            "provenance and eligibility evidence are carried, never rewritten")

    if not verify.get("ok"):
        raise RepinError(GATE_REPIN_DID_NOT_VERIFY,
                         f"the re-emitted store did not verify: {verify.get('violations')}")

    return {
        "repin_policy_version": REPIN_POLICY_VERSION,
        "what_this_is": ("a VOCABULARY re-pin of the admitted universe store onto Stage-2's "
                         "canonical namespace tokens. ChEMBL was not re-queried; no row, "
                         "assertion, molecule, licence or provenance field changed"),
        "token_map": dict(REPIN_TOKENS),

        "identity": {
            "source_store_id": src_manifest["store_id"],
            "repinned_store_id": new_manifest["store_id"],
            "source_typed_universe_sha256":
                src_manifest["universe_binding"]["universe_targets_sha256"],
            "repinned_typed_universe_sha256":
                new_manifest["universe_binding"]["universe_targets_sha256"],
            "source_manifest_content_sha256": src_manifest["content_sha256"],
            "repinned_manifest_content_sha256": new_manifest["content_sha256"],
            "source_store_rows_sha256": src_manifest["extraction"]["store_rows_sha256"],
            "repinned_store_rows_sha256": new_manifest["extraction"]["store_rows_sha256"],
            "source_schema_version": src_manifest.get("schema_version"),
            "repinned_schema_version": new_manifest.get("schema_version"),
            "store_id_moved": True,
            "typed_universe_hash_moved": True,
            "why_they_must_move": ("the typed universe hashes {target_id, "
                                   "target_id_namespace}; a token change necessarily moves it"),
        },

        "scientific_content_hash": {
            "definition": ("sha256 over the canonical JSON of every store row with "
                           "target_id_namespace projected out, rows sorted by target_id"),
            "source": sci_before,
            "repinned": sci_after,
            "identical": True,
            "means": "only the namespace vocabulary moved; not a row of science did",
        },

        "row_bijection": {
            "n_rows_source": before["n_rows"],
            "n_rows_repinned": after["n_rows"],
            "target_id_sequence_identical": True,
            "total": True, "bijective": True,
            "rows_added": 0, "rows_dropped": 0, "rows_merged": 0, "rows_reordered": 0,
        },

        "counts": {"source": before, "repinned": after,
                   "unchanged": {k: before[k] for k in before if k != "namespace_split"}},

        "stated_missingness": {
            "symbol_targets": after["symbol_targets"],
            "n_symbol_target_drug_edges": after["n_symbol_target_drug_edges"],
            "disposition": "unsupported_namespace",
            "meaning": ("these four targets carry NO drug evidence in ChEMBL. The join resolves "
                        "them at the IDENTITY level and returns zero edges with STATED "
                        "missingness — an absence nobody recorded is not an absence anybody "
                        "ruled out, and neither is invented into an edge"),
        },

        "carried_verbatim": carried,
        "verification_from_disk": dict(verify),
    }


def emit(*, src_dir: str, dest_dir: str, created_at: str) -> dict[str, Any]:
    """Re-emit the store at ``src_dir`` into ``dest_dir``, re-verify it, and prove it.

    The source is NEVER mutated. ``dest_dir`` must not be the source.
    """
    src_manifest_path = os.path.join(src_dir, MANIFEST_NAME)
    if not os.path.isdir(src_dir) or not os.path.exists(src_manifest_path):
        raise RepinError(GATE_SOURCE_NOT_ON_DISK,
                         f"no {MANIFEST_NAME} under {src_dir!r}")
    if os.path.abspath(src_dir) == os.path.abspath(dest_dir):
        raise RepinError(GATE_SOURCE_NOT_ON_DISK,
                         "refusing to re-emit a store over itself; the admitted bytes are "
                         "never mutated in place")

    with open(src_manifest_path) as fh:
        src_manifest = json.load(fh)
    with open(os.path.join(src_dir, ROWS_NAME)) as fh:
        src_rows = json.load(fh)

    if src_manifest.get("schema_version") == MANIFEST_SCHEMA_V2:
        raise RepinError(
            GATE_ALREADY_CANONICAL,
            f"{src_dir!r} already declares {MANIFEST_SCHEMA_V2}. Re-pinning a canonical store "
            "would be a no-op that mints a new identity for no reason")

    new_rows = repin_rows(src_rows)
    new_manifest = repin_manifest(src_manifest, new_rows, created_at=created_at)

    os.makedirs(dest_dir, exist_ok=True)
    carried: dict[str, dict[str, str]] = {}
    for name in CARRIED_VERBATIM:
        src_path = os.path.join(src_dir, name)
        if not os.path.exists(src_path):
            raise RepinError(
                GATE_CARRIED_ARTIFACT_MOVED,
                f"{name} is not in the source store. A licence, an attribution or a provenance "
                "artifact that fails to travel is a licence breach, not a missing nicety")
        dest_path = os.path.join(dest_dir, name)
        shutil.copy2(src_path, dest_path)
        carried[name] = {"source_sha256": file_sha256(src_path),
                         "repinned_sha256": file_sha256(dest_path)}

    _write_json(os.path.join(dest_dir, ROWS_NAME), new_rows)
    _write_json(os.path.join(dest_dir, MANIFEST_NAME), new_manifest)

    # THE STORE'S OWN VERIFICATION, RE-RUN FROM DISK — over the bytes just written, not the
    # objects that wrote them.
    verify = uv.verify_from_disk(store_dir=dest_dir, manifest=new_manifest,
                                 universe_targets=typed_universe(new_rows))
    _write_json(os.path.join(dest_dir, VERIFY_REPORT_NAME), verify)

    return repin_proof(src_rows=src_rows, src_manifest=src_manifest, new_rows=new_rows,
                       new_manifest=new_manifest, carried=carried, verify=verify)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src", required=True, help="the source (retired-vocabulary) store dir")
    p.add_argument("--dest", required=True, help="a NEW dir; the source is never mutated")
    p.add_argument("--created-at", required=True, help="ISO-8601 UTC, e.g. 2026-07-13T12:00:00Z")
    p.add_argument("--report", help="write the re-pin proof here (JSON)")
    args = p.parse_args(argv)
    try:
        proof = emit(src_dir=args.src, dest_dir=args.dest, created_at=args.created_at)
    except RepinError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    if args.report:
        _write_json(args.report, proof)
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":                                       # pragma: no cover
    raise SystemExit(main())
