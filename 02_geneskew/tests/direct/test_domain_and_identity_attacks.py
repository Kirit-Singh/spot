"""Tamper attacks on the claims a run makes ABOUT ITSELF, and on identity uniqueness.

Three defects, one shape: a check that could be satisfied by the honest half of a pair.

  * THE DOMAIN, checked with an OR. The verifier accepted the correct evidence domain in
    the run binding OR in provenance. Both are written by the same producer, so "at
    least one of them is right" says nothing about either — a forged copy is simply
    masked by whichever honest copy happens to be read first. Both must be right,
    independently, and the domain RULE id and the global scope COUNT must be bound too:
    a manifest matched by a laxer rule, or against a universe one scope smaller, is
    different science with the same name.

  * THE RECORD-ID RULE, compared field by field except for ``null_handling``. That field
    is not a footnote: ``target_ensembl`` is null for every gene_symbol scope and
    ``donor_pair`` is null for every pooled scope, so a table that serialized either
    differently would hash a different payload and mint different ids — while declaring
    an identical rule string and an identical field list.

  * DUPLICATE IDENTITIES, silently collapsed. A second row for the same
    (condition, target) was dropped by a dict assignment, so the scope universe shrank
    by one while the dense loader still read and scored both rows. The manifest is then
    "complete" over a universe that is missing a scope. This is true even when the two
    rows are IDENTICAL — two estimates that agree about their metadata are still two
    estimates, and the old check only caught CONFLICTING ones.
"""
from __future__ import annotations

import copy
import json
import os

import numpy as np
import pytest
from direct import domain, io_data, record_id
from direct.run_screen import build_screen
from fixtures_spec import CONDITION, DONOR_PAIRS
from test_source_replay import run_and_verify, verify


# --------------------------------------------------------------------------- #
# 1. THE EVIDENCE DOMAIN: every copy checked independently.
# --------------------------------------------------------------------------- #
def _tamper_provenance(run_dir, mutate):
    path = os.path.join(run_dir, "provenance.json")
    with open(path) as fh:
        prov = json.load(fh)
    mutate(prov)
    with open(path, "w") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)


def _failed_checks(args):
    """The NAMES of the checks that failed — not merely the exit code.

    Tampering with the run BINDING necessarily also breaks ``run_binding_sha256``, so a
    test that only asserted a non-zero exit would pass even if the domain check did not
    exist. Asserting the named check is what proves the rule is actually there and
    actually fired, which is the same trap the replay-arithmetic attacks had to avoid.
    """
    from direct.verify_run import Report, reconstruct
    rep = Report()
    reconstruct(args.out_dir, os.path.dirname(args.selection), rep, strict=False)
    return [name for name, _detail in rep.failures]


def test_the_honest_run_binds_the_domain_in_BOTH_places(synthetic_run):
    args = run_and_verify(synthetic_run())
    with open(os.path.join(args.out_dir, "provenance.json")) as fh:
        prov = json.load(fh)
    bound = prov["run_binding"]["stage2_evidence_domain"]
    emitted = prov["evidence_domain"]

    assert bound["domain_id"] == emitted["domain_id"] == domain.DOMAIN_ID
    assert bound["rule_id"] == emitted["rule_id"] == domain.DOMAIN_RULE_ID
    assert (bound["n_global_pooled_main_scopes"]
            == emitted["n_global_pooled_main_scopes"])
    assert verify(args, strict=False) == 0


@pytest.mark.parametrize("where,check", [
    ("run_binding", "the evidence domain in the RUN BINDING is the frozen domain"),
    ("provenance", "the evidence domain in PROVENANCE is the frozen domain"),
])
def test_a_forged_domain_id_in_EITHER_copy_is_caught(synthetic_run, where, check):
    """The OR bug: one honest copy used to excuse the other. Now each is asked alone."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        target = (prov["run_binding"]["stage2_evidence_domain"]
                  if where == "run_binding" else prov["evidence_domain"])
        target["domain_id"] = "spot.stage02.direct.evidence_domain.anything_goes.v0"

    _tamper_provenance(args.out_dir, mutate)
    assert check in _failed_checks(args)
    assert verify(args, strict=False) == 1


@pytest.mark.parametrize("where,check", [
    ("run_binding", "the domain RULE id in the RUN BINDING is the frozen rule"),
    ("provenance", "the domain RULE id in PROVENANCE is the frozen rule"),
])
def test_a_forged_domain_RULE_id_in_either_copy_is_caught(synthetic_run, where, check):
    """Each COPY is named, so a forgery cannot hide behind whichever one is honest."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        target = (prov["run_binding"]["stage2_evidence_domain"]
                  if where == "run_binding" else prov["evidence_domain"])
        target["rule_id"] = "spot.stage02.direct.domain_rule.substring_match.v0"

    _tamper_provenance(args.out_dir, mutate)
    assert check in _failed_checks(args)


@pytest.mark.parametrize("where", ["run_binding", "provenance"])
def test_a_shrunken_global_scope_COUNT_is_caught(synthetic_run, where):
    """A universe one scope smaller is a DROPPED scope, invisible to every row check."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        target = (prov["run_binding"]["stage2_evidence_domain"]
                  if where == "run_binding" else prov["evidence_domain"])
        target["n_global_pooled_main_scopes"] -= 1

    _tamper_provenance(args.out_dir, mutate)
    failed = _failed_checks(args)
    assert any("scope count" in name for name in failed), failed


def test_the_bound_scope_count_is_checked_against_the_RAW_release(synthetic_run):
    """Both copies agree with each other and BOTH are wrong. Only the raw DE sees it."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        for block in (prov["run_binding"]["stage2_evidence_domain"],
                      prov["evidence_domain"]):
            block["n_global_pooled_main_scopes"] += 7

    _tamper_provenance(args.out_dir, mutate)
    failed = _failed_checks(args)
    assert ("the scope count in the run binding IS the count the raw DE release ships"
            in failed)
    assert ("the scope count in provenance IS the count the raw DE release ships"
            in failed)


def test_the_bound_replay_rule_ids_are_verified(synthetic_run):
    """run_id must bind WHICH rule proved its gate — not merely the word 'complete'."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        sr = prov["run_binding"]["guide_manifest"]["source_replay"]
        sr["completeness_rule_id"] = "spot.stage02.direct.completeness_rule.v1"

    _tamper_provenance(args.out_dir, mutate)
    assert "run_id binds the exact v2 completeness rule id" in _failed_checks(args)


def test_a_resurrected_OBSOLETE_rule_key_is_refused(synthetic_run):
    """The v2 report has no `completeness_rule`; a null nobody checks binds nothing."""
    args = run_and_verify(synthetic_run())

    def mutate(prov):
        sr = prov["run_binding"]["guide_manifest"]["source_replay"]
        sr["completeness_rule"] = None

    _tamper_provenance(args.out_dir, mutate)
    assert "no OBSOLETE rule key survives in the run binding" in _failed_checks(args)


# --------------------------------------------------------------------------- #
# 2. THE RECORD-ID RULE METADATA: every field, including null_handling.
# --------------------------------------------------------------------------- #
def test_the_compiled_rule_declares_null_handling():
    assert "null_handling" in record_id.RULE_METADATA
    assert record_id.RULE_METADATA["null_handling"] == record_id.NULL_HANDLING


@pytest.mark.parametrize("field", ["rule", "canonical_json", "null_handling",
                                   "identity_payload_fields"])
def test_the_generator_refuses_a_table_that_misdeclares_ANY_rule_field(field):
    declared = copy.deepcopy(record_id.RULE_METADATA)
    declared[field] = (["forged"] if field == "identity_payload_fields"
                       else "a rule this producer does not implement")
    assert record_id.rule_metadata_violation(declared) is not None


@pytest.mark.parametrize("field", ["rule", "canonical_json", "null_handling",
                                   "identity_payload_fields"])
def test_the_STANDALONE_verifier_refuses_the_same_misdeclaration(field):
    """The verifier restates the rule; it must catch the same drift independently.

    ``null_handling`` is the one this check used to omit — so a table could declare that
    nulls serialize as empty strings, mint every id under that rule, and pass.
    """
    from direct import verify_evidence as E
    from direct.verify_run import Report

    table = {"schema_version": E.RECORDS_SCHEMA,
             E.RULE_METADATA_KEY: copy.deepcopy(record_id.RULE_METADATA),
             "records": []}
    table[E.RULE_METADATA_KEY][field] = (
        ["forged"] if field == "identity_payload_fields" else "not the compiled rule")
    manifest = {"schema_version": E.MANIFEST_SCHEMA,
                "source_record_table_schema_version": E.RECORDS_SCHEMA}

    rep = Report()
    assert E.check_schema_versions(manifest, table, rep) is False
    assert any("record-id rule" in name for name, _d in rep.failures)


def test_the_honest_table_still_passes_the_rule_check():
    from direct import verify_evidence as E
    from direct.verify_run import Report

    table = {"schema_version": E.RECORDS_SCHEMA,
             E.RULE_METADATA_KEY: copy.deepcopy(record_id.RULE_METADATA),
             "records": []}
    manifest = {"schema_version": E.MANIFEST_SCHEMA,
                "source_record_table_schema_version": E.RECORDS_SCHEMA}
    rep = Report()
    assert E.check_schema_versions(manifest, table, rep) is True
    assert rep.failures == []


# --------------------------------------------------------------------------- #
# 3. DUPLICATE RELEASED IDENTITIES: identical duplicates fail too.
# --------------------------------------------------------------------------- #
def _duplicate_main(path, which="identical"):
    """Append a SECOND pooled-main row for a (condition, target) already present."""
    import h5py
    from fixtures_io import _write_categorical

    with h5py.File(path, "r") as fh:
        obs = fh["obs"]
        idx = obs.attrs.get("_index", "index")
        cols = {}
        for name in obs:
            node = obs[name]
            if isinstance(node, h5py.Group):
                cats = [c.decode() if isinstance(c, bytes) else str(c)
                        for c in node["categories"][:]]
                codes = node["codes"][:]
                cols[name] = [cats[c] if c >= 0 else None for c in codes]
            else:
                cols[name] = list(node[:])
        layers = {k: fh[f"layers/{k}"][:] for k in fh["layers"]}
        genes = list(fh["var/gene_ids"][:])

    dup_at = next(i for i, c in enumerate(cols["culture_condition"])
                  if c == CONDITION)
    for name, values in cols.items():
        v = values[dup_at]
        if name == idx and which == "conflicting":
            v = b"OTHER_RELEASE_KEY" if isinstance(v, bytes) else "OTHER_RELEASE_KEY"
        values.append(v)
    for k in layers:
        layers[k] = np.vstack([layers[k], layers[k][dup_at][None, :]])

    os.remove(path)
    with h5py.File(path, "w") as fh:
        obs = fh.create_group("obs")
        obs.attrs["_index"] = idx
        for name, values in cols.items():
            if name == idx or all(isinstance(v, (bytes, str)) for v in values):
                if name == idx:
                    obs.create_dataset(name, data=np.array(
                        [v if isinstance(v, bytes) else str(v).encode()
                         for v in values]))
                else:
                    _write_categorical(obs, name, [str(v) for v in values])
            else:
                obs.create_dataset(name, data=np.array(values))
        fh.create_group("layers")
        for k, v in layers.items():
            fh.create_dataset(f"layers/{k}", data=v)
        fh.create_group("var")
        fh.create_dataset("var/gene_ids", data=np.array(genes))


@pytest.mark.parametrize("which", ["identical", "conflicting"])
def test_a_duplicate_pooled_main_identity_fails_closed(synthetic_run, which):
    """Both kinds. An identical duplicate used to be collapsed silently."""
    args = synthetic_run()
    _duplicate_main(args.de_main, which)
    with pytest.raises(ValueError, match="not unique"):
        build_screen(args)


@pytest.mark.parametrize("which", ["identical", "conflicting"])
def test_the_metadata_loader_itself_refuses_the_duplicate(synthetic_run, which):
    """At the root: the identity universe is where the scope count comes from."""
    args = synthetic_run()
    _duplicate_main(args.de_main, which)
    with pytest.raises(ValueError, match="not unique"):
        io_data.load_main_identity_universe(args.de_main)


@pytest.mark.parametrize("which", ["identical", "conflicting"])
def test_the_STANDALONE_verifier_also_sees_the_duplicate(synthetic_run, which):
    """It derives the global scope set from the raw DE — into a SET, which hides this.

    An identical duplicate collapses into the set and vanishes, so the universe the
    verifier checks the manifest against is one scope smaller than the release it
    actually scored.
    """
    from direct.verify_run import Report, derive_global_scopes

    args = synthetic_run()
    _duplicate_main(args.de_main, which)
    rep = Report()
    derive_global_scopes(args.de_main, rep)
    assert any("unique per" in name for name, _d in rep.failures)


# --------------------------------------------------------------------------- #
# 4. DUPLICATE SUPPORT IDENTITIES: accounting must not undercount.
# --------------------------------------------------------------------------- #
def _read_obs(obs):
    """Every obs column, tagged with how it is stored, so it can be written back."""
    import h5py
    cols = {}
    for name in obs:
        node = obs[name]
        if isinstance(node, h5py.Group):                     # categorical
            cats = [c.decode() if isinstance(c, bytes) else str(c)
                    for c in node["categories"][:]]
            cols[name] = ("cat", [cats[c] if c >= 0 else None
                                  for c in node["codes"][:]])
        else:
            arr = node[:]
            if arr.dtype.kind == "S":
                cols[name] = ("str", [v.decode() for v in arr])
            else:
                cols[name] = ("num", list(arr))
    return str(obs.attrs.get("_index", "index")), cols


def _write_obs(parent, idx, cols):
    from fixtures_io import _write_categorical
    obs = parent.create_group("obs")
    obs.attrs["_index"] = idx
    for name, (kind, values) in cols.items():
        if kind == "cat":
            _write_categorical(obs, name, [str(v) for v in values])
        elif kind == "str":
            obs.create_dataset(name, data=np.array(
                [str(v).encode() for v in values], dtype="S96"))
        else:
            obs.create_dataset(name, data=np.array(values))


def _duplicate_support_identity(h5mu_path, modality):
    """A second, IDENTICAL row for a target already present in ONE support modality.

    Identical on purpose: a conflicting duplicate was always visible, but an exact one
    was absorbed by ``if str(t) in by_target: continue`` and vanished without a trace.
    The layer row is duplicated too, so the object stays structurally faithful — the
    point is that nothing needs to READ that layer to refuse this.
    """
    import h5py

    with h5py.File(h5mu_path, "r") as fh:
        mod = fh[f"mod/{modality}"]
        idx, cols = _read_obs(mod["obs"])
        layers = {k: mod[f"layers/{k}"][:] for k in mod["layers"]}
        genes = list(mod["var/_index"][:])

    conds = cols["culture_condition"][1]
    dup_at = next(i for i, c in enumerate(conds) if str(c) == CONDITION)
    for name, (kind, values) in cols.items():
        cols[name] = (kind, list(values) + [values[dup_at]])
    for k in layers:
        layers[k] = np.vstack([layers[k], layers[k][dup_at][None, :]])

    with h5py.File(h5mu_path, "a") as fh:
        del fh[f"mod/{modality}"]
        mod = fh.create_group(f"mod/{modality}")
        mod.create_group("var").create_dataset("_index", data=np.array(genes))
        _write_obs(mod, idx, cols)
        for k, v in layers.items():
            mod.create_dataset(f"layers/{k}", data=v)


def test_a_duplicate_guide_slot_identity_fails_closed(synthetic_run):
    """Support is unavailable, so identity is ALL we expose — it must be honest.

    Silently keeping the first row undercounts the released support estimates, and that
    count is bound into the support contract and into run_id: the run would claim to
    have accounted for every released support estimate while having dropped one.
    """
    args = synthetic_run()
    _duplicate_support_identity(args.by_guide, "guide_1")
    with pytest.raises(ValueError, match="not unique"):
        build_screen(args)


def test_the_support_identity_loader_itself_refuses_the_duplicate(synthetic_run):
    args = synthetic_run()
    _duplicate_support_identity(args.by_guide, "guide_1")
    with pytest.raises(ValueError, match="not unique"):
        io_data.load_support_identities(args.by_guide, "guide_1", CONDITION)


def test_a_duplicate_donor_pair_identity_fails_closed_without_a_dense_read(
        synthetic_run, monkeypatch):
    """The refusal is decidable from obs alone — no support LAYER is ever touched."""
    args = synthetic_run()
    _duplicate_support_identity(args.by_donors, DONOR_PAIRS[0])

    from direct import io_data as IO
    monkeypatch.setattr(IO, "load_support_modality", _forbidden)
    with pytest.raises(ValueError, match="not unique"):
        build_screen(args)


def _forbidden(*a, **k):
    raise AssertionError("a dense support matrix was read; support is out of domain "
                         "in this pass and its layers must never be touched")


# --------------------------------------------------------------------------- #
# 5. THE LEGACY DENSE SUPPORT LOADER: the same defect, one function further down.
#
# ``load_support_modality`` is not used by Direct — support is never projected here —
# but Perturb2State calls it, and it still silently kept the FIRST row of a duplicate
# ``(modality, condition, target)`` and skipped the rest.
#
# It is worse there than anywhere else the bug was fixed, because this loader hands back
# an EFFECT VECTOR. Collapsing a duplicate means every downstream number for that target
# comes from one arbitrarily chosen released estimate while a second, equally released
# estimate is discarded without a trace — and the choice between them is made by file
# order. Two estimates that agree about their metadata are still two estimates.
# --------------------------------------------------------------------------- #
def test_the_honest_object_still_loads_through_the_dense_support_loader(synthetic_run):
    """The duplicate rule must not refuse a well-formed object. A guard that refuses
    everything is not a guard."""
    args = synthetic_run()
    loaded = io_data.load_support_modality(args.by_guide, "guide_1", CONDITION)
    assert loaded["by_target"]
    assert all("effect" in v for v in loaded["by_target"].values())


def test_the_dense_support_loader_refuses_a_duplicate_GUIDE_modality(synthetic_run):
    """An exact duplicate: identical metadata, identical layer row. Still two estimates."""
    args = synthetic_run()
    _duplicate_support_identity(args.by_guide, "guide_1")
    with pytest.raises(ValueError, match="not unique"):
        io_data.load_support_modality(args.by_guide, "guide_1", CONDITION)


def test_the_dense_support_loader_refuses_a_duplicate_DONOR_modality(synthetic_run):
    args = synthetic_run()
    _duplicate_support_identity(args.by_donors, DONOR_PAIRS[0])
    with pytest.raises(ValueError, match="not unique"):
        io_data.load_support_modality(args.by_donors, DONOR_PAIRS[0], CONDITION)


def test_the_dense_loader_names_the_two_estimates_it_refused(synthetic_run):
    """The refusal has to be diagnosable: WHICH target, and which two released ids."""
    args = synthetic_run()
    _duplicate_support_identity(args.by_guide, "guide_1")
    with pytest.raises(ValueError) as exc:
        io_data.load_support_modality(args.by_guide, "guide_1", CONDITION)
    msg = str(exc.value)
    assert "guide_1" in msg and CONDITION in msg
    assert "two identical" in msg
