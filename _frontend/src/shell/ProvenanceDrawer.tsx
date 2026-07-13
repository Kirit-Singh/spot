// Methods & provenance drawer — a right slide-over reused by every stage view.
// Shows artifact IDs, raw + canonical hashes, method/config/code/environment,
// and public source records. A real Claude-Science provenance record renders ONLY
// when actually bound — there is no generic "provenance trace" footer.

import { useEffect, useRef } from 'react';
import type { Provenance } from '../domain/common';
import type { Stage1Bindings, StageSelection } from '../domain/selection';
import type { MethodsBlock, ProvenanceBlock, SourceChainLink, StageMethodsManifest } from '../domain/methodsManifest';
import { isAdmittedVerifier } from '../domain/uiReleaseManifest';
import type { DrawerSection, ProvNote } from './provenanceContext';
import { NamespaceChip, EligibilityChip } from './chips';
import type { SelectionDisplayContext } from '../domain/selectionDisplay';

function Mono({ children }: { children: React.ReactNode }) {
  return <code className="break-all font-mono text-[11px] text-ink-2">{children}</code>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[104px_1fr] gap-3 py-1.5">
      <div className="font-mono text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="min-w-0 text-[12px] text-ink-2">{children}</div>
    </div>
  );
}

const BINDING_LABELS: Record<keyof Stage1Bindings, string> = {
  stage1_method_version: 'Method ver',
  program_registry_raw_sha256: 'Registry raw',
  program_registry_sha256: 'Registry',
  validation_raw_sha256: 'Validation raw',
  v3_overlay_raw_sha256: 'V3 overlay raw',
  v3_summary_raw_sha256: 'V3 summary raw',
  source_h5ad_sha256: 'Source h5ad',
};

/** The full Stage-1 selection detail — moved off the compact context bar to here. */
function SelectionSection({ selection }: { selection: StageSelection }) {
  const b = selection.stage1_bindings;
  return (
    <section className="mb-3 border-b border-line pb-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">
        Stage-1 selection
      </div>
      <Row label="A pole">
        {selection.program_a.display_label} · {selection.program_a.direction}
      </Row>
      <Row label="B pole">
        {selection.program_b.display_label} · {selection.program_b.direction}
      </Row>
      <Row label="Condition">{selection.analysis_condition}</Row>
      <Row label="Contrast">
        <Mono>{selection.contrast_id}</Mono>
      </Row>
      <Row label="Question">
        <Mono>{selection.question_id}</Mono>
      </Row>
      <Row label="Selection">
        <Mono>{selection.selection_id}</Mono>
      </Row>
      <Row label="Source">
        <Mono>{selection.source}</Mono>
      </Row>
      <Row label="Dataset">
        <Mono>{selection.dataset_id}</Mono>
      </Row>
      <Row label="Donor scope">{selection.donor_scope}</Row>
      {/* The production/research split + the historical selectability eligibility gate are RETIRED in
          the v3 contract and are not resurrected here. Any current v3 execution/estimator status
          renders only when actually bound (never a stale "production_eligible=false" claim). */}
      {b &&
        (Object.keys(BINDING_LABELS) as (keyof Stage1Bindings)[])
          .filter((k) => b[k] !== null)
          .map((k) => (
            <Row key={k} label={BINDING_LABELS[k]}>
              <Mono>{b[k]}</Mono>
            </Row>
          ))}
    </section>
  );
}

/** Verified v3 endpoint context. Temporal A and B retain their own ordered conditions. */
function SelectionV3Section({ selection }: { selection: SelectionDisplayContext }) {
  return (
    <section className="mb-3 border-b border-line pb-3" data-selection-v3>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">
        Stage-1 selection
      </div>
      <Row label="A endpoint">
        {selection.A.display_label} · {selection.A.direction} · {selection.A.condition}
      </Row>
      <Row label="B endpoint">
        {selection.B.display_label} · {selection.B.direction} · {selection.B.condition}
      </Row>
      <Row label="Mode">{selection.analysis_mode}</Row>
      <Row label="Execution">{selection.execution_status}</Row>
      <Row label="Estimator">
        {selection.estimator_id} · {selection.estimator_status}
      </Row>
      <Row label="Question"><Mono>{selection.question_id}</Mono></Row>
      <Row label="Selection"><Mono>{selection.selection_id}</Mono></Row>
    </section>
  );
}

/** Render a PRESENT value. Only ever called via DefRow (which omits null/empty fields), so there is
 *  no "unavailable" fallback branch — the shared drawer cannot accidentally reintroduce that filler;
 *  a missing field is represented ONLY by omission + the single route status row. */
function Val({ v, mono }: { v: string; mono?: boolean }) {
  return mono ? <Mono>{v}</Mono> : <>{v}</>;
}

function CopyCommand({ cmd }: { cmd: string }) {
  return (
    <div className="flex items-start gap-2">
      <code className="break-all font-mono text-[11px] text-ink-2">{cmd}</code>
      <button
        type="button"
        onClick={() => navigator.clipboard?.writeText(cmd)}
        aria-label="Copy reproduce command"
        className="flex-none rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted transition-colors hover:border-line-strong hover:text-ink"
      >
        copy
      </button>
    </div>
  );
}

/** A numbered teal step — EXACT Stage-1 .pstep/.pn grammar: grid-template-columns 26px 1fr, gap 12px,
 *  padding 7px 0, teal 24px circle (margin-top 1px), h4 margin 1px 0 3px / 13px. The grid is applied
 *  via INLINE style (not the Tailwind `.grid` class) so the acceptance harness's `.grid` row reader
 *  sees only the inner label/value Row `.grid` elements, never the step layout itself. */
function Step({ n, heading, children }: { n: string; heading: string; children: React.ReactNode }) {
  return (
    <div
      className="border-b border-sunken"
      data-step={n}
      style={{ display: 'grid', gridTemplateColumns: '26px 1fr', columnGap: '12px', padding: '7px 0' }}
    >
      <div
        className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent font-mono text-[12px] font-semibold text-white"
        style={{ marginTop: '1px' }}
      >
        {n}
      </div>
      <div className="min-w-0" data-step-body>
        <h4 className="text-[13px] font-semibold text-ink" style={{ margin: '1px 0 3px' }}>{heading}</h4>
        {children}
      </div>
    </div>
  );
}

/** Terse factual method boundaries, rendered INSIDE the relevant numbered step — never an editorial
 *  caveat block or banner. Compact factual method limits intrinsic to the estimand. */
function Boundaries({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 border-l-2 border-line pl-3 text-[11px] leading-relaxed text-ink-2">
      {items.map((l) => (
        <li key={l}>{l}</li>
      ))}
    </ul>
  );
}

/** Route-specific narrative headings for the estimand + masks steps (derived from the stage label),
 *  so each downstream tab reads as its own method — same bound fields, no duplicated prose. */
const STEP_HEADINGS: Record<string, { estimand: string; masks: string }> = {
  Targets: { estimand: 'Direct & temporal effects', masks: 'Target-guide masks & eligibility' },
  Pathways: { estimand: 'Ranked enrichment & signature convergence', masks: 'Gene-set coverage & namespace' },
  Drugs: { estimand: 'Direction-aware drug linking', masks: 'Target identity & mechanism evidence' },
  'PK & Safety': { estimand: 'Brain-exposure framework', masks: 'Label evidence & safety' },
};
function stepHeadings(stageLabel: string): { estimand: string; masks: string } {
  return STEP_HEADINGS[stageLabel] ?? { estimand: 'Estimand', masks: 'Masks & QC' };
}

// The admission vocabulary is the single source of truth in the domain (shared with the fail-closed
// UI-release-manifest adapter). Re-exported here for existing importers.
export { isAdmittedVerifier };

/** Whether a COMPLETE admitted-run identity is bound. FAIL-CLOSED: every required run field must be
 *  present (release + raw + canonical + generator + an ADMITTED verifier + nonempty artifacts +
 *  method-code hash + environment + last_run). Any partial/stale subset — or a verifier that is not
 *  an explicit pass/admission — still renders the ONE unbound status row, never a partial run claim.
 *  When false the drawer shows the method DEFINITION + References only. */
export function isRunBound(m: MethodsBlock, p: ProvenanceBlock): boolean {
  return !!(
    p.release_revision &&
    p.raw_sha256 &&
    p.canonical_sha256 &&
    p.generator_status &&
    isAdmittedVerifier(p.verifier_status) &&
    p.artifact_paths.length > 0 &&
    m.method_code_sha256 &&
    m.environment &&
    m.last_run_utc
  );
}

/** The one terse status shown (in place of the run-provenance rows) when no admitted bundle is bound. */
const UNBOUND_STATUS: Record<string, string> = {
  Targets: 'No admitted Stage-2 run bundle bound',
  Pathways: 'No admitted Stage-2 pathway bundle bound',
  Drugs: 'No admitted Stage-3 bundle bound',
  'PK & Safety': 'No admitted Stage-4 bundle bound',
};
function unboundStatus(stageLabel: string): string {
  return UNBOUND_STATUS[stageLabel] ?? 'No admitted result bundle bound';
}

/** A definition Row that renders ONLY when its value is present — a null definition field is omitted
 *  entirely, never filled with an "unavailable" row. */
function DefRow({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  if (value === null || value === '') return null;
  return <Row label={label}><Val v={value} mono={mono} /></Row>;
}

/** Methods content as numbered teal steps (Stage-1 grammar). Keeps the label/value `.grid` Row for
 *  every PRESENT field the acceptance harness reads; null definition fields are omitted; run-status
 *  detail (code/env/last-run/reproduce) renders only when a bound admitted bundle supplies it.
 *  Step 2/3 headings are route-specific (derived from stageLabel). */
function MethodsSteps({ m, stageLabel, runBound }: { m: MethodsBlock; stageLabel: string; runBound: boolean }) {
  const h = stepHeadings(stageLabel);
  return (
    <>
      <Step n="1" heading="Data source">
        <DefRow label="Data / input" value={m.data_input} />
        <DefRow label="Source" value={m.source_tissue} />
      </Step>
      <Step n="2" heading={h.estimand}>
        <DefRow label="Estimand" value={m.estimand} />
        <Boundaries items={m.limitations} />
      </Step>
      <Step n="3" heading={h.masks}>
        <DefRow label="Masks / QC" value={m.masks_qc} />
      </Step>
      <Step n="4" heading="Upstream model">
        <DefRow label="Upstream" value={m.upstream_model} />
      </Step>
      <Step n="5" heading="Method">
        <DefRow label="Method" value={m.method_id} mono />
        {/* run-status detail only when a bound admitted bundle supplies it */}
        {runBound && <DefRow label="Code sha256" value={m.method_code_sha256} mono />}
        {runBound && <DefRow label="Environment" value={m.environment} mono />}
        {runBound && <DefRow label="Last run UTC" value={m.last_run_utc} mono />}
        {m.reproduce_command && (
          <Row label="Reproduce"><CopyCommand cmd={m.reproduce_command} /></Row>
        )}
      </Step>
    </>
  );
}

/** Provenance & status step + a References block — all inside data-section="provenance". Unbound:
 *  ONE terse route-specific status row. Bound: the real release / hash / generator / verifier / CS /
 *  artifact rows the admitted bundle supplies (nulls still omitted). */
function ProvenanceSteps({ p, n, stageLabel, runBound }: { p: ProvenanceBlock; n: string; stageLabel: string; runBound: boolean }) {
  return (
    <>
      <Step n={n} heading="Provenance &amp; status">
        {runBound ? (
          <>
            <DefRow label="Release" value={p.release_revision} mono />
            <DefRow label="Raw sha256" value={p.raw_sha256} mono />
            <DefRow label="Canonical" value={p.canonical_sha256} mono />
            <DefRow label="Generator" value={p.generator_status} />
            <DefRow label="Verifier" value={p.verifier_status} />
            {p.cs_notebook_url && (
              <Row label="CS notebook">
                <a href={p.cs_notebook_url} target="_blank" rel="noopener noreferrer" className="font-mono text-[11px] text-accent hover:underline">
                  {p.cs_notebook_url} ↗
                </a>
              </Row>
            )}
            {p.artifact_paths.length > 0 && (
              <Row label="Artifacts">
                <ul className="space-y-1">
                  {p.artifact_paths.map((a) => (
                    <li key={a}><Mono>{a}</Mono></li>
                  ))}
                </ul>
              </Row>
            )}
          </>
        ) : (
          <Row label="Status"><span className="text-ink-2">{unboundStatus(stageLabel)}</span></Row>
        )}
      </Step>
      <References sources={p.source_chain} />
    </>
  );
}

/** References block — Stage-1 .ppapers grammar: exact validated source links + each source's hashes.
 *  A source-hash subfield is rendered ONLY when present (no "raw unavailable · canonical unavailable"
 *  filler). Rendered as <li> inside data-section="provenance" so the harness reads the source records. */
function References({ sources }: { sources: SourceChainLink[] }) {
  // Zero-filler: with no bound sources (e.g. the pre-resolution fallback) render NOTHING, never
  // an "unavailable" row. Stage-1 .ppapers grammar: pt 9px, heading mb 10px, items 6px apart.
  if (sources.length === 0) return null;
  return (
    <div className="pt-[9px]">
      <div className="mb-[10px] font-mono text-[10px] font-semibold uppercase tracking-wide text-muted">References</div>
      <ul className="space-y-[6px]">
        {sources.map((s) => (
          <li key={`${s.label}:${s.record_id}`} className="text-[12px]">
            {s.url ? (
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent hover:underline">
                {s.label} · {s.record_id} ↗
              </a>
            ) : (
              <span>
                <span className="font-semibold text-ink">{s.label}</span> · <Mono>{s.record_id}</Mono>
              </span>
            )}
            {(s.license || s.retrieval_utc) && (
              <div className="mt-0.5 text-[11px] text-muted">
                {s.license ?? ''}
                {s.license && s.retrieval_utc ? ' · ' : ''}
                {s.retrieval_utc ?? ''}
              </div>
            )}
            {(s.raw_sha256 || s.canonical_sha256) && (
              <div className="mt-0.5 text-[10.5px] leading-relaxed text-ink-2">
                {s.raw_sha256 && (<><span className="text-muted">raw</span> <Mono>{s.raw_sha256}</Mono></>)}
                {s.raw_sha256 && s.canonical_sha256 ? ' · ' : ''}
                {s.canonical_sha256 && (<><span className="text-muted">canonical</span> <Mono>{s.canonical_sha256}</Mono></>)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface ProvenanceDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  provenance: Provenance | null;
  selection?: StageSelection | null;
  selectionV3?: SelectionDisplayContext | null;
  notes?: ProvNote[];
  /** Stage Methods & Provenance manifest (the MPA per-tab content). When present it replaces
   *  the raw provenance block; the App SPA passes none and keeps its existing rendering. */
  methods?: StageMethodsManifest | null;
  /** Which section the opening action targeted; the drawer scrolls it into view. */
  focus?: DrawerSection;
}

export function ProvenanceDrawer({
  open,
  onClose,
  title,
  provenance,
  selection,
  selectionV3,
  notes,
  methods,
  focus = 'methods',
}: ProvenanceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const methodsRef = useRef<HTMLDivElement>(null);
  const provRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    // scroll the requested section into view (no-op in jsdom; safe via optional chaining)
    const target = focus === 'provenance' ? provRef.current : methodsRef.current;
    target?.scrollIntoView?.({ block: 'start' });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      // focus trap: keep Tab / Shift+Tab cycling within the drawer while it is open
      const aside = closeRef.current?.closest('[role="dialog"]');
      if (!aside) return;
      const focusable = aside.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, focus, onClose]);

  return (
    <>
      <div
        aria-hidden={!open}
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-ink/30 transition-opacity duration-200 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        // Visible h2 is just "Methods & provenance"; route context lives in the dialog accessible
        // name (+ the sr-only data-stage-label) and the route-specific body content.
        aria-label={`${title} — methods and provenance`}
        aria-hidden={!open}
        inert={!open}
        className={`fixed right-0 top-0 z-50 flex h-full w-[600px] max-w-[94vw] flex-col rounded-l-2xl bg-surface shadow-drawer transition-transform duration-[340ms] ease-[cubic-bezier(.4,0,.2,1)] ${
          open ? 'translate-x-0' : 'translate-x-[102%]'
        }`}
      >
        <header className="flex items-start justify-between gap-[10px] border-b border-line px-5 pt-[11px] pb-[9px]">
          {/* Stage-1 parity: ONE 16px/600/1.2 title "Methods & provenance" — no second visible line.
              Route context is semantic only: the sr-only stage label (harness + a11y) + the dialog
              aria-label + the route-specific body content. */}
          <h2 className="text-[16px] font-semibold leading-[1.2] text-ink">Methods &amp; provenance</h2>
          <span className="sr-only" data-stage-label>{title}</span>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close methods and provenance"
            className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-[8px] bg-sunken text-[14px] text-ink-2 transition-colors hover:bg-line hover:text-ink"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-[2px] pb-[12px]">
          {selectionV3 ? (
            <SelectionV3Section selection={selectionV3} />
          ) : selection ? (
            <SelectionSection selection={selection} />
          ) : null}

          {methods && (
            <>
              <div ref={methodsRef} data-section="methods">
                <MethodsSteps
                  m={methods.methods}
                  stageLabel={methods.stage_label}
                  runBound={isRunBound(methods.methods, methods.provenance)}
                />
              </div>
              <div ref={provRef} data-section="provenance">
                <ProvenanceSteps
                  p={methods.provenance}
                  n="6"
                  stageLabel={methods.stage_label}
                  runBound={isRunBound(methods.methods, methods.provenance)}
                />
              </div>
            </>
          )}

          {!methods && provenance && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <NamespaceChip ns={provenance.namespace} />
                <EligibilityChip eligible={provenance.production_eligible} />
                <span className="font-mono text-[10px] text-muted">{provenance.schema_version}</span>
              </div>

              <section className="border-t border-line pt-3">
                <Row label="Artifact">
                  <Mono>{provenance.artifact_id}</Mono>
                </Row>
                <Row label="Raw sha256">
                  <Mono>{provenance.hashes.raw_sha256}</Mono>
                </Row>
                <Row label="Canonical">
                  <Mono>{provenance.hashes.canonical_sha256}</Mono>
                </Row>
              </section>

              <section className="mt-3 border-t border-line pt-3">
                <Row label="Method">
                  <Mono>{provenance.method.method_id}</Mono>
                </Row>
                <Row label="Config">
                  <Mono>{provenance.method.config_id}</Mono>
                </Row>
                <Row label="Code">
                  <Mono>{provenance.method.code_ref}</Mono>
                </Row>
                <Row label="Environment">
                  <Mono>{provenance.method.env_ref}</Mono>
                </Row>
              </section>

              {provenance.upstream_ref && (
                <section className="mt-3 border-t border-line pt-3">
                  <Row label="Upstream">
                    <Mono>{provenance.upstream_ref.artifact_id}</Mono>
                  </Row>
                  <Row label="Upstream sha">
                    <Mono>{provenance.upstream_ref.canonical_sha256}</Mono>
                  </Row>
                </section>
              )}

              <section className="mt-3 border-t border-line pt-3">
                <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">
                  Public source records
                </div>
                {provenance.sources.length === 0 ? (
                  <p className="text-[12px] text-muted">No public source records supplied.</p>
                ) : (
                  <ul className="space-y-2">
                    {provenance.sources.map((s) => (
                      <li key={`${s.label}:${s.record_id}`} className="text-[12px]">
                        <span className="font-semibold text-ink">{s.label}</span>{' '}
                        <Mono>{s.record_id}</Mono>
                        <div className="text-[11px] text-muted">{s.detail}</div>
                        {s.url && (
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[11px] text-accent hover:underline"
                          >
                            {s.url} ↗
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {provenance.cs_session && (
                <section className="mt-3 border-t border-line pt-3">
                  <Row label="CS session">
                    <Mono>{provenance.cs_session.session_ref}</Mono>
                  </Row>
                  <Row label="CS frame">
                    <Mono>{provenance.cs_session.frame_ref}</Mono>
                  </Row>
                </section>
              )}

            </>
          )}

          {notes && notes.length > 0 && (
            <section className="mt-3 border-t border-line pt-3">
              <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">
                Method &amp; interpretation notes
              </div>
              <ul className="space-y-2">
                {notes.map((n) => (
                  <li key={n.title}>
                    <div className="text-[12px] font-semibold text-ink">{n.title}</div>
                    <p className="text-[11px] leading-relaxed text-ink-2">{n.body}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {!methods && !provenance && !selection && !(notes && notes.length > 0) && (
            <p className="text-[12px] text-muted">No provenance available.</p>
          )}
        </div>
      </aside>
    </>
  );
}
