import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { evidenceFromProvenance } from '../mpa/ScienceEvidence';
import { createDemoRepository } from '../repository/repository';
import { PathwaysView } from '../stages/stage2/PathwaysView';

const sc = MPA_SCAFFOLDS.pathways;
const slot = createDemoRepository().getStage2();
const artifact = slot.status === 'loaded' ? slot.artifact : null;

createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="pathways"
    subtitle="Pathways"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage02_pathways_review"
    renderDemo={() => (artifact ? <PathwaysView artifact={artifact} /> : null)}
    demoEvidence={artifact ? evidenceFromProvenance(artifact.provenance) : null}
  />,
);
