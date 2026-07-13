"""BIND the admitted universe store. Never admit it.

Frozen v2 admission contract, rule 6: *the universe store is admitted by an INDEPENDENT
verifier and bound by its exact ``store_id``; the producer's own verdict is never the
admission.*

So this module does two things and refuses to do a third:

  * it PROVES the store on disk is intact — every artifact present, every hash re-derived from
    the actual bytes, through ``universe_verify.verify_from_disk``;
  * it BINDS that store by the exact ``store_id`` an independent verifier admitted;
  * it does NOT admit. There is no code path here that issues a verdict. A generator that
    admits its own inputs is the same process asserting twice.

THE PIN IS THE WHOLE MECHANISM
------------------------------
A store whose internal hashes all verify is SELF-CONSISTENT — and self-consistency is exactly
what a forged store also has. It proves the bytes were not corrupted in transit; it proves
nothing about whether anybody examined them. So the identity below is a literal, and a store
that is not that store is refused however clean it looks.

Re-admitting a new store is therefore a CODE CHANGE here, deliberately: a pin that can be
overridden at the command line pins whatever the caller wanted it to.

WHY THE PROVENANCE GATE IS SPELLED OUT
--------------------------------------
An earlier producer (``d6066b7``) shipped the provenance gate's REPORT rather than the gate.
``verify_from_disk`` still returned ``ok=True`` on a DELETED provenance file — fail-open — and
the store was refused for it, with byte-identical store contents. A deleted artifact refuses
BY NAME here, and a mutated one refuses at its hash even when the manifest is untouched.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import universe_verify as uv

BINDING_SCHEMA = "spot.stage03_admitted_universe_binding.v1"
MANIFEST_NAME = "universe_manifest.json"

# The exact identities an INDEPENDENT verifier admitted. Literals, not derivations.
#
# RE-PINNED at the namespace-vocabulary standardisation. The store was re-emitted under
# Stage-2's tokens (`ensembl_gene_id` / `gene_symbol`), so its identity necessarily moved —
# the typed universe hashes {target_id, target_id_namespace}. The SCIENCE did not move: the
# store's scientific content hash, taken with the namespace token projected out, is identical
# on both sides (95f81cb1…). See :mod:`druglink.universe_repin` for the proof.
ADMITTED_STORE_ID = \
    "625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff"
ADMITTED_PRODUCER_COMMIT = "d268a74f339d346609951e73810ab26e2e654d86"
ADMISSION_REPORT_SHA256 = \
    "4aba8b5882e5ea32707875fc5026ca6b0b5d811ad01412bfa4b121c29b283bfb"

# Every store this lane has REFUSED, kept by id so a stale binding cannot be reintroduced by
# accident. A bare compare against ADMITTED_STORE_ID would already refuse them — but silently,
# as "some other store", which tells the next reader nothing about WHY.
REFUSED_STORES = {
    "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160":
        "RETIRED NAMESPACE VOCABULARY: this store types its rows `ensembl_gene` / `symbol`, "
        "and Stage-2's W3 release serializes `ensembl_gene_id` / `gene_symbol`. Exact-token "
        "equality — the only honest typed join — refuses every one of its 11,522 Ensembl rows, "
        "so it yields ZERO edges. Its science is intact and is CARRIED FORWARD byte-for-byte "
        "in 625c921f…, which is the same store re-emitted under Stage-2's tokens. Admitting "
        "this one again would re-open the divergence the re-pin closed.",
    "446c3b78937593e89d13afe941eb3a6dbe6d37e3beac17f7edd5dd0abdde914d":
        "pre-repair (e298770): nested ambiguous assertions rankable; no provenance binding",
    "b20ec29bf3d829a23b1c13cd60cd37779fb78c69328d2531b376d0d4bf2f886e":
        "RETRACTED ADMISSION (0e349b1): passed Stage-3's own verifier while the PRODUCER's "
        "gate was fail-open on a deleted provenance file",
}

# Stated as a fact about this module, and asserted by its tests: there is no path here that
# admits anything.
PRODUCER_ADMITS_STORE = False

REFUSE_STORE_NOT_FOUND = "the_universe_store_is_not_on_disk"
REFUSE_STORE_DID_NOT_VERIFY = "the_universe_store_did_not_verify_from_its_own_bytes"
REFUSE_NOT_THE_ADMITTED_STORE = "this_is_not_the_store_an_independent_verifier_admitted"
REFUSE_REFUSED_STORE = "this_store_is_on_the_refused_list_and_names_its_reason"


class AdmittedUniverseError(ValueError):
    """The universe store could not be bound. Refuse; never fall back to a fixture."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def binding_block(*, store_id: str, verify: dict[str, Any]) -> dict[str, Any]:
    """What the Stage-3 bundle binds about the store it stood on."""
    return {
        "schema_version": BINDING_SCHEMA,
        "store_id": store_id,
        "admitted_store_id": ADMITTED_STORE_ID,
        "admitted_producer_commit": ADMITTED_PRODUCER_COMMIT,
        "admission_report_sha256": ADMISSION_REPORT_SHA256,
        "verify_policy_version": verify.get("verify_policy_version"),
        "verified_from_disk": bool(verify.get("ok")),
        # WHO admitted it, and who did not. The producer proved the bytes; it did not decide
        # they were acceptable, and it says so rather than leaving a reader to assume.
        "admitted_by": "independent_verifier",
        "producer_admits_store": PRODUCER_ADMITS_STORE,
    }


def bind(*, store_dir: str,
         universe_targets: list[dict[str, str]]) -> dict[str, Any]:
    """Prove the store on disk, then bind it by the exact admitted ``store_id``.

    ``universe_targets`` is the TYPED target universe this run stands on. The store was
    extracted FOR a particular universe and binds its hash; serving a run a store built against
    a different universe would answer questions about targets it never covered, so a mismatch
    refuses rather than silently returning thin coverage.
    """
    manifest_path = os.path.join(store_dir, MANIFEST_NAME)
    if not os.path.isdir(store_dir) or not os.path.exists(manifest_path):
        raise AdmittedUniverseError(
            REFUSE_STORE_NOT_FOUND,
            f"no {MANIFEST_NAME} under {os.path.basename(store_dir)!r}. There is no fixture "
            "fallback: a Stage-3 run without its admitted universe store does not quietly "
            "become a Stage-3 run with a synthetic one")
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    # THE REFUSED LIST, FIRST — so a store this lane has already rejected refuses BY NAME, with
    # its reason, rather than as an anonymous "some other store". Reading the manifest's own
    # declared id here is safe in the REFUSING direction only: it can add a refusal, never grant
    # an admission, and a store that lied about its id to dodge this list still has to survive
    # the exact-identity compare below.
    declared = str(manifest.get("store_id", ""))
    refused = REFUSED_STORES.get(declared)
    if refused:
        raise AdmittedUniverseError(
            REFUSE_REFUSED_STORE,
            f"{declared[:16]}… is on the REFUSED list: {refused}")

    # THE PRODUCER'S GATE, over the ACTUAL bytes on disk — not the in-memory objects that
    # produced them. A missing artifact is a named refusal; an altered one fails at its hash
    # even when the manifest is untouched.
    verify = uv.verify_from_disk(store_dir=store_dir, manifest=manifest,
                                 universe_targets=universe_targets)
    if not verify.get("ok"):
        raise AdmittedUniverseError(
            REFUSE_STORE_DID_NOT_VERIFY,
            f"the store did not verify from its own bytes: {verify.get('violations')}")

    store_id = str(manifest.get("store_id", ""))
    if store_id != ADMITTED_STORE_ID:
        raise AdmittedUniverseError(
            REFUSE_NOT_THE_ADMITTED_STORE,
            f"this store is {store_id[:16]}…, and the store an independent verifier admitted "
            f"is {ADMITTED_STORE_ID[:16]}…. Every hash inside it may verify — a forged store's "
            "hashes verify too. Internal consistency proves the bytes are intact; it proves "
            "nothing about whether anybody examined them")

    return binding_block(store_id=store_id, verify=verify)
