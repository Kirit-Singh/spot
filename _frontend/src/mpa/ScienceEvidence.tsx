// Science-firewall surface. A stage page ONLY (a) displays a frozen, verified Science
// evidence record {science_evidence_id, sha256, record_type} and (b) offers an enqueue
// seam for an out-of-band review driver. It never runs Science, holds credentials, or
// computes any value — the enqueue button records intent locally and drives nothing.

import { useState } from 'react';
import { StatePill } from '../shell/chips';
import type { ScienceEvidenceRecord } from './evidence';

export type { ScienceEvidenceRecord } from './evidence';

export function ScienceEvidence({
  record,
  enqueueTarget,
}: {
  record: ScienceEvidenceRecord | null;
  enqueueTarget: string;
}) {
  const [requested, setRequested] = useState(false);
  return (
    <section
      aria-label="Science evidence"
      className="rounded-lg border border-line bg-surface px-4 py-3"
    >
      <h4 className="font-mono text-[9.5px] uppercase tracking-wide text-muted">
        Science evidence record
      </h4>
      {record ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10.5px] text-ink-2">
          <StatePill label={record.record_type} tone="accent" />
          <span>
            <span className="text-muted">id</span> {record.science_evidence_id}
          </span>
          <span className="break-all">
            <span className="text-muted">sha256</span> {record.sha256}
          </span>
        </div>
      ) : (
        <div className="mt-2">
          <StatePill label="no evidence record bound" tone="muted" />
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setRequested(true)}
          disabled={requested}
          className="rounded-md border border-line px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {requested ? 'review job requested' : 'Enqueue review job'}
        </button>
        <span className="font-mono text-[10px] text-muted">out-of-band driver · {enqueueTarget}</span>
      </div>
    </section>
  );
}
