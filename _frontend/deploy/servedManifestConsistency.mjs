// Fail-closed consistency verifier for the SERVED Stage-1 distribution (deploy_8347 serves
// 01_programs/app + app/data). It refuses to promote a served tree whose release-manifest
// ATTESTATION contradicts what is physically served — the "do not paper over it" guard.
//
// It does NOT regenerate or judge the Stage-1 attestation (that is gen_stage1_t8.py /
// gen_full_release_verification.py on the compute host); it only proves the served bytes and the
// served manifests tell ONE consistent story. Three deterministic rules:
//
//   R1 overlay gate vs reality — overlay_release_ok:false (or not_lockable includes
//      'overlay_release_blocked') while the v3 overlay is physically served → contradiction. This is
//      the exact audit finding: the manifest says "overlay not served" but the page serves+requires it.
//   R2 served-copy gate agreement — every served file that re-states overlay_release_ok /
//      app_deployment_ready must equal the release manifest's release_gates (no split-brain across
//      served copies).
//   R3 staged-not-served yet present — any release-manifest artifact whose location is
//      'release_staging_not_served' must NOT be physically present under served data/ by its declared
//      served filename (an un-promoted staging artifact cannot also be a served byte).
//
// The pure core takes already-read inputs so it is unit-testable with no filesystem; the CLI reads
// the served tree and exits nonzero (with every contradiction printed) so the deploy can `die` on it.

export const OVERLAY_SERVED_FILE = 'stage01_umap_overlay_v3.json';

/**
 * @param {object} args
 * @param {object} args.releaseManifest  parsed stage01_release_manifest.json
 * @param {string[]} args.servedDataFiles  filenames physically present in served data/
 * @param {string[]} [args.pageRequiredFiles]  ./data/* files the served page hard-requires
 * @param {Array<{source:string, gates:object}>} [args.gateStatements]  other served files re-stating gates
 * @returns {{source:string, rule:string, message:string}[]} contradictions (empty ⇒ consistent)
 */
export function findServedManifestContradictions({ releaseManifest, servedDataFiles, pageRequiredFiles = [], gateStatements = [] }) {
  const out = [];
  const served = new Set(servedDataFiles);
  const required = new Set(pageRequiredFiles.map((p) => p.replace(/^\.\/data\//, '').replace(/^data\//, '')));
  const gates = (releaseManifest && releaseManifest.release_gates) || {};
  const reasons = Array.isArray(releaseManifest && releaseManifest.not_lockable_reason_codes)
    ? releaseManifest.not_lockable_reason_codes
    : [];

  // ── R1: overlay attested un-released while it is physically served (and required) ──
  const overlayBlocked = gates.overlay_release_ok === false || reasons.includes('overlay_release_blocked');
  const overlayServed = served.has(OVERLAY_SERVED_FILE);
  if (overlayBlocked && overlayServed) {
    const req = required.has(OVERLAY_SERVED_FILE) ? ' and the served page hard-requires it' : '';
    out.push({
      source: 'stage01_release_manifest.json',
      rule: 'R1_overlay_gate_vs_reality',
      message: `overlay_release_ok=false / overlay_release_blocked, but ${OVERLAY_SERVED_FILE} is physically served${req}. Regenerate the attestation to reflect the promoted overlay (or unpromote it) — do not ship the contradiction.`,
    });
  }

  // ── R2: split-brain across served files that re-state the same gates ──
  for (const stmt of gateStatements) {
    for (const key of ['overlay_release_ok', 'app_deployment_ready']) {
      if (stmt.gates && key in stmt.gates && key in gates && stmt.gates[key] !== gates[key]) {
        out.push({
          source: stmt.source,
          rule: 'R2_served_gate_agreement',
          message: `${stmt.source} declares ${key}=${stmt.gates[key]} but stage01_release_manifest.json release_gates.${key}=${gates[key]} — served copies disagree.`,
        });
      }
    }
  }

  // ── R3: any staging-not-served artifact physically present under served data/ ──
  const artifacts = (releaseManifest && releaseManifest.artifacts) || {};
  for (const [key, entry] of Object.entries(artifacts)) {
    if (!entry || entry.location !== 'release_staging_not_served') continue;
    const servedName = entry.file || key;
    if (served.has(servedName)) {
      out.push({
        source: 'stage01_release_manifest.json',
        rule: 'R3_staged_artifact_served',
        message: `artifact "${key}" is attested location=release_staging_not_served but ${servedName} is physically present in served data/.`,
      });
    }
  }

  return out;
}

// ───────────────────────── CLI (reads the served tree, fails closed) ─────────────────────────
async function main(appDir) {
  const { readFileSync, readdirSync, existsSync } = await import('node:fs');
  const { join } = await import('node:path');
  const dataDir = join(appDir, 'data');
  const relPath = join(dataDir, 'stage01_release_manifest.json');
  if (!existsSync(relPath)) {
    console.error(`served release manifest not found: ${relPath}`);
    process.exit(2);
  }
  const releaseManifest = JSON.parse(readFileSync(relPath, 'utf8'));
  const servedDataFiles = readdirSync(dataDir);

  // gates re-stated by other served files (best-effort; only compares keys they actually carry)
  const gateStatements = [];
  for (const f of ['stage01_current.json', 'stage01_validation.json']) {
    const p = join(dataDir, f);
    if (!existsSync(p)) continue;
    try {
      const obj = JSON.parse(readFileSync(p, 'utf8'));
      const g = findGateObject(obj);
      if (g) gateStatements.push({ source: f, gates: g });
    } catch { /* a served file that isn't JSON we can read is out of scope here */ }
  }

  // files the served page hard-requires (best-effort parse of T('./data/..') required loads)
  let pageRequiredFiles = [];
  const pagePath = join(appDir, '01_page.html');
  if (existsSync(pagePath)) {
    const html = readFileSync(pagePath, 'utf8');
    pageRequiredFiles = [...html.matchAll(/\.\/data\/(stage01_[a-z0-9_]+\.json)/g)].map((m) => m[1]);
  }

  const contradictions = findServedManifestContradictions({ releaseManifest, servedDataFiles, pageRequiredFiles, gateStatements });
  if (contradictions.length) {
    console.error(`SERVED MANIFEST CONTRADICTIONS (${contradictions.length}) — refusing to promote:`);
    for (const c of contradictions) console.error(`  [${c.rule}] ${c.source}: ${c.message}`);
    process.exit(1);
  }
  console.log('served manifests consistent — no contradiction between attestation and served bytes');
}

/** Find the object that carries overlay_release_ok / app_deployment_ready anywhere one level deep. */
function findGateObject(obj) {
  if (!obj || typeof obj !== 'object') return null;
  if ('overlay_release_ok' in obj || 'app_deployment_ready' in obj) return obj;
  for (const v of Object.values(obj)) {
    if (v && typeof v === 'object' && ('overlay_release_ok' in v || 'app_deployment_ready' in v)) return v;
  }
  return null;
}

// Run as CLI only when invoked directly (never on import from the test).
if (import.meta.url === `file://${process.argv[1]}`) {
  const appDir = process.argv[2];
  if (!appDir) {
    console.error('usage: servedManifestConsistency.mjs <served_app_dir>   (dir containing 01_page.html + data/)');
    process.exit(2);
  }
  main(appDir);
}
