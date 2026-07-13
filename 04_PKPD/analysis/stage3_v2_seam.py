"""The Stage-3 v2 admission seam — deliberately UNPINNED, and therefore deliberately CLOSED.

W16 is still writing `spot.stage03_drug_annotation.v2`. Stage 4 does not know its fields, and this
module exists to make sure Stage 4 never PRETENDS to.

The failure this prevents is specific and quiet. Stage 4's v1 reader (`stage3_contract_v2.py`,
pinned to `spot.stage03_drug_annotation.v1/2026-07-12-r8`) checks the schema id, then reads the
tables it knows. Hand it a v2 bundle and one of two things happens, both bad:

  * it refuses with a confusing low-level error about a missing column, which reads like a broken
    bundle rather than an unimplemented contract; or worse
  * a v2 bundle that happens to carry the v1 column names is READ AS V1 — its new fields silently
    ignored, its new origin vocabulary silently dropped, its evidence admitted under a contract
    nobody checked it against. Every downstream hash would be self-consistent, and every one would
    be a hash of a misreading.

The second is the reason this file is not just documentation. A contract Stage 4 cannot verify is
not a contract Stage 4 may admit, and "it parsed" is not "it was verified".

WHAT UNBLOCKS IT — exactly two things, from W16:

  1. the final **schema-set sha256** for the v2 contract, and
  2. a real `spot.stage03_drug_annotation.v2` bundle that Stage 3's OWN independent verifier has
     admitted (gate 2), not merely emitted.

Then `STAGE3_V2_SCHEMA_SET_SHA256` below is set in ONE deliberate edit, the v2 adapter is written
against the fields W16 actually published, and the literal chain — acquire -> materialize ->
verify_bundle -> run_stage4 -> verify_stage4 — is run against the real v2 output. Until all of
that, a v2 bundle is refused BY NAME.

**A fixture-only v1 green is not completion.** The chain runs today on the frozen v1 annotation
fixture. That proves the plumbing, not the science.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .firewall import Rejection

STAGE3_V2_SCHEMA = "spot.stage03_drug_annotation.v2"

# ─── THE PIN ────────────────────────────────────────────────────────────────────────────────
#
# None means UNPINNED, which means CLOSED. This is the single line that changes when W16 reports
# the final hash — deliberately one line, so re-pinning is an act, not an accident.
#
# It is NOT a guess and must never be filled in with a locally computed hash: the whole point of a
# pin is that it was published by the producer and independently verified. A hash Stage 4 computed
# for itself pins nothing.
STAGE3_V2_SCHEMA_SET_SHA256: Optional[str] = None

# The v2 bundle's OWN independent verifier (gate 2), as a module entry point W16 publishes.
#
# `stage3_admission` runs `python -m verifier.verify_stage3` — which is the **v1** verifier. Point
# it at a v2 bundle and it judges the v2 contract by v1's rules, or judges nothing at all, and
# either way it exits and the bundle is recorded as externally verified. A gate that examined the
# wrong contract is not a weaker gate; it is a gate that reports PASS without having looked.
#
# So this stays None until W16 names its v2 verifier, and a v2 bundle is refused rather than handed
# to v1's.
STAGE3_V2_VERIFIER_ENTRY: Optional[str] = None

# What Stage 4 will CHECK once the pin lands. Published here so W16 can build against a stated
# interface instead of guessing what Stage 4 needs — the mirror image of Stage 4 not guessing what
# W16 is writing.
#
# These are requirements on the CONTRACT, not claims about its fields. Stage 4 does not know the
# v2 field names and has not invented any.
# ─── THE STAGE-2 UPSTREAM CONTRACT W16 MUST CONSUME ─────────────────────────────────────────
#
# Recorded here VERBATIM, as published — not paraphrased and not inferred. W16 currently expects an
# INVENTED Stage-2 aggregate envelope. A Stage-3 bundle standing on a synthetic Stage-2 shape
# carries synthetic numbers into Stage 4 under a real bundle's name, and every hash downstream
# would be a self-consistent hash of a fiction. That is the failure a green suite cannot see.
STAGE2_UPSTREAM_CONTRACT = {
    "manifest_schema": "spot.stage02_run_manifest.v3_topology_only",
    "manifest_carries": ("bundles[]", "stage1_v3_release"),
    "external_report_schema": "spot.stage02_run_manifest_verification.v1",
    "external_report_requires": {
        "verdict": "admit",
        # The producer may not be its own judge. This is the whole point of gate 2.
        "generator_is_not_verifier": True,
        "n_failed": 0,
        "manifest_hashes_equal": True,
        "topology": True,
        "release": True,
        "admission": True,
    },
    # Stated so nobody re-adds them from muscle memory: these are v1 concepts and the v2 upstream
    # contract does NOT have them.
    "absent_by_design": ("artifact_class", "admits block"),
}

# ─── WHAT STILL BLOCKS THE PIN ──────────────────────────────────────────────────────────────
#
# Three, all W16's to close. Named individually so "the seam is closed" never collapses into a
# vague "not ready yet" that nobody can act on.
# NOTE ON A MISLEADING NAME, so nobody mistakes it for the v2 admission contract:
# `analysis/stage3_contract_v2.py` is the "v2" of Stage 4's RESTATEMENT, not of Stage 3's contract.
# It pins `spot.stage03_drug_annotation.v1/2026-07-12-r8` and reads `drug_annotation.json` with the
# v1 candidate keys. Everything Stage 4 currently admits — including the selection-view binding — is
# V1 ONLY. A TRUE v2 admission contract is a SECOND seam: native `drug_annotation.v2.json` +
# `manifest.v2`, admitted through W16's own v2 external verifier and schema-set pins. Widening v1 to
# swallow v2 is not an upgrade; it is the misreading this module exists to prevent.
V2_PIN_BLOCKERS = (
    "the NATIVE v2 documents — `drug_annotation.v2.json` + `manifest.json` (the manifest keeps its "
    "v1 FILENAME and declares spot.stage03_manifest.v2 INSIDE) — admitted by a TRUE v2 contract "
    "module, `analysis/stage3_v2_contract.py`. `analysis/stage3_contract_v2.py` is misleadingly "
    "named: it pins spot.stage03_drug_annotation.v1 and restates the OLD candidate keys, and it "
    "will not be silently widened to accept v2.",
    "ONE canonical document filename. W16 currently emits `drug_annotation.v2.json` while its "
    "fixture uses an underscore variant. Stage 4 discovers by DECLARATION so it sees both — but "
    "the v2 ADAPTER must read a real file, and two names for one document is a contract with a "
    "hole in it.",
    "the PUBLISHED `method.schemas_sha256` — the identity of the SCHEMAS the bundle was written "
    "against. NOT a digest of the document+manifest INSTANCES: that is a hash of one bundle's "
    "contents, it changes with every bundle, and pinning it would pin a single emission while "
    "wearing the name of a contract pin. A hash Stage 4 computed for itself pins nothing.",
    "gate 2 wired: `verifier.verify_stage3_v2`, out-of-process, over ALL its inputs (bundle, "
    "stage2 aggregate manifest + report, the 15-bundle root, stage1 release, universe store, "
    "stage3 bridge, artifact_class). NOT `verifier.verify_stage3` — that is v1's, and judging a v2 "
    "bundle by v1's rules reports PASS without having looked. A verifier run without its upstream "
    "inputs confirms only that the bundle agrees with itself, which a forged bundle also does.",
    "W16's current fixture carries a stale `DISP_NON_RANKABLE_ASSERTION` constant. A fixture that "
    "disagrees with the contract it is meant to demonstrate will be believed over the contract.",
    "W16's current uncommitted selection_v3 identity is a 64-hex ALTERNATE PAYLOAD — stale and "
    "wrong. Stage 4 rejects any 64-hex/alternate question identity by name. Required: the 16-hex "
    "BIOLOGY-ONLY question_id over the endpoint conditions (Stage-1 539431d), independently "
    "re-derived and DISTINCT from selection_id.",
)

# What Stage 4 will CHECK of the Stage-3 v2 BUNDLE once the pin lands. Published so W16 can build
# against a stated interface instead of guessing what Stage 4 needs — the mirror image of Stage 4
# not guessing what W16 is writing.
#
# These are requirements on the CONTRACT, not claims about its fields. Stage 4 does not know the v2
# field names and has NOT invented any. `artifact_class` is deliberately absent from this list: it
# is a v1 concept, the v2 upstream contract does not carry it, and asserting it here would be
# exactly the guessing this module exists to prevent.
STAGE4_REQUIRES_OF_V2 = (
    "schema_version == spot.stage03_drug_annotation.v2, stated in the document",
    "ONE canonical document filename, and the manifest filename, both stated by W16",
    "a published schema-set sha256 that Stage 4 re-derives from the bundle's own bytes",
    "gate 2: the V2 external verifier entry point, named by W16. NOT verifier.verify_stage3 — "
    "that is v1's, and judging a v2 bundle by v1's rules reports PASS without having looked",
    "built on an ACTUAL Stage-2 run_release aggregate: manifest "
    "spot.stage02_run_manifest.v3_topology_only (bundles[] + stage1_v3_release) with an external "
    "spot.stage02_run_manifest_verification.v1 report carrying verdict=admit, "
    "generator_is_not_verifier=true, n_failed=0, hashes equal, topology/release/admission true — "
    "NOT an invented aggregate envelope",
    "the SELECTION-VIEW contract: which selection, which question, which analysis mode and "
    "condition, and the EXACT selected arm keys — plus per-candidate arm membership, so Stage 4 "
    "can carry only the candidates inside the selected view. Stage 4 binds these from v1's "
    "`upstream.direct_selection_id` / `direct_question_id` / `direct_lane` / "
    "`direct_analysis_condition` / `desired_arms`; the v2 names must be COORDINATED, not guessed. "
    "Without it a Stage-4 release is a global candidate display, not the answer to a question",
    "an immutable candidate identifier per candidate, stable across the whole chain",
    "per-source provenance: locator, license/terms, raw_sha256, and the source's own release",
    "an explicit typed ORIGIN per lever, so a MEASURED and an INFERRED origin are never fused",
    "explicit missingness: a lane Stage 3 did not evaluate says so, rather than arriving empty",
    "NO combined objective, NO p/q value, NO rank — Stage 4 refuses a bundle carrying one",
)


class Stage3V2NotAdmissible(Rejection):
    """A v2 bundle arrived before the v2 contract was pinned. Refused, never guessed at."""


def _declared_schemas(bundle_dir: str) -> dict[str, str]:
    """Every schema DECLARED by every JSON document in the bundle. -> {filename: schema}.

    Filename-agnostic, and that is the whole point. The first version of this scanned exactly two
    names — `drug_annotation.json` and `manifest.json` — because those are what v1 emits. W16 emits
    **`drug_annotation.v2.json`**, so a real v2 bundle was INVISIBLE to the seam and fell straight
    through to the v1 reader: the precise misreading this module exists to prevent.

    It passed its own test because the test built the v2 bundle using the v1 FILENAME. A seam that
    only recognises the adversary it imagined is not a seam. So: read what every document SAYS it
    is, and never infer a contract from where it happens to live.
    """
    out: dict[str, str] = {}
    if not os.path.isdir(bundle_dir):
        return out
    for name in sorted(os.listdir(bundle_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(bundle_dir, name), encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        declared = doc.get("schema_version") or doc.get("schema_id")
        if isinstance(declared, str) and declared:
            out[name] = declared
    return out


def is_v2_bundle(bundle_dir: str) -> bool:
    """Does ANY document in this bundle declare the v2 contract, whatever it is called?"""
    return any(schema.startswith(STAGE3_V2_SCHEMA)
               for schema in _declared_schemas(bundle_dir).values())


def v2_documents(bundle_dir: str) -> dict[str, str]:
    """The v2-declaring documents, by filename. Reported in the refusal so a reader can see
    exactly which document tripped the seam, and under what name."""
    return {name: schema for name, schema in _declared_schemas(bundle_dir).items()
            if schema.startswith(STAGE3_V2_SCHEMA)}


# A fixture is SYNTHETIC. It exercises the contract; it is never evidence about a drug — and it must
# never be acquired FOR, because a public request issued on behalf of a synthetic candidate spends a
# real rate limit on a molecule that does not exist, and returns bytes that would then sit in a
# manifest looking exactly like evidence.
FIXTURE_ARTIFACT_CLASS = "fixture"


def declared_artifact_class(bundle_dir: str) -> Optional[str]:
    """What the bundle says it IS. Read from the declaration, never inferred from a filename."""
    if not os.path.isdir(bundle_dir):
        return None
    for name in sorted(os.listdir(bundle_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(bundle_dir, name), encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(doc, dict) and doc.get("artifact_class"):
            return str(doc["artifact_class"])
    return None


def assert_not_a_fixture(bundle_dir: str) -> None:
    """REFUSE a fixture bundle BY NAME, before any request is planned or issued.

    It used to be refused only INCIDENTALLY — the v1 reader could not find `drug_annotation.json`
    and complained about a missing file. That reads as a broken bundle rather than a synthetic one,
    and an incidental refusal is a refusal that stops the day the incidental reason goes away.
    """
    declared = declared_artifact_class(bundle_dir)
    if declared != FIXTURE_ARTIFACT_CLASS:
        return
    raise Rejection(
        "stage3_bundle_is_a_fixture",
        f"this bundle declares artifact_class={declared!r}. A fixture is SYNTHETIC: it exercises "
        "the contract and is never evidence about a drug. Stage 4 will not acquire public evidence "
        "for it — a real request issued on behalf of a synthetic candidate spends a real rate limit "
        "on a molecule that does not exist, and the bytes it returns would sit in a manifest looking "
        "exactly like evidence. Refused BY NAME, before a single request is planned. Substitute an "
        "artifact_class=analysis bundle.",
    )


def assert_v2_admissible(bundle_dir: str, *, schema_set_sha256: Optional[str] = None) -> None:
    """The gate. While the contract is unpinned, a v2 bundle is REFUSED — by name, and loudly.

    This is called at every door BEFORE the v1 reader sees the bundle, so a v2 document can never
    be read under the v1 contract by accident. Being refused for the right reason is a
    prerequisite for being admitted for the right reason.
    """
    if not is_v2_bundle(bundle_dir):
        return

    found = v2_documents(bundle_dir)

    if STAGE3_V2_VERIFIER_ENTRY is None:
        raise Stage3V2NotAdmissible(
            "stage3_v2_external_verifier_not_declared",
            f"this bundle declares {STAGE3_V2_SCHEMA} (in {sorted(found)}), and Stage 4 has no v2 "
            "external verifier to admit it with. It is NOT read under the v1 contract, and it "
            "will NOT be handed to `verifier.verify_stage3`: "
            "that is the v1 verifier, and running it against a v2 bundle would judge the v2 "
            "contract by v1's rules — or judge nothing — and then record the bundle as externally "
            "verified. A gate that examined the wrong contract does not verify less; it reports "
            "PASS without having looked. W16 must publish the v2 verifier entry point. "
            f"Stage 4 requires: {'; '.join(STAGE4_REQUIRES_OF_V2)}",
        )

    if STAGE3_V2_SCHEMA_SET_SHA256 is None:
        raise Stage3V2NotAdmissible(
            "stage3_v2_contract_not_pinned",
            f"this bundle declares {STAGE3_V2_SCHEMA} (in {sorted(found)}), and Stage 4 has not "
            "pinned that contract. "
            "It is NOT read under the v1 contract: a v2 document parsed by a v1 reader would have "
            "its new fields silently ignored and its evidence admitted against a contract nobody "
            "checked it against, and every downstream hash would be a self-consistent hash of a "
            "misreading. W16 must publish the final schema-set sha256 and a bundle its own "
            "verifier has admitted; Stage 4 then re-pins deliberately "
            "(analysis/stage3_v2_seam.py :: STAGE3_V2_SCHEMA_SET_SHA256) and writes the v2 "
            f"adapter against the fields W16 actually published. Stage 4 requires: "
            f"{'; '.join(STAGE4_REQUIRES_OF_V2)}",
        )

    if schema_set_sha256 is None:
        raise Stage3V2NotAdmissible(
            "stage3_v2_schema_set_not_supplied",
            "the v2 contract is pinned, but this bundle supplies no schema-set sha256 to check "
            "the pin against. A pin nothing is compared to is decoration.",
        )

    if schema_set_sha256 != STAGE3_V2_SCHEMA_SET_SHA256:
        raise Stage3V2NotAdmissible(
            "stage3_v2_schema_set_mismatch",
            f"this bundle's schema set hashes to {schema_set_sha256[:16]}…, and Stage 4 is pinned "
            f"to {STAGE3_V2_SCHEMA_SET_SHA256[:16]}…. The contract Stage 4 verified is not the "
            "contract that produced this bundle. Re-pinning is a deliberate act after re-reading "
            "the handoff — never a silent widening to accept whatever arrived.",
        )


def seam_status() -> dict[str, Any]:
    """What an orchestrator (or W1/W16) can read to see exactly where the seam stands."""
    return {
        "stage3_v2_schema": STAGE3_V2_SCHEMA,
        "pinned": STAGE3_V2_SCHEMA_SET_SHA256 is not None,
        "schema_set_sha256": STAGE3_V2_SCHEMA_SET_SHA256,
        "state": ("CLOSED — awaiting W16's final schema-set hash and an externally admitted v2 "
                  "bundle" if STAGE3_V2_SCHEMA_SET_SHA256 is None else "PINNED"),
        "stage4_requires": list(STAGE4_REQUIRES_OF_V2),
        "pin_blockers": list(V2_PIN_BLOCKERS),
        "stage2_upstream_contract": STAGE2_UPSTREAM_CONTRACT,
        "v1_unaffected": "spot.stage03_drug_annotation.v1/2026-07-12-r8 remains admitted and frozen",
    }
