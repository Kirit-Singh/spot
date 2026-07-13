// Full-page Methods (notebook) and Provenance (trace) views for a downstream stage.
// Same clean Stage-1 design language as the drawer, no banners / counts / editorial badges.
// Only source records already admitted into the provenance are rendered (the source verifier
// excludes unresolved/mismatched references upstream — the UI never badges them).

import type { Provenance } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import { NamespaceChip, EligibilityChip } from '../shell/chips';
import { notebookHref, traceHref } from './methodsRoutes';
import type { StageView } from './methodsRoutes';

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

function Awaiting({ what }: { what: string }) {
  return (
    <p className="text-[12px] text-muted">
      {what} appear here once this arm is generated in the content-addressed aggregate.
    </p>
  );
}

function SelectionRows({ selection }: { selection: StageSelection }) {
  return (
    <section className="mb-3 border-b border-line pb-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">Stage-1 selection</div>
      <Row label="A pole">
        {selection.program_a.display_label} · {selection.program_a.direction}
      </Row>
      <Row label="B pole">
        {selection.program_b.display_label} · {selection.program_b.direction}
      </Row>
      <Row label="Condition">{selection.analysis_condition}</Row>
    </section>
  );
}

function CrossLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="font-mono text-[11px] text-accent hover:underline">
      {label}
    </a>
  );
}

/** Methods (notebook): the analysis method + config + code + environment + notes. */
export function NotebookView({
  stage,
  provenance,
  selection,
}: {
  stage: StageView;
  provenance: Provenance | null;
  selection: StageSelection | null;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" data-view="notebook">
      <div className="mb-3 flex items-baseline justify-between">
        <h1 className="font-editorial text-[16px] font-medium text-ink">Methods</h1>
        <CrossLink href={traceHref(stage)} label="Provenance trace →" />
      </div>
      {selection && <SelectionRows selection={selection} />}
      {provenance ? (
        <section className="border-t border-line pt-3">
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
      ) : (
        <Awaiting what="Methods" />
      )}
    </div>
  );
}

/** Provenance (trace): the content-addressed identity + hashes + upstream chain + sources. */
export function TraceView({
  stage,
  provenance,
  selection,
}: {
  stage: StageView;
  provenance: Provenance | null;
  selection: StageSelection | null;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" data-view="trace">
      <div className="mb-3 flex items-baseline justify-between">
        <h1 className="font-editorial text-[16px] font-medium text-ink">Provenance trace</h1>
        <CrossLink href={notebookHref(stage)} label="Methods →" />
      </div>
      {selection && <SelectionRows selection={selection} />}
      {provenance ? (
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
              Verified source records
            </div>
            {provenance.sources.length === 0 ? (
              <p className="text-[12px] text-muted">No verified source records.</p>
            ) : (
              <ul className="space-y-2">
                {provenance.sources.map((s) => (
                  <li key={`${s.label}:${s.record_id}`} className="text-[12px]">
                    <span className="font-semibold text-ink">{s.label}</span> <Mono>{s.record_id}</Mono>
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
        </>
      ) : (
        <Awaiting what="A provenance trace" />
      )}
    </div>
  );
}
