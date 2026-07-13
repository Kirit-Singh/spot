"""THE VERSION-LOCKED PINS for the Direct admission contract — one place to refresh.

These are what W10 is pinned to at a given verifier commit: its ids, its spec, its CODE
hash, the solver lock, and the security-critical gates its inventory must contain. They are
separated from the adapter logic on purpose — when W10's verifier changes, THIS file (and
P2S's mirror) is what refreshes, and nothing else.

RE-DERIVED, not copied: `W10_VERIFIER_CODE_SHA256` is W10's own `verifier_code_sha256()` over
its 9 modules at the PRODUCER-CODE-ROOT verifier head. A test re-derives it and fails if it
drifts.
"""
from __future__ import annotations

W10_VERIFIER_ID_BUNDLE = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_VERIFIER_ID_RELEASE = "spot.stage02.direct.release.verifier.v1"
W10_SPEC_SHA256 = "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f"
PINNED_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

# WHICH CODE ran. Pinned so a WEAKENED FORK — one that keeps the verifier_id string and the
# spec but ran different, gutted gates — is refused. A resealed report can set every other
# field to a pleasing value; it cannot make its own code hash to a number it does not know.
# RE-DERIVED from W10's own recipe (a test re-derives it); this is a version-locked pin, so
# when W10's verifier changes, refresh it (and P2S's).
#
# MOVED by the producer-code-root fix: gate_code_identity now re-derives the code manifest
# from the PRODUCER's supplied tree — proving its git HEAD is the bound commit and its working
# state is the declared one — instead of walking the VERIFIER's own checkout. Three verifier
# modules changed, so the code hash moved with them. Previous pin (pre-fix):
# 8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f
W10_VERIFIER_CODE_SHA256 = \
    "943d32bd5317bbc84d2705a39f98de024f10548d1995cd6bc42ed56fb9efc174"

# THE GATES THAT MUST HAVE RUN. Pinning the code sha says the report NAMES the right code;
# this says its gate inventory actually CONTAINS the security-critical checks — so an empty
# inventory, or a resealed deletion of (say) the mask gate, cannot pass. Substrings, so a
# gate's detail wording can evolve without silently dropping the requirement. Per subject.
REQUIRED_GATES = {
    W10_VERIFIER_ID_BUNDLE: (
        "matches the BYTES ON DISK",
        "the MASK's identity is bound into the run and RE-DERIVES from the shipped "
        "masks.parquet",
        "every SHIPPED mask is the one the verifier independently derives",
        "the supplied solver lock's BYTES hash to the hard-pinned Stage-2 lock",
        "the lock the bundle bound IS the hard-pinned Stage-2 lock",
        "the PRODUCER did not admit its own output",
        "the bundle's admitted set EQUALS the independently derived set",
        "every arm value is the EXACT sign transform",
        "every rank RE-DERIVES per arm",
        "every emitted base delta RE-DERIVES from the bound DE data",
        "the run id RE-DERIVES from its own binding",
        "the target_identity rows are EXACTLY this bundle's arm target set",
        "every observed_perturbation_modality is EXACTLY CRISPRi_knockdown",
        "the target_identity canonical hash is bound into the run identity",
        # THE PRODUCER'S CODE TREE. Before the fix these were a walk of the VERIFIER's own
        # checkout, so a report could carry a code identity nobody had checked against the
        # tree the run was taken from. They are security-critical: without them, the code
        # manifest in a report is a number the artifact chose for itself.
        "the PRODUCER's code root is SUPPLIED to the verifier",
        "the producer tree's git HEAD IS the commit the run bound",
        "the code manifest hash RE-DERIVES from the tree this run claims",
    ),
    W10_VERIFIER_ID_RELEASE: (
        "every bundle cites the SAME scorer view as the release",
        "the Direct release document is SELF-HASHED and re-derives",
        "the PRODUCER did not admit its own release",
        "INDEPENDENTLY ADMITTED in full",
        "every bundle in the release binds the SAME solver lock",
        "every bundle in the release was built by the SAME code",
        "the release target universe is a MIXED namespace union",
    ),
}


# --------------------------------------------------------------------------- #
# EXECUTION-COMPLETENESS PROFILES. Not a security feature — a provenance one: a PRODUCTION
# admission must have run EXACTLY the gate inventory that invocation is defined to run, in
# order. Pinning the ordered inventory hash + count means a report that quietly dropped ANY
# gate — even a currently "non-critical" one like the p/q-absence or column-allowlist check —
# no longer matches its profile and is refused. The counts and the ordered-hash are
# RE-DERIVED by a test that re-runs the verifier with the canonical flags, so a deliberate
# gate change in W10 fails loudly (refresh the profile) rather than silently refusing.
#
# The production BUNDLE invocation binds the Stage-1 v3 release, pins the H5AD object, supplies
# the PRODUCER's code root and recomputes every target (--stage1-v3-release --expect-h5ad-sha256
# --producer-code-root --recompute all): 93 gates. The RELEASE invocation is 28 and does not
# vary with the H5AD pin or the code root (it flows both to its per-bundle verifications).
# Fixture/synthetic reports are separately typed and LENIENT: they satisfy the critical-gate
# SUBSET (REQUIRED_GATES), because a fixture is a test input, not a production provenance
# record.
#
# The bundle profile MOVED (+3 gates, 90 -> 93) with the producer-code-root fix: the code
# root must now be supplied and be a separate git checkout, its HEAD must be the bound commit,
# and its working state must be the one the run declared. Previous pin (pre-fix): 90 gates,
# e6b5da89f1e4e7bf39380318769342cc585630c781c2226fa25b2df8aaf24d45.
PROFILE_BUNDLE_PRODUCTION = "spot.stage02.direct.bundle.production.v1"
PROFILE_RELEASE_PRODUCTION = "spot.stage02.direct.release.production.v1"
PROFILE_BUNDLE_FIXTURE = "spot.stage02.direct.bundle.fixture.v1"
PROFILE_RELEASE_FIXTURE = "spot.stage02.direct.release.fixture.v1"

GATE_PROFILES = {
    PROFILE_BUNDLE_PRODUCTION: {
        "gate_inventory_sha256":
            "91f15db7ceec71c51fd21fda77c24956dcc6a4de998ef32ca7395e13a13fac6e",
        "n_gates": 93,
        "match": "exact",
    },
    PROFILE_RELEASE_PRODUCTION: {
        "gate_inventory_sha256":
            "e66d7f9be7b4f8e38c45b2e7c4815459f7215441ee553ba6278469d9cd3a2437",
        "n_gates": 28,
        "match": "exact",
    },
    # Fixture profiles carry NO exact hash: they are lenient by design (subset match), so a
    # test can hand-build a report without reproducing 77 gate names verbatim.
    PROFILE_BUNDLE_FIXTURE: {"match": "subset"},
    PROFILE_RELEASE_FIXTURE: {"match": "subset"},
}
