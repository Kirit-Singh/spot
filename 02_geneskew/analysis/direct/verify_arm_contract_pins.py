"""THE VERSION-LOCKED PINS for the Direct admission contract — one place to refresh.

These are what W10 is pinned to at a given verifier commit: its ids, its spec, its CODE
hash, the solver lock, and the security-critical gates its inventory must contain. They are
separated from the adapter logic on purpose — when W10's verifier changes, THIS file (and
P2S's mirror) is what refreshes, and nothing else.

RE-DERIVED, not copied: `W10_VERIFIER_CODE_SHA256` is W10's own `verifier_code_sha256()` over
its 8 modules at verifier head 3119900 (adapter commit e4cf8b9). A test re-derives it and
fails if it drifts.
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
# RE-DERIVED from W10's own recipe at commit e4cf8b9 (verifier head 3119900); it matched.
# This is a version-locked pin: when W10's verifier changes, refresh it (and P2S's).
W10_VERIFIER_CODE_SHA256 = \
    "3bc55ba51f6a8a619e9a8f47e4fd8d6318811c92048948159e8d03a93210a834"

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
    ),
    W10_VERIFIER_ID_RELEASE: (
        "every bundle cites the SAME scorer view as the release",
        "the Direct release document is SELF-HASHED and re-derives",
        "the PRODUCER did not admit its own release",
        "INDEPENDENTLY ADMITTED in full",
        "every bundle in the release binds the SAME solver lock",
        "every bundle in the release was built by the SAME code",
    ),
}
