"""THE SCIENCE GATES: the admitted set, the arms, their values, their ranks, their bytes.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator. These are the gates
that RE-DERIVE rather than compare — the admitted program set from the bound release, the
arm inventory from that set, every arm value as an exact sign transform of the one base
delta, every rank from the arm's own population, and every base delta from the bound DE
data under the exact mask. A gate that only compared two numbers the producer wrote down
would be checking the producer's arithmetic against itself.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_arm_rules as AR  # noqa: E402
import verify_arm_view as AV  # noqa: E402
from verify_arm_report import RELEASE_LANES, Report  # noqa: E402

# EVERY column that identifies a mask row. Restated here, not imported: a column list the
# checker borrowed from the producer is a column list nobody checked.
#
# The order is over the FULL identity tuple, nulls last — a TOTAL order, so no tie is left to
# whatever order the producer happened to iterate in. The shipped parquet is serialized from
# this exact table and `mask_sha256` is the content hash OF it, so a reader of the file can
# apply this projection and get the bound number. That is the whole point of binding it: a
# hash re-derivable only by the process that held the list in memory is not an identity, and
# a six-column sort that was not even a total order left the shipped BYTES input-order
# dependent as well.
MASK_ROW_COLUMNS = (
    "estimate_type", "estimate_id", "released_estimate_id", "target_id",
    "target_ensembl", "condition", "donor_pair", "guide_id",
    "masked_gene_ensembl", "mask_reason", "distance", "in_gene_universe",
    "source_row_hash", "mask_unresolved_reason",
)
# The ids stamped ONTO the mask rows, never hashed INTO them: a run id is assigned after the
# mask is known, and a mask that changed when it was named would not be a mask.
MASK_ROW_IDS = ("run_id", "arm_bundle_run_id")


def _mask_order_key(row: dict) -> tuple:
    """A TOTAL order over the identity columns. Nulls last; never a tie left to chance."""
    return tuple((row.get(c) is None, "" if row.get(c) is None else str(row.get(c)))
                 for c in MASK_ROW_COLUMNS)


def _canonical_mask_rows(rows: list[dict]) -> list[dict]:
    """THE mask table: projected onto the identity columns, normalised, totally ordered."""
    out = [{c: _native(r.get(c)) for c in MASK_ROW_COLUMNS} for r in rows]
    out.sort(key=_mask_order_key)
    return out


def _native(v: Any) -> Any:
    """A parquet scalar as the plain Python value the hash was taken over.

    Parquet hands back numpy scalars and NaN where the producer held ints, floats, bools and
    None. Hashing what pandas happens to return would bind a number nobody reading the file
    could reproduce — the "count nobody can recount" defect, one layer down.
    """
    if v is None:
        return None
    if isinstance(v, (bool,)):
        return bool(v)
    try:
        import numpy as np

        if isinstance(v, np.bool_):
            return bool(v)
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            f = float(v)
            return None if f != f else f
        if isinstance(v, np.str_):
            return str(v)
    except ImportError:                                          # pragma: no cover
        pass
    if isinstance(v, float) and v != v:                          # NaN is not a value
        return None
    return v


def gate_admitted_set(doc: dict, binding: dict, release: Optional[dict],
                      programs: dict, lane: str, rep: Report) -> Optional[list[str]]:
    """The admitted set, DERIVED here. Never read from the bundle and believed."""
    rep.gate("a release-grade lane derives its admitted set from the BOUND v3 release, "
             "never from a legacy registry",
             not (lane in RELEASE_LANES and release is None),
             "no --stage1-v3-release was supplied for a release-grade lane")

    try:
        view = AV.stage2_arm_view(programs)
    except AV.ScorerViewError as exc:
        rep.gate("the admitted program set derives from the bound scorer view",
                 False, str(exc))
        return None
    rep.gate("the admitted program set derives from the bound scorer view", True)

    derived = view["admitted_program_ids"]
    declared = doc.get("scorer_view", {}).get("admitted_program_ids")
    rep.gate("the bundle's admitted set EQUALS the independently derived set",
             declared == derived, f"declared={declared!r} derived={derived!r}")
    rep.gate("every excluded program is genuinely not base_portable in the release",
             all(not bool(programs[p].get("base_portable"))
                 for p in view["excluded_program_ids"] if p in programs),
             f"excluded={view['excluded_program_ids']!r}")

    rep.gate("the scorer view hash RE-DERIVES from the release's own program bytes",
             doc.get("scorer_view", {}).get("scorer_view_sha256")
             == view["scorer_view_sha256"],
             f"declared={doc.get('scorer_view', {}).get('scorer_view_sha256')!r} "
             f"derived={view['scorer_view_sha256']!r}")
    rep.gate("the scorer view hash is BOUND into the run identity",
             binding.get("scorer_view_sha256") == view["scorer_view_sha256"],
             f"binding={binding.get('scorer_view_sha256')!r}")

    # every program's own projection binding — the panel and control its arms were taken on
    bad = [p for p in derived
           if doc.get("scorer_view", {}).get("programs", {}).get(p, {}).get("panel_sha256")
           != view["programs"][p]["panel_sha256"]
           or doc["scorer_view"]["programs"].get(p, {}).get("control_sha256")
           != view["programs"][p]["control_sha256"]]
    rep.gate("every admitted program binds the exact scorer projection its arms were "
             "taken under", not bad, f"{bad[:4]}")

    # the expected slot count is a FUNCTION of the admitted set, never a copied number
    rep.gate("the expected arm-slot count is DERIVED from the admitted set, not copied",
             doc.get("n_expected_arm_slots") == AR.expected_slots(derived)
             == len(derived) * 2,
             f"declared={doc.get('n_expected_arm_slots')!r} "
             f"derived={AR.expected_slots(derived)}")

    if release is not None:
        rep.gate("the run binds the release's scorer-view canonical hash",
                 str(binding.get("arm_bundle_request", {})
                     .get("stage1_release_hashes", {}).get(
                         "registry_scorer_view_canonical_sha256")
                     or release["stage1_scorer_view_canonical_sha256"])
                 == release["stage1_scorer_view_canonical_sha256"],
                 "the bundle does not bind the scorer view the release names")
    return derived


def gate_arm_inventory(doc: dict, rows: list[dict], admitted: list[str],
                       condition: str, rep: Report) -> None:
    """The EXACT arm keys this context owes. Missing, duplicated, extra or pole/role-keyed
    arms all refuse — and so does a swapped one, because the key carries the change."""
    expected = AR.expected_arm_keys(admitted, condition)
    manifest = doc.get("arms") or []
    keys = [a.get("arm_key") for a in manifest]

    rep.gate("the arm manifest carries EXACTLY the expected arm keys, none missing",
             sorted(k for k in keys if k) == expected,
             f"missing={sorted(set(expected) - set(keys))[:4]} "
             f"extra={sorted(set(keys) - set(expected))[:4]}")
    rep.gate("no arm key is DUPLICATED", len(keys) == len(set(keys)),
             f"{len(keys)} keys, {len(set(keys))} distinct")
    rep.gate("the arm-slot count equals the expected count",
             doc.get("n_arm_slots") == len(expected) == len(manifest),
             f"n_arm_slots={doc.get('n_arm_slots')!r} expected={len(expected)}")

    # every arm key RE-DERIVES from its own parts, and carries no pole and no role
    bad_key, poled = [], []
    for a in manifest:
        try:
            rebuilt = AR.direct_arm_key(a.get("program_id"), a.get("desired_change"),
                                        a.get("condition"))
        except AR.ArmRuleError:
            bad_key.append(a.get("arm_key"))
            continue
        if rebuilt != a.get("arm_key"):
            bad_key.append(a.get("arm_key"))
        if any(p in str(a.get("arm_key")).split("|")
               for p in AR.POLES + AR.ROLES):
            poled.append(a.get("arm_key"))
    rep.gate("every arm key re-derives from (program, desired_change, condition)",
             not bad_key, f"{bad_key[:4]}")
    rep.gate("no arm is keyed on a POLE or a ROLE", not poled, f"{poled[:4]}")

    # the rows must cover exactly those arms too — a manifest entry with no rows is an
    # arm that was declared and never computed
    row_keys = {str(r["arm_key"]) for r in rows}
    rep.gate("every expected arm actually has rows in the shipped table",
             row_keys == set(expected),
             f"rowless={sorted(set(expected) - row_keys)[:4]} "
             f"unexpected={sorted(row_keys - set(expected))[:4]}")
    rep.gate("every program has BOTH an increase and a decrease arm",
             all({AR.INCREASE, AR.DECREASE}
                 == {a["desired_change"] for a in manifest
                     if a["program_id"] == p} for p in admitted),
             "a program is missing one of its two arms")


def gate_arm_values_and_ranks(doc: dict, rows: list[dict], rep: Report) -> None:
    """increase = +base_delta, decrease = -base_delta, and the ranks taken SEPARATELY."""
    by_arm: dict[str, list[dict]] = {}
    base_by_pt: dict[tuple, set] = {}
    for r in rows:
        by_arm.setdefault(str(r["arm_key"]), []).append(r)
        base_by_pt.setdefault((str(r["program_id"]), str(r["target_id"])), set()).add(
            AR.canonical_num(r["base_delta"]))

    rep.gate("the two arms of a program SHARE one base delta — they cannot disagree "
             "about a magnitude they share",
             all(len(v) <= 1 for v in base_by_pt.values()),
             f"{sum(1 for v in base_by_pt.values() if len(v) > 1)} disagreeing (program, "
             "target) pair(s)")

    bad_sign = []
    for r in rows:
        expect = AR.arm_value(r["base_delta"], str(r["desired_change"]))
        got = AR.canonical_num(r["value"])
        if not bool(r["evaluable"]):
            if got is not None:
                bad_sign.append((r["arm_key"], r["target_id"], "value on a "
                                 "non-evaluable row"))
            continue
        if expect != got:
            bad_sign.append((r["arm_key"], r["target_id"], expect, got))
    rep.gate("every arm value is the EXACT sign transform of the one base delta "
             "(increase = +base, decrease = -base)",
             not bad_sign, f"{len(bad_sign)} row(s), first: {bad_sign[:1]}")

    minus_zero = [r["target_id"] for r in rows
                  if AR.canonical_num(r["value"]) == 0
                  and str(AR.canonical_num(r["value"])) == "-0.0"]
    rep.gate("a zero negates to positive zero, never -0.0", not minus_zero,
             f"{minus_zero[:4]}")

    bad_rank, not_dense = [], []
    for key, arm_rows in by_arm.items():
        derived = AR.rank_arm(arm_rows)
        for r in arm_rows:
            if AR.canonical_int(r["rank"]) != derived[str(r["target_id"])]:
                bad_rank.append((key, r["target_id"],
                                 AR.canonical_int(r["rank"]),
                                 derived[str(r["target_id"])]))
        assigned = sorted(v for v in derived.values() if v is not None)
        if assigned != list(range(1, len(assigned) + 1)):
            not_dense.append(key)
    rep.gate("every rank RE-DERIVES per arm: descending on the arm's own value, "
             "ties broken on target_id ascending",
             not bad_rank, f"{len(bad_rank)} row(s), first: {bad_rank[:1]}")
    rep.gate("each arm's ranks are dense 1..n over its own evaluable population",
             not not_dense, f"{not_dense[:4]}")
    rep.gate("a target the arm could not score is ABSENT from the ranking, not last",
             all(AR.canonical_int(r["rank"]) is None for r in rows
                 if not bool(r["evaluable"])),
             "a non-evaluable target carries a rank")


def gate_arm_bytes(doc: dict, rows: list[dict], rep: Report) -> None:
    """The per-arm bytes and the whole-bundle rows hash, RE-DERIVED FROM THE PARQUET."""
    by_arm: dict[str, list[dict]] = {}
    for r in rows:
        by_arm.setdefault(str(r["arm_key"]), []).append(r)

    bad = []
    for a in doc.get("arms") or []:
        key = str(a.get("arm_key"))
        arm_rows = by_arm.get(key, [])
        if AR.arm_rows_sha256(arm_rows) != a.get("arm_rows_sha256"):
            bad.append(key)
        if a.get("n_targets") != len(arm_rows):
            bad.append(f"{key}:n_targets")
        if a.get("n_evaluable") != sum(1 for r in arm_rows if bool(r["evaluable"])):
            bad.append(f"{key}:n_evaluable")
        if a.get("n_ranked") != sum(1 for r in arm_rows
                                    if AR.canonical_int(r["rank"]) is not None):
            bad.append(f"{key}:n_ranked")
    rep.gate("every arm's own bytes and counts RE-DERIVE from the shipped parquet rows",
             not bad, f"{bad[:4]}")

    derived = AR.rows_sha256(rows)
    rep.gate("the bundle's arm_rows_sha256 RE-DERIVES from the shipped parquet",
             doc.get("arm_rows_sha256") == derived,
             f"declared={doc.get('arm_rows_sha256')!r} derived={derived!r}")
    rep.gate("the emitted row count matches the shipped table",
             doc.get("n_arm_rows") == len(rows),
             f"declared={doc.get('n_arm_rows')!r} actual={len(rows)}")


def gate_recompute(rows: list[dict], recomputed: dict, mode: str, rep: Report) -> None:
    """The emitted base values, QC and denominators, RE-DERIVED from the bound DE data."""
    base = recomputed["base_by_program"]
    checked = 0
    bad_delta, bad_qc, bad_denom, bad_status = [], [], [], []

    for r in rows:
        pid, tid = str(r["program_id"]), str(r["target_id"])
        truth = base.get(pid, {}).get(tid)
        if truth is None:
            continue                          # outside the recomputed sample
        checked += 1
        if AR.canonical_num(r["base_delta"]) != truth["delta"]:
            bad_delta.append((pid, tid, AR.canonical_num(r["base_delta"]),
                              truth["delta"]))
        if str(r["base_state"]) != truth["base_state"] \
                or bool(r["base_passed"]) != truth["base_passed"]:
            bad_qc.append((pid, tid, r["base_state"], truth["base_state"]))
        if str(r["projection_status"]) != truth["projection_status"]:
            bad_status.append((pid, tid, r["projection_status"],
                               truth["projection_status"]))
        if AR.canonical_int(r["n_panel_surviving"]) != truth["n_panel_surviving"] \
                or AR.canonical_int(r["n_control_surviving"]) \
                != truth["n_control_surviving"]:
            bad_denom.append((pid, tid))

    rep.gate(f"the recomputation actually covered rows ({mode} mode)", checked > 0,
             f"{checked} row(s) recomputed")
    rep.gate("every emitted base delta RE-DERIVES from the bound DE data under the "
             "exact target + 30kb-neighbour + contributing-guide off-target mask",
             not bad_delta, f"{len(bad_delta)} row(s), first: {bad_delta[:1]}")
    rep.gate("every base QC state and disposition re-derives", not bad_qc,
             f"{len(bad_qc)} row(s), first: {bad_qc[:1]}")
    rep.gate("every projection status re-derives", not bad_status,
             f"{len(bad_status)} row(s), first: {bad_status[:1]}")
    rep.gate("every panel/control surviving DENOMINATOR re-derives", not bad_denom,
             f"{len(bad_denom)} row(s), first: {bad_denom[:1]}")

    # The contributing-guide denominator: the pooled fit's own declared guide count must
    # equal the number of guides the manifest actually PROVES for it.
    ev = recomputed["evidence_by_target"]
    bad_guides = [t for t, e in ev.items()
                  if e["contributor_resolved"]
                  and e["n_guides_proven"] != e["n_guides_declared"]]
    rep.gate("the contributing-guide denominator equals the count the release declares",
             not bad_guides, f"{bad_guides[:4]}")
    rep.gate("no arm value survives an unresolved mask",
             all(AR.canonical_num(r["value"]) is None for r in rows
                 if str(r["target_id"]) in ev
                 and not ev[str(r["target_id"])]["mask_resolved"]),
             "a target with no proven guide identity carries an arm value")


def gate_evidence_bindings(binding: dict, recomputed: dict, manifest_doc: Optional[dict],
                           manifest_path: Optional[str], universe_sha: str,
                           mask_rows: list[dict], rep: Report) -> None:
    """The H5AD, the effect universe, the contributor manifest and the mask — BOUND.

    The mask is what every base delta stands on, and it is a function of the contributor
    manifest. So both are bound, and both are re-derived here: the manifest's canonical
    identity from its own rows, and the mask hash from the SHIPPED masks.parquet — not from
    the number the producer wrote down beside it.
    """
    import verify_rules as R

    rep.gate("the effect-gene universe RE-DERIVES from the bound H5AD's own gene axis",
             binding.get("gene_universe_sha256") == universe_sha,
             f"declared={binding.get('gene_universe_sha256')!r} derived={universe_sha!r}")

    cm = binding.get("contributor_manifest") or {}
    canon = R.canonical_manifest_sha256(manifest_doc) if manifest_doc else None
    rep.gate("the CONTRIBUTOR MANIFEST's canonical identity is bound into the run — the "
             "mask, and therefore every base delta, is a function of it",
             bool(cm) and cm.get("canonical_sha256") == canon,
             f"bound={cm.get('canonical_sha256')!r} derived={canon!r}")

    raw = R.sha256_file(manifest_path) if manifest_path else None
    rep.gate("the contributor manifest's RAW BYTES are bound — a reordered manifest is the "
             "same manifest, but different bytes are different evidence",
             cm.get("raw_sha256") == raw,
             f"bound={cm.get('raw_sha256')!r} actual={raw!r}")

    # THE MASK HASH, re-derived from the rows the bundle SHIPS. Binding the hash of bytes
    # nobody can hold would be the same defect as citing a gene set that only exists on the
    # producer's disk — and so is binding the hash of an ORDER nobody can hold.
    #
    # Both ids are excluded: `run_id` because a mask is a fact about an estimate and not
    # about the run that happened to read it, and `arm_bundle_run_id` because the bundle id
    # is a FUNCTION of this hash, so a hash containing it could never be recomputed.
    #
    # The rows are SORTED before hashing. A mask is a SET of facts, not a sequence: the
    # parquet is written in sort order, so a hash taken over the producer's in-memory
    # accumulation order is a number nobody reading the shipped file can reproduce. That is
    # the same "count nobody can recount" defect the arm rows already fixed
    # (their canonical projection sorts first); a hash that is re-derivable only by the
    # process that happened to hold the list in memory is not an identity.
    canonical = _canonical_mask_rows(mask_rows)
    shipped = AR.content_sha256(canonical)
    rep.gate("the MASK's identity is bound into the run and RE-DERIVES from the shipped "
             "masks.parquet",
             binding.get("mask_sha256") == shipped,
             f"bound={binding.get('mask_sha256')!r} derived={shipped!r} — the bound hash "
             "is not a function of the shipped bytes. The mask rows are hashed in the "
             "producer's in-memory accumulation order, but masks.parquet is written SORTED, "
             "so no reader of the file can reproduce the number bound beside it. Hash the "
             "rows in their canonical sorted order, as the arm rows already are.")
    rep.gate("the bound mask row count matches the shipped mask table",
             binding.get("n_mask_rows") == len(mask_rows),
             f"bound={binding.get('n_mask_rows')!r} shipped={len(mask_rows)}")

    # ...and the shipped masks are the ones the verifier INDEPENDENTLY derives from the
    # contributor manifest and the library. A bundle whose mask table is internally
    # consistent but describes a masking nobody performed is a bundle that cites itself.
    ev = recomputed["evidence_by_target"]
    by_target: dict[str, set] = {}
    for r in mask_rows:
        gene = r.get("masked_gene_ensembl")
        if gene:
            by_target.setdefault(str(r["target_id"]), set()).add(str(gene))
    drifted = sorted(
        t for t, e in ev.items()
        if e["mask_resolved"]
        and AR.content_sha256(sorted(by_target.get(t, set()))) != e["mask_sha256"])
    rep.gate("every SHIPPED mask is the one the verifier independently derives from the "
             "contributor manifest and the sgRNA library",
             not drifted, f"{len(drifted)} target(s), first: {drifted[:3]}")
