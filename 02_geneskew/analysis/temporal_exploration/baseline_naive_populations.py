import json, os
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(os.environ.get("SPOT_APP_ROOT", REPO_ROOT / "01_programs" / "app"))
d=json.load(open(APP_ROOT / "data" / "stage01_umap_seed.json"))
df=pd.DataFrame(d["cells"])
uni=d["meta"].get("scoring_universe_n") or 396000
SCALE=uni/len(df)
print("display_n=%s scoring_universe_n=%s scale=x%.2f"%(d["meta"].get("display_n"),uni,SCALE))
print("per-condition counts (40k):", df.condition.value_counts().to_dict())
order=["Rest","Stim8hr","Stim48hr"]
for score in ["diff_naive_score","th1_like_score","treg_like_score"]:
    print("\n=== %s ==="%score)
    for c in order:
        s=df[df.condition==c][score]
        n5=int((s>0.5).sum()); n10=int((s>1.0).sum())
        print("  %-9s med=%+.3f p90=%+.3f p99=%+.3f | >0.5: %5.2f%% (%d, ~%d full) | >1.0: %5.2f%% (%d, ~%d full)"%(
            c, s.median(), s.quantile(.9), s.quantile(.99),
            100*(s>0.5).mean(), n5, int(n5*SCALE), 100*(s>1.0).mean(), n10, int(n10*SCALE)))
print("\n=== naive-high (>0.5) cells per condition + their Th1/Treg medians ===")
for c in order:
    sub=df[df.condition==c]; nh=sub[sub.diff_naive_score>0.5]
    print("  %-9s naive-high n=%d (~%d full, %.1f%% of tp) | th1_med=%+.3f treg_med=%+.3f"%(
        c, len(nh), int(len(nh)*SCALE), 100*len(nh)/len(sub), nh.th1_like_score.median(), nh.treg_like_score.median()))
# also stricter naive definition: naive-high AND activated-low (true resting)
print("\n=== stricter 'resting naive' (naive>0.5 AND diff_activated<0) ===")
for c in order:
    sub=df[df.condition==c]; nh=sub[(sub.diff_naive_score>0.5)&(sub.diff_activated_score<0)]
    print("  %-9s n=%d (~%d full, %.1f%% of tp)"%(c, len(nh), int(len(nh)*SCALE), 100*len(nh)/len(sub)))
