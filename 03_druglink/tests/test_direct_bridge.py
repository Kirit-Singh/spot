"""P0-1 and P0-2: the mandatory verified Direct loader, and the two-arm expansion."""
from __future__ import annotations

import json
import shutil

import pandas as pd
import pytest

from druglink import armlever, run_stage3
from druglink import direct_run as dr        # the module; `direct_run` is the fixture
from druglink.armlever import ARM_POLE, ARM_RANK_COLUMN, ARMS


# --------------------------------------------------------------------------- #
# P0-1. Only a Direct run that Direct's OWN verifier reconstructed is admissible.
# --------------------------------------------------------------------------- #
def test_only_verified_direct_run_is_accepted(direct_run, loaded_direct, tmp_path):
    # The happy path: Direct's standalone verifier actually ran, and passed.
    assert loaded_direct.verifier["exit_code"] == 0
    assert loaded_direct.verifier["n_failed"] == 0
    assert loaded_direct.verifier["n_checks"] > 0
    assert loaded_direct.run_id == direct_run["run_id"]

    # Upstream gate fields are preserved verbatim as CONTEXT. Stage 3 gates on none of
    # them — it has no promotion vocabulary left to gate.
    ctx = loaded_direct.binding["upstream_gate_context"]
    assert ctx["direct_lane"] == "research_only"
    assert "does not gate" in ctx["note"]
    from druglink import artifact_class as ac
    assert ac.retired_keys_in(loaded_direct.binding) == []

    # There is no caller-authored lever-set path: argparse rejects the flag outright,
    # because the argument does not exist for any code path to reach.
    with pytest.raises(SystemExit):
        run_stage3.main(["--namespace", "analysis",
                         "--lever-set", str(tmp_path / "lever.json"),
                         "--cache-root", str(tmp_path),
                         "--output-root", str(tmp_path)])

    # A missing file is fatal: the inventory must be exact.
    trimmed = tmp_path / "trimmed"
    shutil.copytree(direct_run["run_dir"], trimmed)
    (trimmed / "masks.parquet").unlink()
    with pytest.raises(dr.DirectRunError, match="inventory"):
        dr.load(str(trimmed), direct_run["inputs_root"],
                        artifact_class="analysis",
                        direct_analysis=direct_run["analysis"])

    # An EXTRA file is equally fatal.
    extra = tmp_path / "extra"
    shutil.copytree(direct_run["run_dir"], extra)
    (extra / "notes.json").write_text("{}")
    with pytest.raises(dr.DirectRunError, match="inventory"):
        dr.load(str(extra), direct_run["inputs_root"],
                        artifact_class="analysis",
                        direct_analysis=direct_run["analysis"])


def test_resealed_row_mutation_is_refused(direct_run, tmp_path):
    """Change one arm value, then refresh EVERY local self-hash. Still refused.

    Source reconstruction, not self-consistency, is the authority: Direct's verifier
    rebuilds screen.parquet from the raw matrices, so a row that no longer follows
    from the sources fails even though the document agrees with itself.
    """
    mutated = tmp_path / "mutated"
    shutil.copytree(direct_run["run_dir"], mutated)

    screen = pd.read_parquet(mutated / "screen.parquet")
    row = screen.index[screen["away_from_A"].notna()][0]
    screen.loc[row, "away_from_A"] = float(screen.loc[row, "away_from_A"]) + 5.0
    screen.to_parquet(mutated / "screen.parquet", index=False)

    # Reseal: make verification.json's own artifact digests agree with the new bytes.
    import hashlib
    verification = json.loads((mutated / "verification.json").read_text())
    for name in list(verification["artifact_sha256"]):
        path = mutated / name
        if path.exists():
            verification["artifact_sha256"][name] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    (mutated / "verification.json").write_text(json.dumps(verification, indent=2,
                                                          sort_keys=True))

    with pytest.raises(dr.DirectRunError, match="verifier REFUSED"):
        dr.load(str(mutated), direct_run["inputs_root"],
                        artifact_class="analysis",
                        direct_analysis=direct_run["analysis"])


# --------------------------------------------------------------------------- #
# P0-2. Two arms, first-class and order-independent.
# --------------------------------------------------------------------------- #
def test_emits_exactly_two_arm_rows_per_direct_row(loaded_direct, arm_levers):
    n_screen = len(loaded_direct.screen)
    rows = arm_levers["arm_levers"]

    assert len(rows) == 2 * n_screen
    assert arm_levers["counts"]["n_unique_immutable_keys"] == 2 * n_screen

    # Both arms carry EVERY screen row, evaluable or not. Nothing is dropped for
    # being non-evaluable, unranked, or in the symbol namespace.
    for arm in ARMS:
        assert sum(1 for r in rows if r["desired_arm"] == arm) == n_screen

    # Rows whose target is a released SYMBOL are retained, with an explicit
    # disposition, and barred from every gene-target drug edge.
    unmapped = [r for r in rows if r["target_identity_state"] != "ensembl_mapped"]
    assert unmapped, "the fixture must contain symbol-namespace targets"
    assert all(not r["gene_target_drug_edge_permitted"] for r in unmapped)
    assert all(r["target_ensembl"] is None for r in unmapped)


def test_arm_mapping_is_field_exact(loaded_direct, arm_levers):
    """An A row never reads a B field, and reciprocally."""
    screen = loaded_direct.screen.to_dict("records")
    by_key = {(r["target_id"], r["desired_arm"]): r
              for r in arm_levers["arm_levers"]}

    saw_conflict = False
    for src in screen:
        for arm in ARMS:
            pole = ARM_POLE[arm]
            row = by_key[(src["target_id"], arm)]

            # value / rank / evaluability / tier / support / modulation all come from
            # THIS arm's own columns.
            want_value = src[arm]
            assert row["arm_value_source_string"] == (
                None if pd.isna(want_value) else repr(float(want_value)))

            want_rank = src[ARM_RANK_COLUMN[arm]]
            assert row["arm_rank"] == (None if pd.isna(want_rank) else int(want_rank))

            assert row["arm_evaluable"] == bool(src[f"{pole}_evaluable"])
            assert row["arm_state"] == src[f"{pole}_state"]
            assert row["arm_evidence_tier"] == src[f"{pole}_evidence_tier"]
            assert row["arm_support_state"] == src[f"{pole}_support_state"]
            assert row["arm_desired_target_modulation"] == \
                src[f"{pole}_desired_target_modulation"]

        # The load-bearing case: one target, two OPPOSITE desired modulations.
        a = by_key[(src["target_id"], "away_from_A")]
        b = by_key[(src["target_id"], "toward_B")]
        if {a["arm_desired_target_modulation"],
                b["arm_desired_target_modulation"]} == {"decrease", "increase"}:
            saw_conflict = True
            # Neither arm has overwritten the other.
            assert a["arm_desired_target_modulation"] == \
                src["A_desired_target_modulation"]
            assert b["arm_desired_target_modulation"] == \
                src["B_desired_target_modulation"]

    assert saw_conflict, ("the fixture must contain a target whose two arms want "
                          "OPPOSITE modulations — that is the case the old "
                          "gene-keyed lever silently collapsed")


def test_permuted_input_is_byte_identical(loaded_direct):
    """Reversing the screen's row order changes nothing."""
    from druglink.artifacts import table_content_hash

    screen = loaded_direct.screen
    forward = armlever.expand(screen, direct_run_id=loaded_direct.run_id)
    reversed_ = armlever.expand(screen.iloc[::-1].reset_index(drop=True),
                                direct_run_id=loaded_direct.run_id)

    assert forward["arm_levers"] == reversed_["arm_levers"]
    assert (table_content_hash("arm_levers", forward["arm_levers"])
            == table_content_hash("arm_levers", reversed_["arm_levers"]))

    # And the acquisition queue selected from it is the same, per arm.
    assert (armlever.select_acquisition_targets(forward["arm_levers"], top_per_arm=5)
            == armlever.select_acquisition_targets(reversed_["arm_levers"],
                                                   top_per_arm=5))


def test_duplicate_arm_key_is_refused(loaded_direct):
    """Two rows for one (target, arm) is fatal. There is no last-row-wins."""
    screen = loaded_direct.screen
    doubled = pd.concat([screen, screen.iloc[[0]]], ignore_index=True)

    with pytest.raises(armlever.ArmLeverError, match="duplicate immutable"):
        armlever.expand(doubled, direct_run_id=loaded_direct.run_id)

    # Even with CONFLICTING content on the duplicate key: still a refusal, never a
    # silent pick of the last row.
    conflicting = screen.copy()
    dup = screen.iloc[[0]].copy()
    dup.loc[dup.index[0], "A_desired_target_modulation"] = "increase"
    conflicting = pd.concat([conflicting, dup], ignore_index=True)
    with pytest.raises(armlever.ArmLeverError, match="duplicate immutable"):
        armlever.expand(conflicting, direct_run_id=loaded_direct.run_id)


def test_no_combined_or_headline_objective(loaded_direct, arm_levers, analysis_build):
    """No combined/balanced/best-of/primary/headline/overall objective, anywhere."""
    banned = armlever.BANNED_OBJECTIVE_COLUMNS

    # Not in the arm-lever rows.
    for row in arm_levers["arm_levers"]:
        assert not banned.intersection(row)

    # Not in any emitted table.
    for name, rows in analysis_build["tables"].items():
        for row in rows:
            assert not banned.intersection(row), f"{name} carries a banned key"

    # Not anywhere in the document, at any depth.
    def walk(node, path="$"):
        hits = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k in banned:
                    hits.append(f"{path}.{k}")
                hits += walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                hits += walk(v, f"{path}[{i}]")
        return hits

    assert not walk(analysis_build["document"])

    # A Direct screen that carried one would be refused on load.
    poisoned = loaded_direct.screen.copy()
    poisoned["balanced_skew"] = 1.0
    with pytest.raises(armlever.ArmLeverError, match="combined/headline"):
        armlever.expand(poisoned, direct_run_id=loaded_direct.run_id)

    # And there is no candidate-level rank field to hold one.
    for cand in analysis_build["tables"]["candidates"]:
        assert "rank" not in cand and "rank_tuple" not in cand
