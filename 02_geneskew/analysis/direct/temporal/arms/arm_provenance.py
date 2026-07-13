"""``temporal_provenance.json`` — WHAT produced this temporal arm bundle, as a typed record.

The aggregate run-manifest reads a bundle's provenance for its ``run_binding`` — the code
identity, the Stage-1 selection/release it stood on, and the Stage-2 inputs it consumed —
and re-derives each against an independently pinned expectation. The producer's job here is
to BIND those facts onto the bundle it just wrote, by content hash, so the provenance and
the arm inventory cannot drift apart: the provenance names the exact ``arm_bundle.json``
bytes (raw + canonical), and the verification report in turn binds this provenance's bytes.

It restates the method, the program admission and the estimand — not as a second copy of
the bundle, but as the provenance record of the identity the bundle was built under. The
ranked values live once, in the bundle and its bound ranking files; they are not repeated
here.
"""
from __future__ import annotations

from typing import Any

from ...hashing import content_hash

SCHEMA_PROVENANCE = "spot.stage02_temporal_arm_provenance.v1"


def build_provenance(bundle: dict[str, Any], *, bundle_file: str,
                     bundle_raw_sha256: str) -> dict[str, Any]:
    """The typed provenance for one temporal bundle, binding it by content hash.

    ``bundle_file`` is the BUNDLE-RELATIVE name of the arm inventory (never an absolute
    path); ``bundle_raw_sha256`` is the sha256 of its bytes on disk, which the verification
    report re-binds. ``run_binding`` carries the identities the aggregate re-derives against
    its pins; where the producer holds only method-level hashes, those are what it binds —
    it never fabricates a commit or a release it did not read.
    """
    method = dict(bundle["method"])
    admission = dict(bundle["program_admission"])
    return {
        "schema_version": SCHEMA_PROVENANCE,
        "bundle_id": bundle["bundle_id"],
        "bundle_key": bundle["bundle_key"],
        "lane": bundle["lane"],
        "context": dict(bundle["context"]),
        # BIND THE EXACT BUNDLE BYTES. A provenance that named a bundle only by key could be
        # paired with a different inventory of the same ordered pair.
        "bundle_file": bundle_file,
        "bundle_raw_sha256": bundle_raw_sha256,
        "bundle_canonical_sha256": content_hash(bundle),
        "n_programs": bundle["n_programs"],
        "n_arms": bundle["n_arms"],
        "n_targets": bundle["n_targets"],
        "n_base_records": bundle["n_base_records"],
        "method": method,
        "program_admission": admission,
        "estimand": dict(bundle["estimand"]),
        # WHAT the run stood on. The aggregate re-derives each against a pin; the producer
        # binds what it actually read, and leaves externally-pinned identities to the run.
        "run_binding": {
            # WHICH BUILD produced the bytes — the shared code-digest tuple the aggregate
            # reads from here and re-derives against a pinned checkout. The producer records
            # its tree state; it does not declare itself clean.
            "code_identity": dict(bundle["code_identity"]),
            # WHAT THE CODE DID — the estimator/method/config digests, kept EXPLICIT beside
            # code_identity: a method hash is not a build, and a build is not a method.
            # A FIXED EXACT-KEY OBJECT: each is its own named field. There is NO generic
            # ``role`` key and no list mini-language — a role vocabulary a reader has to
            # interpret is a role vocabulary that drifts; the field name IS the role.
            "estimator_id": method.get("estimator_id"),
            "estimator_version": method.get("estimator_version"),
            "temporal_method_sha256": method.get("temporal_method_sha256"),
            # A FIXED EXACT-KEY OBJECT whose keys name the inputs directly — no generic
            # ``role`` label/value mini-language (sealed cross-check §B).
            "stage2_inputs": {
                "direct_method_version": method.get("direct_method_version"),
                "direct_config_sha256": method.get("direct_config_sha256"),
                "effect_source_sha256": method.get("effect_source_sha256"),
            },
            # the STAGE-1 v3 release binding the bundle carries — the SAME object, so
            # provenance and the arm inventory cannot name different Stage-1 identities.
            "selection_release": dict(bundle["stage1_binding"]),
        },
    }
