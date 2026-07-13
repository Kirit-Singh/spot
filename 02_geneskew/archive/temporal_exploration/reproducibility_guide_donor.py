"""EXPLORATION: guide + donor reproducibility for the Th1->Treg contrast at 8hr/48hr.
Reuses the frozen compute_guide_support/compute_donor_support + disposition state fns.
Reads main balanced_skew from the already-saved per-condition CSVs (avoids re-loading DE_stats)."""
import sys, json, os, gc
sys.path.insert(0,"/home/tcelab/spot_stage2/02_geneskew/analysis")
import numpy as np, pandas as pd
from direct import config, io_data, disposition as D
from direct import masks as M
import direct.run_screen as RS
DS="/home/tcelab/datasets/marson2025_gwcd4_perturbseq"
BYGUIDE=f"{DS}/GWCD4i.DE_stats.by_guide.h5mu"; BYDONORS=f"{DS}/GWCD4i.DE_stats.by_donors.h5mu"
SGRNA=f"{DS}/suppl_tables/sgrna_library_metadata.suppl_table.csv"
REG="/home/tcelab/spot_stage2/reg/stage01_program_registry.json"
OUT="/home/tcelab/spot_stage2/work/temporal"
programs,_,_=io_data.load_registry(REG)
A,B=programs["th1_like"],programs["treg_like"]
pa={"panel":A["panel_ensembl"],"control":A["control_ensembl"],"sign":+1}
pb={"panel":B["panel_ensembl"],"control":B["control_ensembl"],"sign":+1}
sgrna_by_target=io_data.load_sgrna_rows_by_target(SGRNA)
def masks_for(targets):
    mk={}
    for t in targets:
        if t in sgrna_by_target:
            m=M.build_target_masks({t:sgrna_by_target[t]},config.MASK_NEIGHBORHOOD_COLUMN)[t]; m["resolved"]=True
        else:
            m=M.fallback_self_mask(t); m["resolved"]=False
        mk[t]=m
    return mk
for cond in ["Stim8hr","Stim48hr"]:
    main=pd.read_csv(f"{OUT}/th1_to_treg_{cond}.csv"); main["target"]=main["target"].astype(str)
    targets=main["target"].tolist(); mk=masks_for(targets)
    mainbal={r.target:r.balanced for r in main.itertuples()}
    print(f"[{cond}] targets={len(targets)} — loading guide support…", flush=True)
    gper,_,gmods=RS.compute_guide_support(BYGUIDE,cond,targets,mk,pa,pb); print("  guide mods:",gmods,flush=True)
    print(f"[{cond}] loading donor support…", flush=True)
    dper,_,dmods=RS.compute_donor_support(BYDONORS,cond,targets,mk,pa,pb); print("  donor mods:",dmods,flush=True)
    recs=[]
    for t in targets:
        g=D.guide_support_state(mainbal[t],gper[t]); d=D.donor_support_state(mainbal[t],dper[t],len(dmods))
        recs.append(dict(target=t,cond=cond,guide_agree=g["guide_sign_agreement"],n_guides_eval=g["n_guides_evaluated"],
            donor_agree=d["donor_pair_agreement"],n_donor_pairs=len([x for x in dper[t] if x is not None])))
    rep=pd.DataFrame(recs); out=main.merge(rep,on="target")
    out.to_csv(f"{OUT}/reproducibility_{cond}.csv",index=False)
    elig=out[out.state.str.startswith("eligible")]
    print(f"  [{cond}] eligible n={len(elig)} | guide_agree={int((elig.guide_agree==True).sum())} ({100*(elig.guide_agree==True).mean():.1f}%) | donor_agree={int((elig.donor_agree==True).sum())} ({100*(elig.donor_agree==True).mean():.1f}%) | BOTH={int(((elig.guide_agree==True)&(elig.donor_agree==True)).sum())}")
    for g in ["TBX21","SOCS1","PPP1R14B","CMIP","GATB","SUCLA2","PDIA3","IL21R"]:
        r=out[out.symbol==g]
        if len(r): r=r.iloc[0]; print(f"    {g:9s} bal={r.balanced:+.3f} guide_agree={r.guide_agree} ({int(r.n_guides_eval)}g) donor_agree={r.donor_agree} ({int(r.n_donor_pairs)}pairs) state={r.state}")
    del gper,dper; gc.collect()
print("DONE")
