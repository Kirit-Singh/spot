"""The GENERATOR-INDEPENDENT Stage-3 **v2** verifier.

    PYTHONPATH=. python -m verifier.verify_stage3_v2 \
        --bundle <stage3 v2 bundle dir> \
        --stage2-aggregate-manifest <aggregate run manifest> \
        --stage2-aggregate-report   <SEPARATE independent aggregate report> \
        --stage2-bundles-root       <root of the 15 lane bundles> \
        --stage1-release            <the staged Stage-1 release the aggregate pins> \
        --universe-store            <the admitted universe store dir> \
        --stage3-bridge             <W3 bridge root: bridge + report + receipt> \
        --artifact-class analysis --write-report

Independence is structural and test-enforced: this package imports NOTHING from
``druglink``. It RESTATES the contract (:mod:`verifier.v2_contract`), reimplements content
addressing (:mod:`verifier.canon`), re-expresses Stage-2's NATIVE admission from the actual
bytes (:mod:`verifier.v2_reconstruct`), re-admits W3's Stage-3 BRIDGE and rebuilds every typed
row from the native ranking it was built from (:mod:`verifier.v2_bridge`), re-derives the typed
universe and re-opens the admitted store (:mod:`verifier.v2_store`), re-makes every
arm-to-source-assertion join by exact typed identity, and RE-DERIVES the direction of every edge
(:mod:`verifier.v2_sign`).

THE SIGN IS RE-DERIVED, NEVER READ. The direction comes from the SIGNED ``arm_value`` in the
ADMITTED NATIVE RANKING, against the modality the row DECLARES — and the producer's (and the
bridge's) serialized modulation is then REQUIRED to equal it. A disagreement is a NAMED REFUSAL.
A verifier that classified FROM the producer's token could only prove the producer agreed with
itself, which is the exact generator=evaluator collapse this project has caught six times.

Exit 0 = every named gate passed. Fail-closed: a missing artifact is a NAMED refusal, never
an exception and never a silent pass.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Optional

from . import v2_bridge as br
from . import v2_checks as K
from . import v2_table_checks as TK
from . import v2_stage4 as S4
from . import v2_contract as C
from . import v2_rebuild as vb
from . import v2_reconstruct as vr
from .report import Report


# --------------------------------------------------------------------------- #
# The whole gate.
# --------------------------------------------------------------------------- #
def verify(*, bundle: str, stage2_aggregate_manifest: str, stage2_aggregate_report: str,
           stage2_bundles_root: str, stage1_release: str, universe_store: str,
           stage3_bridge_root: str, artifact_class: str,
           science_registry_root: Optional[str] = None,
           expected_code_sha256: Optional[str] = None,
           expected_env_sha256: Optional[str] = None) -> Report:
    rep = Report()

    if artifact_class not in C.ARTIFACT_CLASSES:
        K._gate(rep, C.GATE_FIXTURE_FIREWALL,
              f"the requested artifact class is one of {list(C.ARTIFACT_CLASSES)}",
              False, f"got {artifact_class!r}")
        return rep

    manifest_path = os.path.join(str(bundle or ""), "manifest.json")
    if not K._gate(rep, C.GATE_BUNDLE_NOT_ON_DISK,
                 "the Stage-3 v2 bundle is on disk and carries a manifest",
                 os.path.isfile(manifest_path), f"not found: {manifest_path!r}"):
        return rep
    manifest = K.read_json(manifest_path)

    doc_file = manifest.get("document_file")
    doc_path = os.path.join(bundle, str(doc_file or ""))
    if not K._gate(rep, C.GATE_BUNDLE_NOT_ON_DISK,
                 "the manifest names a document file, and that document is on disk",
                 bool(doc_file) and os.path.isfile(doc_path),
                 f"document_file={doc_file!r}"):
        return rep
    doc = K.read_json(doc_path)

    emitted: dict[str, list[dict[str, Any]]] = {}
    columns: dict[str, list[str]] = {}
    for name in sorted(C.TABLES):
        got = K.read_table(bundle, name)
        if got is None:
            K._gate(rep, C.GATE_BUNDLE_INVENTORY, f"the bundle ships the {name} table",
                  False, "absent")
            continue
        emitted[name], columns[name] = got

    K.check_identity(rep, bundle=bundle, manifest=manifest, doc=doc,
                   artifact_class=artifact_class)
    K.check_hygiene(rep, doc=doc, manifest=manifest, emitted=emitted, columns=columns)
    K.check_science_registry(rep, doc=doc, root=science_registry_root)
    S4.check_stage4_read_contract(rep, emitted=emitted)
    S4.check_candidate_identity(rep, doc=doc, emitted=emitted)

    aggregate = vr.admit_aggregate(rep, manifest_path=stage2_aggregate_manifest,
                                   report_path=stage2_aggregate_report,
                                   bundles_root=stage2_bundles_root,
                                   stage1_release=stage1_release)
    K.check_schema_and_firewall(rep, manifest=manifest, doc=doc,
                              artifact_class=artifact_class, aggregate=aggregate)
    store = vr.open_store(rep, store_dir=universe_store, artifact_class=artifact_class)

    digest = C.direction_vocabulary_digest()
    K.check_v2_admission_contract(rep, doc=doc, edges=emitted.get("target_drug_edges") or [],
                                digest=digest, artifact_class=artifact_class)
    # THE SIGN, ON THE EMITTED BYTES. Named refusals, before anything is rebuilt: a
    # reconstruction mismatch refuses every inversion under ONE name, and these say WHICH.
    TK.check_sign_rule(rep, doc=doc, emitted=emitted)
    modality_digest = TK.check_modality_vocabulary(rep, doc=doc)

    # THE W3 BRIDGE. The native ranking row carries neither namespace nor modality — those two
    # facts exist ONLY here. It is re-hashed, its SEPARATE report and RECEIPT are required to
    # admit these exact bytes over the aggregate we just admitted, and every row is REBUILT from
    # the native bytes: the bridge may ADD identity and modality, and may never CHANGE a value
    # the admitted ranking already states.
    bridge = (br.admit_bridge(rep, bridge_root=stage3_bridge_root, aggregate=aggregate)
              if aggregate is not None else None)

    if aggregate is None or store is None or modality_digest is None or bridge is None:
        K._gate(rep, C.GATE_RECONSTRUCTION_MISMATCH,
              "the bundle's evidence is reconstructed from its admitted sources — the Stage-2 "
              "aggregate, the W3 Stage-3 bridge and the universe store — under a sign contract "
              "this verifier agrees with. An input that did not admit cannot be reconstructed "
              "FROM, so nothing downstream is allowed to pass on no evidence",
              False, "the Stage-2 aggregate, the W3 bridge, the universe store or the sign "
                     "contract did not admit")
        return rep

    # THE BUNDLE MUST NAME THE BRIDGE IT WAS TYPED BY — these exact bytes.
    br.check_bundle_names_this_bridge(rep, doc=doc, bridge=bridge)

    rebuilt = vb.reconstruct(rep, aggregate=aggregate, store=store,
                             bridge_rows=bridge["rows"], artifact_class=artifact_class,
                             modality_digest=modality_digest)
    if rebuilt is None:
        return rep

    K.check_bindings(rep, doc=doc, aggregate=aggregate, store=store, digest=digest,
                   expected_code=expected_code_sha256, expected_env=expected_env_sha256)
    S4.check_provenance(rep, emitted=emitted, aggregate=aggregate, store=store, doc=doc,
                     digest=digest)
    TK.check_tables(rep, emitted=emitted, rebuilt=rebuilt, doc=doc, manifest=manifest)
    return rep


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Independent Stage-3 v2 verifier")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--stage2-aggregate-manifest", required=True)
    ap.add_argument("--stage2-aggregate-report", required=True)
    ap.add_argument("--stage2-bundles-root", required=True)
    ap.add_argument("--stage1-release", required=True)
    ap.add_argument("--universe-store", required=True)
    ap.add_argument("--stage3-bridge", required=True,
                    help="the W3 Stage-3 bridge root: stage3_bridge.json + its SEPARATE "
                         "verification report + the Stage-2->Stage-3 receipt")
    ap.add_argument("--artifact-class", required=True, choices=list(C.ARTIFACT_CLASSES))
    ap.add_argument("--science-registry", default=None)
    ap.add_argument("--expected-code-sha256", default=None)
    ap.add_argument("--expected-env-sha256", default=None)
    ap.add_argument("--write-report", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        rep = verify(bundle=args.bundle,
                     stage2_aggregate_manifest=args.stage2_aggregate_manifest,
                     stage2_aggregate_report=args.stage2_aggregate_report,
                     stage2_bundles_root=args.stage2_bundles_root,
                     stage1_release=args.stage1_release,
                     universe_store=args.universe_store,
                     stage3_bridge_root=args.stage3_bridge,
                     artifact_class=args.artifact_class,
                     science_registry_root=args.science_registry,
                     expected_code_sha256=args.expected_code_sha256,
                     expected_env_sha256=args.expected_env_sha256)
    except Exception as exc:                 # a crash IS a verification failure
        rep = Report()
        rep.check(f"the verifier completed ({type(exc).__name__}: {exc})", False)

    payload = rep.as_dict(
        artifact_class=args.artifact_class, contract_id=C.CONTRACT_ID,
        bundle_id=os.path.basename(os.path.abspath(str(args.bundle).rstrip("/"))),
        verified_at=_dt.datetime.now(_dt.UTC).isoformat())

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(rep.render())
        if rep.failures:
            print("\nREFUSED:")
            for name, detail in rep.failures:
                print(f"  - {name} {detail}")

    if args.write_report:
        with open(os.path.join(args.bundle, "verification.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")

    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
