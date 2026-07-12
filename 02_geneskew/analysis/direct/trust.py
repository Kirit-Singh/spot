"""Stage-1 trust: what Stage-2 is allowed to believe, and how it proves it.

Three SEPARATE loaders, distinguished by API and by return TYPE — not by a
mutable field on a generic loader:

    load_production_release(release_manifest_path) -> ProductionRelease
    load_research_release(...)                     -> ResearchRelease
    load_fixture_release(...)                      -> FixtureRelease

Only ``ProductionRelease`` may ever back a production run, and only it can carry
Stage-3 eligibility or write a production pointer. A fixture cannot be relabelled
into production by editing a string, because there is no string to edit: the type
is the lane.

The production loader NEVER trusts:

  * a registry's own internal ``registry_sha256`` field (a file cannot contain
    its own hash; a self-declared hash proves nothing and is trivially forged);
  * a stored ``stage2_selectable`` / ``production_selectable`` boolean.

Instead it reads the immutable Stage-1 release manifest, resolves every artifact
path FROM that manifest, verifies raw bytes and canonical content against the
declared hashes, derives the registry's canonical content itself, and RE-DERIVES
the program-condition hard-gate outcome from the immutable validation rows against
the gate spec. Every required binding is mandatory; a missing one is fatal, never
advisory.

With the current frozen Stage-1 validation (0/33 production-selectable pairs),
``ProductionRelease.selectable_pairs`` is empty and every real production
selection refuses.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import config
from .hashing import content_hash, file_sha256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RELEASE_SCHEMA = "spot.stage01_release_manifest.v1"

# Every one of these bindings is REQUIRED for a production release. An omitted
# binding is fatal: an unbound input is an untrusted input.
REQUIRED_ARTIFACTS = (
    "registry", "validation", "gate_spec", "input_manifest",
    "scores", "code", "environment", "selectability_pointer",
)

# The registry's own self-declared hash field, which is never a binding.
SELF_HASH_FIELDS = ("registry_sha256", "self_sha256", "sha256")

# Comparators a gate may use. An unknown comparator cannot be re-derived, so it
# is fatal rather than assumed to pass.
COMPARATORS = {
    "ge": lambda v, t: v >= t,
    "gt": lambda v, t: v > t,
    "le": lambda v, t: v <= t,
    "lt": lambda v, t: v < t,
    "eq": lambda v, t: v == t,
}


class TrustError(ValueError):
    """A Stage-1 binding could not be proved. Refuse; never downgrade."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TrustError(msg)


# --------------------------------------------------------------------------- #
# Release types. The TYPE is the lane.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Release:
    kind: str
    method_version: str
    programs: dict[str, dict]
    hashes: dict[str, str]                       # every bound artifact hash
    selectable_pairs: frozenset                  # DERIVED (program_id, condition)
    gate_evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def may_write_production_pointer(self) -> bool:
        return self.kind == "production"

    @property
    def may_confer_stage3_eligibility(self) -> bool:
        return self.kind == "production"


@dataclass(frozen=True)
class ProductionRelease(_Release):
    """Immutable, fully-verified Stage-1 release. The only production-capable type."""


@dataclass(frozen=True)
class ResearchRelease(_Release):
    """Research-only. Never production; never Stage-3 eligible."""


@dataclass(frozen=True)
class FixtureRelease(_Release):
    """Synthetic fixture. Never production; never Stage-3 eligible."""


# --------------------------------------------------------------------------- #
# Hash verification.
# --------------------------------------------------------------------------- #
def canonical_content_sha256(doc: Any) -> str:
    """Independently derive a document's canonical content hash.

    Any self-declared hash field is REMOVED before hashing: a document cannot
    attest to itself, so a self hash is excluded from its own canonical content.
    """
    if isinstance(doc, dict):
        stripped = {k: canonical_content_sha256_payload(v)
                    for k, v in doc.items() if k not in SELF_HASH_FIELDS}
        return content_hash(stripped)
    return content_hash(doc)


def canonical_content_sha256_payload(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: canonical_content_sha256_payload(x)
                for k, x in v.items() if k not in SELF_HASH_FIELDS}
    if isinstance(v, list):
        return [canonical_content_sha256_payload(x) for x in v]
    return v


def _verify_artifact(name: str, entry: Any, base_dir: str) -> dict[str, Any]:
    """Resolve an artifact from the manifest and verify raw + canonical hashes."""
    _require(isinstance(entry, dict),
             f"Stage-1 release: artifact {name!r} is malformed")
    rel_path = entry.get("path")
    raw_declared = str(entry.get("raw_sha256", "")).lower()
    canon_declared = str(entry.get("canonical_sha256", "")).lower()
    _require(bool(rel_path), f"Stage-1 release: artifact {name!r} has no path")
    _require(bool(_SHA256_RE.match(raw_declared)),
             f"Stage-1 release: artifact {name!r} has no valid raw_sha256")

    # The path is fixed BY the manifest; nothing else may point Stage-2 elsewhere.
    _require(not os.path.isabs(str(rel_path)) and ".." not in str(rel_path).split("/"),
             f"Stage-1 release: artifact {name!r} path {rel_path!r} must be a "
             "manifest-relative path")
    path = os.path.join(base_dir, str(rel_path))
    _require(os.path.exists(path),
             f"Stage-1 release: artifact {name!r} is missing at its manifest path")

    raw = file_sha256(path)
    _require(raw == raw_declared,
             f"Stage-1 release: artifact {name!r} raw bytes do not match the "
             f"pinned raw_sha256 (declared {raw_declared}, actual {raw})")

    doc = None
    if str(rel_path).endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        _require(bool(_SHA256_RE.match(canon_declared)),
                 f"Stage-1 release: artifact {name!r} has no valid canonical_sha256")
        derived = canonical_content_sha256(doc)
        _require(derived == canon_declared,
                 f"Stage-1 release: artifact {name!r} canonical content does not "
                 f"match the pinned canonical_sha256 (declared {canon_declared}, "
                 f"independently derived {derived})")
    return {"name": name, "path": path, "raw_sha256": raw,
            "canonical_sha256": canon_declared, "doc": doc}


# --------------------------------------------------------------------------- #
# Independent hard-gate re-derivation. No stored boolean is ever read.
# --------------------------------------------------------------------------- #
def derive_selectable_pairs(validation: dict, gate_spec: dict) -> tuple[frozenset, dict]:
    """Re-derive production-selectable (program_id, condition) pairs from evidence.

    Reads the immutable validation ROWS (metric values) and the gate spec
    (thresholds + comparators) and recomputes every hard gate. A stored
    ``passed`` / ``selectable`` boolean in the validation file is IGNORED: the
    verdict is derived, not believed.
    """
    hard_gates = gate_spec.get("hard_gates")
    thresholds = gate_spec.get("thresholds")
    _require(isinstance(hard_gates, list) and hard_gates,
             "Stage-1 gate spec: 'hard_gates' must be a non-empty list")
    _require(isinstance(thresholds, dict),
             "Stage-1 gate spec: 'thresholds' must be an object")

    rows = validation.get("rows")
    _require(isinstance(rows, list),
             "Stage-1 validation: 'rows' must be a list of gate measurements")

    measured: dict[tuple, dict[str, bool]] = {}
    for i, row in enumerate(rows):
        for key in ("program_id", "condition", "gate_id", "value"):
            _require(key in row, f"Stage-1 validation row {i}: missing {key!r}")
        gate = str(row["gate_id"])
        if gate not in hard_gates:
            continue                                   # soft/advisory gate
        spec = thresholds.get(gate)
        _require(isinstance(spec, dict),
                 f"Stage-1 gate spec: no threshold for hard gate {gate!r}")
        comparator = spec.get("comparator")
        _require(comparator in COMPARATORS,
                 f"Stage-1 gate spec: gate {gate!r} has unknown comparator "
                 f"{comparator!r}; a gate that cannot be re-derived cannot pass")
        value = row["value"]
        _require(value is not None,
                 f"Stage-1 validation row {i}: gate {gate!r} has a null value; "
                 "an unmeasured hard gate cannot pass")
        passed = COMPARATORS[comparator](float(value), float(spec["threshold"]))
        key = (str(row["program_id"]), str(row["condition"]))
        measured.setdefault(key, {})[gate] = bool(passed)

    selectable = set()
    evidence: dict[str, Any] = {"hard_gates": list(hard_gates), "pairs": {}}
    for key, gates in sorted(measured.items()):
        complete = all(g in gates for g in hard_gates)
        all_pass = complete and all(gates[g] for g in hard_gates)
        evidence["pairs"][f"{key[0]}|{key[1]}"] = {
            "gates_measured": {g: gates.get(g) for g in hard_gates},
            "all_hard_gates_measured": complete,
            "production_selectable_derived": all_pass,
        }
        if all_pass:
            selectable.add(key)
    evidence["n_pairs_evaluated"] = len(measured)
    evidence["n_production_selectable"] = len(selectable)
    evidence["rule_id"] = config.SELECTABILITY_RULE_ID
    evidence["stored_boolean_read"] = False
    return frozenset(selectable), evidence


def _programs_from_registry(registry: dict) -> dict[str, dict]:
    programs = registry.get("programs")
    _require(isinstance(programs, list) and programs,
             "Stage-1 registry: 'programs' must be a non-empty list")
    out = {}
    for prog in programs:
        pid = prog.get("program_id")
        _require(bool(pid), "Stage-1 registry: a program has no program_id")
        out[str(pid)] = prog
    return out


def load_production_release(release_manifest_path: str) -> ProductionRelease:
    """Load and PROVE the immutable Stage-1 release. Every binding is mandatory."""
    _require(os.path.exists(release_manifest_path),
             f"Stage-1 release manifest not found: "
             f"{os.path.basename(release_manifest_path)}")
    with open(release_manifest_path) as fh:
        manifest = json.load(fh)
    _require(str(manifest.get("schema_version", "")) == RELEASE_SCHEMA,
             f"Stage-1 release manifest: schema_version must be {RELEASE_SCHEMA!r}")

    method_version = str(manifest.get("method_version", ""))
    _require(bool(method_version),
             "Stage-1 release manifest: method_version is a required binding")

    artifacts = manifest.get("artifacts") or {}
    missing = [a for a in REQUIRED_ARTIFACTS if a not in artifacts]
    _require(not missing,
             f"Stage-1 release manifest: required bindings omitted: {missing}. "
             "An omitted binding is fatal, never advisory.")

    base_dir = os.path.dirname(os.path.abspath(release_manifest_path))
    verified = {name: _verify_artifact(name, artifacts[name], base_dir)
                for name in REQUIRED_ARTIFACTS}

    registry = verified["registry"]["doc"]
    validation = verified["validation"]["doc"]
    gate_spec = verified["gate_spec"]["doc"]
    _require(registry is not None and validation is not None and gate_spec is not None,
             "Stage-1 release: registry, validation and gate_spec must be JSON")

    selectable, evidence = derive_selectable_pairs(validation, gate_spec)

    hashes = {f"{name}_raw_sha256": v["raw_sha256"] for name, v in verified.items()}
    hashes.update({f"{name}_canonical_sha256": v["canonical_sha256"]
                   for name, v in verified.items() if v["canonical_sha256"]})
    hashes["release_manifest_raw_sha256"] = file_sha256(release_manifest_path)
    hashes["method_version"] = method_version

    return ProductionRelease(
        kind="production",
        method_version=method_version,
        programs=_programs_from_registry(registry),
        hashes=hashes,
        selectable_pairs=selectable,
        gate_evidence=evidence,
    )


def load_fixture_release(registry_path: str, validation_path: str,
                         gate_spec_path: str) -> FixtureRelease:
    """A synthetic fixture release. Cannot back a production run, ever."""
    with open(registry_path) as fh:
        registry = json.load(fh)
    with open(validation_path) as fh:
        validation = json.load(fh)
    with open(gate_spec_path) as fh:
        gate_spec = json.load(fh)

    # A fixture's gates are re-derived by the SAME code, so the fixture exercises
    # the real rule rather than a shortcut.
    selectable, evidence = derive_selectable_pairs(validation, gate_spec)
    hashes = {
        "registry_raw_sha256": file_sha256(registry_path),
        "registry_canonical_sha256": canonical_content_sha256(registry),
        "validation_raw_sha256": file_sha256(validation_path),
        "gate_spec_raw_sha256": file_sha256(gate_spec_path),
        "method_version": str(registry.get("method_version", "fixture")),
    }
    return FixtureRelease(
        kind="fixture",
        method_version=str(registry.get("method_version", "fixture")),
        programs=_programs_from_registry(registry),
        hashes=hashes,
        selectable_pairs=selectable,
        gate_evidence=evidence,
    )


# A research release needs the SAME verified measurement bundle as production,
# minus the production selectability pointer. The gates are still RE-DERIVED; the
# research lane records their outcome instead of requiring it to pass.
RESEARCH_REQUIRED_ARTIFACTS = ("registry", "validation", "gate_spec",
                               "input_manifest", "scores", "code", "environment")


def load_research_release(release_manifest_path: str) -> ResearchRelease:
    """Load and PROVE a v3 measurement bundle for research-only analysis.

    Identical verification to production — raw + canonical hashes, manifest-fixed
    paths, independently derived registry content, re-derived hard gates — except
    that a failing gate is RECORDED rather than fatal.
    """
    _require(os.path.exists(release_manifest_path),
             f"Stage-1 research bundle not found: "
             f"{os.path.basename(release_manifest_path)}")
    with open(release_manifest_path) as fh:
        manifest = json.load(fh)
    _require(str(manifest.get("schema_version", "")) == RELEASE_SCHEMA,
             f"Stage-1 research bundle: schema_version must be {RELEASE_SCHEMA!r}")

    method_version = str(manifest.get("method_version", ""))
    _require(bool(method_version),
             "Stage-1 research bundle: method_version is a required binding")

    artifacts = manifest.get("artifacts") or {}
    missing = [a for a in RESEARCH_REQUIRED_ARTIFACTS if a not in artifacts]
    _require(not missing,
             f"Stage-1 research bundle: required bindings omitted: {missing}. "
             "Research demands COMPLETE measured evidence; only the production "
             "selectability gate is relaxed.")

    base_dir = os.path.dirname(os.path.abspath(release_manifest_path))
    verified = {name: _verify_artifact(name, artifacts[name], base_dir)
                for name in RESEARCH_REQUIRED_ARTIFACTS}

    registry = verified["registry"]["doc"]
    validation = verified["validation"]["doc"]
    gate_spec = verified["gate_spec"]["doc"]
    _require(registry is not None and validation is not None and gate_spec is not None,
             "Stage-1 research bundle: registry, validation and gate_spec must be JSON")

    selectable, evidence = derive_selectable_pairs(validation, gate_spec)
    evidence["production_gate_passed"] = bool(selectable)
    # Research RECORDS the gate without requiring it to pass, and never confers
    # production or Stage-3 eligibility. Flags, not a paragraph: a consumer branches on
    # these, and the reasoning behind them is in the lane docs.
    evidence["gate_required_to_pass"] = config.RESEARCH_REQUIRES_PRODUCTION_GATE_PASS
    evidence["confers_production_eligibility"] = False
    evidence["confers_stage3_eligibility"] = False

    hashes = {f"{name}_raw_sha256": v["raw_sha256"] for name, v in verified.items()}
    hashes.update({f"{name}_canonical_sha256": v["canonical_sha256"]
                   for name, v in verified.items() if v["canonical_sha256"]})
    hashes["release_manifest_raw_sha256"] = file_sha256(release_manifest_path)
    hashes["method_version"] = method_version

    return ResearchRelease(
        kind="research",
        method_version=method_version,
        programs=_programs_from_registry(registry),
        hashes=hashes,
        selectable_pairs=selectable,
        gate_evidence=evidence,
    )
