import { createRoot } from 'react-dom/client';
import '../index.css';
import { StageIsland } from '../mpa/StageIsland';
import { MPA_SCAFFOLDS } from '../mpa/scaffolds';
import { createDemoRepository } from '../repository/repository';
import { Stage3View } from '../stages/stage3/Stage3View';

const sc = MPA_SCAFFOLDS.drugs;
createRoot(document.getElementById('root')!).render(
  <StageIsland
    page="drugs"
    subtitle="Drug link"
    purpose={sc.purpose}
    regions={sc.regions}
    enqueueTarget="stage03_review"
    renderDemo={() => {
      const s = createDemoRepository().getStage3();
      return s.status === 'loaded' ? <Stage3View artifact={s.artifact} /> : null;
    }}
  />,
);
