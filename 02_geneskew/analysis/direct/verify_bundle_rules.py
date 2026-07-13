"""PER-ARTIFACT RULES for the aggregate verifier: reports, gene sets, code, provenance.

Split out of ``verify_manifest_rules`` for size. INDEPENDENCE RULE holds here too: nothing
is imported from the producer.
"""
from __future__ import annotations

from typing import Any, Optional

# ONE-WAY: the per-artifact rules build on the core. The core never imports back.
from verify_manifest_rules import ADMIT, PASS, _scan, content_sha256  # noqa: F401

# --------------------------------------------------------------------------- #
# WHAT A LANE VERIFICATION REPORT MUST BE (round-4 review, seam 2).
#
# ``report.get("verdict") == "admit"`` was the whole check. A two-byte file saying
# ``{"verdict": "admit"}`` passed it, provided the bundle bound its bytes — so the
# aggregate manifest was, in the end, admitting arms on the strength of a string.
#
# A report is now a TYPED artifact from a NAMED verifier, and it must BIND THE BUNDLE IT
# JUDGED: an ADMIT is meaningless unless it says what it was an admission OF. The expected
# verifier identity and the gate inventory come from a PINNED input, never from the report
# (a forger writes the report).
# --------------------------------------------------------------------------- #
REQUIRED_REPORT_FIELDS = ("verifier_id", "schema_version", "verdict", "n_failed",
                          "fail_closed", "generator_is_not_verifier", "bundle_id",
                          "binds")


def report_gate_names(report: Any) -> set:
    """The gates a report claims to have PASSED. Tolerates 'gate' and 'check' keys."""
    if not isinstance(report, dict):
        return set()
    out = set()
    for c in (report.get("checks") or []):
        if isinstance(c, dict) and c.get("status") == PASS:
            out.add(str(c.get("gate") or c.get("check")))
    return out


def check_report(report: Any, lane: str, bundle_id: str, expect: Any,
                 arm_raw: Optional[str], prov_raw: Optional[str]) -> list[str]:
    """Is this an ADMIT from the right verifier, ABOUT THIS BUNDLE, with its gates run?"""
    bad: list[str] = []
    if not isinstance(report, dict):
        return [f"{bundle_id}: the verification report is not a document"]

    missing = [f for f in REQUIRED_REPORT_FIELDS if f not in report]
    if missing:
        bad.append(f"{bundle_id}: the report omits {missing}; a bare verdict string is "
                   "not an independent admission")

    pin = (expect or {}).get(lane) or {}
    if pin.get("verifier_id") and report.get("verifier_id") != pin["verifier_id"]:
        bad.append(f"{bundle_id}: the report is signed {report.get('verifier_id')!r}; the "
                   f"pinned {lane} verifier is {pin['verifier_id']!r}")
    if pin.get("schema_version") and report.get("schema_version") != pin["schema_version"]:
        bad.append(f"{bundle_id}: report schema {report.get('schema_version')!r} is not "
                   f"the pinned {pin['schema_version']!r}")

    if report.get("verdict") != ADMIT:
        bad.append(f"{bundle_id}: verdict is {report.get('verdict')!r}, not {ADMIT!r}")
    if report.get("fail_closed") is not True:
        bad.append(f"{bundle_id}: the report does not declare itself fail-closed")
    if report.get("generator_is_not_verifier") is not True:
        bad.append(f"{bundle_id}: the report does not declare generator != verifier")
    if int(report.get("n_failed") or 0) != 0 or (report.get("failed_gates") or []):
        bad.append(f"{bundle_id}: ADMIT with {report.get('n_failed')} failed gate(s) "
                   f"{report.get('failed_gates')}")

    # THE GATE INVENTORY. An ADMIT that ran no gates is an ADMIT that checked nothing.
    required = set(pin.get("required_gates") or [])
    passed = report_gate_names(report)
    absent = sorted(required - passed)
    if absent:
        bad.append(f"{bundle_id}: the report does not record these pinned {lane} gates as "
                   f"passed: {absent[:4]}")

    # THE BINDING. A report that names no bundle can be copied onto any bundle.
    if report.get("bundle_id") != bundle_id:
        bad.append(f"{bundle_id}: the report judges bundle "
                   f"{report.get('bundle_id')!r} — it was written about something else")
    binds = report.get("binds") or {}
    if arm_raw and binds.get("arm_bundle_sha256") != arm_raw:
        bad.append(f"{bundle_id}: the report binds arm inventory "
                   f"{str(binds.get('arm_bundle_sha256'))[:16]}, but this bundle's is "
                   f"{arm_raw[:16]}")
    if prov_raw and binds.get("provenance_sha256") != prov_raw:
        bad.append(f"{bundle_id}: the report binds provenance "
                   f"{str(binds.get('provenance_sha256'))[:16]}, but this bundle's is "
                   f"{prov_raw[:16]}")
    return bad


def check_gene_sets(declared: Any, pinned: Any, source: str,
                    bundle_id: str) -> list[str]:
    """The gene-set identity, FIELD BY FIELD, against the pinned source identity.

    Checking only that the two sources DIFFER and agree within themselves was never
    identity: a bundle could declare a forged Reactome release, name it ``reactome``, and
    pass, because nothing ever compared it to the Reactome that was actually pinned.
    """
    bad: list[str] = []
    if not isinstance(declared, dict):
        return [f"{bundle_id}: the bundle declares no gene-set identity"]
    if declared.get("gene_set_source") != source:
        bad.append(f"{bundle_id}: declares source {declared.get('gene_set_source')!r} in "
                   f"the {source!r} slot")
    if not isinstance(pinned, dict):
        return bad + [f"{bundle_id}: {source!r} is not a pinned gene-set source"]

    for field, want in sorted(pinned.items()):
        if field == "fixture":
            continue
        got = declared.get(field)
        if got != want:
            bad.append(f"{bundle_id}/{source}: {field} is {str(got)[:24]!r}; the pinned "
                       f"identity is {str(want)[:24]!r}")
    return bad


# WHICH fields of a bundle's run_binding identify the CODE that produced it.
#
# W5's native bundle deliberately binds NO commit and NO clean_tree: its producer "never
# fabricates a commit or a release it did not read", and leaves externally-pinned
# identities to the run. That is not a gap to paper over -- it is the same principle that
# closed the C3 seam, where `clean_tree: true` was believed because the artifact said so.
# A run does not get to be the witness for its own checkout.
#
# So the CHECKOUT is attested by the external pin alone, and what each BUNDLE must bind is
# what its code actually DID: the method and config hashes. A lane built from code that
# differs in any way that matters changes these; a lane built from identical code bytes
# under a different commit sha does not -- and that is the right answer, because the
# science is then identical.
# TWO ROLES, KEPT EXPLICIT (owner rule):
#   code_identity  -- WHICH BUILD produced the bytes (commit + digest + recorded tree
#                     state, the shared Stage-2 code-digest convention);
#   method digests -- WHAT THE CODE DID (estimator/method/config hashes).
# A method hash is not a build: two builds can compute the same method. A build is not a
# method: the same commit can be asked a different question. Both are bound; neither
# stands in for the other.
METHOD_BINDING_FIELDS = ("temporal_method_sha256", "pathway_method_sha256",
                         "estimator_id", "estimator_version", "direct_method_version",
                         "direct_config_sha256", "effect_source_sha256")


def method_binding(prov: Any) -> dict:
    """WHAT the code did: the estimator/method/config digests the bundle binds.

    ``stage2_inputs`` is a FIXED KEYED OBJECT. The role/value list it replaced is refused
    by ``check_keyed_provenance`` rather than parsed.
    """
    rb = (prov or {}).get("run_binding") or {}
    out = {k: rb[k] for k in METHOD_BINDING_FIELDS if rb.get(k) is not None}
    inputs = rb.get("stage2_inputs")
    if isinstance(inputs, dict):
        out.update({k: v for k, v in inputs.items() if k in METHOD_BINDING_FIELDS})
    return out


def code_binding(prov: Any) -> dict:
    """WHICH BUILD produced the bytes. Required: an unattributable arm came from anywhere."""
    rb = (prov or {}).get("run_binding") or {}
    return rb.get("code_identity") or {}


def check_code_identity(code: Any, pinned: Any, bundle_id: str) -> list[str]:
    """A bundle's ``code_identity`` against an INDEPENDENTLY pinned build.

    REQUIRED: an arm nobody can attribute to a build is an arm that could have come from
    anywhere, and "a lane produced from another commit" is precisely the mutation this
    exists to stop. The producer RECORDS its tree state; it does not get to declare itself
    clean — the verifier decides that against the pin.
    """
    bad: list[str] = []
    if not isinstance(code, dict) or not code:
        return [f"{bundle_id}: the bundle binds no code_identity, so the build that "
                "produced its bytes cannot be attributed"]
    if not isinstance(pinned, dict) or not pinned:
        return [f"{bundle_id}: no expected code identity was pinned; a run's code identity "
                "may not be taken from the run"]
    shared = [f for f in pinned if f in code]
    if not shared:
        return [f"{bundle_id}: the pinned code identity {sorted(pinned)[:4]} shares no "
                f"field with what the bundle binds {sorted(code)[:4]}, so the pin checks "
                "nothing"]
    for field in shared:
        if code[field] != pinned[field]:
            bad.append(f"{bundle_id}: code {field} is {str(code[field])[:20]!r}; the "
                       f"pinned build is {str(pinned[field])[:20]!r}")
    return bad

