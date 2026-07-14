// The exact Stage-1 v3 contract release this UI is BUILT AGAINST (contract 539431d, independently GO).
// These are release-level identity hashes lifted verbatim from the authoritative release manifest
// `01_programs/analysis/stage2_bridge/release/stage01_v3_release.json` (schema spot.stage01_v3_release.v1):
//
//   STAGE1_SELECTION_SCHEMA_RAW_SHA256 = components.selection_schema_v3.raw_sha256
//       — the raw sha256 of spot.stage01_selection.v3.schema.json (role: selection_contract_schema).
//   STAGE1_V3_RELEASE_SELF_SHA256      = self_release_sha256
//       — the self-hash of the whole Stage-1 v3 release bundle.
//
// They pin the RELEASE, not any one selection (selection_id / question_id are re-derived per selection
// in the selectionV3 verifier). The loader refuses a served results/current.json whose stage1_binding
// declares a different release identity than the UI was built against — so a deployed UI can only ever
// resolve downstream results that descend from THIS 539431d contract. Bump both together on a Stage-1
// release change; a stale pin fails closed (every route unbound) rather than binding cross-release data.

export const STAGE1_SELECTION_SCHEMA_RAW_SHA256 =
  'f8104283d7139ed47059978751dbed33e8426c920ba0d8086082eda9c43f4c1d' as const;

export const STAGE1_V3_RELEASE_SELF_SHA256 =
  '2262430931707552f4414808be3d6734fa3c7287748ec23339ce3ef498224b11' as const;
