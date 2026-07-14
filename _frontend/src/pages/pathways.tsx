import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { resolveProductionThenDevelopment } from '../mpa/devRealAdapter';

// Production only — no demo/fixture import reaches this served bundle.
createRoot(document.getElementById('root')!).render(
  <StageIsland page="pathways" subtitle="Pathways" loadRealArtifact={resolveProductionThenDevelopment} />,
);
