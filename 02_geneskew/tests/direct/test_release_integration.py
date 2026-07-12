"""REAL-RELEASE integration tests. OPT-IN ONLY — never part of the synthetic suite.

    SPOT_STAGE2_RELEASE_TESTS=1 pytest tests/direct/test_release_integration.py

These read the pinned Marson artifacts (a ~44 GB pseudobulk H5AD, a ~16 GB DE object).
They are the only thing that proves the replay and identity rules hold against the
artifact the adapter actually ships against, rather than only against a fixture that
was built to satisfy them — so the coverage is kept. But they belong on tcefold, where
the cores, the RAM and the data are; on a code host they are a data job wearing a
test's clothes, and ``release_gate`` refuses to start one by accident.

Metadata only: obs columns, never a dense effect layer. Even so, do not run this on a
code/fixture host.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from direct import replay
from direct.record_id import RULE_METADATA, RULE_METADATA_KEY, derive_record_id
from direct.sources import SCHEMA_VERSION as RECORDS_SCHEMA

from release_gate import PSEUDOBULK, needs
from fixtures_spec import SYMBOL_TARGETS

pytestmark = [pytest.mark.filterwarnings("ignore"), needs(PSEUDOBULK)]

IDENTITY_METHOD = "released_per_guide_identity_column"
N_RELEASE_OBS_ROWS = 278684          # the pinned release


def _read_obs():
    """The release's own evidence columns. obs only — no dense matrix is touched."""
    import h5py
    import numpy as np

    with h5py.File(PSEUDOBULK, "r") as fh:
        obs = fh["obs"]

        def cat(name):
            grp = obs[name]
            cats = np.array([x.decode() if isinstance(x, bytes) else str(x)
                             for x in grp["categories"][:]], dtype=object)
            codes = grp["codes"][:]
            out = np.empty(codes.shape, dtype=object)
            out[codes >= 0] = cats[codes[codes >= 0]]
            return out

        names = np.array([x.decode() if isinstance(x, bytes) else str(x)
                          for x in obs[obs.attrs.get("_index", "index")][:]],
                         dtype=object)
        return {"guide_id": cat("guide_id"), "target": cat("perturbed_gene_id"),
                "condition": cat("culture_condition"),
                "guide_type": cat("guide_type"),
                "keep": obs["keep_for_DE"][:], "row_names": names}


def _bundle(tmp_path, scopes):
    """A manifest + v2 record table over a FEW REAL released scopes.

    Each record carries the COMPLETE offset proof for its (target, condition, guide):
    every kept raw row, in order, with the names the source gives them. Completeness is
    therefore a real question about the real source, not a fixture convenience.
    """
    from direct.hashing import file_sha256

    cols = _read_obs()
    source_sha = file_sha256(PSEUDOBULK)
    source_id = os.path.basename(PSEUDOBULK)

    kept_by_contrib: dict[tuple, list[int]] = {}
    guides_by_scope: dict[tuple, set] = {}
    for i in range(len(cols["target"])):
        if not bool(cols["keep"][i]):
            continue
        scope = (str(cols["target"][i]), str(cols["condition"][i]))
        if scope not in scopes:
            continue
        g = str(cols["guide_id"][i])
        kept_by_contrib.setdefault(scope + (g,), []).append(i)
        guides_by_scope.setdefault(scope, set()).add(g)

    rows, records = [], []
    for scope in sorted(scopes):
        target, condition = scope
        is_ensg = target.startswith("ENSG")
        ident = {
            "released_estimate_id": f"{target}_{condition}",
            "target_id": target,
            "target_id_namespace": "ensembl_gene_id" if is_ensg else "gene_symbol",
            "target_symbol": target,
            "target_ensembl": target if is_ensg else None,
        }
        for g in sorted(guides_by_scope.get(scope, ())):
            offsets = kept_by_contrib[scope + (g,)]
            rec = dict(ident, estimate_type="main", estimate_id="main",
                       condition=condition, donor_pair=None, guide_id=g,
                       identity_method=IDENTITY_METHOD, source_id=source_id,
                       source_sha256=source_sha,
                       pseudobulk_source_offsets=list(offsets),
                       pseudobulk_source_rows=[str(cols["row_names"][i])
                                               for i in offsets],
                       source_row_index=offsets[0])
            rec["source_record_id"] = derive_record_id(rec)
            records.append(rec)
            rows.append(dict(ident, estimate_type="main", estimate_id="main",
                             condition=condition, donor_pair=None, guide_id=g,
                             evidence_state="determined", included=True,
                             identity_method=IDENTITY_METHOD, source_id=source_id,
                             source_sha256=source_sha,
                             source_record_id=rec["source_record_id"]))

    table = os.path.join(str(tmp_path), "records.json")
    with open(table, "w") as fh:
        json.dump({"schema_version": RECORDS_SCHEMA,
                   RULE_METADATA_KEY: dict(RULE_METADATA), "records": records}, fh)
    manifest = os.path.join(str(tmp_path), "manifest.json")
    with open(manifest, "w") as fh:
        json.dump({"rows": rows}, fh)
    return table, manifest, records, source_sha, source_id


def _pick_scopes(cols, n_ensg=6):
    """The four SYMBOL scopes (the namespace trap) plus a few ordinary Ensembl ones."""
    symbol, ensg = set(), []
    for i in range(len(cols["target"])):
        if not bool(cols["keep"][i]):
            continue
        t, c = str(cols["target"][i]), str(cols["condition"][i])
        if t in SYMBOL_TARGETS:
            symbol.add((t, c))
        elif t.startswith("ENSG") and (t, c) not in ensg and len(ensg) < n_ensg:
            ensg.append((t, c))
    assert symbol, "the release must carry the symbol-target evidence rows"
    return symbol | set(ensg)


def test_records_built_from_the_real_release_replay_and_are_COMPLETE(tmp_path):
    """Source-native replay + completeness, against the REAL pinned source.

    The records are built FROM the release's own obs rows and carry the whole kept
    contributor set for each scope, so replaying them must succeed AND be complete.
    """
    cols = _read_obs()
    scopes = _pick_scopes(cols)
    table, manifest, records, source_sha, source_id = _bundle(tmp_path, scopes)

    report = replay.build_report(table_path=table, manifest_path=manifest,
                                 source_path=PSEUDOBULK, source_id=source_id)
    assert report["verdict"] == replay.REPLAYED, report["failures"]
    assert report["n_failed"] == 0
    assert report["n_replayed"] == report["n_records"] == len(records)
    assert report["completeness_verdict"] == replay.COMPLETE, \
        report["completeness_failures"]
    assert report["n_scopes_incomplete"] == 0
    assert report["n_records_offset_proven"] == len(records)
    assert report["n_nontargeting_guides_cited"] == 0
    assert report["n_source_rows"] == N_RELEASE_OBS_ROWS
    assert report["source_sha256"] == source_sha

    # every symbol record kept a NULL target_ensembl through the replay: the
    # ENSG-looking release key of a DIFFERENT gene was never promoted
    symbol_records = [r for r in records if r["target_id_namespace"] == "gene_symbol"]
    assert {r["target_id"] for r in symbol_records} == set(SYMBOL_TARGETS)
    assert all(r["target_ensembl"] is None for r in symbol_records)


def test_the_real_source_refuses_a_dropped_contributor(tmp_path):
    """Delete ONE guide's record from a real scope. Every remaining record still
    replays; the scope no longer names the whole contributor set the source kept."""
    cols = _read_obs()
    scopes = _pick_scopes(cols)
    table, manifest, records, _sha, source_id = _bundle(tmp_path, scopes)

    doc = json.load(open(table))
    victim = doc["records"][0]
    doc["records"] = [r for r in doc["records"]
                      if r["source_record_id"] != victim["source_record_id"]]
    mdoc = json.load(open(manifest))
    mdoc["rows"] = [r for r in mdoc["rows"]
                    if r["source_record_id"] != victim["source_record_id"]]
    bad_table = os.path.join(str(tmp_path), "dropped.json")
    bad_manifest = os.path.join(str(tmp_path), "dropped_manifest.json")
    json.dump(doc, open(bad_table, "w"))
    json.dump(mdoc, open(bad_manifest, "w"))

    report = replay.build_report(table_path=bad_table, manifest_path=bad_manifest,
                                 source_path=PSEUDOBULK, source_id=source_id)
    assert report["verdict"] == replay.REFUSED
    assert report["completeness_verdict"] == replay.INCOMPLETE
    assert report["n_scopes_incomplete"] >= 1


def test_the_real_source_refuses_a_stale_locator(tmp_path):
    """A re-keyed record pointing at a real row that belongs to another contributor."""
    cols = _read_obs()
    scopes = _pick_scopes(cols)
    table, manifest, records, _sha, source_id = _bundle(tmp_path, scopes)

    doc = json.load(open(table))
    first, donor = doc["records"][0], doc["records"][-1]
    assert first["source_record_id"] != donor["source_record_id"]
    first["pseudobulk_source_offsets"] = list(donor["pseudobulk_source_offsets"])
    first["pseudobulk_source_rows"] = list(donor["pseudobulk_source_rows"])
    first["source_row_index"] = donor["source_row_index"]
    first["source_record_id"] = derive_record_id(first)      # the CONSISTENT forger
    bad_table = os.path.join(str(tmp_path), "stale.json")
    json.dump(doc, open(bad_table, "w"))

    report = replay.build_report(table_path=bad_table, manifest_path=manifest,
                                 source_path=PSEUDOBULK, source_id=source_id)
    assert report["verdict"] == replay.REFUSED
    assert report["n_failed"] >= 1 or report["n_scopes_incomplete"] >= 1
