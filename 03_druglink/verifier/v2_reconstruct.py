"""Independent ADMISSION of the Stage-3 v2 inputs: the NATIVE Stage-2 aggregate, and the store.

Nothing here is copied from the emitted bundle. The Stage-2 release is re-admitted from the
actual bytes on disk, its 15 all-arm bundle DIRECTORIES and 300 arm slots are rebuilt, every
bound byte is re-hashed, the typed universe is re-derived from the store's own rows, and the
store is re-proved against its own artifacts. What is EMITTED from all of that is rebuilt one
module over, in :mod:`verifier.v2_rebuild`.

Imports NOTHING from ``druglink``. Every refusal is a NAMED gate on the report: a missing
artifact fails closed by name, never as an exception and never as a silent pass.

THE NATIVE CONTRACT, RESTATED — AND WHAT IT REPLACED
----------------------------------------------------
What stood here parsed a Stage-2 schema that DOES NOT EXIST. It read an ``inventory[]`` array, a
``stage1_release.raw_sha256`` pin and an ``admits{}`` block, and it asserted independence by
looking for the substring ``"independent"`` in the verifier's id. Stage 2 emits none of those.
Against the real bytes, ``report.get("admits") or {}`` yields ``{}`` — so both hash comparisons
became ``None != <sha>``, which is not a check but an accident; and the substring gate would have
REFUSED the genuine report (whose id contains no such word) while ADMITTING any forgery that
merely named itself "…independent…".

The real contract:

manifest  ``spot.stage02_run_manifest.v3_topology_only`` — top-level ``bundles[]``, each an
          all-arm bundle DIRECTORY (an ``out_dir`` NAME + a ``files{}`` map + ``arm_keys``), the
          bound ``stage1_v3_release``, and a ``manifest_sha256`` that is the SEMANTIC self-hash:
          the content hash of the document EXCLUDING ``created_at``, ``manifest_sha256`` and
          ``path``. We RE-DERIVE it; we never read it.
report    ``spot.stage02_run_manifest_verification.v1``, written by the pinned verifier
          ``spot.stage02.run_manifest.verifier.v1``. INDEPENDENCE IS A STRUCTURED FIELD —
          ``generator_is_not_verifier`` — and the identity is the EXACT pinned id. A name is not
          a binding, so THAT is what is bound, and a null in either is a refusal.

The report must admit THESE bytes: both its ``manifest_sha256`` and its own
``manifest_sha256_recomputed`` must equal the self-hash WE derived from the manifest on disk. So
a report about some other manifest, and a manifest edited after it was judged, are one refusal.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import canon
from . import v2_contract as C
from .report import Report
from .v2_store import (  # noqa: F401  (one front door: the store half of the admission)
    derive_typed_universe,
    open_store,
    typed_universe_sha256,
)


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def stage2_content_sha256(obj: Any) -> str:
    """Stage-2's content hash: keys SORTED, array order PRESERVED, no NaN.

    Reimplemented from Stage-2's written spec rather than borrowed: this is the rule the number
    under test was computed under, and a verifier that borrows the producer's hasher cannot
    disagree with it. It is NOT Stage-3's ``canon.chash``, which refuses floats — hashing
    Stage-2's document under a Stage-3 rule would fail for the WRONG reason, and a wrong-reason
    failure teaches the next reader to add an exception.
    """
    return canon.sha256_hex(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                   allow_nan=False))


def manifest_self_hash(manifest: dict[str, Any]) -> str:
    return stage2_content_sha256(canon.without(manifest, C.SELF_HASH_EXCLUDED))


def _load_json(rep: Report, path: str, what: str, gate: str) -> Optional[tuple[Any, str]]:
    """Read a JSON artifact and hash the BYTES ON DISK. A missing file is a NAMED refusal."""
    if not path or not os.path.isfile(path):
        _gate(rep, gate,
              f"the {what} is on disk and is opened for admission (there is no fixture "
              "fallback: a Stage-3 run without its admitted input does not quietly become "
              "one with a synthetic input)",
              False, f"not found: {path!r}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        _gate(rep, gate, f"the {what} parses as JSON", False, f"{type(exc).__name__}: {exc}")
        return None
    return doc, canon.file_sha256(path)


# --------------------------------------------------------------------------- #
# 1. STAGE-2's OWN ADMISSION. Every clause is a separate, named gate.
# --------------------------------------------------------------------------- #
def _check_report(rep: Report, report: dict[str, Any], *, self_hash: str) -> tuple[str, str]:
    verifier_id = str(report.get("verifier_id") or "")
    _gate(rep, C.GATE_VERIFIER_NOT_PINNED,
          f"the aggregate report is signed by the EXACT pinned verifier "
          f"({C.STAGE2_AGGREGATE_VERIFIER_ID}). Its id contains no self-flattering substring, "
          "and never did: a gate keyed on the word 'independent' would refuse the genuine report "
          "and admit any forgery that named itself so",
          verifier_id == C.STAGE2_AGGREGATE_VERIFIER_ID, f"signed {verifier_id!r}")
    _gate(rep, C.GATE_GENERATOR_IS_VERIFIER,
          "the report ASSERTS generator_is_not_verifier=true (independence is a structured "
          "field, not a name — a producer agreeing with itself is the one thing an independent "
          "verifier exists to rule out, and a missing assertion is a refusal, never a default)",
          report.get("generator_is_not_verifier") is True,
          f"got {report.get('generator_is_not_verifier')!r}")

    verdict = report.get("verdict")
    _gate(rep, C.GATE_VERDICT_NOT_ADMIT,
          f"the aggregate verifier's verdict is EXACTLY {C.ADMIT!r} — asserted as a value, not "
          "merely present as a key",
          verdict == C.ADMIT, f"got {verdict!r}")
    _gate(rep, C.GATE_GATES_FAILED,
          "the aggregate verifier recorded ZERO failed gates (a release with a failed gate is "
          "not admitted, whatever its verdict string says)",
          report.get("n_failed") == 0,
          f"n_failed={report.get('n_failed')!r} {report.get('failed_gates')}")
    _gate(rep, C.GATE_TOPOLOGY_NOT_COMPLETE,
          "the aggregate verifier found the topology COMPLETE (a partial run is never "
          "release-admissible)",
          report.get("topology_complete") is True,
          f"got {report.get('topology_complete')!r}")
    _gate(rep, C.GATE_NOT_RELEASE_ADMISSIBLE,
          "the aggregate verifier found the release ADMISSIBLE",
          report.get("release_admissible") is True,
          f"got {report.get('release_admissible')!r}")
    status = (report.get("admission") or {}).get("status")
    _gate(rep, C.GATE_ADMISSION_NOT_GRANTED,
          f"admission.status is exactly {C.ADMITTED!r} — admission is GRANTED by the separate "
          "aggregate report, or not at all",
          status == C.ADMITTED, f"got {status!r}")

    claimed = report.get(C.SELF_HASH_FIELD)
    recomputed = report.get("manifest_sha256_recomputed")
    _gate(rep, C.GATE_REPORT_BINDS_NOTHING,
          "the report BINDS the manifest it admits — it names the bytes, and it says it "
          "recomputed them (an ADMIT that names no bytes is an opinion about some other "
          "artifact, and a friendly verifier name with no bound manifest admits nothing)",
          bool(claimed) and bool(recomputed),
          f"manifest_sha256={str(claimed)[:16]!r} recomputed={str(recomputed)[:16]!r}")
    _gate(rep, C.GATE_REPORT_BINDS_ANOTHER_MANIFEST,
          "the report admits THIS manifest: both its claim and its OWN recomputation equal the "
          "semantic self-hash this verifier derived from the manifest bytes on disk. So a report "
          "about some other manifest, and a manifest edited after it was judged, are the same "
          "refusal",
          claimed == self_hash and recomputed == self_hash,
          f"report admits {str(claimed)[:16]}… (recomputed {str(recomputed)[:16]}…); on disk "
          f"{self_hash[:16]}…")
    return verifier_id, (str(verdict) if verdict is not None else "")


def _release_topology(rep: Report, manifest: dict[str, Any]) -> Optional[list[str]]:
    """(programs) from the manifest's BOUND release. DERIVED, never a Stage-3 constant."""
    bound = manifest.get("stage1_v3_release") or {}
    programs = sorted(bound.get("programs") or [])
    conditions = list(bound.get("conditions") or [])
    sources = list(bound.get("gene_set_sources") or [])
    ok = _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
               "the manifest's BOUND Stage-1 release names its programs, conditions and "
               "gene-set sources (the topology is DERIVED from the release; a release that "
               "declares none cannot say what a complete run is)",
               bool(programs) and bool(conditions) and bool(sources),
               f"{len(programs)} programs, {conditions}, {sources}")
    ok = _gate(rep, C.GATE_STAGE1_RELEASE_UNBOUND,
               f"the bound release is the one Stage 3 is pinned to — {C.N_PROGRAMS} programs x "
               f"{list(C.CONDITIONS)} x {list(C.PATHWAY_SOURCES)}. A different release is a "
               "different aggregate, and its arms are not these arms",
               sorted(conditions) == sorted(C.CONDITIONS)
               and sorted(sources) == sorted(C.PATHWAY_SOURCES)
               and len(programs) == C.N_PROGRAMS,
               f"{len(programs)} x {conditions} x {sources}") and ok
    return programs if ok else None


def _check_stage1(rep: Report, manifest: dict[str, Any], stage1_release: str) -> Optional[str]:
    bound = manifest.get("stage1_v3_release") or {}
    pinned = bound.get("release_canonical_sha256")
    loaded = _load_json(rep, stage1_release, "pinned Stage-1 v3 release",
                        C.GATE_ARTIFACT_NOT_ON_DISK)
    if loaded is None:
        return None
    release, raw = loaded
    on_disk = stage2_content_sha256(release)
    declared_raw = bound.get("release_raw_sha256")
    ok = _gate(rep, C.GATE_STAGE1_RELEASE_UNBOUND,
               "the Stage-1 release ON DISK is the release the aggregate pins, by canonical AND "
               "raw hash (an aggregate that cannot name the release it stands on cannot be "
               "replayed against it, and a re-serialised file is not the file that was judged)",
               bool(pinned) and on_disk == pinned
               and (not declared_raw or declared_raw == raw),
               f"pinned={str(pinned)[:16]}… on_disk={on_disk[:16]}…")
    return on_disk if ok else None


# --------------------------------------------------------------------------- #
# 2. The 15 bundle DIRECTORIES, and every byte the manifest bound.
# --------------------------------------------------------------------------- #
def _resolve_dir(rep: Report, name: Any, root: str, what: str) -> Optional[str]:
    """Resolve an out_dir NAME to exactly ONE directory inside the root, or refuse.

    A bare name is required (so an absolute path and ``..`` never resolve), and AMBIGUITY is
    refused: two directories of one name under a root are two bundles claiming one identity, and
    taking the first match would let the loser's bytes go unread.
    """
    bad = (not isinstance(name, str) or not name or os.path.isabs(str(name))
           or "/" in str(name) or "\\" in str(name) or name in (".", ".."))
    if bad:
        _gate(rep, C.GATE_PATH_TRAVERSAL,
              f"{what} names a bare bundle directory inside the explicit bundles root (an "
              "absolute or traversing path reads bytes from outside it)",
              False, f"out_dir={name!r}")
        return None
    real_root = os.path.realpath(root)
    hits = [os.path.join(base, d)
            for base, dirs, _f in os.walk(real_root) for d in dirs if d == name]
    if len(hits) != 1:
        _gate(rep, C.GATE_DUPLICATE_BUNDLE if hits else C.GATE_ARTIFACT_NOT_ON_DISK,
              f"{what} resolves to EXACTLY ONE bundle directory under the bundles root (two "
              "directories of one name are two bundles claiming one identity, and one of them "
              "would never be read)",
              False, f"{len(hits)} match(es) for {name!r}")
        return None
    full = os.path.realpath(hits[0])
    if os.path.commonpath([real_root, full]) != real_root:
        _gate(rep, C.GATE_PATH_TRAVERSAL,
              f"{what} resolves INSIDE the bundles root (a symlink counts — realpath is what "
              "actually gets opened)",
              False, f"resolved={full!r}")
        return None
    return full


def _bundle_key(lane: Any, ctx: dict[str, Any]) -> str:
    """Stage-3's slot label, derived from the bundle's OWN native context."""
    if lane == C.LANE_DIRECT:
        return f"{C.LANE_DIRECT}|{ctx.get('condition')}"
    if lane == C.LANE_TEMPORAL:
        return f"{C.LANE_TEMPORAL}|{ctx.get('from_condition')}|{ctx.get('to_condition')}"
    return (f"{C.LANE_PATHWAY}|{ctx.get('condition')}|"
            f"{ctx.get(C.NATIVE_PATHWAY_SOURCE_KEY)}")


def _bundles(rep: Report, manifest: dict[str, Any],
             bundles_root: str) -> Optional[list[tuple[dict[str, Any], str]]]:
    entries = manifest.get("bundles")
    if not isinstance(entries, list) or not entries:
        _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
              f"the manifest ships a `bundles` array (the release is exactly {C.N_BUNDLES} "
              "all-arm bundle DIRECTORIES; a partial release is never admissible — and an "
              "`inventory` array is not this contract: Stage 2 has never emitted one)",
              False, f"bundles={type(entries).__name__}")
        return None

    expected = C.expected_bundle_keys()
    seen: dict[str, dict[str, Any]] = {}
    out: list[tuple[dict[str, Any], str]] = []
    unknown, duplicate, moved = [], [], []
    for entry in entries:
        lane, ctx = entry.get("lane"), entry.get("context") or {}
        key = _bundle_key(lane, ctx)
        if lane not in C.LANES or key not in expected or expected.get(key) != lane:
            unknown.append(f"{key!r} (lane={lane!r})")
            continue
        if key in seen:
            duplicate.append(key)
            continue
        full = _resolve_dir(rep, entry.get("out_dir"), bundles_root, f"bundle {key!r}")
        if full is None:
            return None

        files = entry.get("files")
        if not isinstance(files, dict) or C.ARM_BUNDLE_FILE not in files:
            moved.append(f"{key}: binds no {C.ARM_BUNDLE_FILE}")
            continue
        # EVERY bound byte, re-hashed from disk. Not a sample: the file a forger edits is the one
        # nobody re-read.
        for rel, sha in sorted(files.items()):
            path = os.path.realpath(os.path.join(full, str(rel)))
            if os.path.commonpath([full, path]) != full:
                moved.append(f"{key}: {rel!r} escapes its bundle")
            elif not os.path.isfile(path):
                moved.append(f"{key}: {rel!r} is not on disk")
            elif canon.file_sha256(path) != sha:
                moved.append(f"{key}: {rel!r} hashes to "
                             f"{canon.file_sha256(path)[:12]}… vs bound {str(sha)[:12]}…")
        if stage2_content_sha256(files) != entry.get("artifact_sha256"):
            moved.append(f"{key}: the verified file map does not hash to its artifact_sha256")

        entry = dict(entry, bundle_key=key,
                     raw_sha256=str(files.get(C.ARM_BUNDLE_FILE)),
                     canonical_sha256=stage2_content_sha256(files),
                     condition=ctx.get("condition"),
                     from_condition=ctx.get("from_condition"),
                     to_condition=ctx.get("to_condition"),
                     pathway_source=ctx.get(C.NATIVE_PATHWAY_SOURCE_KEY))
        seen[key] = entry
        out.append((entry, full))

    ok = _gate(rep, C.GATE_UNKNOWN_LANE,
               f"every bundle is one of the {C.N_BUNDLES} DERIVED from {list(C.CONDITIONS)} x "
               f"{list(C.PATHWAY_SOURCES)} and agrees with its own context (a mislabelled bundle "
               "fills the wrong slot)",
               not unknown, "; ".join(unknown[:3]))
    ok = _gate(rep, C.GATE_DUPLICATE_BUNDLE,
               "no bundle key appears twice (a duplicate silently fills a missing slot, and the "
               "count still looks right)",
               not duplicate, str(duplicate[:3])) and ok
    ok = _gate(rep, C.GATE_BUNDLE_BYTES_MOVED,
               "EVERY byte the manifest bound is still on disk and still hashes to what it "
               "bound, and each bundle's file map hashes to its own artifact_sha256 (the file a "
               "forger edits is the one nobody re-reads)",
               not moved, "; ".join(moved[:3])) and ok

    missing = sorted(set(expected) - set(seen))
    ok = _gate(rep, C.GATE_MISSING_BUNDLE,
               f"the manifest resolves all {C.N_BUNDLES} bundles — 3 Direct, 6 ORDERED temporal "
               "pairs, 6 pathway condition x source (a missing bundle is indistinguishable from "
               "one computed and found empty)",
               not missing and len(out) == C.N_BUNDLES,
               f"missing={missing[:4]} resolved={len(out)}") and ok
    return out if ok else None


def _arms_of(rep: Report, entry: dict[str, Any], full: str,
             provenance: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """The arms a bundle DIRECTORY actually ships, with each arm's ranking rows VERBATIM."""
    loaded = _load_json(rep, os.path.join(full, C.ARM_BUNDLE_FILE),
                        f"arm inventory of bundle {entry['bundle_key']!r}",
                        C.GATE_ARTIFACT_NOT_ON_DISK)
    if loaded is None:
        return None
    doc, _raw = loaded

    arms: list[dict[str, Any]] = []
    broken: list[str] = []
    for arm in (doc.get("arms") or ()):
        arm_key = str(arm.get("arm_key") or "")
        program_id, change = arm.get("program_id"), arm.get("desired_change")
        if not arm_key or not program_id or change not in C.DESIRED_CHANGES:
            broken.append(f"{arm.get('arm_key')!r}/{change!r}")
            continue
        binding = arm.get("ranking") or {}
        path = os.path.realpath(os.path.join(full, str(binding.get("path") or "")))
        if os.path.commonpath([full, path]) != full or not os.path.isfile(path):
            broken.append(f"{arm_key}: ranking is not inside the bundle")
            continue
        if canon.file_sha256(path) != binding.get("raw_sha256"):
            broken.append(f"{arm_key}: its ranking hashes to {canon.file_sha256(path)[:12]}… "
                          f"but the bundle bound {str(binding.get('raw_sha256'))[:12]}…")
            continue
        ranking = _load_json(rep, path, f"ranking of arm {arm_key!r}",
                             C.GATE_ARTIFACT_NOT_ON_DISK)
        if ranking is None:
            return None
        rows = (ranking[0] or {}).get("records")
        if not isinstance(rows, list):
            broken.append(f"{arm_key}: its ranking ships no `records` rows")
            continue
        arms.append({
            "arm_key": arm_key, "lane": entry["lane"], "bundle_key": entry["bundle_key"],
            "program_id": str(program_id), "desired_change": str(change),
            "condition": entry.get("condition"),
            "from_condition": entry.get("from_condition"),
            "to_condition": entry.get("to_condition"),
            "pathway_source": entry.get("pathway_source"),
            "ranking": dict(binding),
            "bundle_raw_sha256": entry["raw_sha256"],
            "bundle_canonical_sha256": entry["canonical_sha256"],
            "provenance": dict(provenance),
            # VERBATIM. Nothing is renamed and nothing is defaulted in: a field Stage 2 does not
            # emit is a field Stage 3 does not have.
            "records": [dict(r) for r in rows]})

    ok = _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
               f"every arm in bundle {entry['bundle_key']!r} names a key, a program and a known "
               "desired_change, and binds a ranking that is ON DISK and still hashes to what the "
               "bundle bound (an arm whose ranking nobody can read is an arm nobody can replay)",
               not broken, "; ".join(broken[:3]))

    declared = sorted(str(k) for k in (entry.get("arm_keys") or []))
    ok = _gate(rep, C.GATE_ARM_INDEX_DISAGREES,
               f"the manifest's arm index for bundle {entry['bundle_key']!r} IS the set of arms "
               "the bundle ships (an index that disagrees with the bytes describes a bundle that "
               "is not there)",
               declared == sorted(a["arm_key"] for a in arms),
               f"manifest indexes {len(declared)}, the bundle ships {len(arms)}") and ok
    return arms if ok else None


def _arm_topology(rep: Report, arms: list[dict[str, Any]], bundles: list[dict[str, Any]],
                  programs: list[str]) -> bool:
    got = sorted({a["program_id"] for a in arms})
    slots = {(a["bundle_key"], a["program_id"], a["desired_change"]) for a in arms}
    expected = {(b["bundle_key"], p, d)
                for b in bundles for p in programs for d in C.DESIRED_CHANGES}
    return _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
                 f"the release resolves the FULL {C.N_ARM_SLOTS}-slot arm topology — "
                 f"{C.N_PROGRAMS} programs x {len(C.DESIRED_CHANGES)} desired changes x "
                 f"{C.N_BUNDLES} contexts, each filled exactly once, with no duplicate standing "
                 "in for a missing slot (DERIVED from the loaded arms, never read from a "
                 "declared count)",
                 got == programs and len(slots) == len(arms)
                 and len(slots) == C.N_ARM_SLOTS and not (expected - slots),
                 f"programs={len(got)} slots={len(slots)} arms={len(arms)} "
                 f"missing={len(expected - slots)}")


def admit_aggregate(rep: Report, *, manifest_path: str, report_path: str,
                    bundles_root: str, stage1_release: str) -> Optional[dict[str, Any]]:
    """Re-express Stage-2's admission from the ACTUAL bytes. Never a Boolean, never a default."""
    before = len(rep.failures)
    if not _gate(rep, C.GATE_SELF_ADMISSION,
                 "the aggregate manifest and its verification report are SEPARATE artifacts (a "
                 "producer does not admit itself)",
                 os.path.realpath(str(manifest_path)) != os.path.realpath(str(report_path)),
                 "the report and the manifest are the same file"):
        return None

    loaded = _load_json(rep, manifest_path, "Stage-2 aggregate run manifest",
                        C.GATE_ARTIFACT_NOT_ON_DISK)
    reported = _load_json(rep, report_path, "Stage-2 aggregate verification report",
                          C.GATE_ARTIFACT_NOT_ON_DISK)
    if loaded is None or reported is None:
        return None
    manifest, manifest_raw = loaded
    report, report_raw = reported

    ok = _gate(rep, C.GATE_MANIFEST_NOT_NATIVE,
               f"the manifest IS the native Stage-2 run manifest ({C.STAGE2_MANIFEST_SCHEMA}); a "
               "document Stage 2 never emitted is not evidence Stage 2 produced, and a shape "
               "Stage 3 invented for itself is not a contract",
               isinstance(manifest, dict)
               and manifest.get("schema_version") == C.STAGE2_MANIFEST_SCHEMA,
               f"declares {(manifest or {}).get('schema_version')!r}")
    ok = _gate(rep, C.GATE_REPORT_NOT_NATIVE,
               f"the report IS the native Stage-2 verification artifact "
               f"({C.STAGE2_REPORT_SCHEMA})",
               isinstance(report, dict)
               and report.get("schema_version") == C.STAGE2_REPORT_SCHEMA,
               f"declares {(report or {}).get('schema_version')!r}") and ok
    if not ok:
        return None

    self_hash = manifest_self_hash(manifest)
    if not _gate(rep, C.GATE_MANIFEST_SELF_HASH,
                 "the aggregate manifest recomputes its OWN semantic identity from its own "
                 "content, excluding only the hash that cannot cover itself, the clock, and the "
                 "path it happens to sit at (a manifest that cannot prove who it is, is not a "
                 "root of trust — it is a document asserting a number)",
                 manifest.get(C.SELF_HASH_FIELD) == self_hash,
                 f"declares {str(manifest.get(C.SELF_HASH_FIELD))[:16]}…, its content hashes to "
                 f"{self_hash[:16]}…"):
        return None

    verifier_id, verdict = _check_report(rep, report, self_hash=self_hash)
    stage1_sha = _check_stage1(rep, manifest, stage1_release)
    programs = _release_topology(rep, manifest)
    if len(rep.failures) > before:      # THIS gate's own refusals, not the whole report's
        return None

    bound = _bundles(rep, manifest, bundles_root)
    if bound is None or programs is None or stage1_sha is None:
        return None

    provenance = {"manifest_raw_sha256": manifest_raw,
                  "manifest_canonical_sha256": stage2_content_sha256(manifest),
                  "manifest_self_hash": self_hash,
                  "aggregate_verifier_id": verifier_id,
                  "aggregate_verdict": verdict,
                  "report_raw_sha256": report_raw,
                  "stage1_release_sha256": stage1_sha}

    arms: list[dict[str, Any]] = []
    for entry, full in bound:
        got = _arms_of(rep, entry, full, provenance)
        if got is None:
            return None
        arms.extend(got)

    bundles = [e for e, _ in bound]
    if not _arm_topology(rep, arms, bundles, programs):
        return None

    return {"manifest": manifest, "report": report, "bundles": bundles, "arms": arms,
            "programs": programs, "provenance": provenance, **provenance}


# --------------------------------------------------------------------------- #
# 3. The typed universe and the admitted store.
#
# They live one module over (:mod:`verifier.v2_store`): the store is re-opened from disk, its
# typed universe is DERIVED from its own rows, its eligibility verdicts are REPLAYED from their
# own predicate inputs, and its source assertions are rebuilt from the rows they live in.
# Re-exported here so a caller binds ONE front door.
# --------------------------------------------------------------------------- #
