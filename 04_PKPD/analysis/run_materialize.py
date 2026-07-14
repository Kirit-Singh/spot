"""Stage-4 materializer CLI — the acquisition -> evidence-bundle step that did not exist.

    python -m analysis.run_materialize \
        --stage3-bundle <dir> --run-root <dir> --out evidence_bundle.json
        [--require-external-verifier] [--contract v1|v2]

The full production chain, which until now had a hole in the middle:

    run_acquire   --stage3-bundle <dir> --run-root <R>        # acquire public bytes
    run_materialize --stage3-bundle <dir> --run-root <R> --out <B>    # <-- THIS
    run_stage4    --stage3-bundle <dir> --evidence-bundle <B>  # score, emit, verify

The Stage-3 bundle is admitted through BOTH gates before a single byte is read: Stage 4 restates
it, and Stage 3's own `verifier.verify_stage3` must pass out-of-process (`--require-external-
verifier` makes gate 2 mandatory rather than best-effort). Evidence acquired for a bundle that
was never admitted is evidence about nothing.

It touches no network: it reads only what `run_acquire` already cached and hashed. It emits
`not_evaluated` with a reason for every lane the acquisition could not reach, and refuses to
build a bundle out of fixtures.

Exit: 0 the bundle was written · 2 REFUSED (a stable code, on stderr)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .acquisition import (
    MANIFEST_FILE,
    AcquisitionManifest,
    RunRoot,
    manifest_content_sha256,
)
from pydantic import ValidationError

from .contract_version import ContractVersion
from .firewall import Rejection
from .materialize import materialize
from .stage3_annotation import adapt_annotation_bundle


def load_manifest(run_root: str) -> AcquisitionManifest:
    """Read the acquisition manifest — and re-derive its content hash before believing a word.

    `as_document()` writes `content_sha256` and `hard_rules` alongside the manifest content. Both
    are stripped to rebuild the model, and then the hash is RECOMPUTED and compared: a manifest
    edited after the acquisition ran — a record's hash swapped, an absence quietly deleted — is
    refused here rather than materialized into an evidence bundle that looks acquired.
    """
    path = os.path.join(run_root, MANIFEST_FILE)
    if not os.path.exists(path):
        raise Rejection(
            "acquisition_manifest_missing",
            f"no {MANIFEST_FILE} under {run_root!r}. Run `python -m analysis.run_acquire "
            "--stage3-bundle <dir> --run-root <dir>` first: a bundle can only be materialized "
            "from an acquisition that actually happened.",
        )
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    declared = doc.pop("content_sha256", None)
    doc.pop("hard_rules", None)
    manifest = AcquisitionManifest.model_validate(doc)

    recomputed = manifest_content_sha256(manifest)
    if declared is not None and declared != recomputed:
        raise Rejection(
            "acquisition_manifest_tampered",
            f"the manifest declares content_sha256 {declared[:12]}… but its content hashes to "
            f"{recomputed[:12]}…. It has been edited since the acquisition ran, so nothing in it "
            "can be trusted to describe the bytes on disk.",
        )
    return manifest


def run(stage3_bundle: str, run_root: str, out: str, *,
        require_external_verifier: bool = False,
        version: ContractVersion = ContractVersion.V2) -> int:
    # BOTH gates, before a single acquired byte is read: Stage 4 restates the bundle, and Stage
    # 3's own `verifier.verify_stage3` must pass out-of-process. Evidence acquired for a bundle
    # that was never admitted is evidence about nothing.
    admission = adapt_annotation_bundle(
        stage3_bundle, require_external_verifier=require_external_verifier)
    manifest = load_manifest(run_root)
    doc = materialize(admission, manifest, RunRoot(run_root), version)

    # Deterministic bytes: sorted keys, a trailing newline, nothing from the wall clock.
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")

    lanes = {k: len(v) for k, v in sorted(doc.items())
             if isinstance(v, list) and v}
    absent = [s["lane"] for s in doc["config"]["not_evaluated"]]
    print(json.dumps({
        "schema_id": doc["schema_id"],
        "evidence_bundle": out,
        "sources": len(doc["sources"]),
        "lanes_with_evidence": lanes,
        "not_evaluated": sorted(set(absent)),
        "acquisition_run_id": doc["config"]["acquisition_run_id"],
    }, indent=2, sort_keys=True))
    return 0



def _route(annotation: Optional[str], legacy: Optional[str]) -> str:
    """Exactly one door, named for what it opens.

    This CLI consumes Stage 3's DRUG-ANNOTATION bundle (`spot.stage03_drug_annotation.v1`) through
    `stage3_annotation.py`. The flag used to be called `--stage3-bundle`, which is the name of the
    OTHER door — the wire bundle (`stage3_adapter.py`) — so a caller who read the flag and handed
    it a wire bundle got a confusing failure deep inside the annotation reader, and a caller who
    read the README was told to run the wrong command.

    The legacy name is not silently accepted: a wrong bundle admitted under a right-looking flag is
    exactly how evidence gets bound to the wrong upstream.
    """
    if legacy and annotation:
        raise Rejection(
            "stage3_bundle_flag_ambiguous",
            "--stage3-bundle and --stage3-annotation-bundle were both given. They are different "
            "doors; supply exactly one.",
        )
    if legacy:
        raise Rejection(
            "stage3_bundle_flag_retired",
            "--stage3-bundle is retired here. This command reads Stage 3's DRUG-ANNOTATION bundle "
            "(spot.stage03_drug_annotation.v1) via analysis/stage3_annotation.py, not the wire "
            "bundle. Re-run with --stage3-annotation-bundle. The flag was renamed because the old "
            "name pointed at the other door, and a bundle admitted through the wrong door binds "
            "evidence to the wrong upstream.",
        )
    if not annotation:
        raise Rejection("stage3_bundle_missing", "--stage3-annotation-bundle is required")
    return annotation


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_materialize", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage3-annotation-bundle", dest="annotation_bundle",
                    help="an ADMITTED Stage-3 drug-annotation bundle "
                         "(spot.stage03_drug_annotation.v1)")
    ap.add_argument("--stage3-bundle", dest="legacy_bundle",
                    help=argparse.SUPPRESS)   # legacy name; routed to a refusal, see below
    ap.add_argument("--run-root", required=True,
                    help="the run root `run_acquire` wrote (acquisition_manifest.json + raw/)")
    ap.add_argument("--out", required=True, help="write the evidence bundle here")
    ap.add_argument("--contract", choices=["v1", "v2"], default="v2",
                    help="the evidence contract to speak. v1 is FROZEN and carries no "
                         "acquisition lane; v2 is the acquisition contract. Default v2.")
    ap.add_argument("--require-external-verifier", action="store_true",
                    help="a REAL run: refuse a Stage-3 bundle whose own verifier has not passed")
    args = ap.parse_args(argv)

    try:
        bundle = _route(args.annotation_bundle, args.legacy_bundle)
        return run(bundle, args.run_root, args.out,
                   require_external_verifier=args.require_external_verifier,
                   version=ContractVersion(args.contract))
    except Rejection as exc:
        print(f"REFUSED [{exc.code}] {exc.detail}", file=sys.stderr)
        return 2
    except ValidationError as exc:
        # A contract violation is a REFUSAL, not a crash. This escaped as a raw pydantic traceback
        # -- which is how the `accessed_at_utc` defect presented: a stack trace instead of a named,
        # fail-closed rejection an operator could act on. The contract caught the problem; the CLI
        # just failed to say so.
        first = exc.errors(include_url=False)[:2]
        print(f"REFUSED [evidence_row_violates_contract] the acquisition cannot be materialized "
              f"into a valid evidence bundle: {first}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
