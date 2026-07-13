"""The INDEPENDENT pathway RELEASE verifier — the aggregate envelope over the six bundles.

The per-bundle verifier (``verify_signature_matrix``) admits ONE (condition, source) pathway
bundle against the external primaries. A release is more than six admitted bundles: it is the
claim that they are the COMPLETE 3x2 grid — the AUTHORITATIVE conditions x gene-set sources the
Stage-1 v3 release declares — computed against ONE Stage-1 release, ONE scorer view, ONE code
identity and ONE solver lock, each cell distinct, and each cell INDEPENDENTLY admitted. Nothing
in a single bundle can see that: a missing cell, a duplicate, a cell built on a different
release, a locally-invalid bundle — each looks fine on its own.

Everything the release stands on is anchored OUTWARD, never derived from the bundles being
judged (that is the whole reseal-proofing story):

  * the condition + source UNIVERSE  -> the Stage-1 v3 release ``selector`` (``--release``),
    not the set the bundles happen to name (a self-consistent Foo/Bar/Baz x X/Y forgery would
    otherwise pass);
  * the solver lock                  -> the pinned ``2983d140…`` constant, not a value the
    bundle carries;
  * each cell's LOCAL validity        -> the SEPARATE independent per-bundle verification report
    (``spot.stage02_signature_matrix_verification.v1``), whose self-hash + verdict + full gate
    inventory + re-derived run id this re-checks — NEVER the producer's own
    ``pathway_verification.json``;
  * the producer INVENTORY            -> required, PENDING, and byte-bound to what landed on disk;
    its ``release_id`` must re-derive.

LANE-SPECIFIC, NOT TEMPORAL. The envelope carries a pathway schema and a pathway verifier id.
Its self-hash field (``report_id``) and its ``binds`` block follow the integration adapter's
rule (``verify_release_envelope``) so the aggregate can consume it — but the schema string stays
pathway-specific, so a temporal envelope can never be presented for a pathway release. (The one
change this asks of the integration is to ADD the pathway admission schema to its accepted set;
see the W1 coordination note.)

GENERATOR != VERIFIER. It imports no producer module — only ``json``/``hashlib`` and the
verifier-side ``verify_rules``. It never edits producer bytes; it reads them and writes ONE new
file, the admission envelope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from . import verify_rules as R  # noqa: E402

# LANE-SPECIFIC identities. Never the temporal ones.
ADMISSION_SCHEMA = "spot.stage02_pathway_arm_external_admission.v1"
VERIFIER_ID = "spot.stage02.pathway.arm.independent_verifier.v1"
ADMISSION_FILE = "pathway_arm_external_admission.json"
REPORT_ID_FIELD = "report_id"                     # the integration adapter's self-hash field

# The PENDING producer inventory this admits a lane against (pathway_release.py).
RELEASE_SCHEMA = "spot.stage02_pathway_arm_release.v1"
RELEASE_FILE = "pathway_arm_release.json"

# The AUTHORITATIVE Stage-1 v3 release: the ONLY source of the condition + source universe.
STAGE1_RELEASE_SCHEMA = "spot.stage01_v3_release.v1"

# The INDEPENDENT per-bundle verifier whose reports prove each cell is locally valid.
BUNDLE_REPORT_SCHEMA = "spot.stage02_signature_matrix_verification.v1"
BUNDLE_VERIFIER_ID = "spot.stage02.signature_matrix.verifier.v1"

# The pinned Stage-2 solver lock — an EXTERNAL constant, never a value the bundle supplies.
STAGE2_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

RUN_ID_LEN = 16
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "pathway_provenance.json"

ADMIT, REFUSE = "ADMIT", "REFUSE"                 # byte-exact tokens the aggregate maps
PASS, FAIL = "pass", "fail"

# THE NAMED GATE INVENTORY — the exact list the envelope carries.
G_RELEASE_ANCHOR = "the_condition_and_source_universe_comes_from_the_authoritative_stage1_release"
G_TOPOLOGY = "the_bundles_are_exactly_the_authoritative_condition_x_source_grid_once_each"
G_REOPEN = "every_bundle_reopens_and_its_nonnull_run_id_rederives_from_its_own_binding"
G_ONE_RELEASE = "one_nonnull_scorer_view_code_identity_stage1_release_and_pinned_solver_lock"
G_DISTINCT = "every_cell_has_a_distinct_nonnull_run_id_and_distinct_nonnull_arm_record_bytes"
G_SOURCE = "each_bundle_agrees_with_itself_about_which_condition_x_source_cell_it_is"
G_BUNDLE_ADMITTED = "every_cell_carries_an_independent_admitting_per_bundle_verification_report"
G_INVENTORY_PRESENT = "the_producer_inventory_is_present_pending_rederives_and_binds_this_verifier"
G_INVENTORY_BYTES = "the_producer_inventory_binds_the_exact_bytes_that_landed_on_disk"
GATE_INVENTORY = (G_RELEASE_ANCHOR, G_TOPOLOGY, G_REOPEN, G_ONE_RELEASE, G_DISTINCT, G_SOURCE,
                  G_BUNDLE_ADMITTED, G_INVENTORY_PRESENT, G_INVENTORY_BYTES)


def _check(name, ok, detail=""):
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _json(path):
    with open(path) as fh:
        return json.load(fh)


def _hashes(path):
    with open(path, "rb") as fh:
        raw = hashlib.sha256(fh.read()).hexdigest()
    return {"raw_sha256": raw, "canonical_sha256": R.content_sha256(_json(path))}


def _norm_source(s):
    """Case-fold a gene-set source id. The Stage-1 release names sources display-cased
    (``GO-BP``, ``Reactome``); the bundles and ids use lowercase (``go_bp``, ``reactome``)."""
    return None if s is None else str(s).strip().lower().replace("-", "_")


# --------------------------------------------------------------------------- #
# The authoritative universe: read it from the Stage-1 v3 release, never the bundles.
# --------------------------------------------------------------------------- #
def _authoritative_universe(release_path):
    """(conditions, sources, detail) from ``release.selector`` — or (None, None, why)."""
    if not release_path or not os.path.exists(release_path):
        return None, None, ("no authoritative Stage-1 v3 release was supplied (--release); the "
                            "condition/source universe may not be taken from the bundles being "
                            "judged — a self-consistent wrong-universe forgery would pass")
    try:
        rel = _json(release_path)
    except Exception as exc:                            # noqa: BLE001
        return None, None, f"the Stage-1 release is not readable JSON: {exc}"
    if rel.get("schema") != STAGE1_RELEASE_SCHEMA:
        return None, None, (f"the release schema is {rel.get('schema')!r}, not "
                            f"{STAGE1_RELEASE_SCHEMA!r} — this is not the Stage-1 v3 release")
    selector = rel.get("selector") or {}
    conds = [str(c) for c in (selector.get("conditions") or [])]
    srcs = [_norm_source(s) for s in (selector.get("pathway_sources") or [])]
    if not conds or not srcs:
        return None, None, ("the release selector declares no conditions and/or no "
                            "pathway_sources; the universe is not derivable")
    return conds, srcs, f"conditions={conds}; sources={srcs}"


def verify(*, bundle_dirs: list[str], inventory_path: Optional[str],
           release_path: Optional[str], bundle_report_paths: Optional[list[str]]) -> dict[str, Any]:
    """Re-open the six bundles and re-derive the aggregate release contract, anchored outward."""
    checks: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []

    # ---- G_RELEASE_ANCHOR: the authoritative condition/source universe ----
    auth_conds, auth_srcs, anchor_detail = _authoritative_universe(release_path)
    checks.append(_check(G_RELEASE_ANCHOR, auth_conds is not None and auth_srcs is not None,
                         anchor_detail))
    auth_cond_set = set(auth_conds or [])
    auth_src_set = set(auth_srcs or [])

    # ---- reopen every bundle; re-derive its identity from its own binding ----
    reopen_bad = []
    for d in bundle_dirs:
        pp, bp = os.path.join(d, PROVENANCE_FILE), os.path.join(d, BUNDLE_FILE)
        if not (os.path.exists(pp) and os.path.exists(bp)):
            reopen_bad.append(f"{d}: missing {PROVENANCE_FILE} or {BUNDLE_FILE}")
            continue
        prov, doc = _json(pp), _json(bp)
        binding = prov.get("run_binding") or {}
        rederived = R.content_sha256(binding) if binding else None
        run_id = prov.get("pathway_run_id")
        if not run_id or rederived is None or rederived != prov.get("pathway_run_sha256") \
                or rederived[:RUN_ID_LEN] != run_id:
            reopen_bad.append(f"{d}: pathway_run_id is null or does not re-derive from run_binding")
        bundles.append({
            "dir": d,
            "condition": binding.get("condition") or doc.get("condition"),
            "source": _norm_source(binding.get("source") or doc.get("source")),
            "binding_condition": binding.get("condition"),
            "binding_source": _norm_source(binding.get("source")),
            "doc_condition": doc.get("condition"), "doc_source": _norm_source(doc.get("source")),
            "run_id": run_id,
            "scorer_view_sha256": binding.get("scorer_view_sha256"),
            "release_scorer_view_canonical_sha256":
                binding.get("release_scorer_view_canonical_sha256"),
            "code_identity": binding.get("code_identity"),
            "stage1_release_hashes": binding.get("stage1_release_hashes"),
            "env_lock_sha256": (binding.get("environment_lock") or {}).get("sha256"),
            "records_sha256": binding.get("records_sha256"),
            "arm_bundle_hashes": _hashes(bp), "provenance_hashes": _hashes(pp),
        })
    checks.append(_check(G_REOPEN, bool(bundles) and not reopen_bad, "; ".join(reopen_bad[:4])))

    # ---- G_TOPOLOGY: exactly the AUTHORITATIVE grid, once each ----
    cells = [(b["condition"], b["source"]) for b in bundles]
    got: dict[Any, int] = {}
    for c in cells:
        got[c] = got.get(c, 0) + 1
    expected = {(c, s) for c in auth_cond_set for s in auth_src_set}
    dups = [c for c, n in got.items() if n > 1]
    unknown = sorted(k for k in got if k not in expected)      # cells the release never shipped
    missing = sorted(expected - set(got))
    topo_ok = bool(expected) and len(bundles) == len(expected) and not dups \
        and not unknown and not missing
    checks.append(_check(
        G_TOPOLOGY, topo_ok,
        f"{len(bundles)} bundles vs authoritative grid of {len(expected)}; "
        f"duplicated {dups[:2]}; not-in-release {unknown[:2]}; missing {missing[:2]} — a "
        f"complete release is exactly the release's condition x source grid, once each"))

    # ---- G_ONE_RELEASE: one NONNULL binding each, and the pinned solver lock ----
    one_bad = []
    for key, label in (("scorer_view_sha256", "scorer view"),
                       ("release_scorer_view_canonical_sha256", "release scorer view"),
                       ("code_identity", "code identity"),
                       ("stage1_release_hashes", "Stage-1 release"),
                       ("env_lock_sha256", "solver lock")):
        vals = [b.get(key) for b in bundles]
        if any(v is None for v in vals):
            one_bad.append(f"a bundle binds a NULL {label} — an unbound field is not a shared one")
            continue
        if len({json.dumps(v, sort_keys=True) for v in vals}) > 1:
            one_bad.append(f"the release does not share ONE {label} across its bundles")
    # the solver lock is not merely single-valued: it must BE the pinned constant.
    locks = {b.get("env_lock_sha256") for b in bundles}
    if bundles and locks != {STAGE2_SOLVER_LOCK_SHA256}:
        one_bad.append("the bound solver lock is not the pinned 2983d140… constant")
    checks.append(_check(G_ONE_RELEASE, bool(bundles) and not one_bad, "; ".join(one_bad[:3])))

    # ---- G_DISTINCT: distinct NONNULL run id + distinct NONNULL arm record bytes ----
    run_ids = [b["run_id"] for b in bundles]
    recs = [b["records_sha256"] for b in bundles]
    distinct_ok = (bool(bundles)
                   and all(x is not None for x in run_ids) and len(set(run_ids)) == len(run_ids)
                   and all(x is not None for x in recs) and len(set(recs)) == len(recs))
    checks.append(_check(
        G_DISTINCT, distinct_ok,
        "a cell has a null run id or null arm record bytes, or two cells share either — six "
        "identical bundles are not a release, they are one bundle counted six times"))

    # ---- G_SOURCE: each bundle agrees with itself about which cell it is ----
    src_bad = []
    for b in bundles:
        if b["source"] is None or (auth_src_set and b["source"] not in auth_src_set):
            src_bad.append(f"{b['dir']}: source {b['source']!r} is null or not in the release")
        for field, dv, bv in (("source", b["doc_source"], b["binding_source"]),
                              ("condition", b["doc_condition"], b["binding_condition"])):
            if dv is not None and bv is not None and dv != bv:
                src_bad.append(f"{b['dir']}: arm_bundle {field} {dv!r} != run_binding {bv!r}")
    checks.append(_check(G_SOURCE, bool(bundles) and not src_bad, "; ".join(src_bad[:3])))

    # ---- G_BUNDLE_ADMITTED: every cell has an INDEPENDENT admitting per-bundle report ----
    checks.append(_verify_bundle_reports(bundle_report_paths, bundles))

    # ---- G_INVENTORY_PRESENT + G_INVENTORY_BYTES ----
    inv_present, inv_bytes, inv_release_id, inv_raw = _verify_inventory(inventory_path, bundles)
    checks.append(inv_present)
    checks.append(inv_bytes)

    failures = [c for c in checks if c["status"] != PASS]
    verdict = ADMIT if not failures else REFUSE
    body = {
        "schema_version": ADMISSION_SCHEMA,
        "verifier_id": VERIFIER_ID,
        "lane": "pathway",
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "authoritative_universe": {"conditions": auth_conds, "sources": auth_srcs},
        "n_bundles": len(bundles),
        "cells": sorted([[b["condition"], b["source"]] for b in bundles]),
        "bundle_run_ids": sorted(x for x in run_ids if x),
        # the integration adapter's binding block: the release this envelope admits.
        "binds": {"producer_release_id": inv_release_id,
                  "producer_release_raw_sha256": inv_raw,
                  "inventory_raw_sha256": inv_raw},
        "gate_inventory": list(GATE_INVENTORY),
        "gates": [{"check": c["check"], "status": c["status"]} for c in checks],
        "n_failed": len(failures),
        "verdict": verdict,
    }
    # report_id: the integration self-hash rule — canonical JSON excluding ONLY report_id.
    body[REPORT_ID_FIELD] = R.content_sha256(body)
    return {"body": body, "checks": checks, "verdict": verdict}


def _verify_bundle_reports(report_paths, bundles):
    """Every cell must carry an INDEPENDENT admitting per-bundle verification report.

    NEVER the producer's ``pathway_verification.json`` — that is the generator marking its own
    homework. Only the SEPARATE independent verifier's report counts, and every one is re-checked:
    its self-hash recomputes, its verdict is admit, its full gate inventory passes, and its
    RE-DERIVED run ids are the bundles' — so a locally-invalid (rejected) cell cannot pass.
    """
    want_ids = {b["run_id"] for b in bundles if b["run_id"]}
    if not report_paths:
        return _check(G_BUNDLE_ADMITTED, False,
                      "no independent per-bundle verification reports were supplied "
                      "(--bundle-report); a release may not be admitted over cells whose local "
                      "validity was never independently checked")
    seen_ids: set[str] = set()
    bad = []
    for p in report_paths:
        if not os.path.exists(p):
            bad.append(f"{p}: missing report")
            continue
        try:
            rep = _json(p)
        except Exception as exc:                        # noqa: BLE001
            bad.append(f"{p}: unreadable report ({exc})")
            continue
        if rep.get("schema_version") != BUNDLE_REPORT_SCHEMA \
                or rep.get("verifier_id") != BUNDLE_VERIFIER_ID:
            bad.append(f"{p}: not an independent signature-matrix verification report")
            continue
        body = {k: v for k, v in rep.items() if k != "report_sha256"}
        recomputed = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if recomputed != rep.get("report_sha256"):
            bad.append(f"{p}: report self-hash does not recompute (tampered report)")
            continue
        gates = rep.get("gates") or []
        if rep.get("verdict") != "admit" or rep.get("n_failed") not in (0, "0") \
                or not gates or any(g.get("status") != PASS for g in gates):
            bad.append(f"{p}: the per-bundle report is not a clean ADMIT")
            continue
        rids = rep.get("run_ids") or []
        if not rids:
            bad.append(f"{p}: the report names no run id, so it binds to no bundle")
            continue
        seen_ids.update(rids)
    missing = sorted(want_ids - seen_ids)
    extra = sorted(seen_ids - want_ids)
    if missing:
        bad.append(f"cells with no admitting report: {missing[:3]}")
    if extra:
        bad.append(f"reports for cells not in this release: {extra[:3]}")
    ok = bool(want_ids) and not bad
    return _check(G_BUNDLE_ADMITTED, ok, "; ".join(bad[:4]))


def _entry_cell(e):
    """(condition, normalized source) of an inventory entry — flat OR generic context form."""
    ctx = e.get("context") if isinstance(e.get("context"), dict) else {}
    cond = e.get("condition") or ctx.get("condition")
    src = e.get("source") or ctx.get("gene_set_source") or ctx.get("source")
    return (str(cond) if cond is not None else None, _norm_source(src))


def _verify_inventory(inventory_path, bundles):
    """Require the PENDING producer inventory, re-derive its id, and bind the exact bytes.

    Handles the real pathway producer shape (``pathway_release.py``): flat ``condition``/
    ``source`` entries (or the generic ``context``/``relative_dir`` form), a ``files`` map keyed
    by bare top-file name, and ``release_id == content_hash(inventory - release_id)``.
    """
    none = (None, None)
    if not inventory_path or not os.path.exists(inventory_path):
        return (_check(G_INVENTORY_PRESENT, False,
                       "no pathway_arm_release.json producer inventory was supplied"),
                _check(G_INVENTORY_BYTES, False, "no inventory to bind"), *none)
    try:
        with open(inventory_path, "rb") as fh:
            raw = fh.read()
        inv = json.loads(raw)
        inv_raw_sha = hashlib.sha256(raw).hexdigest()
    except Exception as exc:                            # noqa: BLE001
        return (_check(G_INVENTORY_PRESENT, False, f"the inventory is not readable: {exc}"),
                _check(G_INVENTORY_BYTES, False, "the inventory did not load"), *none)

    present = []
    if inv.get("schema_version") != RELEASE_SCHEMA:
        present.append(f"inventory schema is {inv.get('schema_version')!r}, not {RELEASE_SCHEMA!r}")
    ea = inv.get("external_admission") or {}
    if ea.get("status") != "pending":
        present.append("the producer inventory is not PENDING — a producer that admits itself "
                       "is marking its own homework")
    req = inv.get("required_verifier_id") or ea.get("required_verifier_id")
    if req is not None and req != VERIFIER_ID:
        present.append(f"the inventory requires verifier {req!r}, not this one ({VERIFIER_ID!r})")
    # RE-DERIVE the inventory's own content address: release_id = hash(inventory - release_id).
    release_id = inv.get("release_id")
    rederived = R.content_sha256({k: v for k, v in inv.items() if k != "release_id"})
    if release_id is not None and release_id != rederived:
        present.append("the inventory release_id does not re-derive from its own bytes")
    present_ok = not present

    # G_INVENTORY_BYTES: the inventory names exactly the disk cells and binds their real bytes.
    byte_bad = []
    inv_entries = inv.get("bundles") or inv.get("inventory") or []
    inv_by_cell = {_entry_cell(e): e for e in inv_entries}
    disk_by_cell = {(b["condition"], b["source"]): b for b in bundles}
    if set(inv_by_cell) != set(disk_by_cell):
        byte_bad.append("the inventory names a different set of cells than landed on disk")
    for cell, b in disk_by_cell.items():
        e = inv_by_cell.get(cell)
        if e is None:
            continue
        files = e.get("files") or {}
        for name, want in ((BUNDLE_FILE, b["arm_bundle_hashes"]),
                           (PROVENANCE_FILE, b["provenance_hashes"])):
            f = files.get(name) or {}
            if f.get("raw_sha256") != want["raw_sha256"] or \
                    f.get("canonical_sha256") != want["canonical_sha256"]:
                byte_bad.append(f"{cell}: the inventory's {name} bytes are not the ones on disk")
        bid = e.get("bundle_id")
        if bid is not None and b["run_id"] is not None and str(bid) != str(b["run_id"]):
            byte_bad.append(f"{cell}: the inventory names a different bundle id than the bundle")
    return (_check(G_INVENTORY_PRESENT, present_ok, "; ".join(present[:3])),
            _check(G_INVENTORY_BYTES, present_ok and not byte_bad, "; ".join(byte_bad[:4])),
            release_id, inv_raw_sha)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m direct.verify_pathway_release",
        description="Independent Stage-2 pathway RELEASE verifier: re-opens the pathway bundles, "
                    "anchors the condition x source universe to the authoritative Stage-1 v3 "
                    "release, requires an independent admitting per-bundle report for every cell, "
                    "re-derives the aggregate contract (topology; one scorer view / code "
                    "identity / Stage-1 release / pinned solver lock; distinct cells), binds the "
                    "PENDING producer inventory, and emits a lane-specific content-addressed "
                    "pathway_arm_external_admission. Imports no producer module. Exit 0 = ADMIT, "
                    "nonzero = REFUSE.")
    ap.add_argument("--bundle", required=True, action="append", dest="bundles", metavar="DIR",
                    help="a pathway bundle dir (repeatable; the condition x source cells)")
    ap.add_argument("--release", default=None,
                    help="the AUTHORITATIVE Stage-1 v3 release json (selector.conditions + "
                         "selector.pathway_sources define the grid — NOT the bundles)")
    ap.add_argument("--bundle-report", action="append", dest="bundle_reports", default=None,
                    metavar="PATH", help="an INDEPENDENT per-bundle verification report "
                    "(repeatable; one admitting report per cell)")
    ap.add_argument("--inventory", default=None,
                    help="the PENDING producer root inventory pathway_arm_release.json")
    ap.add_argument("--out", required=True,
                    help=f"path to write {ADMISSION_FILE} (content-addressed, ADMIT/REFUSE)")
    args = ap.parse_args(argv)

    try:
        result = verify(bundle_dirs=list(args.bundles), inventory_path=args.inventory,
                        release_path=args.release,
                        bundle_report_paths=list(args.bundle_reports or []))
        body = result["body"]
    except Exception as exc:                            # a crash IS a refusal
        body = {"schema_version": ADMISSION_SCHEMA, "verifier_id": VERIFIER_ID,
                "lane": "pathway", "verdict": REFUSE, "n_failed": 1,
                "gates": [{"check": "verifier_completed_without_error", "status": FAIL}],
                "detail": f"{type(exc).__name__}: {exc}"}
        body[REPORT_ID_FIELD] = R.content_sha256(body)
        result = {"checks": [], "verdict": REFUSE}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(body, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"verdict": body["verdict"], "n_failed": body.get("n_failed"),
                      "out": args.out, REPORT_ID_FIELD: body[REPORT_ID_FIELD]}, indent=2))
    if body["verdict"] != ADMIT:
        for c in result.get("checks", []):
            if c["status"] != PASS:
                print(f"  REFUSE [{c['check']}] {c.get('detail', '')}", file=sys.stderr)
    return 0 if body["verdict"] == ADMIT else 1


if __name__ == "__main__":
    sys.exit(main())
