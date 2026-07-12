"""Consume the IMMUTABLE Stage-1 selection contract.

Stage-2 never constructs a selection and never names a program, a condition or a
dataset. It receives one contract carrying two ordered axes (A, B) and one
shared analysis condition, validates it structurally, and refuses anything it
cannot execute honestly.

Contract shape (Stage-1 owns it; Stage-2 only reads):

    {"schema_version": "spot.stage01_selection_contract.v1",
     "A": {"program_id": ..., "direction": "high"|"low"},
     "B": {"program_id": ..., "direction": "high"|"low"},
     "analysis_condition": "<one real condition>",
     "combination_policy": "deferred_to_stage2",
     "ids": {"question_id": ..., "selection_id": ...},
     "hashes": {"registry_sha256", "method_version",
                "input_manifest_sha256", "code_sha256",
                "validation_sha256"?}}

The combination of the two arms is a Stage-2 descriptive option; a contract that
tries to hand Stage-2 a combined objective (a Stage-1 ``balanced_a_to_b``) is
REJECTED — the combination must never re-enter Stage 1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from . import config, trust
from .hashing import content_hash, file_sha256

ACCEPTED_SCHEMA_PREFIX = "spot.stage01_selection_contract."
# The deterministic Stage-1 research bridge uses its own schema id.
ACCEPTED_SCHEMAS = (ACCEPTED_SCHEMA_PREFIX, "spot.stage01_selection.")

# A contract must not carry an executable combined objective back into Stage-2.
FORBIDDEN_CONTRACT_KEYS = (
    "objective", "balanced_a_to_b", "balanced_objective", "combination_objective",
    "sensitivity", "sensitivity_lane",
)
FORBIDDEN_CONDITIONS = ("all", "all_conditions", "alltimes", "all_times", "")


# ID namespaces. The namespace is checked against the LOADER that was called, so
# a contract cannot be relabelled into another lane by editing a field.
FIXTURE_PREFIXES = ("fx_",)
RESEARCH_PREFIXES = config.RESEARCH_NAMESPACE_PREFIXES          # rq_ / ra_
NAMESPACE_BY_KIND = {
    "production": {"forbidden": RESEARCH_PREFIXES + FIXTURE_PREFIXES,
                   "required": ()},
    "research": {"forbidden": FIXTURE_PREFIXES, "required": RESEARCH_PREFIXES},
    "fixture": {"forbidden": RESEARCH_PREFIXES, "required": FIXTURE_PREFIXES},
}
LANE_BY_KIND = {"production": config.LANE_PRODUCTION,
                "research": config.LANE_RESEARCH,
                "fixture": config.LANE_SYNTHETIC}

# A research contract arrives over the deterministic Stage-1 research bridge.
RESEARCH_BRIDGE_REQUIRED = {
    "namespace": config.RESEARCH_NAMESPACE,
    "production_gate_passed": False,
    "source": config.RESEARCH_BRIDGE_SOURCE,
}
# Research demands COMPLETE measured evidence. Only the production-selectability
# gate is relaxed; every measurement binding is still mandatory.
RESEARCH_REQUIRED_HASHES = (
    "registry_sha256", "method_version", "input_manifest_sha256", "code_sha256",
    "validation_sha256", "gate_spec_sha256", "scores_sha256", "environment_sha256",
)

# Bindings a PRODUCTION contract must carry. An omitted binding is fatal.
PRODUCTION_REQUIRED_HASHES = (
    "registry_sha256", "method_version", "input_manifest_sha256", "code_sha256",
    "validation_sha256", "gate_spec_sha256", "scores_sha256",
    "environment_sha256", "selectability_pointer_sha256",
)


class SelectionError(ValueError):
    """The selection contract cannot be executed; refuse rather than repair."""


@dataclass(frozen=True)
class Pole:
    program_id: str
    direction: str

    @property
    def sign(self) -> int:
        return config.POLE_SIGN[self.direction]


@dataclass(frozen=True)
class Selection:
    """A validated, immutable Stage-1 selection."""
    a: Pole
    b: Pole
    lane: str
    analysis_condition: str
    question_id: str
    selection_id: str
    registry_sha256: str
    stage1_method_version: str
    stage1_input_manifest_sha256: Optional[str]
    stage1_code_sha256: Optional[str]
    stage1_validation_sha256: Optional[str]
    contract_sha256: str
    raw: dict[str, Any]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SelectionError(msg)


def _pole(raw: dict, key: str) -> Pole:
    node = raw.get(key)
    _require(isinstance(node, dict), f"selection contract: '{key}' must be an object")
    pid = node.get("program_id")
    direction = node.get("direction")
    _require(isinstance(pid, str) and pid.strip() != "",
             f"selection contract: {key}.program_id missing")
    _require(direction in config.POLE_SIGN,
             f"selection contract: {key}.direction must be 'high' or 'low', got {direction!r}")
    return Pole(program_id=pid, direction=direction)


def validate_stage1_method_version(method_version: Any) -> str:
    """Reject stale Stage-1 selections (e.g. v2) before any data is touched."""
    _require(isinstance(method_version, str) and method_version.strip() != "",
             "selection contract: hashes.method_version missing")
    mv = method_version.strip()
    for stale in config.REJECTED_STAGE1_METHOD_PREFIXES:
        if mv.startswith(stale):
            raise SelectionError(
                f"stale Stage-1 selection rejected: method_version={mv!r} "
                f"(Stage-2 requires {config.ACCEPTED_STAGE1_METHOD_PREFIX}*)")
    _require(mv.startswith(config.ACCEPTED_STAGE1_METHOD_PREFIX),
             f"unsupported Stage-1 method_version={mv!r} "
             f"(Stage-2 requires {config.ACCEPTED_STAGE1_METHOD_PREFIX}*)")
    return mv


def parse_selection(raw: dict[str, Any], contract_sha256: str) -> Selection:
    """Validate a selection-contract mapping and return an immutable Selection."""
    _require(isinstance(raw, dict), "selection contract: not a JSON object")

    schema = raw.get("schema_version")
    _require(isinstance(schema, str)
             and any(schema.startswith(p) for p in ACCEPTED_SCHEMAS),
             f"selection contract: unsupported schema_version {schema!r}")

    present_forbidden = sorted(k for k in FORBIDDEN_CONTRACT_KEYS if k in raw)
    _require(not present_forbidden,
             "selection contract carries Stage-2-only or non-executable keys "
             f"{present_forbidden}: the arm combination is descriptive Stage-2 "
             "output and must never be handed back through Stage 1")

    combo = raw.get("combination_policy")
    if combo is not None:
        _require(combo == "deferred_to_stage2",
                 f"selection contract: combination_policy must be "
                 f"'deferred_to_stage2', got {combo!r}")

    a, b = _pole(raw, "A"), _pole(raw, "B")
    _require(a.program_id != b.program_id,
             "selection contract: A and B name the same program")

    cond = raw.get("analysis_condition")
    _require(isinstance(cond, str), "selection contract: analysis_condition missing")
    _require(cond.strip().lower() not in FORBIDDEN_CONDITIONS,
             f"selection contract: analysis_condition {cond!r} is not one "
             "executable condition")

    ids = raw.get("ids") or {}
    hashes = raw.get("hashes") or {}
    _require(isinstance(ids, dict) and isinstance(hashes, dict),
             "selection contract: 'ids' and 'hashes' must be objects")
    selection_id = ids.get("selection_id")
    question_id = ids.get("question_id")
    _require(isinstance(selection_id, str) and selection_id.strip() != "",
             "selection contract: ids.selection_id missing")
    _require(isinstance(question_id, str) and question_id.strip() != "",
             "selection contract: ids.question_id missing")

    registry_sha = hashes.get("registry_sha256")
    _require(isinstance(registry_sha, str) and registry_sha.strip() != "",
             "selection contract: hashes.registry_sha256 missing")
    method_version = validate_stage1_method_version(hashes.get("method_version"))

    lane = raw.get("lane")
    _require(lane in config.LANES,
             f"selection contract: lane must be one of {list(config.LANES)}, "
             f"got {lane!r}")
    # A research-namespace RUN IDENTIFIER may never enter the production lane. The
    # biological program ids are frozen registry ids and are never namespaced.
    if lane == config.LANE_PRODUCTION:
        for name, value in (("question_id", question_id),
                            ("selection_id", selection_id)):
            for prefix in config.RESEARCH_NAMESPACE_PREFIXES:
                _require(not str(value).startswith(prefix),
                         f"production firewall: research-namespace {name}={value!r} "
                         f"(prefix {prefix!r}) may not enter the production lane")

    return Selection(
        a=a, b=b,
        lane=lane,
        analysis_condition=cond,
        question_id=question_id,
        selection_id=selection_id,
        registry_sha256=registry_sha,
        stage1_method_version=method_version,
        stage1_input_manifest_sha256=hashes.get("input_manifest_sha256"),
        stage1_code_sha256=hashes.get("code_sha256"),
        # Pending until the Stage-1 v3 validation artifact exists; carried as an
        # explicit null so that filling it later changes run_id.
        stage1_validation_sha256=hashes.get("validation_sha256"),
        contract_sha256=contract_sha256,
        raw=raw,
    )


def load_selection(path: str) -> Selection:
    with open(path) as fh:
        raw = json.load(fh)
    return parse_selection(raw, contract_sha256=file_sha256(path))


ID_LEN = 32
LANE_ID_PREFIX = {config.LANE_PRODUCTION: "",
                  config.LANE_RESEARCH: "rq_",
                  config.LANE_SYNTHETIC: "fx_"}


def derive_question_id(sel: Selection) -> str:
    """The canonical, namespaced question id. Biology only."""
    body = content_hash({
        "A": {"program_id": sel.a.program_id, "direction": sel.a.direction},
        "B": {"program_id": sel.b.program_id, "direction": sel.b.direction},
        "analysis_condition": sel.analysis_condition,
    })[:ID_LEN]
    return f"{LANE_ID_PREFIX.get(sel.lane, '')}{body}"


def derive_selection_id(sel: Selection) -> str:
    body = content_hash({
        "question_id": sel.question_id,
        "registry_sha256": sel.registry_sha256,
        "method_version": sel.stage1_method_version,
        "input_manifest_sha256": sel.stage1_input_manifest_sha256,
    })[:ID_LEN]
    return f"{LANE_ID_PREFIX.get(sel.lane, '')}{body}"


def recomputed_ids(sel: Selection) -> dict[str, Any]:
    """Re-derive the canonical ids. A mismatch is FATAL upstream, never advisory.

    A contract cannot bless itself by re-hashing its own tampered content: the id
    is derived from the SCIENCE (poles, directions, condition, registry, method,
    inputs), so a forged id simply fails to reproduce.
    """
    question = derive_question_id(sel)
    selection = derive_selection_id(sel)
    return {
        "question_id_recomputed": question,
        "selection_id_recomputed": selection,
        "question_id_matches_declared": question == sel.question_id,
        "selection_id_matches_declared": selection == sel.selection_id,
        "rule_id": config.ID_RECOMPUTE_RULE_ID,
        "mismatch_is_fatal": True,
    }


# The lane namespace attaches to RUN IDENTIFIERS ONLY. Biological program ids are
# frozen Stage-1 registry ids (``treg_like``, ``th1_like``, ...) and are carried
# byte-for-byte: prefixing them would rename the biology, and the registry binding
# would then fail to find them. Isolation between lanes is enforced where it
# belongs -- on question_id and selection_id.
NAMESPACED_IDENTIFIERS = ("question_id", "selection_id")


def _check_namespace(sel: Selection, kind: str) -> None:
    rule = NAMESPACE_BY_KIND[kind]
    values = {"question_id": sel.question_id, "selection_id": sel.selection_id}
    for name, value in values.items():
        for bad in rule["forbidden"]:
            _require(not str(value).startswith(bad),
                     f"namespace firewall: {kind} loader refuses {name}={value!r} "
                     f"(reserved prefix {bad!r})")
        if rule["required"]:
            _require(any(str(value).startswith(good) for good in rule["required"]),
                     f"namespace firewall: {kind} loader requires {name}={value!r} "
                     f"to carry one of the prefixes {list(rule['required'])}")


def _verify_ids(sel: Selection) -> None:
    """Re-derive question_id / selection_id. A mismatch is FATAL, never advisory."""
    check = recomputed_ids(sel)
    _require(check["question_id_matches_declared"],
             "identifier mismatch: the contract's question_id is not the canonical "
             "hash of (A, B, directions, analysis_condition). A re-self-hashed "
             "contract does not become trustworthy by hashing itself again.")
    _require(check["selection_id_matches_declared"],
             "identifier mismatch: the contract's selection_id is not the canonical "
             "hash of (question_id, registry, method_version, input_manifest).")


def bind_release(sel: Selection, release: trust._Release) -> dict[str, Any]:
    """Bind the selection to a verified Stage-1 release.

    Selectability is taken from the release's INDEPENDENTLY DERIVED gate result,
    never from a stored ``stage2_selectable`` / ``production_selectable`` boolean,
    and the registry is bound by its canonical content hash, never by a hash the
    registry declares about itself.
    """
    kind = release.kind
    _check_namespace(sel, kind)

    # The registry is bound by its INDEPENDENTLY DERIVED canonical content. A hash
    # the registry declares about itself is not a binding and is never accepted.
    # Checked BEFORE the ids, so a self-hash forgery is named for what it is.
    derived_registry = release.hashes.get("registry_canonical_sha256")
    _require(sel.registry_sha256 == derived_registry,
             f"registry binding mismatch: the contract names registry_sha256="
             f"{sel.registry_sha256!r}, but the registry's independently derived "
             f"canonical content hashes to {derived_registry!r}. A registry's own "
             "internal self-hash is not a binding.")
    _verify_ids(sel)

    _require(sel.lane == LANE_BY_KIND[kind],
             f"a {kind} release may not back a {sel.lane!r} selection")

    if kind in ("production", "research"):
        required = (PRODUCTION_REQUIRED_HASHES if kind == "production"
                    else RESEARCH_REQUIRED_HASHES)
        missing = [h for h in required if not sel.raw.get("hashes", {}).get(h)]
        _require(not missing,
                 f"{kind} contract omits required Stage-1 bindings {missing}; "
                 "an unbound input is an untrusted input")
        # every declared binding must EXACTLY match the verified release
        expected = {
            "registry_sha256": release.hashes.get("registry_canonical_sha256"),
            "validation_sha256": release.hashes.get("validation_raw_sha256"),
            "gate_spec_sha256": release.hashes.get("gate_spec_raw_sha256"),
            "input_manifest_sha256": release.hashes.get("input_manifest_raw_sha256"),
            "scores_sha256": release.hashes.get("scores_raw_sha256"),
            "code_sha256": release.hashes.get("code_raw_sha256"),
            "environment_sha256": release.hashes.get("environment_raw_sha256"),
            "selectability_pointer_sha256":
                release.hashes.get("selectability_pointer_raw_sha256"),
            "method_version": release.method_version,
        }
        declared = sel.raw.get("hashes", {})
        for key, want in expected.items():
            if key not in required:
                continue
            got = declared.get(key)
            _require(got == want,
                     f"Stage-1 binding mismatch on {key!r}: contract declares "
                     f"{got!r}, verified release is {want!r}")

    if kind == "research":
        bridge = sel.raw.get("bridge") or {}
        for key, want in RESEARCH_BRIDGE_REQUIRED.items():
            _require(bridge.get(key) == want,
                     f"research bridge: {key!r} must be {want!r}, got "
                     f"{bridge.get(key)!r}")
        _require(str(sel.raw.get("schema_version")) == config.RESEARCH_BRIDGE_SCHEMA,
                 f"research bridge: schema_version must be "
                 f"{config.RESEARCH_BRIDGE_SCHEMA!r}")

    out: dict[str, Any] = {
        "release_kind": kind,
        "registry_hash_binding": "independently_derived_canonical_content",
        "gate_evidence": release.gate_evidence,
        "may_confer_stage3_eligibility": release.may_confer_stage3_eligibility,
    }
    selectability: dict[str, Any] = {}
    for key, pole in (("A", sel.a), ("B", sel.b)):
        prog = release.programs.get(pole.program_id)
        _require(prog is not None,
                 f"selection contract: program {pole.program_id!r} ({key}) is not "
                 "in the bound Stage-1 registry")

        pair = (pole.program_id, sel.analysis_condition)
        derived_selectable = pair in release.selectable_pairs
        selectability[key] = {
            "program_condition": f"{pole.program_id}|{sel.analysis_condition}",
            "selectable_derived": derived_selectable,
            "rule_id": config.SELECTABILITY_RULE_ID,
            "stored_boolean_read": False,
        }
        if kind == "research":
            # Research REQUIRES a primary, base-portable axis, and requires the gate
            # to have been MEASURED — but not to have passed. The failed gate is
            # recorded as provenance.
            if config.RESEARCH_REQUIRES_PRIMARY_BASE_PORTABLE_AXES:
                _require(prog.get("primary") is True,
                         f"research: program {pole.program_id!r} ({key}) is not "
                         "declared a primary axis by Stage-1")
                _require(prog.get("base_portable") is True,
                         f"research: program {pole.program_id!r} ({key}) is not "
                         "declared base-portable by Stage-1")
            _require(f"{pair[0]}|{pair[1]}" in release.gate_evidence.get("pairs", {}),
                     f"research: program-condition {pair[0]!r}|{pair[1]!r} ({key}) "
                     "has no measured Stage-1 gate evidence; research demands "
                     "complete measured evidence")
            selectability[key]["production_gate_passed"] = derived_selectable
        else:
            # THE PRODUCTION GATE. With the frozen 0/33 validation, this refuses.
            _require(derived_selectable,
                     f"Stage-1 gate: program-condition {pair[0]!r}|{pair[1]!r} ({key}) "
                     f"is NOT production-selectable under the re-derived hard gates "
                     f"({release.gate_evidence.get('n_production_selectable', 0)}/"
                     f"{release.gate_evidence.get('n_pairs_evaluated', 0)} pairs pass); "
                     "no ranking may be generated for it")

        panel = prog.get("panel_ensembl")
        control = prog.get("control_ensembl")
        _require(isinstance(panel, list) and len(panel) > 0,
                 f"registry program {pole.program_id!r}: panel_ensembl missing")
        _require(isinstance(control, list) and len(control) > 0,
                 f"registry program {pole.program_id!r}: control_ensembl missing")
        out[key] = {
            "program_id": pole.program_id,
            "direction": pole.direction,
            "sign": pole.sign,
            "panel": [str(g) for g in panel],
            "control": [str(g) for g in control],
        }
    out["selectability"] = selectability
    out["namespace"] = (config.RESEARCH_NAMESPACE if kind == "research"
                        else "production" if kind == "production" else "synthetic")
    out["production_eligible"] = (kind == "production")
    out["stage3_eligible"] = (kind == "production")
    out["may_write_production_pointer"] = release.may_write_production_pointer
    out["production_gate_passed"] = bool(release.selectable_pairs)
    return out


def load_production_selection(path: str) -> Selection:
    sel = load_selection(path)
    _require(sel.lane == config.LANE_PRODUCTION,
             f"load_production_selection: contract declares lane {sel.lane!r}")
    _check_namespace(sel, "production")
    return sel


def load_fixture_selection(path: str) -> Selection:
    sel = load_selection(path)
    _require(sel.lane == config.LANE_SYNTHETIC,
             f"load_fixture_selection: contract declares lane {sel.lane!r}")
    _check_namespace(sel, "fixture")
    return sel


def load_research_selection(path: str) -> Selection:
    """The deterministic Stage-1 research bridge (``spot.stage01_selection.v1``).

    The bridge must self-declare namespace=research_only, production_gate_passed=
    false, and source=stage01_research_bridge. The synthetic fixture lane may never
    stand in for research.
    """
    sel = load_selection(path)
    _require(sel.lane == config.LANE_RESEARCH,
             f"load_research_selection: contract declares lane {sel.lane!r}")
    bridge = sel.raw.get("bridge") or {}
    for key, want in RESEARCH_BRIDGE_REQUIRED.items():
        _require(bridge.get(key) == want,
                 f"research bridge: {key!r} must be {want!r}, got {bridge.get(key)!r}")
    _check_namespace(sel, "research")
    return sel
