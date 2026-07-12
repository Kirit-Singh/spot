import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { evidenceFromProvenance } from '../mpa/evidence';
import { createDemoRepository } from '../repository/repository';
import { Stage4View } from '../stages/stage4/Stage4View';

const sc = MPA_SCAFFOLDS.pksafety;
const slot = createDemoRepository().getStage4();
const artifact = slot.status === 'loaded' ? slot.artifact : null;

createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="pksafety"
    subtitle="PK / PD · brain"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage04_review"
    renderDemo={() => (artifact ? <Stage4View artifact={artifact} /> : null)}
    demoEvidence={artifact ? evidenceFromProvenance(artifact.provenance) : null}
  />,
);
