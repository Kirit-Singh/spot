"""Aggregate admission for the temporal release. TWO artifacts, from TWO lanes, or nothing.

Frozen by independent report ``a12f7eee``. Stage 3 admits the temporal release only when
BOTH of these are present and agree:

  1. **W5's producer release** — ``temporal_arm_release.json``, content-addressed, carrying
     ``external_verification.status = pending`` and the **exact six-bundle inventory**.
  2. **W11's independent envelope** — a *separate* ``temporal_verification.json`` with an
     **ADMIT** verdict that binds **that exact producer release's raw AND canonical hash**.

THE PRODUCER'S OWN WORD IS NOT ADMISSION — AND IT SAYS SO ITSELF
---------------------------------------------------------------
W5's release declares ``status = pending``. That is the producer honestly stating that it is
*waiting to be verified*. Reading it as "verified" would be the purest possible form of the
bug this lane keeps meeting: **a component admitting itself**. It has now happened three
times — B6 (a manifest that never recomputed its own identity), M4b (a verifier that was a
stale copy of the generator's rule), and the temporal bundle's original ``verification_ref``
pointing at the producer's own module.

So W5's preflight, self-check, internal verification report, or any field it signs about its
own correctness is **never** admission, no matter how green it is. Only W11's envelope
admits, and it must bind the bytes — an ADMIT that names no hash is an opinion about some
other artifact.

WHY BOTH HASHES
---------------
The envelope binds **raw** (the bytes on disk) and **canonical** (the parsed content). Raw
alone would miss a re-serialisation that changes meaning; canonical alone would let the
shipped file differ from what was judged. Requiring both means the thing W11 read is the
thing Stage 3 loads.

TOPOLOGY IS DERIVED, NEVER DECLARED
-----------------------------------
``topology_complete`` is not a boolean anyone gets to assert. It is re-derived here from the
inventory — six bundles, one per ordered pair, 120 logical arms — because a producer that
can declare its own completeness can declare a partial release complete, and a missing
bundle would then be indistinguishable from a bundle that was computed and found empty.
"""
from __future__ import annotations

from typing import Any, Optional

RELEASE_FILENAME = "temporal_arm_release.json"
ENVELOPE_FILENAME = "temporal_verification.json"

# The six ordered pairs. Derived from the conditions, never copied from the release.
N_CONDITIONS = 3
N_BUNDLES = 6                       # ordered pairs: 3 x 2
N_PROGRAMS = 10
N_DESIRED_CHANGES = 2
N_LOGICAL_ARMS = N_PROGRAMS * N_DESIRED_CHANGES * N_BUNDLES      # 120

PENDING = "pending"
ADMIT = "admit"

# `stage2_inputs` is a FIXED KEYED OBJECT — not a generic role list. A positional or
# role-keyed list lets two inputs swap places silently; a fixed key cannot.
STAGE2_INPUT_KEYS = ("de_stats", "pseudobulk", "sgrna", "by_guide", "by_donor")

# Anything the PRODUCER says about its own correctness. None of it is admission.
PRODUCER_SELF_CLAIMS = frozenset({
    "preflight", "preflight_passed", "self_check", "self_verification",
    "self_verified", "internal_verification", "producer_verdict", "producer_admit",
    "verified_by_producer", "own_verification",
})


class AggregateAdmissionError(ValueError):
    """The temporal release is not admissible."""


class SelfAdmissionRefused(AggregateAdmissionError):
    """A producer tried to admit itself. It does not get to."""


# --------------------------------------------------------------------------- #
# 1. The producer release. It is EVIDENCE, never a verdict.
# --------------------------------------------------------------------------- #
def check_producer_release(release: dict[str, Any]) -> dict[str, Any]:
    """W5's release: content-addressed, pending, exactly six bundles. Not admission."""
    self_claims = sorted(k for k in release if k in PRODUCER_SELF_CLAIMS)
    if self_claims:
        raise SelfAdmissionRefused(
            f"the producer release carries self-verification claims {self_claims}. A "
            "producer's preflight or self-check is not admission — it is the producer "
            "agreeing with itself, which is the one thing an independent verifier exists "
            "to rule out.")

    ext = release.get("external_verification")
    if not isinstance(ext, dict):
        raise AggregateAdmissionError(
            "the producer release must carry an external_verification block declaring it "
            "is waiting to be verified")
    if ext.get("status") != PENDING:
        raise AggregateAdmissionError(
            f"the producer release declares external_verification.status="
            f"{ext.get('status')!r}; Stage 3 expects {PENDING!r}. The producer does not "
            "get to move itself past pending — only W11's envelope can.")

    raw = release.get("raw_sha256")
    canonical = release.get("canonical_sha256")
    if not raw or not canonical:
        raise AggregateAdmissionError(
            "the producer release must be CONTENT-ADDRESSED (raw_sha256 + "
            "canonical_sha256); a release nobody can address is a release nobody can "
            "admit")

    bundles = release.get("bundles")
    if not isinstance(bundles, list):
        raise AggregateAdmissionError("the producer release must ship a bundle inventory")
    if len(bundles) != N_BUNDLES:
        raise AggregateAdmissionError(
            f"the inventory has {len(bundles)} bundles; the temporal release is exactly "
            f"{N_BUNDLES} (one per ordered condition pair). A short inventory is a "
            "partial release, and a partial release is never admissible.")

    keys = [b.get("bundle_key") for b in bundles]
    if len(set(keys)) != N_BUNDLES or not all(keys):
        raise AggregateAdmissionError(
            f"the six bundles must be six DISTINCT ordered pairs; got {keys}. A duplicate "
            "silently fills a missing slot.")
    for b in bundles:
        if not (b.get("raw_sha256") and b.get("canonical_sha256")):
            raise AggregateAdmissionError(
                f"bundle {b.get('bundle_key')!r} is not content-addressed")

    return {"raw_sha256": raw, "canonical_sha256": canonical,
            "bundle_keys": sorted(keys), "n_bundles": len(bundles)}


def check_stage2_inputs(release: dict[str, Any]) -> dict[str, Any]:
    """`stage2_inputs` is a FIXED KEYED OBJECT. Not a list, and not role-keyed.

    A list lets two inputs swap places and still validate. A fixed key cannot: `de_stats`
    is `de_stats` or it is missing, and either way you know which.
    """
    inputs = release.get("stage2_inputs")
    if not isinstance(inputs, dict):
        raise AggregateAdmissionError(
            f"stage2_inputs must be a fixed KEYED OBJECT, got "
            f"{type(inputs).__name__}. A generic role list lets two inputs swap places "
            "silently and still validate.")

    missing = [k for k in STAGE2_INPUT_KEYS if k not in inputs]
    if missing:
        raise AggregateAdmissionError(f"stage2_inputs is missing {missing}")
    extra = [k for k in inputs if k not in STAGE2_INPUT_KEYS]
    if extra:
        raise AggregateAdmissionError(
            f"stage2_inputs carries unknown keys {extra}; the key set is fixed")

    for key in STAGE2_INPUT_KEYS:
        entry = inputs[key]
        if not isinstance(entry, dict) or not entry.get("sha256"):
            raise AggregateAdmissionError(
                f"stage2_inputs[{key!r}] must bind its bytes with a sha256")
    return {k: inputs[k]["sha256"] for k in STAGE2_INPUT_KEYS}


# --------------------------------------------------------------------------- #
# 2. W11's envelope. The ONLY thing that admits.
# --------------------------------------------------------------------------- #
def check_independent_envelope(envelope: dict[str, Any], *,
                               release_raw_sha256: str,
                               release_canonical_sha256: str) -> dict[str, Any]:
    """W11's ADMIT, and it must be about THESE EXACT BYTES."""
    verifier = envelope.get("verifier_id") or ""
    if "independent" not in verifier:
        raise SelfAdmissionRefused(
            f"the admission envelope names verifier {verifier!r}, which is not an "
            "INDEPENDENT verifier. Stage 3 has now met this defect three times (B6, M4b, "
            "and the temporal bundle's original verification_ref); it will not be a "
            "fourth.")

    verdict = envelope.get("verdict")
    if verdict != ADMIT:
        raise AggregateAdmissionError(
            f"the independent verifier's verdict is {verdict!r}, not {ADMIT!r}")

    bound = envelope.get("admits") or {}
    raw, canonical = bound.get("raw_sha256"), bound.get("canonical_sha256")
    if not raw or not canonical:
        raise AggregateAdmissionError(
            "the envelope must BIND the producer release it admits, by raw AND canonical "
            "hash. An ADMIT that names no bytes is an opinion about some other artifact.")

    if raw != release_raw_sha256 or canonical != release_canonical_sha256:
        raise AggregateAdmissionError(
            "the envelope admits a DIFFERENT release than the one shipped:\n"
            f"  envelope admits raw={raw[:16]}… canonical={canonical[:16]}…\n"
            f"  release ships    raw={release_raw_sha256[:16]}… "
            f"canonical={release_canonical_sha256[:16]}…\n"
            "Both hashes must match: raw alone would miss a re-serialisation that changes "
            "meaning; canonical alone would let the shipped file differ from what was "
            "judged.")

    return {"verifier_id": verifier, "verdict": verdict,
            "admits_raw_sha256": raw, "admits_canonical_sha256": canonical}


# --------------------------------------------------------------------------- #
# 3. Both, or nothing. Topology re-derived, never declared.
# --------------------------------------------------------------------------- #
def admit_release(*, producer_release: dict[str, Any],
                  independent_envelope: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The aggregate gate. BOTH artifacts, from BOTH lanes, agreeing on the same bytes."""
    addressed = check_producer_release(producer_release)
    inputs = check_stage2_inputs(producer_release)

    if independent_envelope is None:
        raise SelfAdmissionRefused(
            "the producer release is present and PENDING, and no independent envelope was "
            f"supplied. `{RELEASE_FILENAME}` alone never admits anything — it is the "
            "producer saying it is waiting to be checked. Stage 3 requires W11's "
            f"`{ENVELOPE_FILENAME}` ADMIT envelope bound to these exact bytes.")

    admitted = check_independent_envelope(
        independent_envelope,
        release_raw_sha256=addressed["raw_sha256"],
        release_canonical_sha256=addressed["canonical_sha256"])

    # topology_complete is DERIVED. Nobody declares it.
    declared = producer_release.get("topology_complete")
    if declared is not None:
        raise SelfAdmissionRefused(
            "the release DECLARES topology_complete. It does not get to: a producer that "
            "can assert its own completeness can assert a partial release complete, and a "
            "missing bundle then looks exactly like a bundle that was computed and found "
            "empty. Stage 3 re-derives it from the inventory.")

    n_arms = N_PROGRAMS * N_DESIRED_CHANGES * addressed["n_bundles"]
    topology_complete = (addressed["n_bundles"] == N_BUNDLES
                         and n_arms == N_LOGICAL_ARMS)

    return {
        "admission_status": "externally_admitted",
        "topology_complete": topology_complete,
        "n_bundles": addressed["n_bundles"],
        "n_logical_arms": n_arms,
        "bundle_keys": addressed["bundle_keys"],
        "producer_raw_sha256": addressed["raw_sha256"],
        "producer_canonical_sha256": addressed["canonical_sha256"],
        "stage2_inputs": inputs,
        **admitted,
    }
