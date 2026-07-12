"""Target identity: the release key is a KEY, not a gene.

Verified against the complete public release (33,983 rows): exactly 12 dispositions
carry a non-Ensembl ``obs.target_contrast`` — 4 symbols x 3 conditions. Nine of them
carry an ENSG-looking ``obs.index`` prefix that belongs to a DIFFERENT gene than the
symbol being targeted; OCLM's key is symbol-prefixed. All 12 are
``ontarget_significant=false`` and ``low_target_gex=true`` and must still be emitted.
"""
import os

import pandas as pd
import pytest

from direct import guides, identity
from direct.run_screen import build_screen

from fixtures_spec import RELEASE_CONDITIONS, SYMBOL_TARGETS

# The exact, verified membership of the symbol-namespace disposition set.
EXPECTED_SYMBOLS = {"MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM"}
EXPECTED_SCOPES = {(s, c) for s in EXPECTED_SYMBOLS for c in RELEASE_CONDITIONS}
EXPECTED_N = 12
RELEASE_TOTAL_ROWS = 33983

# ENSG-looking release keys that belong to a DIFFERENT gene than the target symbol.
DECOY_KEYS = {
    "MTRNR2L1": "ENSG00000256618",
    "MTRNR2L4": "ENSG00000232196",
    "MTRNR2L8": "ENSG00000255823",
    "OCLM": None,                    # symbol-prefixed key
}

from release_gate import DE_STATS as _RELEASE, needs

# OPT-IN ONLY. The presence of a 16 GB DE object on this host is not permission to
# read it: the ordinary synthetic suite must cost the same everywhere. See
# release_gate.py.
needs_release = needs(_RELEASE)


# --------------------------------------------------------------------------- #
# The identity rule itself.
# --------------------------------------------------------------------------- #
def test_an_ensg_looking_release_key_never_becomes_the_target_ensembl():
    """The exact trap: the key says ENSG00000232196, the target is MTRNR2L4."""
    ident = identity.resolve("ENSG00000232196_Rest", "MTRNR2L4", "MTRNR2L4")
    assert ident.released_estimate_id == "ENSG00000232196_Rest"   # verbatim
    assert ident.target_id == "MTRNR2L4"
    assert ident.target_id_namespace == identity.GENE_SYMBOL
    assert ident.target_ensembl is None                            # NOT the prefix
    assert ident.ensembl_resolved is False


def test_a_symbol_prefixed_release_key_is_also_a_symbol_scope():
    ident = identity.resolve("OCLM_Stim8hr", "OCLM", "OCLM")
    assert ident.released_estimate_id == "OCLM_Stim8hr"
    assert (ident.target_id, ident.target_id_namespace) == ("OCLM", "gene_symbol")
    assert ident.target_ensembl is None


def test_an_ordinary_ensembl_target_is_unchanged():
    ident = identity.resolve("ENSG00000141510_Rest", "ENSG00000141510", "TP53")
    assert ident.target_id == "ENSG00000141510"
    assert ident.target_id_namespace == identity.ENSEMBL_GENE_ID
    assert ident.target_ensembl == "ENSG00000141510"               # named source field
    assert ident.target_symbol == "TP53"


def test_only_an_explicit_map_can_give_a_symbol_an_ensembl_id():
    without = identity.resolve("OCLM_Rest", "OCLM", "OCLM")
    assert without.target_ensembl is None

    with_map = identity.resolve("OCLM_Rest", "OCLM", "OCLM",
                                {"OCLM": "ENSG00000262180"})
    assert with_map.target_ensembl == "ENSG00000262180"
    assert with_map.ensembl_source == "explicit_target_identity_map"
    # the namespace still describes what target_id IS
    assert with_map.target_id_namespace == identity.GENE_SYMBOL


def test_a_map_may_not_supply_a_non_ensembl_value(tmp_path):
    import json
    p = tmp_path / "map.json"
    p.write_text(json.dumps({"schema_version": identity.IDENTITY_MAP_SCHEMA,
                             "map": {"OCLM": "OCLM"}}))
    with pytest.raises(identity.IdentityError, match="not an Ensembl gene id"):
        identity.load_identity_map(str(p))


# --------------------------------------------------------------------------- #
# MUTATION: the forbidden shortcuts must be absent from the code itself.
# --------------------------------------------------------------------------- #
def test_no_module_derives_an_identity_by_splitting_the_release_key():
    """Namespace coercion / inferred Ensembl ids would need to parse the key."""
    import ast
    here = os.path.dirname(os.path.abspath(identity.__file__))
    for mod in ("identity.py", "run_screen.py", "guides.py", "masks.py",
                "verify_rules.py", "verify_tables.py", "verify_run.py"):
        src = open(os.path.join(here, mod)).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("split", "rsplit", "partition",
                                           "removesuffix", "removeprefix"):
                target = getattr(node.func.value, "id", "") or \
                    getattr(getattr(node.func.value, "attr", None), "__str__",
                            lambda: "")()
                assert "released_estimate_id" not in str(target), (
                    f"{mod} splits the release key")
        assert "released_estimate_id.split" not in src
        assert 'released_estimate_id"].split' not in src


def test_the_ensembl_rule_is_exact():
    for bad in ("ENSG", "ENSG00000232196_Rest", "ensg00000232196", "MTRNR2L4",
                "ENSG00000232196X", " ENSG00000232196"):
        assert identity.is_ensembl_gene_id(bad) is False
    assert identity.is_ensembl_gene_id("ENSG00000232196") is True


# --------------------------------------------------------------------------- #
# The FULL public universe: exactly 12 symbol-namespace dispositions.
# --------------------------------------------------------------------------- #
@needs_release
def test_the_full_release_universe_has_exactly_twelve_symbol_scopes():
    import h5py
    import numpy as np

    with h5py.File(_RELEASE, "r") as f:
        obs = f["obs"]

        def col(n):
            g = obs[n]
            if isinstance(g, h5py.Group):
                cats = np.array([x.decode() if isinstance(x, bytes) else str(x)
                                 for x in g["categories"][:]], dtype=object)
                codes = g["codes"][:]
                out = np.empty(codes.shape, dtype=object)
                out[codes >= 0] = cats[codes[codes >= 0]]
                return out
            return g[:]

        idx = np.array([x.decode() if isinstance(x, bytes) else str(x)
                        for x in obs[obs.attrs.get("_index", "index")][:]],
                       dtype=object)
        tc, gn, cond = col("target_contrast"), col("target_contrast_gene_name"), \
            col("culture_condition")
        ots, low = col("ontarget_significant"), col("low_target_gex")

    assert len(idx) == RELEASE_TOTAL_ROWS          # lossless disposition universe

    symbol_rows = []
    for i in range(len(idx)):
        ident = identity.resolve(idx[i], tc[i], gn[i])
        if ident.target_id_namespace == identity.GENE_SYMBOL:
            symbol_rows.append((ident, str(cond[i]), bool(ots[i]), bool(low[i])))

    # EXACTLY 12, and exactly the expected membership
    assert len(symbol_rows) == EXPECTED_N
    assert {(i.target_id, c) for i, c, _o, _l in symbol_rows} == EXPECTED_SCOPES

    for ident, condition, ontarget_sig, low_gex in symbol_rows:
        # target_ensembl is NULL for every one of them
        assert ident.target_ensembl is None, ident.target_id
        # the release key is preserved verbatim, prefix and all
        prefix = DECOY_KEYS[ident.target_id] or ident.target_id
        assert ident.released_estimate_id == f"{prefix}_{condition}"
        # and they are all non-significant / low-expression -- still emitted
        assert ontarget_sig is False and low_gex is True

    # the nine ENSG-prefixed keys are the parse trap; OCLM's three are not
    ensg_prefixed = [i for i, _c, _o, _l in symbol_rows
                     if i.released_estimate_id.startswith("ENSG")]
    assert len(ensg_prefixed) == 9
    for ident in ensg_prefixed:
        # the prefix is a REAL Ensembl accession -- of a different gene
        assert identity.is_ensembl_gene_id(
            ident.released_estimate_id.rsplit("_", 1)[0])
        assert ident.target_ensembl is None       # ...and it is still not adopted


@needs_release
def test_every_ordinary_ensembl_row_still_resolves():
    import h5py
    import numpy as np

    with h5py.File(_RELEASE, "r") as f:
        obs = f["obs"]
        g = obs["target_contrast"]
        cats = np.array([x.decode() if isinstance(x, bytes) else str(x)
                         for x in g["categories"][:]], dtype=object)
        codes = g["codes"][:]
        tc = np.empty(codes.shape, dtype=object)
        tc[codes >= 0] = cats[codes[codes >= 0]]
        idx = np.array([x.decode() if isinstance(x, bytes) else str(x)
                        for x in obs[obs.attrs.get("_index", "index")][:]],
                       dtype=object)

    n_ensg = 0
    for i in range(len(idx)):
        ident = identity.resolve(idx[i], tc[i], None)
        if ident.target_id_namespace == identity.ENSEMBL_GENE_ID:
            assert ident.target_ensembl == ident.target_id
            n_ensg += 1
    assert n_ensg == RELEASE_TOTAL_ROWS - EXPECTED_N


# --------------------------------------------------------------------------- #
# End to end: symbol scopes are emitted, non-evaluable, unranked.
# --------------------------------------------------------------------------- #
@pytest.fixture
def screen(synthetic_run):
    result = build_screen(synthetic_run())
    df = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    return result, df.set_index("target_id")


def test_symbol_scopes_are_emitted_and_never_ranked(screen):
    _, df = screen
    for sym in EXPECTED_SYMBOLS:
        assert sym in df.index, f"{sym} was DROPPED from the disposition table"
        row = df.loc[sym]
        assert row["target_id_namespace"] == "gene_symbol"
        assert pd.isna(row["target_ensembl"])                    # nullable, null
        assert row["base_qc_state"] == "unresolved_target_identity"
        assert bool(row["base_qc_passed"]) is False
        assert "unresolved_target_identity" in row["base_qc_reasons"]
        for pole, rank in (("A", "rank_away_from_A"), ("B", "rank_toward_B")):
            assert bool(row[f"{pole}_evaluable"]) is False
            assert pd.isna(row[rank])
        assert row["mask_unresolved_reason"] == guides.UNRESOLVED_TARGET_IDENTITY


def test_the_exact_release_key_is_preserved_for_every_symbol_scope(screen):
    _, df = screen
    for sym, decoy in DECOY_KEYS.items():
        expected = f"{decoy or sym}_StimX"          # the fixture's one condition
        assert df.loc[sym, "released_estimate_id"] == expected


def test_the_oclm_low_expression_non_significant_row_is_still_emitted(screen):
    """OCLM is ontarget_significant=false + low_target_gex=true. It stays."""
    _, df = screen
    assert "OCLM" in df.index
    row = df.loc["OCLM"]
    assert bool(row["qc_ontarget_significant"]) is False
    assert bool(row["qc_low_target_expression"]) is True
    # ...and the low-expression/non-significant flags are NOT why it is unranked
    assert row["base_qc_state"] == "unresolved_target_identity"
    assert "low_target_expression" in row["base_qc_reasons"]
    assert "no_detectable_source_on_target_repression" in row["base_qc_reasons"]


def test_symbol_scopes_never_mask_a_gene(screen):
    result, _ = screen
    masks = pd.read_parquet(os.path.join(result["out_dir"], "masks.parquet"))
    for sym in EXPECTED_SYMBOLS:
        rows = masks[masks["target_id"] == sym]
        assert len(rows) > 0                             # the estimate IS disposed
        assert rows["masked_gene_ensembl"].isna().all()  # ...but masks no gene
        decoy = DECOY_KEYS[sym]
        if decoy:
            assert decoy not in set(masks["masked_gene_ensembl"].dropna())


def test_ordinary_ensembl_targets_are_unchanged(screen):
    _, df = screen
    ensg = df[df["target_id_namespace"] == "ensembl_gene_id"]
    assert len(ensg) == 14
    assert (ensg["target_ensembl"] == ensg.index).all()   # id == the target itself
    assert ensg["rank_away_from_A"].notna().any()         # still ranked normally


def test_the_disposition_table_is_lossless(screen):
    """Non-significant / low-expression rows are never dropped."""
    result, df = screen
    assert len(df) == 18                                  # 14 ENSG + 4 symbol
    assert result["verification"]["complete_disposition"] is True
    assert df.index.is_unique


# --------------------------------------------------------------------------- #
# MUTATION: the independent verifier must catch every identity forgery.
# --------------------------------------------------------------------------- #
def _verify(result, args) -> int:
    import contextlib
    import io as _io
    from direct.verify_run import main as verify_main
    with contextlib.redirect_stdout(_io.StringIO()):
        return verify_main(["--run-dir", result["out_dir"],
                            "--inputs-root", os.path.dirname(args.selection)])


@pytest.fixture
def bundle(synthetic_run):
    args = synthetic_run()
    return build_screen(args), args


def test_the_verifier_passes_the_honest_bundle(bundle):
    result, args = bundle
    assert _verify(result, args) == 0


def test_mutation_namespace_coercion_is_caught(bundle):
    """Relabel a gene_symbol scope as ensembl_gene_id."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df.loc[df["target_id"] == "MTRNR2L4", "target_id_namespace"] = "ensembl_gene_id"
    df.to_parquet(p, index=False)
    assert _verify(result, args) == 1


def test_mutation_inferred_ensembl_id_from_the_release_key_is_caught(bundle):
    """Promote the ENSG-looking release-key prefix into target_ensembl."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df.loc[df["target_id"] == "MTRNR2L4", "target_ensembl"] = "ENSG00000232196"
    df.to_parquet(p, index=False)
    assert _verify(result, args) == 1


def test_mutation_dropping_a_symbol_row_is_caught(bundle):
    """OCLM is non-significant and low-expression. Dropping it must be caught."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df = df[df["target_id"] != "OCLM"]
    df.to_parquet(p, index=False)
    assert _verify(result, args) == 1


def test_mutation_forging_evaluability_on_a_symbol_row_is_caught(bundle):
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    m = df["target_id"] == "MTRNR2L8"
    df.loc[m, "A_evaluable"] = True
    df.loc[m, "base_qc_state"] = "qc_pass_two_guide"
    df.to_parquet(p, index=False)
    assert _verify(result, args) == 1


def test_mutation_tampering_with_the_release_key_is_caught(bundle):
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df.loc[df["target_id"] == "OCLM", "released_estimate_id"] = "ENSG00000262180_StimX"
    df.to_parquet(p, index=False)
    assert _verify(result, args) == 1
