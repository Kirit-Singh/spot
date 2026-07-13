"""The P2S v2 SECONDARY runner: support for ONE reusable Direct arm (and its sibling).

    python -m p2s_arms.run_p2s_arms \
        --direct-bundle  <the W10-ADMITTED Direct bundle dir for that condition> \
        --w10-report     <DIRECT_BUNDLE_ADMISSION_<condition>.json> \
        --env-lock       analysis/stage02_solver_lock.txt \
        --stage1-release <the bound v3 release> \
        --arm-key 'direct|treg_like|increase|Stim48hr' \
        --cells <prepared npz> --effects <parquet> --masks <parquet> --eligible <parquet> \
        --out-root <outside every tracked tree>

IT RUNS ONLY FROM A REAL, W10-ADMITTED DIRECT ARM
-------------------------------------------------
The four bindings above are REQUIRED. "Sequencing alone is not a binding": a wrapper can run
this lane after Direct and W10 and still have bound nothing, because a producer that does not
ACCEPT the bundle and the report cannot be said to have run from them.

Exit 0 = support emitted. Exit 2 = a NAMED refusal, with a TYPED DEFERRED DISPOSITION written
to ``p2s_deferred_disposition.json``. Never exit 1, which is a crash: a scheduler has to be
able to tell "P2S declined this arm, for this reason" from "P2S broke".

It writes ONLY into its own content-addressed run directory. It never writes into Direct's
output, never imports into Direct, and changes no byte under ``analysis/direct/`` — which is
what makes the byte-identity invariant structural rather than a promise.

THE GRID
--------
Both arms of the program come from ONE fit per (donor scope, effect layer, model config):

    all_donor  x  {zscore, log_fc}  x  {pca_off, pca_on_50}     = 4 fits
    lodo_D*    x  {zscore}          x  {pca_off}                = 1 fit per donor

The LODO fits OVERLAP — they share most of their cells — and are never called independent
replicates. They measure whether a coefficient survives dropping a donor, which is a
different and much weaker statement than replication.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Optional

import numpy as np
from direct import runid
from direct.hashing import content_hash

from . import (
    argvutil,
    armfit,
    armref,
    binding,
    config,
    emit,
    io_data,
    model,
    pmatrix,
    prepared,
    signature,
    stability,
    universe,
    upstream,
)
from . import (
    disposition as D,
)

ALL_DONOR = "all_donor"
LODO_PREFIX = "lodo_"

# The ONLY lane in which a stand-in model may run. See ``execute``.
LANE_SYNTHETIC = "synthetic"


def scopes_for(donors: np.ndarray) -> list[tuple[str, Optional[str]]]:
    """``all_donor`` plus one leave-one-donor-out scope per donor."""
    uniq = sorted({str(d) for d in donors})
    return [(ALL_DONOR, None)] + [(f"{LODO_PREFIX}{d}", d) for d in uniq]


def grid(scope: str) -> list[tuple[str, config.ModelConfig]]:
    """The ONE-FACTOR-AT-A-TIME grid. NEVER a Cartesian product.

    A Cartesian ``layers x configs`` would create the ``log_fc + pca_off`` cell — TWO factors
    changed at once, which no sensitivity family names, so it would sit in the coefficients
    and the denominators would not account for it. OFAT changes exactly one thing from the
    primary at a time:

        all_donor:  (zscore, pca_on_60)   THE PRIMARY
                    (log_fc, pca_on_60)   effect-layer sensitivity
                    (zscore, pca_off)     model-config sensitivity
        lodo_D*:    (zscore, pca_on_60)   donor sensitivity, one per donor

    Four donors => 3 + 4 = SEVEN fits per (program, condition).
    """
    primary = (config.PRIMARY_LAYER, config.PRIMARY_CONFIG)
    if scope == ALL_DONOR:
        return [
            primary,
            ("log_fc", config.PRIMARY_CONFIG),          # change ONLY the effect layer
            (config.PRIMARY_LAYER, config.SENSITIVITY_CONFIG),   # change ONLY the config
        ]
    return [primary]                                    # LODO changes ONLY the donor set


def run_grid(*, program_id: str, condition: str, cells: dict[str, Any],
             universe_gene_ids: list[str], effects: dict[str, Any],
             eligible_targets: list[str], mask_by_target: dict[str, set],
             fit=None, seed: int = config.RANDOM_STATE) -> dict[str, Any]:
    """Every fit for one program. Both arms come out of each, as an exact sign transform."""
    scores = cells["scores"]
    if program_id not in scores:
        raise io_data.InputError(
            "program_score_absent",
            f"the prepared cell matrix carries no Stage-1 score for {program_id!r}; scores "
            "are read by barcode and never recomputed")
    if config.ACTIVATION_PROGRAM_ID not in scores:
        raise io_data.InputError(
            "activation_score_absent",
            f"the activation covariate {config.ACTIVATION_PROGRAM_ID!r} has no score in the "
            "prepared cell matrix, so the confound it exists to absorb cannot be adjusted "
            "for")

    donors = cells["donors"]
    expr_all = cells["expr"]
    col_of = {g: i for i, g in enumerate(cells["gene_ids"])}
    missing = [g for g in universe_gene_ids if g not in col_of]
    if missing:
        raise io_data.InputError(
            "universe_gene_absent_from_cells",
            f"{len(missing)} readout gene(s) are not in the cell matrix (e.g. {missing[:3]})")
    take = np.asarray([col_of[g] for g in universe_gene_ids], dtype=int)

    coef_rows: list[dict[str, Any]] = []
    recon_rows: list[dict[str, Any]] = []
    signatures: dict[str, dict[str, Any]] = {}

    for scope, held_out in scopes_for(donors):
        keep = np.ones(len(donors), dtype=bool) if held_out is None \
            else (donors != held_out)

        z_program = signature.within_donor_z(scores[program_id][keep], donors[keep])
        z_act = signature.within_donor_z(
            scores[config.ACTIVATION_PROGRAM_ID][keep], donors[keep])

        sig = signature.base_signature(
            z_program=z_program, activation=z_act, donors=donors[keep],
            expr=expr_all[np.ix_(keep, take)])
        signatures[scope] = {
            "n_units": sig["n_units"], "rank": sig["rank"],
            "design_columns": sig["design_columns"],
            "signature_sha256": content_hash(
                [round(float(v), 6) for v in sig["signature"]]),
        }

        for layer, cfg in grid(scope):
            x, _coverage = pmatrix.build_masked_x(
                effect_by_target=effects["by_layer"][layer],
                effect_gene_ids=effects["gene_ids"],
                universe_gene_ids=universe_gene_ids,
                target_order=eligible_targets,
                mask_by_target=mask_by_target)

            got = armfit.fit_program(
                program_id=program_id, condition=condition,
                base_signature=sig["signature"], x=x, cfg=cfg, layer=layer, scope=scope,
                fit=fit, seed=seed)
            coef_rows += got["coefficients"]
            recon_rows += got["reconstruction"]

    return {"coefficients": coef_rows, "reconstruction": recon_rows,
            "signatures": signatures}


def execute(*, bound: dict[str, Any], release, view: dict[str, Any],
            paths: dict[str, str], up: dict[str, Any], out_root: str,
            lane: str = "production", seed: int = config.RANDOM_STATE,
            env_lock: Optional[str] = None, argv: Optional[list[str]] = None,
            derived_from: Optional[dict[str, Any]] = None,
            p2s_lock: Optional[dict[str, Any]] = None,
            prepared: Optional[dict[str, Any]] = None,
            fit=None) -> dict[str, Any]:
    """The pipeline AFTER binding: fit, stabilise, emit. Pure of argparse.

    ``fit`` is injectable so the whole producer can be driven end to end without the
    upstream package — the tests exercise THIS function, not a re-implementation of it.
    It is REFUSED outside the synthetic lane (see below).

    ``p2s_lock`` and ``prepared`` are the SECOND environment lock and the verified
    prepared-inputs binding; both go into the run identity so a run cannot be re-attributed
    to another environment or have its matrices swapped.
    """
    if fit is not None and lane != LANE_SYNTHETIC:
        raise model.ModelError(
            "stand_in_model_outside_the_synthetic_lane",
            f"a stand-in fit was supplied in the {lane!r} lane. A stand-in is a DIFFERENT "
            "MODEL producing numbers under this lane's name and under the pinned model's "
            f"provenance, so it may run only in the {LANE_SYNTHETIC!r} lane. Everywhere "
            "else the pinned upstream model is not optional")

    # A RELEASE run is pinned to seed 42. The seed goes into the run binding and hence the run
    # id; a release run under a different seed would produce real-looking numbers a re-run
    # cannot reproduce, so it is refused (and the verifier re-checks the recorded seed).
    if lane in config.RELEASE_LANES and seed != config.RANDOM_STATE:
        raise D.RefusalError(
            D.REFUSE_NONCANONICAL_SEED,
            f"a {lane!r} run was given seed {seed}, not the pinned {config.RANDOM_STATE}. The "
            "seed is bound into the run identity; a release result under an off-pin seed is "
            "one nobody else can reproduce")

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ref = bound["arm"]

    cells = io_data.load_cells(paths["cells"])
    # THE CONDITION the cells were prepared for must be the arm's condition — a run cannot
    # reconstruct a Stim48hr arm from Rest cells that were handed in under the wrong name.
    if cells.get("condition") is not None and cells["condition"] != ref.condition:
        raise D.RefusalError(
            D.REFUSE_PREPARED_CONDITION,
            f"the prepared cells are for condition {cells['condition']!r}, but this arm is "
            f"{ref.condition!r}")
    effects = io_data.load_effects(paths["effects"])
    masks = io_data.load_masks(paths["masks"])
    # ARM-SPECIFIC: only the targets evaluable on THIS arm become perturbation columns.
    elig = io_data.load_eligible(paths["eligible"], arm_key=ref.arm_key)

    # GLOBAL exclusion is program panel/control (+ activation) ONLY. Target self-genes are
    # neutralised PER COLUMN by the Direct mask — never subtracted from the whole universe.
    excluded = universe.panel_and_control(
        release.programs,
        list(view["admitted_program_ids"]) + [config.ACTIVATION_PROGRAM_ID])
    uni = universe.build(effect_gene_ids=effects["gene_ids"],
                         excluded_program_genes=excluded)
    universe.assert_clean(uni, excluded)

    got = run_grid(
        program_id=ref.program_id, condition=ref.condition, cells=cells,
        universe_gene_ids=uni["gene_ids"], effects=effects,
        eligible_targets=elig["targets"],
        mask_by_target=pmatrix.mask_sets(masks["rows"]), fit=fit, seed=seed)

    support_rows = stability.compute(got["coefficients"])

    doc = emit.support_document(
        bound=bound, support_rows=support_rows, coef_rows=got["coefficients"],
        recon_rows=got["reconstruction"], upstream=up, universe=uni)

    run_binding = {
        "runner_id": config.RUNNER_ID,
        "lane": lane,
        "lane_role": config.LANE_ROLE,
        "arm_key": ref.arm_key,
        "method": doc["method"],
        "upstream_software": up,
        "gene_universe_sha256": uni["gene_universe_sha256"],
        "stage2_inputs": sorted(
            [{"name": name, "sha256": obj["sha256"]}
             for name, obj in (("cells", cells), ("effects", effects),
                               ("masks", masks), ("eligible", elig))],
            key=lambda i: i["name"]),
        "environment_lock": runid.env_lock_block(env_lock),
        # TWO ENVIRONMENTS, TWO LOCKS: the Direct lock the arms were computed under, and the
        # P2S runtime lock THIS fit runs under. Both in the identity.
        "direct_solver_lock_sha256": bound["solver_lock"]["sha256"],
        "p2s_runtime_lock_sha256": (p2s_lock or {}).get("sha256"),
        # the VERIFIED prepared-inputs binding: their run id, hashes and the pins they carry.
        # A substituted matrix changes this, hence the run id.
        "prepared_inputs": (prepared or {}).get("manifest_binding"),
        "support_rows_sha256": doc["support_rows_sha256"],
        "coefficient_rows_sha256": doc["coefficient_rows_sha256"],
        "reconstruction_rows_sha256": doc["reconstruction_rows_sha256"],
        "seed": seed,
    }
    run_id, run_sha = emit.run_id_for(run_binding)

    prov = {
        "schema_version": config.SCHEMA_PROVENANCE,
        "p2s_run_id": run_id,
        "p2s_run_sha256": run_sha,
        "created_at": created_at,
        "run_binding": run_binding,
        "signatures": got["signatures"],
        # sanitized: machine-local PATHS become basenames, so the content-addressed provenance
        # does not carry a /home/... path the machine-path firewall would (correctly) reject.
        "argv": argvutil.sanitize_argv(list(argv if argv is not None else sys.argv[1:])),
        # role and pole are SELECTION metadata, recorded as provenance. They are never part
        # of the arm key, and neither may alter a cached arm's values.
        "derived_from": derived_from or {"role": None, "pole": None},
        "n_support_rows": len(support_rows),
    }

    written = emit.write(out_root, doc=doc, provenance=prov,
                         support_rows=support_rows, coef_rows=got["coefficients"],
                         recon_rows=got["reconstruction"], run_id=run_id)
    return dict(written, arm_key=ref.arm_key, n_support_rows=len(support_rows))


def build(args, *, fit=None) -> dict[str, Any]:
    """One run from the command line. Admit the inputs, bind, verify the pin, execute.

    ORDER MATTERS. The solver lock and W10's admission are checked BEFORE the Stage-1 release
    is loaded, so that a missing report or an unadmitted bundle comes back as a NAMED typed
    refusal rather than as whatever the release loader raises on the way past it.
    """
    admitted = binding.admit_inputs(
        bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, lane=args.lane)
    # THE SECOND ENVIRONMENT. The Direct lock pins where the arms came from; this pins where
    # the fit runs. Bound separately; supplying the Direct lock in its place is refused.
    p2s_lock = binding.verify_p2s_runtime_lock(args.p2s_env_lock)

    ref = armref.parse(args.arm_key)
    # VERIFY THE PREPARED INPUTS before a number is computed: re-hash every matrix against its
    # manifest and re-check the pins it bound. A substituted matrix keeps its filename.
    prep = prepared.load_and_verify(args.inputs, condition=ref.condition, lane=args.lane,
                                    admitted=admitted["admission"])

    try:
        release, view = binding.load_release(
            release_path=args.stage1_release, kind=args.release_kind,
            validation_path=args.stage1_validation, gate_spec_path=args.stage1_gate_spec,
            release_root=getattr(args, "stage1_release_root", None))
    except Exception as e:                      # the loader's own error type is not ours
        raise D.RefusalError(
            D.REFUSE_RELEASE_UNREADABLE,
            f"the bound Stage-1 v3 release could not be loaded ({e})") from e

    bound = binding.bind(
        arm_key=args.arm_key, bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, view=view, release=release, lane=args.lane,
        admitted=admitted)
    up = upstream.identity()      # commit + version + tree pin, all mandatory, no override

    return execute(
        bound=bound, release=release, view=view, up=up, paths=prep["paths"],
        out_root=args.out_root, lane=args.lane, seed=args.seed, env_lock=args.env_lock,
        p2s_lock=p2s_lock, prepared={"manifest_binding": _prepared_binding(prep)},
        derived_from={"role": args.derived_from_role, "pole": args.derived_from_pole},
        fit=fit)


def _prepared_binding(prep: dict[str, Any]) -> dict[str, Any]:
    """The verified prepared-inputs binding that goes into the run identity.

    It carries the WHOLE of what the prepared inputs were built from — not only their id — so a
    swap of any source input, lock, or the Direct bundle/identity they were prepared against
    MOVES the run id. Binding only the prepared id would let two source-different input sets
    that happened to share an id (they cannot, but the binding must not rely on that) speak for
    each other.
    """
    m = prep["manifest"]
    return {
        "p2s_inputs_run_id": prep["p2s_inputs_run_id"],
        "condition": prep["condition"],
        "artifact_sha256": m.get("artifact_sha256"),
        "artifact_sha256_verified": True,
        # the RAW public inputs, hashed from the bytes handed in at preparation
        "raw_input_sha256": m.get("raw_input_sha256"),
        "stage1_scores_raw_sha256": prep["stage1_scores"].get("raw_sha256"),
        "stage1_scores_canonical_sha256":
            prep["stage1_scores"].get("canonical_scores_sha256"),
        "public_source": m.get("public_source"),
        # BOTH environment locks the inputs were prepared under
        "environment_locks": prep.get("environment_locks"),
        # the COMPLETE Direct bundle + identity binding — the bundle A the inputs came from,
        # cross-checked against the run's admitted bundle B in prepared.load_and_verify
        "direct_binding": m.get("direct_binding"),
        "target_identity": m.get("target_identity"),
        "target_identity_raw_sha256": m.get("target_identity_raw_sha256"),
        # the code that prepared the inputs, and that this binding was compared to literals
        "code_identity": m.get("code_identity"),
        "compared_to_code_literals": prep.get("compared_to_code_literals"),
        "self_id_rederived": prep.get("self_id_rederived"),
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Perturb2State SECONDARY reconstruction support for ONE reusable arm")

    # THE FOUR BINDINGS the W7 wrapper's preflight checks for BY NAME
    # (stage2_run.py -> SECONDARY_LANE_BINDING_GAP). Its note is the whole point:
    #
    #     "Sequencing alone is not a binding."
    #
    # A wrapper can run this lane AFTER Direct and W10 and still have bound nothing. A
    # producer that does not ACCEPT the bundle and the report cannot be said to have run
    # from them. All four are REQUIRED: a default here would be a binding nobody supplied.
    ap.add_argument("--direct-bundle", required=True, dest="direct_bundle",
                    help="the ADMITTED Direct all-arm bundle directory "
                         "(<out-root>/<arm_bundle_run_id>); discover it with "
                         "`python -m direct.bundle_index`, never by guessing a path")
    ap.add_argument("--w10-report", required=True, dest="w10_report",
                    help="W10's INDEPENDENT admission report for that bundle "
                         "(DIRECT_BUNDLE_ADMISSION_<condition>.json). NOT the bundle's own "
                         "verification.json, which is the producer's empty slot")
    ap.add_argument("--env-lock", required=True, dest="env_lock",
                    help="the DIRECT solver lock (stage02_solver_lock.txt) — the environment "
                         "the ARMS were computed in")
    ap.add_argument("--p2s-env-lock", required=True, dest="p2s_env_lock",
                    help="the P2S RUNTIME lock (stage02_p2s_runtime_lock.txt) — a SEPARATE "
                         "environment; the Direct lock cannot execute this lane")
    ap.add_argument("--inputs", required=True,
                    help="the directory `prepare_inputs` produced; its p2s_inputs.json is "
                         "verified against code literals and every matrix re-hashed")
    ap.add_argument("--stage1-release", required=True)
    ap.add_argument("--stage1-release-root", default=None,
                    help="the staged v3 release ROOT (components resolve under it); defaults "
                         "to the release file's own directory")

    ap.add_argument("--arm-key", required=True,
                    help="direct|program_id|desired_change|condition")
    ap.add_argument("--release-kind", default="production",
                    choices=("production", "research_only", "fixture"))
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--out-root", required=True,
                    help="OUTSIDE every tracked tree; the run dir is named for its content")
    ap.add_argument("--lane", default="production", choices=list(config.LANES))
    ap.add_argument("--seed", type=int, default=config.RANDOM_STATE)
    ap.add_argument("--derived-from-role", default=None,
                    choices=(None, "away_from_A", "toward_B"))
    ap.add_argument("--derived-from-pole", default=None, choices=(None, "high", "low"))
    return ap


DEFERRED_FILE = "p2s_deferred_disposition.json"

# Exit codes. 0 = support emitted. 2 = a NAMED refusal (never 1, which is a crash): a
# scheduler must be able to tell "P2S declined this arm, for this reason" from "P2S broke".
EXIT_OK = 0
EXIT_REFUSED = 2


def emit_deferred(out_root: str, refusal: "D.RefusalError", *, arm_key: str,
                  argv: list[str]) -> str:
    """A TYPED DEFERRED DISPOSITION — a refusal RECORDED, never a silence.

    A refused arm is not an arm P2S has no opinion about; it is an arm P2S refused to speak
    for, and this says which. It NEVER fills a primary slot and it carries no support.
    """
    rec = refusal.record(arm_key=arm_key)
    rec["argv"] = argvutil.sanitize_argv(list(argv))
    rec["lane_role"] = config.LANE_ROLE
    rec["counts_toward_completeness"] = False
    rec["filled_a_primary_slot"] = False
    os.makedirs(out_root, exist_ok=True)
    path = os.path.join(out_root, DEFERRED_FILE)
    emit.write_json(path, rec)
    return path


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.seed != config.RANDOM_STATE:
        print(f"note: seed {args.seed} is not the pinned {config.RANDOM_STATE}; it is "
              "recorded in the run binding and CHANGES the run id", file=sys.stderr)

    try:
        out = build(args)
    except D.RefusalError as e:
        path = emit_deferred(args.out_root, e, arm_key=args.arm_key, argv=argv)
        print(json.dumps({"state": "refused", "reason": e.reason,
                          "arm_key": args.arm_key, "support_emitted": False,
                          "disposition": os.path.basename(path)}, indent=2),
              file=sys.stderr)
        return EXIT_REFUSED

    print(f"{out['p2s_run_id']}  {out['arm_key']}  "
          f"{out['n_support_rows']} support row(s)  -> {os.path.basename(out['out_dir'])}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
