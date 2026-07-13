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

import os
from typing import Any, Optional

from . import v2_contract as C
from .report import Report
from .v2_bundles import (  # noqa: F401  (one front door: the bundle half of the admission)
    _arm_topology,
    _arms_of,
    _bundle_key,
    _bundles,
    _resolve_dir,
)
from .v2_reconstruct_util import (  # noqa: F401
    SELF_HASH_EXCLUDED,
    _gate,
    _load_json,
    manifest_self_hash,
    stage2_content_sha256,
)
from .v2_store import (  # noqa: F401  (one front door: the store half of the admission)
    derive_typed_universe,
    open_store,
    typed_universe_sha256,
)


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
