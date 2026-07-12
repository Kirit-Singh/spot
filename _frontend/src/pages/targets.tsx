import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { createDemoRepository } from '../repository/repository';
import { Stage2View } from '../stages/stage2/Stage2View';

const sc = MPA_SCAFFOLDS.targets;
createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="targets"
    subtitle="Targets"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage02_review"
    renderDemo={() => {
      const s = createDemoRepository().getStage2();
      return s.status === 'loaded' ? <Stage2View artifact={s.artifact} /> : null;
    }}
  />,
);
