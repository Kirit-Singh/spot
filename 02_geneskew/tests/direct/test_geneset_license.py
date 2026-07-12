"""m3 — Reactome is CC0, not CC BY 4.0. The licence is ENFORCED, not annotated.

The provenance recorded Reactome as CC BY 4.0. It is not: the Reactome database data and
files derived from it are released under CC0 1.0 (https://reactome.org/license). A wrong
licence is not a typo in a footnote — it is a redistribution and attribution claim, and it
would be cited by whoever ships the artifact next.

So the correct licence is a CONTRACT the loader checks, not a string somebody remembered
to update. A bundle asserting the retired claim is refused by name.

GO stays CC BY 4.0, and must name a DATED release: "GO" is not a version, and a CC BY
attribution that cannot name what it is attributing is not an attribution.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import genesets

UNIVERSE = [f"ENSG{i:011d}" for i in range(20)]
SETS = [{"set_id": "R-HSA-1", "name": "a pathway", "genes": UNIVERSE[:5]}]


def _bundle(tmp_path, **release) -> str:
    doc = {
        "schema_version": genesets.SCHEMA_VERSION,
        "release": release,
        "gene_id_namespace": "ensembl_gene_id",
        "sets": SETS,
    }
    p = os.path.join(str(tmp_path), "bundle.json")
    with open(p, "w") as fh:
        json.dump(doc, fh)
    return p


class TestReactomeIsCC0:
    def test_the_policy_records_reactome_as_CC0(self):
        assert genesets.SOURCE_LICENSE["reactome"] == "CC0-1.0"

    def test_it_cites_the_reactome_licence_page(self):
        assert genesets.SOURCE_LICENSE_REFERENCE["reactome"] == \
            "https://reactome.org/license"

    def test_a_correctly_licensed_reactome_bundle_loads(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="CC0-1.0",
                       license_reference="https://reactome.org/license")
        bundle = genesets.load(path, UNIVERSE)
        assert bundle["gene_set_license"] == "CC0-1.0"
        assert bundle["gene_set_license_reference"] == "https://reactome.org/license"

    def test_the_V97_release_notice_is_nameable_as_the_release_id(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="CC0-1.0",
                       license_reference="https://reactome.org/license")
        assert genesets.load(path, UNIVERSE)["gene_set_release"]["release_id"] == "V97"


class TestTheRetiredClaimIsRefusedByName:
    def test_a_reactome_bundle_claiming_CC_BY_4_0_is_REFUSED(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="CC BY 4.0",
                       license_reference="https://reactome.org/license")
        with pytest.raises(genesets.GeneSetError) as e:
            genesets.load(path, UNIVERSE)
        assert "CC0" in str(e.value)
        assert "reactome.org/license" in str(e.value)

    def test_the_refusal_says_what_actually_happened(self, tmp_path):
        # A generic "mismatch" would leave the next person guessing which one is right.
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="cc-by-4.0",
                       license_reference="https://reactome.org/license")
        with pytest.raises(genesets.GeneSetError) as e:
            genesets.load(path, UNIVERSE)
        assert "not CC BY 4.0" in str(e.value)

    def test_the_spelling_of_the_wrong_licence_does_not_get_it_through(self, tmp_path):
        for spelling in ("CC BY 4.0", "cc_by_4.0", "CC-BY-4.0", " CC BY 4.0 "):
            path = _bundle(tmp_path, source="reactome", release_id="V97",
                           license=spelling,
                           license_reference="https://reactome.org/license")
            with pytest.raises(genesets.GeneSetError):
                genesets.load(path, UNIVERSE)


class TestABundleMustDeclareItsLicenceAtAll:
    def test_a_bundle_with_no_licence_is_refused(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97")
        with pytest.raises(genesets.GeneSetError) as e:
            genesets.load(path, UNIVERSE)
        assert "license is required" in str(e.value)

    def test_a_licence_nobody_can_look_up_is_refused(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="CC0-1.0")           # no reference
        with pytest.raises(genesets.GeneSetError) as e:
            genesets.load(path, UNIVERSE)
        assert "license_reference" in str(e.value)


class TestGOStaysCCBYAndMustNameADatedRelease:
    def test_the_policy_records_go_as_CC_BY_4_0(self):
        assert genesets.SOURCE_LICENSE["go_bp"] == "CC-BY-4.0"

    def test_a_dated_go_release_loads(self, tmp_path):
        path = _bundle(
            tmp_path, source="go_bp", release_id="go-basic 2026-05-01",
            license="CC BY 4.0",
            license_reference="http://geneontology.org/docs/go-citation-policy/")
        assert genesets.load(path, UNIVERSE)["gene_set_license"] == "CC-BY-4.0"

    def test_an_UNDATED_go_release_is_refused(self, tmp_path):
        path = _bundle(
            tmp_path, source="go_bp", release_id="go-basic",
            license="CC BY 4.0",
            license_reference="http://geneontology.org/docs/go-citation-policy/")
        with pytest.raises(genesets.GeneSetError) as e:
            genesets.load(path, UNIVERSE)
        assert "DATED release" in str(e.value)

    def test_a_go_bundle_claiming_CC0_is_refused(self, tmp_path):
        path = _bundle(
            tmp_path, source="go_bp", release_id="go-basic 2026-05-01",
            license="CC0-1.0",
            license_reference="http://geneontology.org/docs/go-citation-policy/")
        with pytest.raises(genesets.GeneSetError):
            genesets.load(path, UNIVERSE)


class TestTheLicenceIsBoundNotJustNoted:
    def test_it_enters_the_run_binding(self, tmp_path):
        path = _bundle(tmp_path, source="reactome", release_id="V97",
                       license="CC0-1.0",
                       license_reference="https://reactome.org/license")
        block = genesets.binding_block(genesets.load(path, UNIVERSE))
        assert block["gene_set_license"] == "CC0-1.0"
        assert block["gene_set_license_reference"] == "https://reactome.org/license"
