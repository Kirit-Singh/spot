// Generic downstream island page — PRODUCTION ONLY. There is NO public demo/fixture route: the
// former ?demo=1 gate is retired, and no synthetic fixture is imported into the served bundle
// (synthetic fixtures are test-only). The built JS therefore carries no GENE_A / COMPOUND_A /
// fixture rows.
//
//  · Header contrast comes ONLY from the fully-verified async v3 selection (readStage1SelectionV3 →
//    hash recompute + routing re-derivation); a forged valid-shaped v3 is rejected and the header
//    shows the neutral prompt (never a forged contrast). The canvas renders real rows only when an
//    admitted W5/W11 temporal artifact resolves, else a COMPACT NEUTRAL pending panel — no banner,
//    no scaffold card, no fixture data.
//  · The ONE shared Methods & Provenance drawer always carries the REAL per-tab method-DEFINITION
//    manifest (method id / estimand / inputs / sources / masking / offline reproduce command),
//    content-addressed and loaded INDEPENDENT of result admission; result-run fields render
//    "unavailable" until an admitted run exists.
//  · <main> stays clean: compact functional state + real rows ONLY — no Science-evidence surface,
//    no review-job control, no scaffold card, no batch/confound copy.

import { useEffect, useState } from 'react';
import { PageShell } from './PageShell';
import type { PageKey } from './pages';
import type { ScaffoldRegion } from '../shell/StageScaffold';
import type { ScienceEvidenceRecord } from './evidence';
import {
  contrastTitle,
  clearStage1Selection,
  readStage1SelectionV3,
  NO_SELECTION_TITLE,
} from './contrastTitle';
import type { Stage1Selection } from './contrastTitle';
import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { unavailableManifest } from '../domain/methodsManifest';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import { buildStageMethodsManifest } from './stageMethods';
import { StatePill } from '../shell/chips';
import { renderReal } from './renderReal';
import type { RealArtifactResolution } from './renderReal';

export interface StageIslandProps {
  page: PageKey;
  subtitle: string;
  /**
   * Real (production) artifact-resolution seam. Returns an ADMITTED resolution to render real rows,
   * or null when nothing is bound (→ pending state). The admission gate lives inside the loader;
   * StageIsland awaits it and renders pending until it resolves. NEVER demo/fixture.
   */
  loadRealArtifact?: () => Promise<RealArtifactResolution | null> | RealArtifactResolution | null;
  // Deprecated demo-entry props — accepted (optional, unused) for test call-site compatibility only;
  // the demo route is retired and none of these are read. No fixture is imported here.
  purpose?: string;
  regions?: ScaffoldRegion[];
  enqueueTarget?: string;
  renderDemo?: () => React.ReactNode;
  demoEvidence?: ScienceEvidenceRecord | null;
}

/** Compact, neutral pending panel — no banner, no scaffold card, no fixture data. */
function PendingArtifact({ resolving }: { resolving: boolean }) {
  return (
    <div className="flex min-h-0 flex-1 items-start p-4">
      <section
        aria-label="Artifact status"
        className="inline-flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-line bg-surface px-3 py-2"
      >
        <StatePill label={resolving ? 'resolving' : 'not generated'} tone="muted" />
        <span className="font-mono text-[10.5px] text-ink-2">pending independent admission</span>
      </section>
    </div>
  );
}

/** Header contrast from a fully-verified v3 selection (program_ids as labels; v3 carries no label). */
function contrastFromV3(sel: SelectionV3): Stage1Selection {
  return {
    program_a: { display_label: sel.A.program_id, direction: sel.A.direction },
    program_b: { display_label: sel.B.program_id, direction: sel.B.direction },
    analysis_condition: sel.conditions[0],
  };
}

interface ProdState {
  loading: boolean;
  selection: SelectionV3 | null; // verified v3 (null → prompt); NEVER an unverified/forged contract
  manifest: StageMethodsManifest | null; // real per-tab method-definition manifest
  real: RealArtifactResolution | null; // admitted artifact (already admission-gated) or null
}

export function StageIsland({ page, subtitle, loadRealArtifact }: StageIslandProps) {
  const [prod, setProd] = useState<ProdState>({
    loading: true,
    selection: null,
    manifest: null,
    real: null,
  });

  useEffect(() => {
    let cancelled = false;
    setProd((p) => ({ ...p, loading: true }));
    (async () => {
      const [selection, manifest, real] = await Promise.all([
        readStage1SelectionV3().catch(() => null), // fail-closed: forged/absent v3 → null
        buildStageMethodsManifest(page).catch(() => null), // real, admission-independent (canonical label)
        (loadRealArtifact ? Promise.resolve(loadRealArtifact()) : Promise.resolve(null)).catch(() => null),
      ]);
      if (cancelled) return;
      // ADMISSION gate: a temporal artifact renders ONLY when admission === 'admitted'.
      const admitted = real && real.admission === 'admitted' ? real : null;
      setProd({ loading: false, selection, manifest, real: admitted });
    })();
    return () => {
      cancelled = true;
    };
  }, [page, loadRealArtifact]);

  // Header contrast: production → the VERIFIED v3 ONLY (never a forged or synthetic contrast).
  const contrast = prod.selection ? contrastTitle(contrastFromV3(prod.selection)) : null;
  const headerTitle = contrast ?? NO_SELECTION_TITLE;
  const headerNode = contrast ? undefined : (
    <>
      Select populations in{' '}
      <a
        href="01_page.html"
        className="underline decoration-ink underline-offset-[3px] hover:text-accent hover:decoration-accent"
      >
        Programs
      </a>{' '}
      →
    </>
  );
  // Offer Clear only when a real (verified) selection is bound — NEVER for a forged/absent v3
  // (which resolves to the neutral prompt with no clear control).
  const onClearSelection = contrast
    ? () => {
        clearStage1Selection();
        window.location.assign('01_page.html');
      }
    : undefined;

  // The drawer manifest: the REAL method-definition manifest once resolved, else the honest
  // pre-resolution fallback (source-tissue only; other definition rows + run details are OMITTED and
  // the drawer shows ONE route status — no "unavailable" wall). The harness may internally call
  // missing run fields "unavailable", but they are ABSENT from the DOM in this pending state. Never
  // blocks on result admission; never a synthetic fixture.
  const methodsManifest = prod.manifest ?? unavailableManifest(subtitle);

  return (
    <PageShell
      page={page}
      subtitle={headerTitle}
      subtitleNode={headerNode}
      onClearSelection={onClearSelection}
      methodsManifest={methodsManifest}
    >
      {prod.real ? (
        // prod.real is only set when admission === 'admitted' (gated above)
        renderReal(prod.real.view, prod.real.bundles)
      ) : (
        <PendingArtifact resolving={prod.loading} />
      )}
    </PageShell>
  );
}
