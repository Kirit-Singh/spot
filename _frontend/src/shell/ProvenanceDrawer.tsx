// Methods & provenance drawer — a right slide-over reused by every stage view.
// Shows artifact IDs, raw + canonical hashes, method/config/code/environment,
// public source records, and the Claude Science session/frame reference when
// supplied. Claude output itself is never evidence — stated in the footer.

import { useEffect, useRef } from 'react';
import type { Provenance } from '../domain/common';
import type { Stage1Bindings, StageSelection } from '../domain/selection';
import type { MethodsBlock, ProvenanceBlock, StageMethodsManifest } from '../domain/methodsManifest';
import type { ProvNote } from './provenanceContext';
import { NamespaceChip, EligibilityChip } from './chips';

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
      <Row label="Prod. gate">
        production_gate_passed={String(selection.production_gate_passed)} · production_eligible=false
      </Row>
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

/** Render a value or an honest "unavailable" — never a fabricated placeholder. */
function Val({ v, mono }: { v: string | null; mono?: boolean }) {
  if (v === null || v === '') return <span className="text-muted">unavailable</span>;
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

/** Methods content: exact data, estimand, masks/QC, upstream, factual limitations, hashes, run, reproduce. */
function MethodsSection({ m }: { m: MethodsBlock }) {
  return (
    <section className="mb-3 border-b border-line pb-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">Methods</div>
      <Row label="Data / input"><Val v={m.data_input} /></Row>
      <Row label="Estimand"><Val v={m.estimand} /></Row>
      <Row label="Masks / QC"><Val v={m.masks_qc} /></Row>
      <Row label="Upstream"><Val v={m.upstream_model} /></Row>
      <Row label="Limitations">
        {m.limitations.length === 0 ? (
          <span className="text-muted">unavailable</span>
        ) : (
          <ul className="space-y-1">
            {m.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        )}
      </Row>
      <Row label="Method"><Val v={m.method_id} mono /></Row>
      <Row label="Code sha256"><Val v={m.method_code_sha256} mono /></Row>
      <Row label="Environment"><Val v={m.environment} mono /></Row>
      <Row label="Last run UTC"><Val v={m.last_run_utc} mono /></Row>
      <Row label="Reproduce">
        {m.reproduce_command ? <CopyCommand cmd={m.reproduce_command} /> : <span className="text-muted">unavailable</span>}
      </Row>
    </section>
  );
}

/** Provenance content: content-addressed chain, release, hashes, generator/verifier, notebook, paths. */
function ProvenanceManifestSection({ p }: { p: ProvenanceBlock }) {
  return (
    <section className="mb-3 border-b border-line pb-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">Provenance</div>
      <Row label="Release"><Val v={p.release_revision} mono /></Row>
      <Row label="Raw sha256"><Val v={p.raw_sha256} mono /></Row>
      <Row label="Canonical"><Val v={p.canonical_sha256} mono /></Row>
      <Row label="Generator"><Val v={p.generator_status} /></Row>
      <Row label="Verifier"><Val v={p.verifier_status} /></Row>
      <Row label="CS notebook">
        {p.cs_notebook_url ? (
          <a href={p.cs_notebook_url} className="font-mono text-[11px] text-accent hover:underline">
            {p.cs_notebook_url} ↗
          </a>
        ) : (
          <span className="text-muted">unavailable</span>
        )}
      </Row>
      <Row label="Artifacts">
        {p.artifact_paths.length === 0 ? (
          <span className="text-muted">unavailable</span>
        ) : (
          <ul className="space-y-1">
            {p.artifact_paths.map((a) => (
              <li key={a}><Mono>{a}</Mono></li>
            ))}
          </ul>
        )}
      </Row>
      <div className="mb-1 mt-2 font-mono text-[10px] uppercase tracking-wide text-muted">Source chain</div>
      {p.source_chain.length === 0 ? (
        <p className="text-[12px] text-muted">unavailable</p>
      ) : (
        <ul className="space-y-2">
          {p.source_chain.map((s) => (
            <li key={`${s.label}:${s.record_id}`} className="text-[12px]">
              <span className="font-semibold text-ink">{s.label}</span> <Mono>{s.record_id}</Mono>
              <div className="text-[11px] text-muted">
                {s.license ?? 'license unavailable'}
                {s.retrieval_utc ? ` · ${s.retrieval_utc}` : ''}
              </div>
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
  );
}

export interface ProvenanceDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  provenance: Provenance | null;
  selection?: StageSelection | null;
  notes?: ProvNote[];
  /** Stage Methods & Provenance manifest (the MPA per-tab content). When present it replaces
   *  the raw provenance block; the App SPA passes none and keeps its existing rendering. */
  methods?: StageMethodsManifest | null;
}

export function ProvenanceDrawer({
  open,
  onClose,
  title,
  provenance,
  selection,
  notes,
  methods,
}: ProvenanceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

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
        aria-label={title}
        aria-hidden={!open}
        inert={!open}
        className={`fixed right-0 top-0 z-50 flex h-full w-[560px] max-w-[94vw] flex-col rounded-l-2xl bg-surface shadow-drawer transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : 'translate-x-[102%]'
        }`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3">
          <div>
            <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
            <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-muted">
              Methods &amp; provenance
            </p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close methods and provenance"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-lg border border-line bg-sunken text-ink-2 transition-colors hover:border-line-strong hover:bg-line hover:text-ink"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {selection && <SelectionSection selection={selection} />}

          {methods && (
            <>
              <div className="mb-3 text-[13px] font-semibold text-ink" data-stage-label>
                {methods.stage_label}
              </div>
              <MethodsSection m={methods.methods} />
              <ProvenanceManifestSection p={methods.provenance} />
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

          {methods || provenance || selection || (notes && notes.length > 0) ? (
            <section className="mt-4 border-t border-line pt-3">
              <Row label="Claude Science role">provenance trace</Row>
            </section>
          ) : (
            <p className="text-[12px] text-muted">No provenance available.</p>
          )}
        </div>
      </aside>
    </>
  );
}
