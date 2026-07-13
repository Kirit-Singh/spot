// Tiny hash-based router (no dependency added). Stages 2–4 live in this shell;
// Stage 1 links out to the existing /01_page.html and is not redrawn here.

import { useEffect, useState } from 'react';

export type StageRoute = 'stage-2' | 'stage-3' | 'stage-4';

const ROUTES: StageRoute[] = ['stage-2', 'stage-3', 'stage-4'];

export function parseHash(hash: string): StageRoute {
  const key = hash.replace(/^#\/?/, '');
  return (ROUTES as string[]).includes(key) ? (key as StageRoute) : 'stage-2';
}

export function useStageRoute(): [StageRoute, (r: StageRoute) => void] {
  const [route, setRoute] = useState<StageRoute>(() =>
    typeof window === 'undefined' ? 'stage-2' : parseHash(window.location.hash),
  );

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = (r: StageRoute) => {
    if (typeof window !== 'undefined') window.location.hash = `/${r}`;
    setRoute(r);
  };

  return [route, navigate];
}
