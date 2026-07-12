"""SOURCE-NATIVE replay and CONTRIBUTOR COMPLETENESS, through the standalone verifier.

The threat this module exists for: a producer that is perfectly self-consistent and
completely wrong. Its manifest cites its source-record table; its table resolves; every
hash is correct; its replay report says "replayed". Nothing in the generated artifacts
contradicts anything else — because ONE process wrote them all. Agreement is not
provenance.

Only the RAW SOURCE can catch that. So:

  * the DEFAULT verifier checks the PINNED replay report binds these exact table bytes
    to those exact source bytes and carries the completeness fields — a real check, but
    a check of a REPORT;
  * ``--strict-replay`` re-derives the whole verdict from the raw H5AD itself.

WHY EXISTENCE WAS NOT ENOUGH. The superseded v1 report asked one question: does each
cited locator point at a kept raw row that says what the record says? A subset-existence
check cannot see a contributor that was silently DROPPED. Every guide the manifest names
is real, every hash is right, every locator replays — and the mask is still built from
an incomplete guide set, which changes the score. v1 could certify a wrong answer, so it
is refused as a gate. The completeness attacks below are the ones it could not see.

Every attack is pinned HONESTLY. If a refusal appears, it came from the source.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys

import pytest

from direct import replay
from direct.manifest import ManifestError
from direct.run_screen import build_screen

from fixtures_evidence import (NON_TARGETING_GUIDES, SOURCE_NAME, kept_proof,
                               manifest_rows, raw_source_rows, source_record_doc,
                               source_records)
from fixtures_direct import default_specs
from fixtures_spec import SYMBOL_TARGETS, TARGET_GENES

pytestmark = pytest.mark.filterwarnings("ignore")

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
ENSG_TARGET = TARGET_GENES[0]


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def verify(args, strict: bool) -> int:
    """The standalone verifier, IN PROCESS (its exit code is the verdict)."""
    from direct.verify_run import main as verify_main
    argv = ["--run-dir", args.out_dir, "--inputs-root",
            os.path.dirname(args.selection)]
    if strict:
        argv.append("--strict-replay")
    with contextlib.redirect_stdout(io.StringIO()):
        return verify_main(argv)


def verify_subprocess(run_dir: str, inputs_root: str, strict: bool
                      ) -> subprocess.CompletedProcess:
    """The verifier as a SEPARATE PROCESS — no shared state with the generator."""
    argv = [sys.executable, "-m", "direct.verify_run", "--run-dir", run_dir,
            "--inputs-root", inputs_root]
    if strict:
        argv.append("--strict-replay")
    env = dict(os.environ, PYTHONPATH=_ANALYSIS)
    return subprocess.run(argv, capture_output=True, text=True, env=env,
                          cwd=_ANALYSIS, timeout=600)


def run_and_verify(args):
    """Build the run and hand back the args, now knowing where it landed."""
    args.out_dir = build_screen(args)["out_dir"]
    return args


def claim_replayed(report: dict) -> dict:
    """The report LIES: it says the source confirmed what the source refutes.

    Both halves of the gate are faked — existence AND completeness — because a report
    that only faked one would be caught by the other, and would not test the source.
    """
    return dict(report, verdict="replayed", n_failed=0,
                n_replayed=report["n_records"], failures=[],
                completeness_verdict="complete", n_scopes_incomplete=0,
                n_scopes_complete=report["n_scopes_determined"],
                n_records_offset_proven=report["n_records"],
                n_nontargeting_guides_cited=0, completeness_failures=[])


def stale_locator(records: list[dict]) -> list[dict]:
    """Point one record's LOCATOR at a real kept row belonging to another contributor.

    The locator is inside the offset proof, which is inside the id — so an honest
    producer cannot do this without re-keying. This forgery re-keys, leaving every id,
    hash and cross-reference internally perfect.
    """
    from direct.record_id import derive_record_id

    out = copy.deepcopy(records)
    first = out[0]
    donor = next(r for r in out[1:]
                 if r["source_row_index"] != first["source_row_index"])
    first["source_row_index"] = donor["source_row_index"]
    first["pseudobulk_source_offsets"] = list(donor["pseudobulk_source_offsets"])
    first["pseudobulk_source_rows"] = list(donor["pseudobulk_source_rows"])
    first["source_record_id"] = derive_record_id(first)
    return out


def tamper_source_row(raw: list[dict]) -> list[dict]:
    """Rewrite the SOURCE's own guide_id at row 0, then pin the tampered bytes."""
    out = copy.deepcopy(raw)
    out[0]["guide_id"] = "g-TAMPERED"
    return out


def drop_a_kept_source_row(raw: list[dict]) -> list[dict]:
    """Delete one KEPT contributor row from the raw source.

    The records still claim the offsets the pristine source had, so their proof is now
    an over-claim. This is the shape an existence-only replay was blind to.
    """
    out = copy.deepcopy(raw)
    kept = next(i for i, r in enumerate(out) if r["keep_for_DE"])
    del out[kept]
    return out


# --------------------------------------------------------------------------- #
# The honest bundle replays — both modes, and as a real subprocess.
# --------------------------------------------------------------------------- #
def test_the_honest_run_passes_the_default_verifier(synthetic_run):
    args = run_and_verify(synthetic_run())
    assert verify(args, strict=False) == 0


def test_the_honest_run_passes_STRICT_replay(synthetic_run):
    """Strict mode re-derives the verdict from the raw source and still agrees."""
    args = run_and_verify(synthetic_run())
    assert verify(args, strict=True) == 0


def test_the_honest_run_passes_the_verifier_as_a_subprocess(synthetic_run):
    args = run_and_verify(synthetic_run())
    proc = verify_subprocess(args.out_dir, os.path.dirname(args.selection),
                             strict=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "every source record replays against the RAW source" in proc.stdout


# --------------------------------------------------------------------------- #
# THE CENTRAL ATTACK: a self-consistent producer that the source refutes.
# --------------------------------------------------------------------------- #
def test_a_lying_replay_report_survives_table_agreement_and_dies_on_the_source(
        synthetic_run):
    """The whole reason strict replay exists.

    The locator is stale, the proof was re-keyed around it, the producer RE-CITED its
    own forgery, and the report claims the source confirmed it. Every hash is correct,
    every id derives, the manifest and the table agree perfectly, and the run BUILDS.
    Only a replay against the raw source refutes it — which is why generated-table
    agreement is never called source verification.
    """
    args = run_and_verify(synthetic_run(source_records_fn=stale_locator,
                                        source_records_recite=True,
                                        source_replay_fn=claim_replayed))

    # the forgery is internally flawless: the run built, and the report-level
    # verifier is satisfied
    assert verify(args, strict=False) == 0

    # ...and the RAW SOURCE refutes it
    assert verify(args, strict=True) == 1
    proc = verify_subprocess(args.out_dir, os.path.dirname(args.selection),
                             strict=True)
    assert proc.returncode == 1
    assert "every source record replays against the RAW source" in proc.stdout


def test_an_honest_report_over_a_stale_locator_takes_the_run_down(synthetic_run):
    """Without the lie, the producer's OWN replay refuses it before the run starts."""
    with pytest.raises(ManifestError, match="the source did not confirm"):
        build_screen(synthetic_run(source_records_fn=stale_locator,
                                   source_records_recite=True))


def test_moving_a_records_proof_without_re_citing_it_breaks_the_citation(
        synthetic_run):
    """The SLOPPY forger never even reaches the source.

    The id is a hash OF the proof, so editing the proof re-keys the record — and the
    manifest is left citing an id that no longer exists. Under the superseded rule the
    id was a truncated hash of a payload that OMITTED the proof, so this same edit
    changed nothing and every citation still resolved.
    """
    from direct.sources import SourceRecordError

    with pytest.raises(SourceRecordError, match="do not resolve to a source record"):
        build_screen(synthetic_run(source_records_fn=stale_locator))


def test_tampering_with_the_source_row_is_caught(synthetic_run):
    """The source no longer says what the locators claim. Its bytes are pinned to the
    tamper, so only a replay can notice."""
    with pytest.raises(ManifestError, match="the source did not confirm"):
        build_screen(synthetic_run(source_rows_fn=tamper_source_row))


def test_tampering_with_the_source_row_dies_on_STRICT_replay(synthetic_run):
    """...and if the report is made to lie about it too, strict replay still wins."""
    args = run_and_verify(synthetic_run(source_rows_fn=tamper_source_row,
                                        source_replay_fn=claim_replayed))
    assert verify(args, strict=False) == 0        # the report is believed...
    assert verify(args, strict=True) == 1         # ...the source is not


# --------------------------------------------------------------------------- #
# COMPLETENESS: the contributor a subset-existence replay could never see.
# --------------------------------------------------------------------------- #
def test_a_dropped_contributor_row_makes_the_scope_incomplete(synthetic_run):
    """ONE guide removed from a pooled scope. Every remaining guide is real, every
    hash is right, every locator still replays — and the mask would be built from an
    incomplete guide set, which changes the score. Completeness is what sees it."""
    def attack(rows):
        out = copy.deepcopy(rows)
        victim = next(r for r in out if r["target_id"] == ENSG_TARGET
                      and r["evidence_state"] == "determined")
        out.remove(victim)
        return out

    with pytest.raises(ManifestError) as exc:
        build_screen(synthetic_run(manifest_rows_fn=attack))
    # The scope names fewer guides than the source kept for it, and the source knows it.
    # Asserted by the SCOPE-completeness rule specifically: a run refused for the wrong
    # stated reason is a run whose next reader debugs the wrong thing.
    assert "INCOMPLETE" in str(exc.value)
    assert "do not name the whole contributor set" in str(exc.value)


def test_a_dropped_kept_source_row_is_caught_by_completeness(synthetic_run):
    """The record's offset array over-claims: it names a row the source no longer keeps.
    An existence check on the LOCATOR alone can still pass; the all-offset proof cannot.
    """
    with pytest.raises(ManifestError, match="the source did not confirm"):
        build_screen(synthetic_run(source_rows_fn=drop_a_kept_source_row))


def test_an_excluded_contributor_makes_its_scope_incomplete(synthetic_run):
    """``included=false`` on a pooled row silently shrinks the contributor set."""
    def attack(rows):
        out = copy.deepcopy(rows)
        for r in out:
            if r["target_id"] == ENSG_TARGET and r["evidence_state"] == "determined":
                r["included"] = False
                break
        return out

    # named by the SCOPE-completeness rule: the refusal says which contract failed and
    # what it means, rather than relaying the producer's one-word "refused"
    with pytest.raises(ManifestError, match="INCOMPLETE"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_non_targeting_guide_can_never_be_a_contributor(synthetic_run):
    """A non-targeting control never contributed to a perturbation estimate.

    The forged guide is a REAL guide in the source with real kept rows — it is simply
    a control. Only obs.guide_type can tell the difference, and the completeness rule
    is what reads it.
    """
    def attack(rows):
        out = copy.deepcopy(rows)
        for r in out:
            if r["target_id"] == ENSG_TARGET and r["evidence_state"] == "determined":
                r["guide_id"] = NON_TARGETING_GUIDES[0]
                break
        return out

    with pytest.raises(ManifestError, match="the source did not confirm|non-targeting"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_the_honest_report_states_the_completeness_it_proved(synthetic_run):
    """A report that never asked whether the sets were COMPLETE cannot be the gate."""
    args = synthetic_run()
    build_screen(args)
    registry = json.load(open(args.source_registry))
    path = os.path.join(os.path.dirname(args.source_registry),
                        registry["sources"]["stage02_source_replay.json"]["path"])
    report = json.load(open(path))

    assert report["schema_version"] == "spot.stage02_source_replay.v2"
    assert report["verdict"] == "replayed"
    assert report["completeness_verdict"] == "complete"
    assert report["n_scopes_incomplete"] == 0
    assert report["n_scopes_complete"] == report["n_scopes_determined"] > 0
    assert report["n_records_offset_proven"] == report["n_records"] > 0
    assert report["n_nontargeting_guides_cited"] == 0
    # determined + ambiguous accounts for EVERY scope: a scope the report never looked
    # at cannot be reported complete
    assert report["n_scopes_named"] == (report["n_scopes_determined"]
                                        + report["n_scopes_ambiguous"])
    assert report["n_scopes_ambiguous"] > 0        # the six-style scopes are counted


def test_an_existence_only_report_may_never_be_the_release_gate(synthetic_run):
    """The superseded v1 schema is refused outright, not read as 'an older report'."""
    def forge(report):
        out = dict(report, schema_version="spot.stage02_source_replay.v1")
        for key in ("completeness_verdict", "n_scopes_complete", "n_scopes_incomplete",
                    "n_records_offset_proven", "n_nontargeting_guides_cited"):
            out.pop(key, None)
        return out

    with pytest.raises(ManifestError, match="EXISTENCE-ONLY|SUPERSEDED"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_a_report_missing_a_completeness_field_is_refused(synthetic_run):
    """It kept the v2 name but never answered the question."""
    def forge(report):
        return {k: v for k, v in report.items() if k != "completeness_verdict"}

    with pytest.raises(ManifestError, match="missing completeness field"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_a_report_claiming_completeness_over_unproven_offsets_is_refused(synthetic_run):
    """'complete' with fewer offset-proven records than records is a contradiction."""
    def forge(report):
        return dict(report, n_records_offset_proven=report["n_records"] - 1)

    with pytest.raises(ManifestError, match="offset proof confirmed|unproven offset"):
        build_screen(synthetic_run(source_replay_fn=forge))


# --------------------------------------------------------------------------- #
# The report must be about THESE bytes.
# --------------------------------------------------------------------------- #
def test_a_report_bound_to_other_source_bytes_is_refused(synthetic_run):
    with pytest.raises(ManifestError, match="not the pinned"):
        build_screen(synthetic_run(
            source_replay_fn=lambda r: dict(r, source_sha256="f" * 64)))


def test_a_report_bound_to_another_table_is_refused(synthetic_run):
    with pytest.raises(ManifestError, match="replays a DIFFERENT source-record"):
        build_screen(synthetic_run(
            source_replay_fn=lambda r: dict(r, source_record_table_sha256="e" * 64)))


def test_a_report_that_skipped_records_is_refused(synthetic_run):
    """Replaying SOME of the evidence is not replaying the evidence."""
    with pytest.raises(ManifestError, match="every record must be replayed"):
        build_screen(synthetic_run(
            source_replay_fn=lambda r: dict(r, n_records=1, n_replayed=1)))


def test_a_refused_replay_verdict_takes_the_run_down(synthetic_run):
    with pytest.raises(ManifestError, match="the source did not confirm"):
        build_screen(synthetic_run(
            source_replay_fn=lambda r: dict(r, verdict="refused", n_failed=1,
                                            n_replayed=0)))


def test_a_run_with_no_replay_report_has_no_contributor_evidence(synthetic_run):
    with pytest.raises(ManifestError, match="source_replay_report' is required"):
        build_screen(synthetic_run(source_replay_report=""))


def test_a_replay_report_naming_an_unpinned_source_is_refused(synthetic_run):
    with pytest.raises(ManifestError, match="not one of the manifest's verified"):
        build_screen(synthetic_run(source_replay_report="not_a_pinned_source.json"))


# --------------------------------------------------------------------------- #
# Replay, exercised directly on the builder.
# --------------------------------------------------------------------------- #
def _bundle(tmp_path, specs=None, records_fn=None):
    """A table + manifest + raw source on disk, for direct build_report calls."""
    from fixtures_evidence import write_evidence
    return write_evidence(str(tmp_path), specs or default_specs(),
                          records_fn=records_fn)


def test_the_honest_records_replay_against_the_raw_source(tmp_path):
    ev = _bundle(tmp_path)
    report = replay.build_report(table_path=ev.table_path,
                                 manifest_path=ev.manifest_path,
                                 source_path=ev.source_path, source_id=SOURCE_NAME)
    assert report["verdict"] == replay.REPLAYED, report["failures"]
    assert report["n_failed"] == 0
    assert report["n_replayed"] == report["n_records"] > 0
    assert report["completeness_verdict"] == replay.COMPLETE
    assert report["source_sha256"] == ev.source_sha256   # pinned to the bytes it judged


def test_the_offsets_a_record_declares_must_be_the_kept_rows(tmp_path):
    """A well-formed, re-keyed proof that simply is not what the source kept.

    The table loads, the citation resolves, every id derives — and the source refuses
    it. This is the exact forgery the superseded id rule left invisible.
    """
    from direct.record_id import derive_record_id

    def forge(records):
        out = copy.deepcopy(records)
        rec = out[0]
        rec["pseudobulk_source_offsets"] = rec["pseudobulk_source_offsets"][:1]
        rec["pseudobulk_source_rows"] = rec["pseudobulk_source_rows"][:1]
        rec["source_row_index"] = rec["pseudobulk_source_offsets"][0]
        rec["source_record_id"] = derive_record_id(rec)
        return out

    ev = _bundle(tmp_path, records_fn=forge)
    report = replay.build_report(table_path=ev.table_path,
                                 manifest_path=ev.manifest_path,
                                 source_path=ev.source_path, source_id=SOURCE_NAME)
    assert report["verdict"] == replay.REFUSED
    assert report["completeness_verdict"] == replay.INCOMPLETE
    assert any(f["reason"] == replay.OFFSETS_NOT_THE_KEPT_ROWS
               for f in report["completeness_failures"])


def test_a_locator_out_of_range_is_refused(tmp_path):
    ev = _bundle(tmp_path)
    # the locator is inside the hashed proof, so an out-of-range one cannot survive
    # load_table; replay is asked directly, which is where the range check lives
    table = json.load(open(ev.table_path))
    table["records"][0]["source_row_index"] = 10 ** 6
    cols = replay.read_evidence(ev.source_path)
    out = replay.replay_records(table["records"], cols)
    assert out["n_failed"] >= 1
    assert out["failures"][0]["reason"] == replay.LOCATOR_OUT_OF_RANGE


def test_a_dropped_source_row_is_not_a_kept_row(tmp_path):
    """keep_for_DE=false rows sit INSIDE each contributor's span in the fixture, so an
    implementation that took a contiguous offset span, or forgot the filter, would
    build a different proof and fail here."""
    ev = _bundle(tmp_path)
    proof = kept_proof(raw_source_rows(default_specs()))
    for rec in json.load(open(ev.table_path))["records"]:
        key = (rec["target_id"], rec["condition"], rec["guide_id"])
        assert rec["pseudobulk_source_offsets"] == proof[key]["offsets"]
        # the offsets are NOT contiguous: a dropped row lies between them
        offsets = rec["pseudobulk_source_offsets"]
        assert offsets == sorted(offsets)
        assert offsets[-1] - offsets[0] > len(offsets) - 1


# --------------------------------------------------------------------------- #
# THE SYMBOL SCOPES, end to end through the strict verifier.
# --------------------------------------------------------------------------- #
def test_symbol_scopes_survive_a_strict_verified_run(synthetic_run):
    """The contract must not buy its refusals by dropping the hard rows."""
    import pandas as pd

    args = run_and_verify(synthetic_run())
    assert verify(args, strict=True) == 0

    screen = pd.read_parquet(os.path.join(args.out_dir, "screen.parquet"))
    symbols = screen[screen["target_id_namespace"] == "gene_symbol"]
    assert set(symbols["target_id"]) == set(SYMBOL_TARGETS)
    assert symbols["target_ensembl"].isna().all()       # null for every one of them
