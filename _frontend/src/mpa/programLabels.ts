// Tier-2 program display labels ("Treg-like", "CD4 CTL-like", …) resolved from the served Stage-1
// DISPLAY registry (data/stage01_program_registry.json — the same registry the frozen Stage-1 page uses
// for its program names). This is DISPLAY-ONLY: no scientific hash is entered here, and a program_id the
// registry does not name falls back to itself rather than crashing. Fail-closed to an empty map (the
// header then shows the raw id only if the registry is unreachable — never a hard error).

const PROGRAM_REGISTRY_PATH = 'data/stage01_program_registry.json';

async function sameOriginFetchText(path: string): Promise<string> {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`fetch ${path} → ${res.status}`);
  return res.text();
}

/** Build program_id → display_label from the served display registry. Empty map on any failure. */
export async function loadProgramLabels(fetchText: (path: string) => Promise<string> = sameOriginFetchText): Promise<Map<string, string>> {
  try {
    const raw = JSON.parse(await fetchText(PROGRAM_REGISTRY_PATH)) as unknown;
    const obj = raw as { programs?: unknown };
    const programs = Array.isArray(obj?.programs) ? obj.programs : Array.isArray(raw) ? (raw as unknown[]) : [];
    const map = new Map<string, string>();
    for (const p of programs) {
      const rec = p as { program_id?: unknown; display_label?: unknown };
      if (typeof rec?.program_id === 'string' && typeof rec?.display_label === 'string' && rec.display_label.trim() !== '') {
        map.set(rec.program_id, rec.display_label);
      }
    }
    return map;
  } catch {
    return new Map();
  }
}

/** The Tier-2 display label for a program_id, or the id itself when the registry does not name it. */
export function programLabel(labels: Map<string, string>, program_id: string): string {
  return labels.get(program_id) ?? program_id;
}
