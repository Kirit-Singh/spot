"""THE ADAPTER BOUNDARY between a bundle-scoped request (W18's) and a temporal bundle.

W18 OWNS THE REQUEST SCHEMA. THIS MODULE DOES NOT.
-------------------------------------------------
Nothing here defines, validates or version-stamps a request object. It declares the NARROW
set of fields this producer needs to READ off one, resolves them against a bundle, and
refuses when they are absent or do not name something the bundle admits. When W18's schema
lands, it plugs in HERE — and if it disagrees with these field names, this adapter changes,
not the bundle and not the estimand.

Duplicating W18's schema in order to "be safe" would create a second definition of the
request that drifts from the first, and the two would disagree quietly, in the direction
nobody was looking.

THIS IS WHERE THE ROLE AND THE POLE LIVE — AND WHY THEY LIVE *HERE*
------------------------------------------------------------------
The bundle is pole-free and role-free by construction: a cached arm keys on the
perturbation's DESIRED CHANGE. The pole (``high|low``) and the role
(``away_from_A|toward_B``) are SELECTION metadata, and this join is the one place they are
allowed to touch a bundle at all — to CHOOSE an arm. They never alter one.

The consequence worth stating plainly, because it is the whole point of the topology:

    the SAME program at the SAME pole means OPPOSITE perturbations in the two roles

        treg_like(high) as away_from_A  ->  desired_change = decrease
        treg_like(high) as toward_B     ->  desired_change = increase

    Both arms are already in the SAME cached bundle. The join picks one. Neither the
    values nor the ranks nor the bytes of the bundle depend on which role asked — a cached
    arm keyed on the pole would have fused these two opposite perturbations under one key
    and served one of them as the other, silently, with numbers that look entirely
    reasonable.
"""
from __future__ import annotations

from typing import Any, Optional

from ...arm_keys import ArmError, _change, desired_change, temporal_arm_key
from . import arm_bundle, arm_programs

# The NARROW read-surface. Exactly what this producer needs from a bundle-scoped request.
# Not a schema — a list of the fields the adapter looks for, so a missing one is a named
# refusal rather than an AttributeError three frames down.
REQUIRED_REQUEST_FIELDS = ("from_condition", "to_condition")
OPTIONAL_REQUEST_FIELDS = ("program_id", "role", "pole", "desired_change")

ADAPTER_ID = "spot.stage02.temporal.arm.request_adapter.v1"
REQUEST_SCHEMA_OWNER = "W18"
REQUEST_SCHEMA_DEFINED_HERE = False


class RequestRefused(ValueError):
    """The request does not name something this bundle can answer. Refuse; never guess."""


def _read(request: Any, name: str) -> Any:
    """One field, from a mapping or an object alike. Absent is ``None``, never an error."""
    if isinstance(request, dict):
        return request.get(name)
    return getattr(request, name, None)


def scope_of(request: Any) -> tuple[str, str]:
    """The FROZEN ORDERED pair a request is scoped to. Both endpoints, or a refusal."""
    missing = [f for f in REQUIRED_REQUEST_FIELDS if _read(request, f) in (None, "")]
    if missing:
        raise RequestRefused(
            f"the request does not name {missing}; a temporal bundle is scoped to an "
            "ORDERED condition pair, and a request missing an endpoint could be resolved "
            "against either direction — which are different bundles with opposite values")
    frm, to = str(_read(request, "from_condition")), str(_read(request, "to_condition"))
    if frm == to:
        raise RequestRefused(
            f"the request names the degenerate pair ({frm!r} -> {to!r}); a condition "
            "compared with itself is 0 by construction, not a measurement")
    return frm, to


def change_of(request: Any) -> str:
    """The DESIRED CHANGE this request resolves to — from a role+pole, or given directly.

    The frozen ``(role, pole) -> desired_change`` mapping is applied here, at the join, and
    it is the ONLY thing that turns selection metadata into an arm key. A request that
    supplies a raw ``desired_change`` is taken at its word only if it is one of the two
    real ones; a pole handed in where a change belongs is refused BY NAME, because the same
    pole is an increase in one role and a decrease in the other.
    """
    role, pole = _read(request, "role"), _read(request, "pole")
    given = _read(request, "desired_change")

    if role is not None and pole is not None:
        change = desired_change(str(role), str(pole))
        if given is not None and str(given) != change:
            raise RequestRefused(
                f"the request declares desired_change={given!r}, but role={role!r} with "
                f"pole={pole!r} maps to {change!r} under the frozen mapping. A declared "
                "direction that disagrees with the one its own role and pole imply is a "
                "sign error nobody would see in the numbers")
        return change
    if given is None:
        raise RequestRefused(
            "the request names neither a (role, pole) nor a desired_change; there is no "
            "default arm, and picking one would silently answer a question nobody asked")
    try:
        # The shared refusal: a pole ('high'/'low') handed in where a desired change
        # belongs is refused BY NAME, not coerced into whichever arm looks likely.
        return validated_change(str(given))
    except ArmError as exc:
        raise RequestRefused(str(exc)) from exc


def validated_change(change: str) -> str:
    """A real ``increase``/``decrease``, or a named refusal (a pole is caught by name)."""
    return _change(change)


def resolve_arm(bundle: dict[str, Any], request: Any) -> dict[str, Any]:
    """The ONE arm in this bundle that answers this request. Never a near match.

    Refuses a request scoped to a different ordered pair, a program the release did not
    admit, or a forged desired change / arm key.
    """
    frm, to = scope_of(request)
    if (frm, to) != (bundle["from_condition"], bundle["to_condition"]):
        raise RequestRefused(
            f"the request is scoped to ({frm} -> {to}) but this bundle is "
            f"({bundle['from_condition']} -> {bundle['to_condition']}). The reverse pair is "
            "a DIFFERENT bundle whose every value is negated, and resolving one against the "
            "other would return the exact opposite of the answer, with a plausible sign")

    program_id = _read(request, "program_id")
    if program_id in (None, ""):
        raise RequestRefused("the request names no program_id; an arm is per-program")
    program_id = str(program_id)

    admitted = {p: None for p in bundle["program_admission"]["programs"]}
    try:
        arm_programs.require_program(admitted, program_id)
    except arm_programs.ProgramAdmissionError as exc:
        raise RequestRefused(str(exc)) from exc

    change = change_of(request)
    key = temporal_arm_key(program_id, change, frm, to)
    for arm in bundle["arms"]:
        if arm["arm_key"] == key:
            return arm
    raise RequestRefused(
        f"no arm {key!r} in bundle {bundle['bundle_key']!r}. The bundle is complete by "
        "construction, so a key it does not hold is a key that was never derived from an "
        "admitted program and a real desired change")


def arm_by_key(bundle: dict[str, Any], arm_key: str) -> dict[str, Any]:
    """Look an arm up by its canonical key, and REFUSE a forged one.

    The key is not merely matched against an index — it is RE-DERIVED from the arm's own
    parts, so a key that has been edited to point somewhere else does not resolve.
    """
    for arm in bundle["arms"]:
        if arm["arm_key"] != str(arm_key):
            continue
        rederived = temporal_arm_key(arm["program_id"], arm["desired_change"],
                                     arm["from_condition"], arm["to_condition"])
        if rederived != arm["arm_key"]:
            raise RequestRefused(
                f"arm key {arm['arm_key']!r} does not re-derive from its own parts "
                f"({rederived!r}); it has been relabelled, and the values under it belong "
                "to a different arm")
        return arm
    raise RequestRefused(f"no arm {arm_key!r} in bundle {bundle['bundle_key']!r}")


def binding_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    """WHAT a future bundle-scoped request must bind in order to name this bundle.

    These are the fields W18's request object should carry so that the artifact it points
    at is the artifact that was verified: the ordered pair it is scoped to, the content
    address, and the method that produced it. A request that bound only the ordered pair
    would still resolve after the bundle was rebuilt by a different method.
    """
    return {
        "adapter_id": ADAPTER_ID,
        "request_schema_owner": REQUEST_SCHEMA_OWNER,
        "request_schema_defined_here": REQUEST_SCHEMA_DEFINED_HERE,
        "schema_version": bundle["schema_version"],
        "bundle_key": bundle["bundle_key"],
        "bundle_id": bundle["bundle_id"],
        "from_condition": bundle["from_condition"],
        "to_condition": bundle["to_condition"],
        "n_arms": bundle["n_arms"],
        "arm_keys": list(bundle["arm_keys"]),
        "programs": list(bundle["program_admission"]["programs"]),
        "registry_scorer_view_sha256":
            bundle["program_admission"]["registry_scorer_view_sha256"],
        "method": dict(bundle["method"]),
        "required_request_fields": list(REQUIRED_REQUEST_FIELDS),
        "optional_request_fields": list(OPTIONAL_REQUEST_FIELDS),
    }


def reverse_bundle_key(bundle: dict[str, Any]) -> str:
    """The key of the OPPOSITE-direction bundle. A different artifact, not a view of this one."""
    return arm_bundle.bundle_key(bundle["to_condition"], bundle["from_condition"])


def selected_arm_keys(bundle: dict[str, Any], program_id: str,
                      pole: str) -> dict[str, Optional[str]]:
    """The two arm keys the SAME (program, pole) resolves to in the two ROLES.

    This is the mapping the UI performs at join time, made explicit so it can be tested:
    the same pole is an ``away_from_A`` arm and a ``toward_B`` arm that are OPPOSITE
    perturbations — and both of them are already cached, in this same bundle.
    """
    frm, to = bundle["from_condition"], bundle["to_condition"]
    return {
        role: temporal_arm_key(program_id, desired_change(role, pole), frm, to)
        for role in ("away_from_A", "toward_B")
    }
