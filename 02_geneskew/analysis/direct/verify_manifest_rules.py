"""The run-manifest contract, REIMPLEMENTED FROM THE WRITTEN SPEC for the verifier.

INDEPENDENCE RULE (test-enforced): nothing here is imported from the generator — not
``run_manifest``, not ``arm_topology``, not ``config``, not ``hashing``, not
``code_digest``. The canonical hash, the desired-change table, the slot algebra and the
forbidden-key firewall are all restated here, so the verifier can DISAGREE with the
producer. A verifier that reused the producer's own functions would agree with it by
construction, whatever those functions happen to compute today.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Optional

LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY = "direct", "temporal", "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)
INCREASE, DECREASE = "increase", "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)
ADMIT, REJECT, PASS, FAIL = "admit", "reject", "pass", "fail"

# THE VERIFIER'S OWN COPY of the frozen role x pole -> desired_change table.
#
# away_from_A(high) and toward_B(low) are the SAME desired change (both compute -delta);
# away_from_A(high) and toward_B(high) are OPPOSITE ones (-delta vs +delta). That is
# exactly why the arm key is the DESIRED CHANGE and not the pole direction: keying on the
# pole would merge the two arms that disagree and split the two that are identical.
SPEC_DESIRED_CHANGE = {
    ("away_from_A", "high"): DECREASE,
    ("away_from_A", "low"): INCREASE,
    ("toward_B", "high"): INCREASE,
    ("toward_B", "low"): DECREASE,
}

BUNDLE_FILES = {
    LANE_DIRECT: ("arm_bundle.json", "provenance.json", "verification.json"),
    LANE_TEMPORAL: ("arm_bundle.json", "temporal_provenance.json",
                    "temporal_verification.json"),
    LANE_PATHWAY: ("arm_bundle.json", "pathway_provenance.json",
                   "pathway_verification.json", "convergence.json"),
}
PROVENANCE_OF = {lane: files[1] for lane, files in BUNDLE_FILES.items()}
REPORT_OF = {lane: files[2] for lane, files in BUNDLE_FILES.items()}

# Bindings whose BYTES a pathway count must be reconstructible from.
PATHWAY_BINDINGS = ("gene_set_membership", "target_universe", "masked_signatures",
                    "readout_universe")

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


def check_code_identity(code: Any, pinned: Any, bundle_id: str) -> list[str]:
    """Every bundle's code identity, against an INDEPENDENTLY pinned commit + digest.

    ``clean_tree`` used to be believed because the artifact said so. A resealed
    ``clean_tree: true`` over a different commit is exactly the claim that needs an
    outside witness, and the manifest is not one.
    """
    bad: list[str] = []
    if not isinstance(code, dict):
        return [f"{bundle_id}: the bundle binds no code identity"]
    if not isinstance(pinned, dict) or not pinned:
        return [f"{bundle_id}: no expected code identity was pinned; a run's code identity "
                "may not be taken from the run"]
    for field in ("commit", "manifest_sha256", "canonical_digest"):
        if field in pinned and code.get(field) != pinned[field]:
            bad.append(f"{bundle_id}: code {field} is {str(code.get(field))[:16]!r}; the "
                       f"pinned checkout is {str(pinned[field])[:16]!r}")
    return bad

# No p, no q, no FDR produced by spot — at any nesting depth, in any bundle.
FORBIDDEN_KEY_RE = re.compile(
    r"(^|_)(p|q)(_?val(ue)?s?)?($|_)|p_?adj|q_?value|fdr|bonferroni|benjamini",
    re.IGNORECASE)

PAIR_DERIVED_KEYS = ("pareto", "concordance", "joint_order", "joint_ordering",
                     "combined_score", "balanced_skew", "weighted_score",
                     "composite_score", "headline_rank")


# --------------------------------------------------------------------------- #
# The verifier's own hashing and readers.
# --------------------------------------------------------------------------- #
def content_sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                   allow_nan=False).encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: str) -> Optional[Any]:
    """``None`` when the bytes are not a readable JSON document. Never raises."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _scan(obj: Any, hit, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if hit(str(k)):
                out.append(f"{path}.{k}")
            out += _scan(v, hit, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += _scan(v, hit, f"{path}[{i}]")
    return out


def forbidden_keys(obj: Any) -> list[str]:
    return _scan(obj, lambda k: bool(FORBIDDEN_KEY_RE.search(k)))


def pair_derived_keys(obj: Any) -> list[str]:
    return _scan(obj, lambda k: any(bad in k.lower() for bad in PAIR_DERIVED_KEYS))


# --------------------------------------------------------------------------- #
# The independent expectation.
# --------------------------------------------------------------------------- #
def scorer_programs(doc: Optional[dict]) -> tuple[list[str], dict[str, Any]]:
    """RE-DERIVE the admitted program set from the view's OWN portability field.

    The view's declared ``base_portable_programs`` list is never read here — the caller
    compares it against this derivation, and a disagreement refuses the view.
    """
    if not isinstance(doc, dict):
        return [], {}
    field = doc.get("base_portability_source_field")
    programs = doc.get("programs") or []
    derived = sorted(str(p["program_id"]) for p in programs
                     if field and p.get(field))
    scorer = {str(p["program_id"]): p.get("method_hash") for p in programs}
    return derived, scorer


def ordered_pairs(conds: list[str]) -> list[tuple[str, str]]:
    c = sorted(conds)
    return [(a, b) for a in c for b in c if a != b]


def arm_key(lane: str, program: str, dc: str, ctx: dict) -> str:
    if lane == LANE_DIRECT:
        tail = [str(ctx.get("condition"))]
    elif lane == LANE_TEMPORAL:
        tail = [str(ctx.get("from_condition")), str(ctx.get("to_condition"))]
    else:
        tail = [str(ctx.get("condition")), str(ctx.get("gene_set_source"))]
    return "|".join([lane, program, dc] + tail)


def expected_slots(programs: list[str], conds: list[str],
                   sources: list[str]) -> dict[str, set]:
    """Every logical arm slot a complete run must fill. DERIVED, never declared."""
    out: dict[str, set] = {lane: set() for lane in LANES}
    for p in sorted(programs):
        for dc in DESIRED_CHANGES:
            for c in sorted(conds):
                out[LANE_DIRECT].add(arm_key(LANE_DIRECT, p, dc, {"condition": c}))
                for s in sorted(sources):
                    out[LANE_PATHWAY].add(arm_key(
                        LANE_PATHWAY, p, dc, {"condition": c, "gene_set_source": s}))
            for f, t in ordered_pairs(conds):
                out[LANE_TEMPORAL].add(arm_key(
                    LANE_TEMPORAL, p, dc, {"from_condition": f, "to_condition": t}))
    return out


def selection_capacity(n_programs: int, n_conditions: int) -> dict[str, int]:
    """Restated independently: n(n-1) within a condition, n*n across an ordered pair."""
    states = 2 * int(n_programs)
    pairs = int(n_conditions) * (int(n_conditions) - 1)
    within = int(n_conditions) * states * (states - 1)
    temporal = pairs * states * states
    return {"within_condition_selections": within, "temporal_selections": temporal,
            "total_valid_ordered_selections": within + temporal}


# --------------------------------------------------------------------------- #
# RECONSTRUCTION. A declared count is not evidence.
# --------------------------------------------------------------------------- #
def ranked_target_ids(ranking: Any) -> list[str]:
    """The target ids an arm actually RANKED, from the bound ranking bytes."""
    if not isinstance(ranking, dict):
        return []
    return [str(r.get("target_id")) for r in (ranking.get("ranked") or [])
            if r.get("rank") is not None]


def members_by_set(membership: Any) -> dict[str, set]:
    """Gene-set membership in the TARGET namespace, from the bound membership bytes."""
    if not isinstance(membership, dict):
        return {}
    return {str(sid): {str(g) for g in (s.get("genes_target") or [])}
            for sid, s in (membership.get("sets") or {}).items()}


def reconstruct_hits(membership: Any, ranking: Any) -> dict[str, int]:
    """n_hits_in_ranking, RECOMPUTED per set from the bytes the bundle bound.

    This is the number that decides whether an arm is headline-rankable. Before the
    bundle contract bound the ranking and the membership list, nobody could recompute it
    — so it was, in the end, taken on trust.
    """
    ranked = set(ranked_target_ids(ranking))
    return {sid: len(genes & ranked)
            for sid, genes in members_by_set(membership).items()}


def find_bundle_dir(root: str, name: str) -> Optional[str]:
    for base, dirs, _files in os.walk(root):
        for d in dirs:
            if d == name:
                return os.path.join(base, d)
    return None


class Report:
    """Every gate is recorded, passed or failed. A crash IS a verification failure."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def gate(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"gate": name, "status": PASS if ok else FAIL,
                            "detail": "" if ok else detail})
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [c["gate"] for c in self.checks if c["status"] == FAIL]

    def doc(self, verifier_id: str, schema_version: str, **extra: Any) -> dict[str, Any]:
        return {
            "schema_version": schema_version,
            "verifier_id": verifier_id,
            "generator_is_not_verifier": True,
            "fail_closed": True,
            "checks": self.checks,
            "n_failed": len(self.failed),
            "failed_gates": self.failed,
            "verdict": ADMIT if not self.failed else REJECT,
            **extra,
        }
