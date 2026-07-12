"""Independent reconstruction of EVERY emitted table, then exact comparison.

Part of the standalone verifier. Imports nothing from the generator: it rebuilds
screen / masks / contributing_guides / guide_support / donor_support from the raw
inputs using the reimplemented rules in ``verify_rules``, and compares them to the
emitted parquet files field by field.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

# The verifier is standalone: it loads its own rule modules by path, never as part
# of the generator package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R


def _num(v):
    return None if pd.isna(v) else float(v)


def rebuild(ctx):
    """Rebuild every table from the inputs. Returns dict of DataFrames."""
    cond, meta, log_fc = ctx["cond"], ctx["meta"], ctx["log_fc"]
    axis, library, contrib = ctx["axis"], ctx["library"], ctx["contrib"]
    by_guide, by_donor = ctx["by_guide"], ctx["by_donor"]
    index = {g: i for i, g in enumerate(ctx["genes"])}
    splits = R.complementary_splits(sorted(by_donor))
    n_donors = len({d for p in by_donor for d in p.split("_")})

    screen, masks, contribs, gsupport, dsupport = [], [], [], [], []

    for i, t in enumerate(meta["target_contrast"]):
        # IDENTITY: the release key is never parsed; target_ensembl stays null
        # unless obs.target_contrast literally is an Ensembl id (or a map supplies).
        ident = R.target_identity(meta["released_estimate_id"][i], t,
                                  meta["target_contrast_gene_name"][i],
                                  ctx.get("identity_map"))
        target = ident["target_id"]
        tens = ident["target_ensembl"]
        ng = meta["n_guides"][i]
        ng = None if ng is None or np.isnan(float(ng)) else int(float(ng))
        slots_present = sorted(m for m in by_guide
                               if target in by_guide[m]["by_target"])

        def scope_for(kind, eid, donor_pair=None):
            """The FULL released scope identity a contributor row is keyed by.

            Never a reduced (type, id, gene) key: the contributor map is keyed by the
            estimate AND the whole RELEASED target identity, so evidence for one scope
            can never be read as evidence for another that merely shares a gene. The
            released target_ensembl is null for every gene_symbol scope — a run-level
            identity map may enrich ``tens`` for the library join, but it does not
            change what the release published, which is what the manifest binds.
            """
            return R.scope_of({
                "estimate_type": kind, "estimate_id": eid,
                "released_estimate_id": ident["released_estimate_id"],
                "target_id": target,
                "target_id_namespace": ident["target_id_namespace"],
                "target_symbol": ident["target_symbol"],
                "target_ensembl": ident["released_target_ensembl"],
                "condition": cond, "donor_pair": donor_pair})

        def pooled_mask():
            """The POOLED mask: only its own manifest-proven guides and its own count.

            No support object is consulted. The retired slot-contradiction rule refused
            a target outright when the released guide slots disagreed with the pooled
            ``n_guides`` — 6,707 of 33,374 targets — but that disagreement is with a
            support object's COPIED pooled metadata, not an independent witness. The
            pooled fit stands on its own evidence.

            A target with no Ensembl id cannot be joined to the Ensembl-keyed sgRNA
            library, so it is never masked as if its symbol were an accession.
            """
            if tens is None:
                return None, []
            gids = contrib.get(scope_for("main", "main"), [])
            if not gids or tens not in library:
                return None, []
            if ng is None or int(ng) != len(gids):
                return None, []
            if any(g not in library[tens] for g in gids):
                return None, []
            genes = set()
            for g in gids:
                genes |= R.guide_mask_genes(library[tens][g], tens)
            return genes, sorted(gids)

        main_mask, main_guides = pooled_mask()
        for g in main_guides:
            contribs.append({"estimate_type": "main", "estimate_id": "main",
                             "target_id": target, "guide_id": g})
        if main_mask is not None:
            for g in sorted(main_mask):
                masks.append({"estimate_type": "main", "estimate_id": "main",
                              "target_id": target, "masked_gene_ensembl": g})

        # --- per-arm pooled projection ---
        values, statuses, deltas = {}, {}, {}
        for arm in R.ARMS:
            p = R.POLE[arm]
            d, status, npan, ncon = R.program_delta(
                log_fc[i], axis[p]["panel"], axis[p]["control"], index, main_mask)
            statuses[arm] = status
            deltas[arm] = (npan, ncon)
            values[arm] = None if d is None else (
                -axis[p]["sign"] * d if arm == R.ARM_A else axis[p]["sign"] * d)

        base_state, base_pass = R.base_qc(
            mask_resolved=main_mask is not None,
            n_cells=_num(meta["n_cells_target"][i]),
            ontarget_significant=bool(meta["ontarget_significant"][i]),
            low_expression=bool(meta["low_target_gex"][i]), n_guides=ng,
            target_identity_resolved=tens is not None)

        # --- SUPPORT: enumerated, explicitly unavailable, NEVER projected ---
        #
        # The audited contributor artifact is global pooled-main only, so a guide-slot
        # or donor-pair estimate has no evidence of WHICH guide contributed to it. It
        # therefore gets no mask, and its effect vector is never read: projecting it
        # would mean scoring a matrix with a mask it never earned (or with none at
        # all), and the number would then flow into replication and the evidence tier.
        # Its ``n_guides`` is not read either — in this release that field is a COPY of
        # the pooled count, not the estimate's own contributor count.
        #
        # The estimates are still ENUMERATED — the emitted contributor table carries a
        # null-guide row and an explicit reason for each — but they RESOLVE to nothing,
        # so they contribute no guide row here (the comparison is over resolved rows)
        # and no mask gene anywhere.
        slots = []
        for mod_id in slots_present:
            for arm in R.ARMS:
                gsupport.append({"target_id": target, "estimate_id": mod_id,
                                 "arm": arm, "value": None})
            slots.append({"estimate_id": mod_id, "guide_id": None,
                          "values": {arm: None for arm in R.ARMS}})

        pair_vals = {arm: {} for arm in R.ARMS}
        for pair_id in sorted(by_donor):
            for arm in R.ARMS:
                pair_vals[arm][pair_id] = None

        row = {"target_id": target,
               "released_estimate_id": ident["released_estimate_id"],
               "target_id_namespace": ident["target_id_namespace"],
               "target_ensembl": tens,
               "base_qc_state": base_state,
               "base_qc_passed": base_pass,
               "mask_resolved": main_mask is not None,
               "mask_gene_count": None if main_mask is None else len(main_mask),
               "effective_donor_n": n_donors}
        for arm in R.ARMS:
            p = R.POLE[arm]
            state, evaluable = R.arm_state(base_state, base_pass, statuses[arm])
            raw = values[arm]                 # diagnostics keep the raw value
            v = raw if evaluable else None    # the SCORE is null unless evaluable
            rep_ = R.guide_replication(raw, slots, arm, base_state, evaluable)
            ds = R.split_support(raw, pair_vals[arm], splits, evaluable)
            for half_a, half_b in splits:
                dsupport.append({
                    "target_id": target, "arm": arm,
                    "split_id": f"{half_a}|{half_b}",
                    "half_a_value": pair_vals[arm][half_a],
                    "half_b_value": pair_vals[arm][half_b]})
            row.update({
                arm: R.canonical_num(v),
                f"{p}_evaluable": evaluable, f"{p}_state": state,
                f"{p}_projection_status": statuses[arm],
                f"{p}_panel_surviving": deltas[arm][0],
                f"{p}_control_surviving": deltas[arm][1],
                f"{p}_support_status": R.support_status(evaluable, base_pass),
                f"{p}_desired_target_modulation": R.desired_modulation(raw, evaluable),
                f"{p}_guide_replication_state": rep_["state"],
                f"{p}_guide_replication_supported": rep_["supported"],
                f"{p}_n_guides_mapped": rep_["n_mapped"],
                f"{p}_n_guides_evaluated": rep_["n_evaluated"],
                f"{p}_n_guides_concordant": rep_["n_concordant"],
                f"{p}_n_splits_total": ds["n_total"],
                f"{p}_n_splits_evaluable": ds["n_evaluable"],
                f"{p}_n_splits_missing": ds["n_missing"],
                f"{p}_n_splits_internally_concordant": ds["n_internally_concordant"],
                f"{p}_n_splits_internally_discordant": ds["n_internally_discordant"],
                f"{p}_n_splits_agreeing": ds["n_agreeing"],
                f"{p}_donor_split_support": ds["supported"],
                f"{p}_donor_split_denominator": ds["n_total"],
                f"{p}_support_state": R.support_state(evaluable, rep_["supported"],
                                                      ds["supported"]),
                f"{p}_evidence_tier": R.evidence_tier(evaluable, v, rep_["supported"],
                                                      ds["supported"]),
            })
        row["concordance_class"] = R.concordance_class(row[R.ARM_A], row[R.ARM_B])
        row["desired_modulation_agreement"] = R.modulation_agreement(
            row["A_desired_target_modulation"], row["B_desired_target_modulation"])
        screen.append(row)

    # ranks: per arm, over that arm's own population, on the canonical value
    for arm in R.ARMS:
        p = R.POLE[arm]
        pop = [r for r in screen if r[f"{p}_evaluable"] and r[arm] is not None]
        for n, r in enumerate(sorted(pop, key=lambda r: (-r[arm],
                                                         r["target_id"])), 1):
            r[R.RANK_COL[arm]] = n
        for r in screen:
            r.setdefault(R.RANK_COL[arm], None)

    return {"screen": screen, "masks": masks, "contributing_guides": contribs,
            "guide_support": gsupport, "donor_support": dsupport}


SCREEN_COMPARE = (
    ["released_estimate_id", "target_id_namespace", "target_ensembl",
     "base_qc_state", "base_qc_passed", "mask_resolved", "mask_gene_count",
     "effective_donor_n", "concordance_class", "desired_modulation_agreement"]
    + [c for arm in R.ARMS for c in (
        arm, R.RANK_COL[arm],
        f"{R.POLE[arm]}_evaluable", f"{R.POLE[arm]}_state",
        f"{R.POLE[arm]}_projection_status", f"{R.POLE[arm]}_panel_surviving",
        f"{R.POLE[arm]}_control_surviving", f"{R.POLE[arm]}_support_status",
        f"{R.POLE[arm]}_desired_target_modulation",
        f"{R.POLE[arm]}_guide_replication_state",
        f"{R.POLE[arm]}_guide_replication_supported",
        f"{R.POLE[arm]}_n_guides_mapped", f"{R.POLE[arm]}_n_guides_evaluated",
        f"{R.POLE[arm]}_n_guides_concordant", f"{R.POLE[arm]}_n_splits_total",
        f"{R.POLE[arm]}_n_splits_evaluable", f"{R.POLE[arm]}_n_splits_missing",
        f"{R.POLE[arm]}_n_splits_internally_concordant",
        f"{R.POLE[arm]}_n_splits_internally_discordant",
        f"{R.POLE[arm]}_n_splits_agreeing", f"{R.POLE[arm]}_donor_split_support",
        f"{R.POLE[arm]}_donor_split_denominator", f"{R.POLE[arm]}_support_state",
        f"{R.POLE[arm]}_evidence_tier")]
)


def _eq(a, b) -> bool:
    if a is None or (isinstance(a, float) and a != a) or (pd.isna(a) if not isinstance(a, (list, set, dict)) else False):
        a = None
    if b is None or (isinstance(b, float) and b != b) or (pd.isna(b) if not isinstance(b, (list, set, dict)) else False):
        b = None
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
        return bool(a) == bool(b)
    if isinstance(a, (int, float, np.integer, np.floating)) and \
            isinstance(b, (int, float, np.integer, np.floating)):
        return abs(float(a) - float(b)) <= 1e-12
    return str(a) == str(b)


def compare_all(ctx, prov, rep):
    run_dir = ctx["run_dir"]
    built = rebuild(ctx)

    # ---- screen ----
    emitted = pd.read_parquet(os.path.join(run_dir, "screen.parquet"))
    allow = R.screen_allowlist()
    off = sorted(set(emitted.columns) - allow)
    rep.check("screen columns match the exact allowlist (no extra score/rank column)",
              not off, f"off-allowlist: {off}")
    forbidden = sorted(set(emitted.columns) & R.FORBIDDEN_COLUMNS)
    rep.check("screen contains no combined-objective / headline-rank / p-q alias",
              not forbidden, f"forbidden: {forbidden}")
    rep.check("screen is emitted in stable target order (not by any arm)",
              list(emitted["target_id"]) == sorted(emitted["target_id"]))

    want = {r["target_id"]: r for r in built["screen"]}
    rep.check("screen row set reconstructs exactly",
              set(emitted["target_id"]) == set(want))

    got = emitted.set_index("target_id")
    bad = {}
    for col in SCREEN_COMPARE:
        if col not in got.columns:
            bad[col] = "column absent"
            continue
        for t, w in want.items():
            if not _eq(got.loc[t, col], w.get(col)):
                bad.setdefault(col, f"{t}: emitted={got.loc[t, col]!r} "
                                    f"reconstructed={w.get(col)!r}")
    rep.check(f"every reconstructed screen field matches ({len(SCREEN_COMPARE)} "
              "columns incl. disposition, arm state, tier, support, modulation)",
              not bad, "; ".join(f"{k} -> {v}" for k, v in list(bad.items())[:3]))

    for arm in R.ARMS:
        col = R.RANK_COL[arm]
        rep.check(f"{col} dtype is nullable Int64",
                  str(emitted[col].dtype) == "Int64")

    # ---- masks / contributing_guides / guide_support / donor_support ----
    compare_masks(run_dir, built, rep)
    compare_contribs(run_dir, built, rep)
    compare_support(run_dir, built, rep)

    # ---- verification.json must agree with the reconstruction ----
    ver = json.load(open(os.path.join(run_dir, "verification.json")))
    rep.check("verification.json row count agrees with the reconstruction",
              ver["row_count"] == len(built["screen"]))
    for arm in R.ARMS:
        n = sum(1 for r in built["screen"] if r[R.RANK_COL[arm]] is not None)
        rep.check(f"verification.json n_ranked[{arm}] agrees",
                  ver["ranking"]["per_arm"][arm]["n_ranked"] == n)
    rep.check("verification.json declares the column allowlist satisfied",
              ver.get("columns_match_allowlist") is True)


def compare_masks(run_dir, built, rep):
    emitted = pd.read_parquet(os.path.join(run_dir, "masks.parquet"))
    got = {(r.estimate_type, r.estimate_id, r.target_id, r.masked_gene_ensembl)
           for r in emitted.itertuples() if pd.notna(r.masked_gene_ensembl)}
    want = {(m["estimate_type"], m["estimate_id"], m["target_id"],
             m["masked_gene_ensembl"]) for m in built["masks"]}
    rep.check("masks.parquet reconstructs exactly (every estimate-specific gene)",
              got == want,
              f"only-emitted={len(got - want)} only-reconstructed={len(want - got)}")


def compare_contribs(run_dir, built, rep):
    emitted = pd.read_parquet(os.path.join(run_dir, "contributing_guides.parquet"))
    got = {(r.estimate_type, r.estimate_id, r.target_id, r.guide_id)
           for r in emitted.itertuples() if pd.notna(r.guide_id)}
    want = {(c["estimate_type"], c["estimate_id"], c["target_id"],
             c["guide_id"]) for c in built["contributing_guides"]}
    rep.check("contributing_guides.parquet reconstructs exactly (resolved rows only)",
              got == want,
              f"only-emitted={sorted(got - want)[:2]} "
              f"only-reconstructed={sorted(want - got)[:2]}")


def compare_support(run_dir, built, rep):
    g = pd.read_parquet(os.path.join(run_dir, "guide_support.parquet"))
    want_g = {(x["target_id"], x["estimate_id"], x["arm"]): x["value"]
              for x in built["guide_support"]}
    bad = [k for k, v in want_g.items()
           if not _match_value(g, ["target_id", "estimate_id", "arm"], k, v)]
    rep.check("guide_support.parquet reconstructs exactly (per slot, per arm)",
              not bad, f"{len(bad)} mismatched row(s)")

    d = pd.read_parquet(os.path.join(run_dir, "donor_support.parquet"))
    bad_d = []
    for x in built["donor_support"]:
        sub = d[(d["target_id"] == x["target_id"])
                & (d["arm"] == x["arm"]) & (d["split_id"] == x["split_id"])]
        if len(sub) != 1 or not (_eq(sub.iloc[0]["half_a_value"], x["half_a_value"])
                                 and _eq(sub.iloc[0]["half_b_value"],
                                         x["half_b_value"])):
            bad_d.append(x["split_id"])
    rep.check("donor_support.parquet reconstructs exactly (per split, per arm)",
              not bad_d, f"{len(bad_d)} mismatched row(s)")


def _match_value(df, keys, key, value) -> bool:
    mask = np.ones(len(df), dtype=bool)
    for k, v in zip(keys, key):
        mask &= (df[k] == v).to_numpy()
    sub = df[mask]
    return len(sub) == 1 and _eq(sub.iloc[0]["value"], value)
