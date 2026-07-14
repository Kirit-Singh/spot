"""Stage-1 -> Stage-2 (Direct) interoperability bridge.

Deterministic, hash-bound projections that let the Stage-2 "Direct" package consume
the frozen Stage-1 v3.0.1 measurement bundle WITHOUT recomputing any score, control,
coefficient, or metric value. Nothing here mutates a protected numerical/scorer
artifact; every output is a faithful view/projection of frozen inputs.

Modules (each <=500 lines, one purpose):
  canonical            - canonical JSON + SHA-256 helpers (byte-identical to Direct
                         hashing.canonical_json and the browser canonicalJSON).
  protected_hashes     - frozen pre-change baseline of every protected artifact +
                         the scorer-projection invariant; check_protected() guards it.
  build_registry_view  - CP2: the executable Stage-2 registry view (scorer projection).
  build_gate_projection- CP3: Direct hard_gates/thresholds + validation rows projection.
  rederive_selectability - CP3: independent re-derivation of Direct's selectability rule
                         (does NOT read stored pass booleans); proves 33 evaluated/0 selectable.
  build_release_manifest - CP4: spot.stage01_release_manifest.v1 + served bindings.
  build_bridge         - orchestrator (generator).
  verify_bridge        - INDEPENDENT verifier (generator != verifier).

generator != evaluator: build_bridge writes; verify_bridge re-derives everything from
the frozen sources and from the live Direct rule, and never trusts the builder's output.
"""
