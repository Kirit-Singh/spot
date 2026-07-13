import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { resolveProductionRealArtifact } from '../mpa/renderReal';

// Production only — no demo/fixture import reaches this served bundle.
createRoot(document.getElementById('root')!).render(
  <StageIsland page="pksafety" subtitle="PK & Safety" loadRealArtifact={resolveProductionRealArtifact} />,
);
