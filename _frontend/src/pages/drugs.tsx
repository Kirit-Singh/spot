import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { evidenceFromProvenance } from '../mpa/evidence';
import { createDemoRepository } from '../repository/repository';
import { Stage3View } from '../stages/stage3/Stage3View';

const sc = MPA_SCAFFOLDS.drugs;
const slot = createDemoRepository().getStage3();
const artifact = slot.status === 'loaded' ? slot.artifact : null;

createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="drugs"
    subtitle="Drug link"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage03_review"
    renderDemo={() => (artifact ? <Stage3View artifact={artifact} /> : null)}
    demoEvidence={artifact ? evidenceFromProvenance(artifact.provenance) : null}
  />,
);
