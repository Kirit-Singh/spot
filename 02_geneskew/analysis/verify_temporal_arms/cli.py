"""The shipped on-disk verifier, as a command. A REJECTED release is an exit code.

    python -m verify_temporal_arms.cli \\
        --stage1-release-root <dir> --bundle-root <dir> \\
        [--expect-conditions A B C] \\
        [--expect-scorer-view-prefix HEX] [--expect-scorer-projection-prefix HEX] \\
        [--deny-host NAME ...]

Both roots are REQUIRED and neither has a default. A verifier that guessed where the
release lived would bind to whatever happened to be on the machine that ran it, and the
whole point of this lane is that it binds to something a reader can name.

The pins are OPTIONAL and are never applied unless supplied — a pin nobody gave must not
silently pass. For the frozen Stage-1 v3 release the two scorer pins are printed by
``--print-frozen-pins`` so a production caller can pass them without copying a hash out of
a document by hand.

The report goes to stdout as canonical JSON. It is typed and content-addressed, it carries
no timestamp and no machine, and it never reports a "top mover": there is no combined
temporal objective and no headline arm, so there is nothing to head a list with.
"""
from __future__ import annotations

import argparse
import sys

from . import release, verify
from .canonical import canonical_json


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Independent verifier for the Stage-2 reusable temporal ARM release "
                    "(population-level difference-in-differences on program projections; "
                    "NOT per-cell fate, NOT lineage tracing)")
    ap.add_argument("--stage1-release-root", default=None,
                    help="the EXPLICITLY STAGED Stage-1 v3 release root. Component paths "
                         "resolve against it; there is no machine default.")
    ap.add_argument("--bundle-root", default=None,
                    help="the root the six ordered-pair temporal arm bundles were emitted "
                         "under")
    ap.add_argument("--expect-conditions", nargs="*", default=None,
                    help="PIN the condition universe, IN ORDER. The order is the time "
                         "axis, and a reordered release is refused.")
    ap.add_argument("--expect-scorer-view-prefix", default=None,
                    help="PIN the canonical hash of the whole Stage-1 scorer view")
    ap.add_argument("--expect-scorer-projection-prefix", default=None,
                    help="PIN the hash of the admitted program-axis projection")
    ap.add_argument("--deny-host", action="append", default=[],
                    help="refuse this host name wherever it appears in an artifact. Host "
                         "SHAPES (URIs, ssh targets, private addresses, *.local) are "
                         "always refused; this adds names, and the verifier itself holds "
                         "none.")
    ap.add_argument("--sign", action="store_true",
                    help="WRITE the external admission envelope — ONE file at the release "
                         "root. This lane writes the verdict, after reopening the shipped "
                         "bytes; the producer's bundle dirs and preflight are never touched.")
    ap.add_argument("--admission-out", default=None, metavar="FILE",
                    help="WHERE to file the external admission. Default: beside the "
                         "producer's inventory, under --bundle-root. An aggregate that keeps "
                         "its receipts at its own root points this there — the verifier "
                         "still READS the producer's native root and still writes nothing "
                         "into it. The path is not the binding: the admission binds the "
                         "producer's release id and the exact inventory bytes, so a reader "
                         "can get back to the release from anywhere in the tree.")
    ap.add_argument("--producer-checkout", default=None,
                    help="the PINNED checkout the producer ran from. Its code identity is "
                         "RE-DERIVED here and the final clean-tree status is decided here: "
                         "a run is not the witness for its own checkout.")
    ap.add_argument("--env-lock", default=None,
                    help="the COMMITTED Stage-2 environment lock. Its bytes are re-hashed "
                         "here and compared with what the bundles bound: the same source "
                         "resolved against a different environment is a different "
                         "computation.")
    ap.add_argument("--expect-env-lock-sha256",
                    default=None,
                    help="the AUTHORITATIVE Stage-2 lock sha256 the supplied lock must "
                         "itself hash to. Defaults to the frozen Stage-2 solver lock every "
                         "lane is pinned to; override only for synthetic fixtures.")
    ap.add_argument("--direct-bundle", action="append", metavar="COND:PATH", default=None,
                    help="the ADMITTED Direct all-arm bundle for one condition. Repeat per "
                         "condition. The release's endpoints ARE these bundles, and they are "
                         "reopened, rehashed and re-differenced here.")
    ap.add_argument("--w10-report", action="append", metavar="COND:PATH", default=None,
                    help="the INDEPENDENT (W10) admission report for that condition's Direct "
                         "bundle. It is READ, not merely hashed: a report that is present "
                         "admits nothing.")
    ap.add_argument("--allow-dirty-producer", action="store_true",
                    help="RECORD, rather than refuse, a dirty producer checkout. A digest "
                         "over uncommitted bytes does not identify the commit printed "
                         "beside it, so this is never the default.")
    ap.add_argument("--print-contract", action="store_true",
                    help="print the INTEGRATION CONTRACT as JSON and exit: the native files "
                         "this lane reads and writes, the admission document it requires "
                         "for --w10-report, and the typed pointer an aggregate binds it by. "
                         "Emitted as BYTES so a caller binds it rather than transcribing "
                         "it — a contract copied by hand is a contract that drifts.")
    ap.add_argument("--print-frozen-pins", action="store_true",
                    help="print the frozen Stage-1 v3 release's scorer pins and exit")
    args = ap.parse_args(argv)

    # The two print flags answer questions ABOUT the contract, not about a release, so they
    # do not need one. Everything else does, and a missing root is an error, not a default.
    if not (args.print_contract or args.print_frozen_pins):
        missing = [f for f, v in (("--stage1-release-root", args.stage1_release_root),
                                  ("--bundle-root", args.bundle_root)) if not v]
        if missing:
            ap.error(f"the following arguments are required: {', '.join(missing)}")

    if args.print_contract:
        print(canonical_json(verify.integration_contract()))
        return 0

    if args.print_frozen_pins:
        print(canonical_json({
            "scorer_view_sha256_prefix": release.FROZEN_SCORER_VIEW_SHA256_PREFIX,
            "scorer_projection_sha256_prefix":
                release.FROZEN_SCORER_PROJECTION_SHA256_PREFIX,
        }))
        return 0

    def _pairs(items):
        out = {}
        for it in items or []:
            cond, _, path = str(it).partition(":")
            if not path:
                ap.error(f"--direct-bundle/--w10-report must be COND:PATH, got {it!r}")
            out[cond] = path
        return out

    report = verify.verify_release(
        release_root=args.stage1_release_root,
        bundle_root=args.bundle_root,
        expect_conditions=args.expect_conditions,
        expect_scorer_view_prefix=args.expect_scorer_view_prefix,
        expect_scorer_projection_prefix=args.expect_scorer_projection_prefix,
        sign=args.sign,
        admission_out=args.admission_out,
        producer_checkout=args.producer_checkout,
        env_lock=args.env_lock,
        direct_bundles=_pairs(args.direct_bundle),
        w10_reports=_pairs(args.w10_report),
        expect_env_lock_sha256=(
            args.expect_env_lock_sha256
            or verify.code_identity.FROZEN_STAGE2_ENV_LOCK_SHA256),
        require_clean_checkout=not args.allow_dirty_producer,
        host_denylist=args.deny_host)
    print(canonical_json(report))
    # A REJECTED release is an exit code, not a log line somebody has to read.
    return 0 if report["verdict"] == verify.ADMIT else 1


if __name__ == "__main__":
    sys.exit(main())
