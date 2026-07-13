"""m2 — the selection_id IS re-derivable, and it is now CHECKED.

This module used to declare the id non-derivable ("a citation, not a key") and carried it
verbatim, unchecked. An independent audit published the recipe:

    selection_id = sha256( canonical_json( contract.canonical_content ) )[:16]

An id nobody recomputes is a label — and a label can be moved onto a different contract
without anything noticing. So it is derived and enforced, and a contract whose declared id
disagrees with its own canonical content is REFUSED.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from direct import stage1_v3 as G
from test_temporal_v3 import SCHEMA_PATH, v3_contract

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH), reason="the pinned v3 schema is not present")


def sealed(**over):
    """A contract whose selection_id is the one its own canonical_content derives."""
    doc = v3_contract(**over)
    doc["selection_id"] = G.derive_selection_id(doc)
    # resealing the full-contract hash AFTER setting the id: the id is part of the content
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    from direct.hashing import content_hash
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


class TestTheRuleIsTheOnePublished:
    def test_the_module_publishes_the_derivation_rule(self):
        assert G.SELECTION_ID_RULE_ID.startswith("spot.stage01.selection_id.")
        assert "canonical_content" in G.SELECTION_ID_RULE
        assert G.SELECTION_ID_LEN == 16

    def test_the_retired_non_derivable_claim_is_named_as_RETIRED(self):
        # A reader who meets the old id in an archived artifact must learn it was
        # withdrawn, not conclude the check never existed.
        assert G.STAGE1_SELECTION_ID_NOT_REDERIVABLE.startswith("RETIRED:")
        assert G.SELECTION_ID_RULE_ID in G.STAGE1_SELECTION_ID_NOT_REDERIVABLE

    @pytest.mark.skipif(not shutil.which("jq"), reason="jq is not installed")
    def test_the_python_derivation_is_BYTE_IDENTICAL_to_the_published_jq_recipe(
            self, tmp_path):
        """`jq -cS '.canonical_content' <file> | shasum -a 256` — the audit's recipe."""
        doc = sealed()
        path = os.path.join(str(tmp_path), "contract.json")
        with open(path, "w") as fh:
            json.dump(doc, fh, indent=2)

        piped = subprocess.run(
            f"jq -cS '.canonical_content' {path} | tr -d '\\n' | sha256sum",
            shell=True, capture_output=True, text=True, check=True)
        from_jq = piped.stdout.split()[0]

        assert G.canonical_content_sha256(doc) == from_jq
        assert G.derive_selection_id(doc) == from_jq[:16]
        assert doc["selection_id"] == from_jq[:16]


class TestAMatchingIdIsAdmitted:
    def test_a_contract_whose_id_derives_from_its_content_validates(self, schema):
        doc = sealed()
        bound = G.validate(doc, schema)
        assert bound["selection_id"] == G.derive_selection_id(doc)
        assert bound["selection_id_rederived"] == bound["selection_id"]

    def test_the_binding_publishes_the_rule_and_the_full_canonical_hash(self, schema):
        bound = G.validate(sealed(), schema)
        assert bound["selection_id_rule_id"] == G.SELECTION_ID_RULE_ID
        assert len(bound["canonical_content_sha256"]) == 64
        assert bound["canonical_content_sha256"].startswith(bound["selection_id"])


class TestAMISMATCHED_ID_IS_REFUSED:
    def test_a_declared_id_that_does_not_derive_is_REJECTED(self, schema):
        doc = sealed()
        doc["selection_id"] = "0123456789abcdef"        # a plausible-looking forgery
        from direct.hashing import content_hash
        payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
        doc["full_contract_content_sha256"] = content_hash(payload)   # honestly resealed

        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_SELECTION_ID

    def test_an_id_kept_while_the_BIOLOGY_is_swapped_is_REJECTED(self, schema):
        """THE ATTACK the check exists for: move a good id onto a different contract."""
        honest = sealed()
        forged = v3_contract(a="A_DIFFERENT_PROGRAM")
        forged["selection_id"] = honest["selection_id"]      # keep the trusted id
        from direct.hashing import content_hash
        payload = {k: v for k, v in forged.items()
                   if k != "full_contract_content_sha256"}
        forged["full_contract_content_sha256"] = content_hash(payload)

        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(forged, schema)
        assert exc.value.reason == G.REFUSE_SELECTION_ID

    def test_changing_ANY_canonical_content_field_moves_the_id(self, schema):
        base = G.derive_selection_id(sealed())
        for over in (dict(a="OTHER_A"), dict(b="OTHER_B"),
                     dict(conditions=("Rest", "Stim8hr"))):
            assert G.derive_selection_id(v3_contract(**over)) != base

    def test_the_refusal_names_the_rule_so_the_producer_can_fix_it(self, schema):
        from direct.hashing import content_hash
        doc = sealed()
        doc["selection_id"] = "f" * 16
        # resealed honestly, so the CONTENT-HASH check passes and the SELECTION_ID check
        # is the one that has to catch it
        payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
        doc["full_contract_content_sha256"] = content_hash(payload)

        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_SELECTION_ID
        assert "canonical_content" in str(exc.value)

    def test_an_UNSEALED_forgery_is_caught_by_the_content_hash_first(self, schema):
        # Defence in depth: a sloppy forger who edits the id without resealing never even
        # reaches the id check.
        doc = sealed()
        doc["selection_id"] = "f" * 16
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_CONTENT_HASH
