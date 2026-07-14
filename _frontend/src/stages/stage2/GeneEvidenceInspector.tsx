// Per-gene evidence inspector. Opens on a selected lever and shows, for each arm,
// evaluability + reason, contributing guides, donor-support denominators, the
// direct-vs-Perturb2State status, DepMap annotation, and exact source links.

import { useEffect, useRef } from 'react';
import type { GeneLever, LeverArm, Objective } from '../../domain/stage2';
import { StatePill } from '../../shell/chips';

function ArmBlock({ objective, arm }: { objective: Objective; arm: LeverArm }) {
  const label = objective === 'away_from_A' ? 'away from A' : 'toward B';
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted">{label}</span>
        {arm.evaluated ? (
          <StatePill label="evaluated" tone="accent" />
        ) : (
          <StatePill label="not evaluated" tone="muted" />
        )}
      </div>
      {arm.evaluated ? (
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
          <dt className="text-muted">effect</dt>
          <dd className="text-right font-mono text-ink">
            {arm.effect != null ? `${arm.effect >= 0 ? '+' : ''}${arm.effect.toFixed(2)}` : '—'}
          </dd>
          <dt className="text-muted">rank (this arm)</dt>
          <dd className="text-right font-mono text-ink">{arm.rank != null ? `#${arm.rank}` : '—'}</dd>
          <dt className="text-muted">axis coverage</dt>
          <dd className="text-right font-mono text-ink">
            {arm.coverage != null ? arm.coverage.toFixed(2) : '—'}
          </dd>
        </dl>
      ) : (
        <p className="mt-2 text-[11.5px] leading-relaxed text-ink-2">{arm.reason ?? 'not evaluated'}</p>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-3">
      <h4 className="mb-1.5 font-mono text-[9.5px] uppercase tracking-wide text-muted">{title}</h4>
      {children}
    </section>
  );
}

export function GeneEvidenceInspector({ gene, onClose }: { gene: GeneLever; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const ev = gene.evidence;
  return (
    <>
      <div className="fixed inset-0 z-40 bg-ink/30" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence for ${gene.gene_id}`}
        className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[520px] max-w-[94vw] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-surface shadow-drawer"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            <div className="text-[15px] font-semibold text-ink">{gene.gene_id}</div>
            <div className="font-mono text-[10.5px] text-muted">{gene.ensembl_id ?? 'no Ensembl id'}</div>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close evidence inspector"
            className="h-7 w-7 flex-none rounded-lg bg-sunken text-ink-2 hover:text-ink"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-2 gap-3">
            <ArmBlock objective="away_from_A" arm={gene.arms.away_from_A} />
            <ArmBlock objective="toward_B" arm={gene.arms.toward_B} />
          </div>

          <Group title="Contributing guides">
            <ul className="space-y-1">
              {ev.guides.map((g) => (
                <li key={g.guide_id} className="flex items-center justify-between text-[11.5px]">
                  <span className="font-mono text-ink-2">{g.guide_id}</span>
                  <span className="flex items-center gap-3">
                    <span className="font-mono text-ink">
                      {g.effect != null ? `${g.effect >= 0 ? '+' : ''}${g.effect.toFixed(2)}` : '—'}
                    </span>
                    <span className="font-mono text-[10px] text-muted">
                      {g.sign_agrees == null ? 'sign n/a' : g.sign_agrees ? 'sign agrees' : 'sign differs'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </Group>

          <Group title="Donor support">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
              <dt className="text-muted">effective n</dt>
              <dd className="text-right font-mono text-ink">{ev.donor_support.effective_n}</dd>
              <dt className="text-muted">denominator</dt>
              <dd className="text-right text-ink-2">{ev.donor_support.denominator}</dd>
              <dt className="text-muted">pair discordance</dt>
              <dd className="text-right font-mono text-ink">
                {ev.donor_support.pair_discordance == null
                  ? 'n/a'
                  : ev.donor_support.pair_discordance
                    ? 'yes'
                    : 'no'}
              </dd>
            </dl>
          </Group>

          <Group title="Stability & annotation">
            <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
              <StatePill
                label={`direct/perturb2state: ${ev.perturb2state}`}
                tone={ev.perturb2state === 'perturb2state_discordant' ? 'amber' : 'neutral'}
              />
              <StatePill
                label={
                  ev.on_target_detected == null
                    ? 'on-target: n/a'
                    : ev.on_target_detected
                      ? 'on-target: detected'
                      : 'on-target: none'
                }
                tone="muted"
              />
              <StatePill label={`DepMap: ${ev.depmap.status}`} tone="muted" />
              <StatePill label={`support: ${ev.support_status}`} tone="neutral" />
            </div>
            {ev.depmap.detail && <p className="mt-1.5 text-[10.5px] text-muted">{ev.depmap.detail}</p>}
          </Group>

          <Group title="Source links">
            <ul className="space-y-1">
              {ev.source_links.map((l, i) => (
                <li key={i} className="text-[11.5px]">
                  <span className="text-ink-2">{l.label}</span>{' '}
                  <span className="text-muted">— {l.detail}</span>
                  {l.url && (
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-1 font-mono text-[11px] text-accent hover:underline"
                    >
                      ↗
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </Group>
        </div>
      </div>
    </>
  );
}
