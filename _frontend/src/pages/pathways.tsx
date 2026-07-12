import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { createDemoRepository } from '../repository/repository';
import { PathwaysView } from '../stages/stage2/PathwaysView';

const sc = MPA_SCAFFOLDS.pathways;
createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="pathways"
    subtitle="Pathways"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage02_pathways_review"
    renderDemo={() => {
      const s = createDemoRepository().getStage2();
      return s.status === 'loaded' ? <PathwaysView artifact={s.artifact} /> : null;
    }}
  />,
);
