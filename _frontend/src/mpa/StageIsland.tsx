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
import { loadProgramLabels, programLabel } from './programLabels';
import { directionLabel } from './contrastTitle';
import { StatePill } from '../shell/chips';
import { renderRouteReal } from './renderReal';
import type { RealRouteResolution } from './renderReal';
import type { DevelopmentRealResolution } from './devRealAdapter';
import { renderDevelopmentReal } from './devRealRender';
import type { SelectionDisplayContext } from '../domain/selectionDisplay';

export interface StageIslandProps {
  page: PageKey;
  subtitle: string;
  /**
   * Real (production) artifact-resolution seam. Returns an ADMITTED resolution to render real rows,
   * or null when nothing is bound (→ pending state). The admission gate lives inside the loader;
   * StageIsland awaits it and renders pending until it resolves. NEVER demo/fixture.
   */
  loadRealArtifact?: (page: PageKey) => Promise<RealRouteResolution | DevelopmentRealResolution | null> | RealRouteResolution | DevelopmentRealResolution | null;
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

/** Header contrast from a fully-verified v3 selection, with Tier-2 display labels resolved from the
 *  Stage-1 display registry (never a raw program_id when the registry names it; v3 carries no label). */
export function contrastFromV3(sel: SelectionV3, labels: Map<string, string>): Stage1Selection {
  const conditionA = sel.conditions[0];
  const conditionB = sel.conditions[1] ?? conditionA;
  return {
    program_a: { display_label: programLabel(labels, sel.A.program_id), direction: sel.A.direction },
    program_b: { display_label: programLabel(labels, sel.B.program_id), direction: sel.B.direction },
    condition_a: conditionA,
    condition_b: conditionB,
    analysis_condition: sel.conditions.length === 1 ? conditionA : undefined,
  };
}

/** Drawer projection from the same verified v3 object used for routing and the visible title. */
export function selectionDisplayFromV3(
  sel: SelectionV3,
  labels: Map<string, string>,
): SelectionDisplayContext {
  const conditionA = sel.conditions[0];
  const conditionB = sel.conditions[1] ?? conditionA;
  return {
    selection_id: sel.selection_id,
    question_id: sel.question_id,
    analysis_mode: sel.analysis_mode,
    execution_status: sel.execution_status,
    estimator_id: sel.estimator_id,
    estimator_status: sel.estimator_status,
    A: {
      program_id: sel.A.program_id,
      display_label: programLabel(labels, sel.A.program_id),
      direction: sel.A.direction,
      condition: conditionA,
    },
    B: {
      program_id: sel.B.program_id,
      display_label: programLabel(labels, sel.B.program_id),
      direction: sel.B.direction,
      condition: conditionB,
    },
  };
}

/** A content-consistent selection still must name axes offered by the served Stage-1 registry.
 *  Hash recomputation proves internal consistency; registry membership proves display provenance. */
export function selectionProgramsAreKnown(
  sel: SelectionV3,
  labels: Map<string, string>,
): boolean {
  return labels.has(sel.A.program_id) && labels.has(sel.B.program_id);
}

interface ProdState {
  loading: boolean;
  selection: SelectionV3 | null; // verified v3 (null → prompt); NEVER an unverified/forged contract
  manifest: StageMethodsManifest | null; // real per-tab method-definition manifest
  real: RealRouteResolution | DevelopmentRealResolution | null;
  labels: Map<string, string>; // program_id → Tier-2 display label (from the Stage-1 display registry)
}

export function StageIsland({ page, subtitle, loadRealArtifact }: StageIslandProps) {
  const [prod, setProd] = useState<ProdState>({
    loading: true,
    selection: null,
    manifest: null,
    real: null,
    labels: new Map(),
  });

  useEffect(() => {
    let cancelled = false;
    setProd((p) => ({ ...p, loading: true }));
    (async () => {
      const [selection, manifest, real, labels] = await Promise.all([
        readStage1SelectionV3().catch(() => null), // fail-closed: forged/absent v3 → null
        buildStageMethodsManifest(page).catch(() => null), // real, admission-independent (canonical label)
        (loadRealArtifact ? Promise.resolve(loadRealArtifact(page)) : Promise.resolve(null)).catch(() => null),
        loadProgramLabels().catch(() => new Map<string, string>()), // Tier-2 display labels (display-only)
      ]);
      if (cancelled) return;
      // Production remains admitted-only. The narrowly-scoped development resolver is separately
      // typed and may render only its exact Rest/Stim8 real-data artifacts; it is never relabelled admitted.
      const admitted = real && (real.admission === 'admitted' || real.admission === 'development') ? real : null;
      setProd({ loading: false, selection, manifest, real: admitted, labels });
    })();
    return () => {
      cancelled = true;
    };
  }, [page, loadRealArtifact]);

  // Header contrast: production → the VERIFIED v3 ONLY (never a forged or synthetic contrast), with
  // Tier-2 display labels resolved from the registry (never a raw program_id when the registry names it).
  const displaySelection = prod.selection && selectionProgramsAreKnown(prod.selection, prod.labels)
    ? prod.selection
    : null;
  const contrast = displaySelection ? contrastTitle(contrastFromV3(displaySelection, prod.labels)) : null;
  const developmentContrast = prod.real?.admission === 'development'
    ? contrastTitle({
        program_a: {
          display_label: programLabel(prod.labels, prod.real.context.programA),
          direction: 'high',
        },
        program_b: {
          display_label: programLabel(prod.labels, prod.real.context.programB),
          direction: 'high',
        },
        condition_a: prod.real.context.condition,
        condition_b: prod.real.context.condition,
        analysis_condition: prod.real.context.condition,
      })
    : null;
  const selectionDisplay = displaySelection
    ? selectionDisplayFromV3(displaySelection, prod.labels)
    : null;
  const headerTitle = developmentContrast ?? contrast ?? NO_SELECTION_TITLE;
  const headerNode = developmentContrast || contrast ? undefined : (
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

  // The drawer manifest, in fail-closed precedence:
  //   1. prod.real.manifest — an ADMITTED run: the STATIC route method-definition MERGED with the
  //      admitted run's exact code / environment / run-UTC / generator / verifier / artifacts /
  //      reproduce command / Claude-Science notebook (mergeAdmittedManifest, after the release manifest
  //      passes parseUiReleaseManifest). isRunBound → true, so the drawer shows the real run rows.
  //   2. prod.manifest — the static, content-addressed route method-DEFINITION (no admitted bundle):
  //      run-status stays collapsed to the ONE-LINE unbound status row.
  //   3. the honest pre-resolution fallback (source-tissue only; other rows omitted; one status row).
  // Never blocks on result admission; never a synthetic fixture.
  const methodsManifest = (prod.real?.admission === 'admitted' ? prod.real.manifest : null)
    ?? prod.manifest
    ?? unavailableManifest(subtitle);

  return (
    <PageShell
      page={page}
      subtitle={headerTitle}
      subtitleNode={headerNode}
      onClearSelection={onClearSelection}
      selectionV3={selectionDisplay}
      methodsManifest={methodsManifest}
    >
      {prod.real ? (
        // prod.real is only set when admission === 'admitted' (gated above); each route renders its
        // OWN native path — Stage 3/4 never fall through to the Stage-2 tables. The label map is
        // display-only (same registry the header uses); it never reaches an artifact or a hash.
        //
        // The canvas reads the SAME registry-gated displaySelection the header does: a selection whose
        // program axes the served registry does not name is refused everywhere, so it can never label a
        // pole on the map while the header has already reverted to the prompt.
        prod.real.admission === 'development' ? renderDevelopmentReal(prod.real, prod.labels) : renderRouteReal(prod.real, {
          labels: prod.labels,
          poleDirections: displaySelection
            ? { A: directionLabel(displaySelection.A.direction), B: directionLabel(displaySelection.B.direction) }
            : undefined,
        })
      ) : (
        <PendingArtifact resolving={prod.loading} />
      )}
    </PageShell>
  );
}
