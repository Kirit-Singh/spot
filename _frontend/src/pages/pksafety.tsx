import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { createDemoRepository } from '../repository/repository';
import { Stage4View } from '../stages/stage4/Stage4View';

const sc = MPA_SCAFFOLDS.pksafety;
createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="pksafety"
    subtitle="PK / PD · brain"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage04_review"
    renderDemo={() => {
      const s = createDemoRepository().getStage4();
      return s.status === 'loaded' ? <Stage4View artifact={s.artifact} /> : null;
    }}
  />,
);
