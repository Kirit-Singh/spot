"""The v2 schema could not validate a single honest edge, and nobody could hit it.

`$defs/edge` REQUIRED two columns — `stage2_independent_verifier_id` and
`stage2_independent_verdict` — that Stage-2's loader has never emitted, declared NONE of the
`aggregate_*` columns the producer actually writes, and set `additionalProperties: false`.

So the schema demanded fields nothing produces and forbade the fields everything produces. Every
honest v2 bundle would have failed validation. It survived because no v2 bundle had ever been
built from native Stage-2 bytes — the defect was unreachable, so no test reached it.

Worse, the verifier id carried `"pattern": "independent"`. The real Stage-2 verifier is
`spot.stage02.run_manifest.verifier.v1` — no such substring. That rule therefore REFUSED every
genuine release, while ADMITTING any forgery that merely renamed itself "…independent…".

A name is not a binding. Independence is the STRUCTURED field `generator_is_not_verifier`,
checked by the loader against the report's own bytes. The schema's job is to require that an edge
NAMES who admitted it — not to infer independence from spelling.
"""
from __future__ import annotations

import json
import os

import pytest

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "schemas",
                      "spot.stage03_drug_annotation.v2.json")

RETIRED = ("stage2_independent_verifier_id", "stage2_independent_verdict")
# What Stage-2's native report actually carries. Its id contains no "independent".
REAL_VERIFIER_ID = "spot.stage02.run_manifest.verifier.v1"


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def edge(schema):
    return schema["$defs"]["edge"]


def test_no_schema_infers_independence_from_a_NAME(schema):
    """The rule that refused every honest report and admitted any forgery that renamed itself."""
    raw = json.dumps(schema)
    assert '"pattern": "independent"' not in raw, (
        "a verifier-id pattern is back. The real verifier id "
        f"({REAL_VERIFIER_ID!r}) contains no such substring, so this rule refuses every "
        "genuine release — and admits anything that calls itself independent.")


def test_the_edge_requires_the_columns_the_producer_ACTUALLY_emits(edge):
    required = set(edge["required"])
    assert {"aggregate_verifier_id", "aggregate_verdict"} <= required
    assert not (required & set(RETIRED)), (
        f"the edge requires {sorted(required & set(RETIRED))} — columns Stage-2's loader has "
        "never emitted. A schema that requires what nothing produces cannot admit an honest "
        "bundle.")


def test_the_retired_columns_are_gone_from_the_properties_too(edge):
    for name in RETIRED:
        assert name not in edge["properties"]


def test_the_real_verifier_id_VALIDATES(edge):
    """The exact string Stage-2 emits must satisfy the schema. Under the old pattern it did not —
    which is the whole defect, stated as one assertion."""
    spec = edge["properties"]["aggregate_verifier_id"]
    assert spec.get("type") == "string"
    assert "pattern" not in spec, "independence is a structured field, not a spelling"
    assert len(REAL_VERIFIER_ID) >= spec.get("minLength", 1)


def test_the_verdict_is_pinned_to_admit(edge):
    assert edge["properties"]["aggregate_verdict"] == {"const": "admit"}


def test_the_edge_still_closes_additional_properties(edge):
    """The fix must not be 'allow anything'. Closing the schema is what makes an unknown column a
    refusal rather than silently-carried noise — it just has to close over the RIGHT columns."""
    assert edge.get("additionalProperties") is False


def test_the_REAL_verifier_id_validates_against_its_own_subschema(schema, edge):
    """The assertion that IS the defect: the exact id Stage-2 emits must satisfy the column.

    Under `pattern: "independent"` this failed — `spot.stage02.run_manifest.verifier.v1` has no
    such substring — so every honest release was refused. A whole-row validation is not used
    here: the edge carries if/then conditionals, and a synthetic row satisfying them would be my
    guess about the science rather than the producer's output. Whole-row validation belongs to
    the producer's own emission tests, over a bundle built from native bytes.
    """
    jsonschema = pytest.importorskip("jsonschema")
    spec = {**edge["properties"]["aggregate_verifier_id"], "$defs": schema["$defs"]}
    jsonschema.validate(REAL_VERIFIER_ID, spec)          # used to raise. It must not.

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate("", spec)                    # an unnamed admitter is still refused


def test_every_required_edge_column_is_satisfiable(schema, edge):
    """Every REQUIRED column must be constructible from its own subschema. A required column with
    no satisfiable value can never be emitted — which is exactly what the two retired columns
    were: required, and produced by nothing."""
    defs = schema["$defs"]

    def resolve(spec):
        """Follow a local $ref so an enum or const behind one is still seen."""
        seen = 0
        while "$ref" in spec and spec["$ref"].startswith("#/$defs/") and seen < 8:
            spec = defs[spec["$ref"].split("/")[-1]]
            seen += 1
        return spec

    def value_for(name, spec):
        spec = resolve(spec)
        for branch in ("anyOf", "oneOf"):          # take the first satisfiable branch
            if branch in spec:
                for sub in spec[branch]:
                    sub = resolve(sub)
                    if sub.get("type") != "null":
                        return value_for(name, sub)
        if "const" in spec:
            return spec["const"]
        if "enum" in spec:                          # enum FIRST — it may sit behind a $ref
            return spec["enum"][0]
        typ = spec.get("type")
        if isinstance(typ, list):
            typ = next((t for t in typ if t != "null"), "string")
        if typ == "string":
            if name == "aggregate_verifier_id":
                return REAL_VERIFIER_ID
            if spec.get("minLength") == 64 or spec.get("pattern", "").find("[0-9a-f]") >= 0:
                return "a" * 64
            return "x"
        if typ in ("number", "integer"):
            return 0
        if typ == "boolean":
            return False
        if typ == "array":
            items = resolve(spec.get("items") or {})
            n = spec.get("minItems", 0)
            return [value_for(name, items) for _ in range(max(n, 0))]
        if typ == "object":
            sub = spec.get("properties") or {}
            return {k: value_for(k, v) for k, v in sub.items()
                    if k in (spec.get("required") or [])}
        return None

    row = {name: value_for(name, edge["properties"][name]) for name in edge["required"]}

    assert row["aggregate_verifier_id"] == REAL_VERIFIER_ID   # the string that used to be refused
    unsatisfiable = [k for k, v in row.items() if v is None]
    assert not unsatisfiable, (
        f"required edge columns with no satisfiable value: {unsatisfiable}. A required column "
        "nothing can produce cannot appear in an honest bundle.")
