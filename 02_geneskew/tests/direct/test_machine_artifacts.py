"""Emitted artifacts are MACHINE artifacts, not essays.

Every JSON a run writes — and the preflight verdict, and the contributor evidence, and
the re-issued pair, and the STRING COLUMNS of every parquet — is consumed by a program:
the standalone verifier, the P2S adapter, the frontend, a Stage-3 lane. Those consumers
branch on ids, enums, booleans, counts and hashes. They cannot branch on a paragraph.

Prose in a machine artifact is worse than useless, and the failure mode is specific.
It is written once and then never re-read, so it drifts: the code changes, the sentence
does not, and now the artifact asserts something false with the full authority of a
provenance record. It is also duplicated into every run — into every ROW, in a parquet —
so a caveat that belongs in the method docs is instead restated tens of thousands of
times, none of them authoritative and none of them checked. And because it LOOKS like
documentation, a reader trusts it more than the code it contradicts.

So the rule: routine artifact values are compact. What a rule MEANS is stated ONCE, in
the module docstrings, in the method docs and in HANDOFF, and the artifact carries the
rule's ID.

TWO HOLES THIS FILE USED TO HAVE
--------------------------------
1. IT ONLY LOOKED AT SERVED JSON. The parquets — the artifacts a consumer actually
   reads row by row — were never scanned, and neither were the contributor manifest, the
   source-record table, the replay report or the re-issued pair. The rule was enforced
   exactly where prose was least likely to be added.

2. ``description`` WAS BLANKET-EXEMPT. Any key named ``description``, anywhere, at any
   depth, in any artifact, could hold a paragraph. That is not an exemption, it is an
   escape hatch with a name — and an escape hatch that exists will be used.

Prose is now allowed in exactly two places, both named explicitly:

  * ACTIONABLE REFUSALS. A human has to diagnose these, so they may say what went wrong.
    That is the ``error`` leaf and anything under a ``failures`` block.
  * THE COMPILED RULE DOCUMENT. ``canonical_source_record_id_rule.null_handling`` DEFINES
    the null semantics of the hashed record-id payload. It is not a caveat about the
    data; it is part of the specification the verifier compares field by field, and it is
    written once per TABLE, not once per row.

Gene symbols, accessions, hashes, file names and enum values are all strings, and none
of them is prose. The detector counts WORDS, so an id is one token and a sentence is not.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from direct import config, preflight, reissue
from direct.run_screen import build_screen

# Keys retired outright. Each held a paragraph that a consumer could not branch on and
# a reader could not verify; each is replaced by a rule ID plus the flag the paragraph
# was really trying to say.
RETIRED_KEYS = {
    "run_key_note", "consumer_rule", "cross_arm_rule", "family_size_note",
    "note", "detail", "research_note", "derivation", "no_pq_emitted_reason",
    # the obsolete replay-rule keys: they read as null from a v2 report, and a null
    # nobody checks is a rule that quietly stopped being bound
    "replay_rule", "completeness_rule",
    # the retired pinned-preflight gate: it authenticated nothing
    "strict_preflight_sha256",
}

# A value that is a SENTENCE. Hashes (64 hex, no spaces), ids, enums, gene symbols,
# accessions, semicolon-joined reason lists and file names all pass this comfortably;
# a caveat does not.
MAX_WORDS = 9

# Where a human genuinely has to diagnose a refusal, prose IS the point. Matched on the
# exact leaf name or an exact path segment — never as a substring, which would have let
# an allowlisted ``_note`` quietly excuse ``family_size_note`` and every other key
# ending in it.
PROSE_ALLOWED_LEAVES = {"error"}
PROSE_ALLOWED_SEGMENTS = {"failures"}

# THE ONLY narrative field in any routine artifact, allowed by EXACT PATH in EXACTLY one
# artifact class. It is the compiled record-id rule's null-handling clause: a
# specification the verifier compares field by field, not a caveat about the data.
# ``description`` is deliberately NOT allowlisted anywhere.
PROSE_ALLOWED_PATHS = {
    "source_records": {".canonical_source_record_id_rule.null_handling"},
    "reissued_records": {".canonical_source_record_id_rule.null_handling"},
}


def _segments(path):
    return [p.split("[")[0] for p in path.lstrip(".").split(".")]


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def _prose_hits(doc, artifact=""):
    allowed = PROSE_ALLOWED_PATHS.get(artifact, frozenset())
    hits = []
    for path, value in _walk(doc):
        if not isinstance(value, str):
            continue
        segs = _segments(path)
        if segs[-1] in PROSE_ALLOWED_LEAVES or PROSE_ALLOWED_SEGMENTS & set(segs):
            continue
        if path in allowed:
            continue
        if len(value.split()) > MAX_WORDS:
            hits.append((path, value))
    return hits


def _retired_hits(doc):
    return [path for path, _v in _walk(doc)
            if _segments(path)[-1] in RETIRED_KEYS]


SERVED = ("provenance.json", "verification.json", "axis.json", "gene_universe.json",
          "input_manifest.json")
PARQUETS = ("screen.parquet", "masks.parquet", "contributing_guides.parquet",
            "guide_support.parquet", "donor_support.parquet")
EVIDENCE = {
    "contributor_manifest": "contributing_guides.manifest.json",
    "source_records": "stage02_source_records.json",
    "source_replay": "stage02_source_replay.json",
    "source_registry": "source_registry.json",
}


@pytest.fixture
def run(synthetic_run):
    """One real run: its served JSON, its parquets, its evidence, its re-issued pair."""
    args = synthetic_run()
    result = build_screen(args)
    root = os.path.dirname(args.selection)

    docs = {}
    for name in SERVED:
        with open(os.path.join(result["out_dir"], name)) as fh:
            docs[name] = json.load(fh)
    docs["preflight"] = preflight.run(args)
    for key, fn in EVIDENCE.items():
        with open(os.path.join(root, fn)) as fh:
            docs[key] = json.load(fh)

    tables = {fn: pd.read_parquet(os.path.join(result["out_dir"], fn))
              for fn in PARQUETS}
    return {"args": args, "result": result, "root": root, "docs": docs,
            "tables": tables}


@pytest.fixture
def artifacts(run):
    return run["docs"]


# --------------------------------------------------------------------------- #
# 1. SERVED JSON.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", list(SERVED) + ["preflight"])
def test_no_served_artifact_carries_a_retired_editorial_key(artifacts, name):
    hits = _retired_hits(artifacts[name])
    assert not hits, f"{name} still carries retired prose key(s): {hits}"


@pytest.mark.parametrize("name", list(SERVED) + ["preflight"])
def test_no_served_artifact_carries_a_free_text_value(artifacts, name):
    hits = _prose_hits(artifacts[name], name)
    assert not hits, (
        f"{name} carries {len(hits)} free-text value(s); a machine artifact holds ids, "
        f"enums, booleans, counts and hashes. First: {hits[0]}")


# --------------------------------------------------------------------------- #
# 2. THE CONTRIBUTOR EVIDENCE. Pinned, hashed, and read by the verifier.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", sorted(EVIDENCE))
def test_no_evidence_artifact_carries_a_retired_editorial_key(artifacts, name):
    assert not _retired_hits(artifacts[name])


@pytest.mark.parametrize("name", sorted(EVIDENCE))
def test_no_evidence_artifact_carries_a_free_text_value(artifacts, name):
    hits = _prose_hits(artifacts[name], name)
    assert not hits, f"{name} carries free text: {hits[0]}"


def test_the_ONE_allowed_narrative_field_is_the_compiled_RULE_and_nothing_else(
        artifacts):
    """The allowlist is a path, not a key name — and it is load-bearing.

    ``null_handling`` defines the null semantics of the hashed record-id payload: a
    table that serialised ``target_ensembl`` or ``donor_pair`` differently would mint
    different ids while declaring an identical rule string. It is a specification, it is
    compared field by field by the verifier, and it is written once per TABLE.
    """
    table = artifacts["source_records"]
    rule = table["canonical_source_record_id_rule"]
    assert len(rule["null_handling"].split()) > MAX_WORDS      # it IS prose
    assert _prose_hits(table, "source_records") == []          # ...and it is the only one

    # the SAME string, in an artifact class that does not allowlist it, is a violation
    assert _prose_hits(table, "contributor_manifest")


# --------------------------------------------------------------------------- #
# 3. THE PARQUETS. Prose here is duplicated into every ROW.
# --------------------------------------------------------------------------- #
def _table_prose(df):
    hits = []
    for col in df.columns:
        if df[col].dtype != object:
            continue
        for value in df[col].dropna().unique():
            if isinstance(value, str) and len(value.split()) > MAX_WORDS:
                hits.append((col, value))
    return hits


@pytest.mark.parametrize("name", PARQUETS)
def test_no_emitted_table_carries_a_free_text_STRING_COLUMN(run, name):
    """The artifacts a consumer reads row by row were never scanned at all.

    Gene symbols, accessions, run ids, enum states and semicolon-joined reason lists are
    all strings and all fine — they are single tokens. A sentence is not.
    """
    hits = _table_prose(run["tables"][name])
    assert not hits, (
        f"{name} carries {len(hits)} free-text cell value(s), repeated on every row. "
        f"First: {hits[0]}")


@pytest.mark.parametrize("name", PARQUETS)
def test_no_emitted_table_carries_a_retired_editorial_COLUMN(run, name):
    cols = set(run["tables"][name].columns)
    assert not (cols & RETIRED_KEYS), f"{name} carries retired column(s)"


# --------------------------------------------------------------------------- #
# 4. THE RE-ISSUED PAIR. It is written by us, so it is held to our rule.
# --------------------------------------------------------------------------- #
@pytest.fixture
def reissued(run, tmp_path):
    out = str(tmp_path / "reissued")
    paths = reissue.reissue(
        os.path.join(run["root"], EVIDENCE["contributor_manifest"]),
        os.path.join(run["root"], EVIDENCE["source_records"]), out,
        replay_report=os.path.join(run["root"], EVIDENCE["source_replay"]),
        old_registry=os.path.join(run["root"], EVIDENCE["source_registry"]))
    docs = {}
    for key, cls in (("records", "reissued_records"), ("manifest", "reissued_manifest"),
                     ("registry", "reissued_registry")):
        with open(paths[key]) as fh:
            docs[cls] = json.load(fh)
    return docs


@pytest.mark.parametrize("cls", ["reissued_records", "reissued_manifest",
                                 "reissued_registry"])
def test_the_reissued_pair_is_a_machine_artifact_too(reissued, cls):
    assert not _retired_hits(reissued[cls])
    hits = _prose_hits(reissued[cls], cls)
    assert not hits, f"{cls} carries free text: {hits[0]}"


# --------------------------------------------------------------------------- #
# 5. THE DETECTOR MUST ACTUALLY CATCH THINGS — in EVERY artifact class.
#
# A guard that cannot fail is not a guard, and the old one could not fail on four of the
# five classes because it never looked at them.
# --------------------------------------------------------------------------- #
SENTENCE = ("reported for transparency only; NOT a multiplicity family and not a "
            "confirmatory endpoint, see the method docs for the full caveat")


def test_an_injected_sentence_in_SERVED_JSON_is_caught(artifacts):
    doc = dict(artifacts["verification.json"])
    doc["family_size_note"] = SENTENCE
    assert _retired_hits(doc) == [".family_size_note"]
    assert _prose_hits(doc, "verification.json")


@pytest.mark.parametrize("name", sorted(EVIDENCE))
def test_an_injected_sentence_in_EVIDENCE_JSON_is_caught(artifacts, name):
    doc = dict(artifacts[name])
    doc["provenance_note"] = SENTENCE
    assert _prose_hits(doc, name)


@pytest.mark.parametrize("name", sorted(EVIDENCE))
def test_a_RETIRED_verbose_key_in_EVIDENCE_JSON_is_caught(artifacts, name):
    doc = dict(artifacts[name])
    doc["derivation"] = "how these rows were produced"
    assert _retired_hits(doc) == [".derivation"]


@pytest.mark.parametrize("name", PARQUETS)
def test_an_injected_sentence_in_A_PARQUET_is_caught(run, name):
    df = run["tables"][name].copy()
    df["caveat"] = SENTENCE
    hits = _table_prose(df)
    assert hits and hits[0][0] == "caveat"


@pytest.mark.parametrize("name", PARQUETS)
def test_a_RETIRED_verbose_COLUMN_in_a_PARQUET_is_caught(run, name):
    df = run["tables"][name].copy()
    df["note"] = "x"
    assert set(df.columns) & RETIRED_KEYS == {"note"}


@pytest.mark.parametrize("cls", ["reissued_records", "reissued_manifest",
                                 "reissued_registry"])
def test_an_injected_sentence_in_the_REISSUED_pair_is_caught(reissued, cls):
    doc = dict(reissued[cls])
    doc["reissue_note"] = SENTENCE
    assert _prose_hits(doc, cls)


def test_the_blanket_description_EXEMPTION_is_gone(artifacts):
    """It excused any key named `description`, anywhere, in any artifact.

    Nothing in a routine artifact ever needed it — which is exactly why it was so cheap
    to leave in place, and exactly why the next person to want a paragraph would have
    found it waiting.
    """
    assert "description" not in PROSE_ALLOWED_LEAVES
    for name in ("provenance.json", "verification.json", "contributor_manifest",
                 "source_records", "source_replay"):
        doc = dict(artifacts[name])
        doc["description"] = SENTENCE
        assert _prose_hits(doc, name), (
            f"a `description` paragraph is still excused in {name}")


# --------------------------------------------------------------------------- #
# 6. Retiring a caveat may not delete the CONTRACT it was carrying.
# --------------------------------------------------------------------------- #
def test_the_retired_prose_is_replaced_by_a_RULE_ID_a_consumer_can_resolve(artifacts):
    contract = artifacts["provenance.json"]["stage2_direct_contract"]
    assert contract["run_key_rule_id"] == config.RUN_KEY_RULE_ID
    assert contract["question_id_is_a_run_key"] is False
    assert contract["screen"]["consumer_rule_id"] == config.CONSUMER_RULE_ID
    assert contract["screen"]["consumer_must_choose_an_arm"] is True
    assert contract["screen"]["cross_arm_rule_id"] == config.CROSS_ARM_RULE_ID
    assert contract["screen"]["cross_arm_fields_rank_or_gate"] is False
    assert contract["modulation_vocabulary"]["conflicts_resolved_into_a_winner"] is False
    assert contract["arm_state_vocabulary"]["rule_id"] == config.ARM_STATE_RULE_ID

    v = artifacts["verification.json"]
    assert v["family_size_rule_id"] == config.FAMILY_SIZE_RULE_ID
    assert v["family_size_is_a_multiplicity_family"] is False
    assert v["cross_arm"]["conflicts_preserved"] is True

    prov = artifacts["provenance.json"]
    assert prov["no_pq_reason"] == config.NO_PQ_REASON
    assert prov["generator_verifies_itself"] is False
    assert prov["donor_contract"]["pairs_are_independent_replicates"] is False
    assert (prov["selection_contract"]["id_consistency_check"]["rule_id"]
            == config.ID_RECOMPUTE_RULE_ID)


def test_an_absent_manifest_preflight_block_is_a_STATE_not_a_paragraph(synthetic_run):
    """The one that mattered most: 'no evidence' must be machine-readable."""
    report = preflight.run(synthetic_run(manifest=False))
    block = report["contributor_manifest"]
    assert block["status"] == "absent"
    assert block["guide_identity_available"] is False
    assert block["eligible_targets_possible"] is False
    assert "detail" not in block
    # ...and the actionable diagnosis still exists, exactly where a human looks for it
    assert report["verdict"] == preflight.NO_GO
    assert report["failures"][0]["check"] == "contributor_manifest_resolves"
    assert len(report["failures"][0]["error"].split()) > MAX_WORDS


# --------------------------------------------------------------------------- #
# 7. The PUBLISHED contract fixture is a machine artifact too.
# --------------------------------------------------------------------------- #
CANONICAL_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "fixtures", "canonical_two_arm_run.json")


@pytest.fixture
def canonical():
    with open(CANONICAL_FIXTURE) as fh:
        return json.load(fh)


def test_the_canonical_fixture_carries_no_prose_note(canonical):
    assert "_note" not in canonical
    assert not _retired_hits(canonical)
    assert not _prose_hits(canonical, "canonical"), _prose_hits(canonical,
                                                                "canonical")[:2]


def test_the_canonical_fixture_states_its_contract_as_machine_metadata(canonical):
    """Retiring the note may not lose what the note was actually asserting."""
    c = canonical["_contract"]
    assert c["combined_objective_permitted"] is False
    assert c["headline_arm_permitted"] is False
    assert c["support_available_in_this_pass"] is False
    assert c["support_status"] == "unavailable_no_contributor_evidence_in_this_release_pass"
    assert c["max_evidence_tier"] == "tier3_screen_only"
    assert c["target_ensembl_nullable"] is True
    assert c["released_estimate_id_is_parsed"] is False


def test_the_canonical_fixture_agrees_with_what_the_lane_emits(canonical, artifacts):
    """A contract that has drifted from the code is worse than no contract."""
    c = canonical["_contract"]
    assert c["arms"] == list(config.ARMS)
    assert c["arm_rank_columns"] == list(config.ARM_RANK_COLUMN.values())
    assert c["rank_dtype"] == config.RANK_DTYPE
    assert (c["support_available_in_this_pass"]
            == config.SUPPORT_AVAILABLE_IN_THIS_PASS)
    assert (c["evidence_domain"]
            == artifacts["provenance.json"]["evidence_domain"]["domain_id"])
    # the row a consumer codes against really does carry the unavailable status
    assert (canonical["screen"]["row_example"]["A_support_status"]
            == c["support_status"])
    assert (canonical["screen"]["row_example"]["B_support_status"]
            == c["support_status"])
