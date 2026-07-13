"""THE PER-BUNDLE SCAN for the aggregate verifier. Split out of ``verify_run_manifest``.

Reads each bundle's SHIPPED BYTES and collects every finding; it decides nothing. The gates
are named and judged by ``verify_run_manifest``. INDEPENDENCE RULE holds: nothing here is
imported from the producer.
"""
from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_bundle_rules as B  # noqa: E402
import verify_manifest_rules as R  # noqa: E402
import verify_release_rules as W  # noqa: E402  (the W5-audit rules)


def scan(*, bundles: list, bundles_root: str, programs: list, projection: dict,
         pinned: dict, expect_verifiers: dict, expected_code: dict,
         release: dict = None, env_lock_sha256: str = None) -> dict[str, Any]:
    """Every finding the bundles yield, collected. No verdicts."""
    filled: dict[str, list] = {lane: [] for lane in R.LANES}
    arm_values: dict = {}          # (from, to, program, dc) -> {target: value}
    stale, null_stage1, bad_preflight, bad_env = [], [], [], []
    bound_rankings: dict = {}      # relative_dir -> {ranking paths the arms bind}
    ids, codes, selections, inputs, methods = [], [], [], [], []
    geneset_by_source: dict[str, list] = {}
    convergences: list[tuple] = []
    missing, bad_bytes, not_all_arm, bad_map = [], [], [], []
    bad_projection, pair_stored, forbidden, unloadable, bad_hits = [], [], [], [], []
    bad_reports, bad_code, bad_gene_sets, batch_stored = [], [], [], []
    bad_keyed, bad_ranks = [], []

    for b in bundles:
        lane, bid = b.get("lane"), str(b.get("bundle_id"))
        ids.append(bid)
        path = (R.find_bundle_dir(bundles_root, str(b.get("out_dir")))
                if b.get("out_dir") else None)
        if lane not in R.LANES or path is None:
            missing.append(f"{bid}: bundle directory {b.get('out_dir')!r} not found")
            continue

        # (a) the required files exist and LOAD. An expected filename holding arbitrary
        #     bytes is not an artifact, however neatly it hashes.
        for fn in R.BUNDLE_FILES[lane]:
            fp = os.path.join(path, fn)
            if not os.path.exists(fp):
                missing.append(f"{bid}: missing {fn}")
            elif R.load_json(fp) is None:
                unloadable.append(f"{bid}/{fn}: not readable JSON — arbitrary bytes "
                                  "under an expected filename are not an artifact")

        # (b) EVERY file the bundle bound still hashes to what it bound.
        for fn, bound_sha in sorted((b.get("files") or {}).items()):
            fp = os.path.join(path, fn)
            if not os.path.exists(fp):
                missing.append(f"{bid}: bound {fn} is absent")
            elif R.file_sha256(fp) != bound_sha:
                bad_bytes.append(f"{bid}/{fn}: bound {str(bound_sha)[:16]}, on disk "
                                 f"{R.file_sha256(fp)[:16]}")

        # STALE RANKING FILES. A ranking nobody binds is a ranking nobody checked, and it
        # sits in the release looking exactly like evidence.
        stale += W.stale_rankings(path, R.load_json(
            os.path.join(path, "arm_bundle.json")), bid)

        inv = R.load_json(os.path.join(path, "arm_bundle.json"))
        prov = R.load_json(os.path.join(path, R.PROVENANCE_OF[lane]))
        report = (R.load_json(os.path.join(path, R.REPORT_OF[lane]))
                  if lane in R.REPORT_OF else None)
        if not isinstance(inv, dict) or not isinstance(prov, dict):
            continue
        if lane in R.REPORT_OF and not isinstance(report, dict):
            continue

        forbidden += R.forbidden_keys(inv) + R.forbidden_keys(prov)
        bad_keyed += R.check_keyed_provenance(prov, bid)
        pair_stored += R.pair_derived_keys(inv)
        batch_stored += R.batch_keys(inv)

        # (c) the bundle is an ALL-ARM bundle for its context.
        #
        # The context comes from the bundle's NATIVE shape, via the same normalizer the
        # producer side uses — `inv.get("context")` is a temporal-ism, and reading it here
        # gave Direct and pathway an EMPTY context, so `want_keys` was built over the wrong
        # slots and the all-arm check compared two sets of keys that could never match.
        norm = R.native_view(inv)          # the VERIFIER's own restatement of the shapes
        if norm is None:
            missing.append(
                f"{bid}: schema {str(inv.get('schema_version'))!r} names no known lane, or "
                "the bundle does not carry its lane's own id and context fields. Three "
                "producers, three contracts; an unrecognised fourth is a bundle nobody "
                "can read")
            continue
        if norm["lane"] != lane:
            missing.append(f"{bid}: the manifest calls this a {lane} bundle; its own schema "
                           f"{norm['schema_version']!r} makes it {norm['lane']}")
            continue
        ctx = norm["context"]
        arms = norm["arms"]
        want_keys = {R.arm_key(lane, p, dc, ctx)
                     for p in programs for dc in R.DESIRED_CHANGES}
        akf = norm["arm_key_field"]          # pathway names it `pathway_arm_key`
        got_keys = [str(a.get(akf)) for a in arms]
        if sorted(got_keys) != sorted(want_keys):
            not_all_arm.append(
                f"{bid}: carries {len(got_keys)} arms; an all-arm bundle for this context "
                f"is {len(want_keys)} ({len(programs)} programs x 2 desired changes). A "
                "pair-specific bundle leaves the rest of its slots empty")
        filled[lane] += got_keys
        bound_rankings[os.path.relpath(path, bundles_root).replace(os.sep, "/")] = {
            str((a.get("ranking") or {}).get("path")) for a in arms}

        membership = (R.load_json(os.path.join(
            path, ((inv.get("bindings") or {}).get("gene_set_membership") or {})
            .get("path", ""))) if lane == R.LANE_PATHWAY else None)

        for a in arms:
            key = str(a.get(akf))
            # (d) THE ARM IS PAIR-AGNOSTIC. It carries no role, no pole and no pair-derived
            #     program id, and none is required of it. What must hold is that its key and
            #     its declared desired_change agree, and that the change is one of the two.
            dc = a.get("desired_change")
            if dc not in R.DESIRED_CHANGES:
                bad_map.append(f"{key}: desired_change {dc!r} is not one of "
                               f"{list(R.DESIRED_CHANGES)}")
            elif key.split("|")[2:3] != [str(dc)]:
                bad_map.append(f"{key}: the key says "
                               f"{key.split('|')[2:3]} but the arm declares {dc!r}")
            if str(a.get("program_id")) not in programs:
                bad_map.append(f"{key}: program {a.get('program_id')!r} is not admitted by "
                               "the release")
            # (f) RECONSTRUCT the counts from the bound bytes. Never read them.
            ranking = R.load_json(os.path.join(
                path, (a.get("ranking") or {}).get("path", "")))
            # RETAINED-ROW semantics (W5): every target stays in the rows with rank null
            # when it is not rankable, so n_ranked is a count of RANKS, not of rows.
            # THE RANKS THEMSELVES, re-derived from the arm's own values. A resealed
            # rank-SWAP preserves every count and every hash, and reorders the evidence.
            bad_ranks += R.check_ranks(ranking, key)
            if lane == R.LANE_TEMPORAL:
                arm_values[(str(ctx.get("from_condition")),
                            str(ctx.get("to_condition")),
                            str(a.get("program_id")), str(dc))] = {
                    str(r.get("target_id")): r.get("arm_value")
                    for r in R.arm_records(ranking)}
            if a.get("n_ranked") is not None and \
                    int(a["n_ranked"]) != R.n_ranked(ranking):
                bad_hits.append(
                    f"{key}: declares n_ranked={a.get('n_ranked')}, but the bound ranking "
                    f"carries {R.n_ranked(ranking)} non-null ranks over "
                    f"{len(R.arm_records(ranking))} retained rows")
            if lane == R.LANE_PATHWAY:
                recomputed_hits = R.reconstruct_hits(membership, ranking)
                claimed_hits = {str(k): int(v) for k, v in
                                (a.get("n_hits_by_set") or {}).items()}
                if claimed_hits != recomputed_hits:
                    bad_hits.append(
                        f"{key}: declares hits {dict(list(claimed_hits.items())[:3])}; "
                        f"recomputing from the bound membership and ranking bytes gives "
                        f"{dict(list(recomputed_hits.items())[:3])}")

        # THE STAGE-1 IDENTITIES: present, non-null, and EXACTLY the release's own.
        null_stage1 += W.stage1_bindings(prov, release, programs, bid, projection)
        null_stage1 += W.method_field(prov, lane, bid)
        bad_env += W.check_env_lock(prov, env_lock_sha256, bid)

        binding = prov.get("run_binding") or {}
        codes.append((bid, R.content_sha256(B.code_binding(prov))))
        selections.append((bid, R.content_sha256(binding.get("selection_release"))))
        inputs.append((bid, R.content_sha256(binding.get("stage2_inputs"))))
        methods.append((bid, R.content_sha256(B.method_binding(prov))))

        arm_raw = R.file_sha256(os.path.join(path, "arm_bundle.json"))
        prov_raw = R.file_sha256(os.path.join(path, R.PROVENANCE_OF[lane]))
        independent_id = (expect_verifiers.get(lane) or {}).get("verifier_id")
        if lane in R.REPORT_OF:
            # Lanes that still ship a per-bundle report: it must be a TYPED admission from
            # the PINNED verifier, about THIS bundle.
            bad_reports += B.check_report(report, lane, bid, expect_verifiers,
                                          arm_raw, prov_raw)
        if lane in R.PREFLIGHT_OF:
            # Temporal ships a PREFLIGHT. It proves the FINAL bytes and admits NOTHING;
            # the admission is the one root envelope.
            bad_preflight += B.check_preflight(
                R.load_json(os.path.join(path, R.PREFLIGHT_OF[lane])),
                set(os.listdir(path)), lane, bid, independent_id, arm_raw, prov_raw)
        # Every bundle's code identity, against an INDEPENDENTLY pinned checkout.
        bad_code += B.check_code_identity(B.code_binding(prov), expected_code, bid)

        if lane == R.LANE_PATHWAY:
            src = str(ctx.get("gene_set_source"))
            geneset_by_source.setdefault(src, []).append(
                (bid, R.content_sha256(inv.get("gene_sets"))))
            # ...and the gene-set identity FIELD BY FIELD against the pinned source.
            bad_gene_sets += B.check_gene_sets(
                inv.get("gene_sets"), pinned.get(src), src, bid)
            conv = inv.get("convergence") or {}
            cpath = os.path.join(path, "convergence.json")
            convergences.append((
                bid, str(conv.get("convergence_id")),
                {str(a.get("convergence_id")) for a in arms if a.get("convergence_id")},
                conv.get("sha256"),
                R.file_sha256(cpath) if os.path.exists(cpath) else None))

    return {
        "filled": filled, "ids": ids, "codes": codes, "selections": selections,
        "inputs": inputs, "methods": methods,
        "geneset_by_source": geneset_by_source, "convergences": convergences,
        "missing": missing, "bad_bytes": bad_bytes, "not_all_arm": not_all_arm,
        "bad_map": bad_map, "bad_projection": bad_projection,
        "pair_stored": pair_stored, "forbidden": forbidden, "unloadable": unloadable,
        "bad_hits": bad_hits, "bad_reports": bad_reports, "bad_code": bad_code,
        "bad_gene_sets": bad_gene_sets, "batch_stored": batch_stored,
        "bad_keyed": bad_keyed, "bad_ranks": bad_ranks,
        "arm_values": arm_values, "stale": stale, "null_stage1": null_stage1,
        "bad_preflight": bad_preflight, "bound_rankings": bound_rankings,
        "bad_env": bad_env,
    }
