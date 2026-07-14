// Compact, low-chrome operational states for a stage that has real selection
// context but no scored result yet — or whose artifact/selection was rejected.
// No banners and no explanatory paragraphs: a status pill plus the target key and
// the selection/artifact id, stated once. The reason why is a stable code, not prose.

import { StatePill } from './chips';

function StateCard({
  pill,
  tone,
  fields,
}: {
  pill: string;
  tone: Parameters<typeof StatePill>[0]['tone'];
  fields: [string, string][];
}) {
  return (
    <div className="min-h-0 flex-1 px-5 py-4">
      <div className="max-w-xl rounded-lg border border-line bg-surface px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <StatePill label={pill} tone={tone} />
          {fields.map(([k, v]) => (
            <span key={k} className="min-w-0 font-mono text-[10.5px] text-ink-2">
              <span className="text-muted">{k}</span>{' '}
              <span className="break-all">{v}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Valid research selection, no scored artifact for this stage yet. */
export function AnalysisNotGenerated({
  target,
  contrastId,
}: {
  target: string;
  contrastId: string | null;
}) {
  const fields: [string, string][] = [['artifact', target]];
  if (contrastId) fields.push(['contrast', contrastId]);
  return <StateCard pill="analysis not generated" tone="muted" fields={fields} />;
}

/** An artifact was present but did not bind to this selection / namespace. */
export function ArtifactRejected({ reason, target }: { reason: string; target: string }) {
  return (
    <StateCard
      pill="artifact rejected"
      tone="danger"
      fields={[
        ['reason', reason],
        ['artifact', target],
      ]}
    />
  );
}

/** The stored selection itself could not be read as a valid research selection. */
export function SelectionRejected({ reason, target }: { reason: string; target: string }) {
  return (
    <StateCard
      pill="selection rejected"
      tone="danger"
      fields={[
        ['reason', reason],
        ['selection', target],
      ]}
    />
  );
}
