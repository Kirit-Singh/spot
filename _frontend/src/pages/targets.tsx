import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { evidenceFromProvenance } from '../mpa/ScienceEvidence';
import { createDemoRepository } from '../repository/repository';
import { TargetsView } from '../stages/stage2/TargetsView';

const sc = MPA_SCAFFOLDS.targets;
const slot = createDemoRepository().getStage2();
const artifact = slot.status === 'loaded' ? slot.artifact : null;

createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="targets"
    subtitle="Targets"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage02_review"
    renderDemo={() => (artifact ? <TargetsView artifact={artifact} /> : null)}
    demoEvidence={artifact ? evidenceFromProvenance(artifact.provenance) : null}
  />,
);
