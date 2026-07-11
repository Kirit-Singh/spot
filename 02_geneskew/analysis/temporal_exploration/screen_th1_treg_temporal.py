import sys, json, os
sys.path.insert(0, "/home/tcelab/spot_stage2/02_geneskew/analysis")
import numpy as np, pandas as pd
from direct import config, io_data, projection as proj, disposition as D
from direct import masks as M
REG="/home/tcelab/spot_stage2/reg/stage01_program_registry.json"
DE="/home/tcelab/datasets/marson2025_gwcd4_perturbseq/GWCD4i.DE_stats.h5ad"
SGRNA="/home/tcelab/datasets/marson2025_gwcd4_perturbseq/suppl_tables/sgrna_library_metadata.suppl_table.csv"
OUT="/home/tcelab/spot_stage2/work/temporal"; os.makedirs(OUT, exist_ok=True)
programs, registry_sha, reg = io_data.load_registry(REG)
A, B = programs["th1_like"], programs["treg_like"]
pa={"panel":A["panel_ensembl"],"control":A["control_ensembl"],"sign":+1}
pb={"panel":B["panel_ensembl"],"control":B["control_ensembl"],"sign":+1}
sgrna_by_target=io_data.load_sgrna_rows_by_target(SGRNA)
def screen(cond):
    main=io_data.load_main(DE,cond); gi=main["gene_index"]; meta=main["meta"]
    targets=[str(t) for t in meta["target_ensembl"]]; rows=[]
    for i,t in enumerate(targets):
        if t in sgrna_by_target:
            mk=M.build_target_masks({t:sgrna_by_target[t]}, config.MASK_NEIGHBORHOOD_COLUMN)[t]; mk["resolved"]=True
        else:
            mk=M.fallback_self_mask(t); mk["resolved"]=False
        ms=mk["gene_set"]
        da=proj.program_delta(main["log_fc"][i],pa["panel"],pa["control"],gi,ms,config.MIN_SURVIVING_PANEL,config.MIN_SURVIVING_CONTROL)
        db=proj.program_delta(main["log_fc"][i],pb["panel"],pb["control"],gi,ms,config.MIN_SURVIVING_PANEL,config.MIN_SURVIVING_CONTROL)
        ax=proj.axis_scores(da["delta"],db["delta"],pa["sign"],pb["sign"])
        ok=da["status"]==proj.OK and db["status"]==proj.OK
        ps=da["status"] if da["status"]!=proj.OK else db["status"]
        state,_=D.classify_eligibility(row_present=True,projection_status=ps,mask_resolved=mk["resolved"],
              n_cells=float(meta["n_cells_target"][i]),low_target_gex=bool(meta["low_target_gex"][i]),
              ontarget_significant=bool(meta["ontarget_significant"][i]),n_guides=float(meta["n_guides"][i]))
        rows.append(dict(target=t,symbol=str(meta["target_symbol"][i]),balanced=ax["balanced_skew"],
            away_th1=ax["away_from_A"],toward_treg=ax["toward_b"],state=state,
            eligible=state.startswith("eligible"),ok=ok,ontarget_sig=bool(meta["ontarget_significant"][i]),
            n_cells=float(meta["n_cells_target"][i])))
    df=pd.DataFrame(rows); df.to_csv(f"{OUT}/th1_to_treg_{cond}.csv",index=False)
    print(f"[{cond}] n={len(df)} eligible={int(df.eligible.sum())} ontarget_sig={int(df.ontarget_sig.sum())} states={df.state.value_counts().to_dict()}")
    return df
d8,d48=screen("Stim8hr"),screen("Stim48hr")
m=d8.merge(d48,on=["target","symbol"],suffixes=("_8","_48")); m["diff"]=m.balanced_48-m.balanced_8
m.to_csv(f"{OUT}/merged.csv",index=False)
elig=m[m.eligible_8&m.eligible_48].copy()
def top(df,col,n=15,asc=False):
    return df.sort_values(col,ascending=asc)[["symbol","balanced_8","balanced_48","diff","n_cells_48"]].head(n).round(4).to_string(index=False)
corr=float(np.corrcoef(elig.balanced_8,elig.balanced_48)[0,1]) if len(elig)>2 else float("nan")
print("\n=== eligible in BOTH: n=%d | corr(8,48)=%.3f ==="%(len(elig),corr))
print("\n--- TOP Th1->Treg levers @ 8hr ---\n",top(elig,"balanced_8"))
print("\n--- TOP Th1->Treg levers @ 48hr ---\n",top(elig,"balanced_48"))
print("\n--- effect GROWS toward Treg 8->48 ---\n",top(elig,"diff"))
print("\n--- effect SHRINKS 8->48 ---\n",top(elig,"diff",asc=True))
json.dump({"n_elig_both":int(len(elig)),"corr_8_48":round(corr,3),"registry_sha8":registry_sha[:8],
  "n8":int(len(d8)),"n48":int(len(d48)),"elig8":int(d8.eligible.sum()),"elig48":int(d48.eligible.sum())},
  open(f"{OUT}/summary.json","w"),indent=2)
print("\nDONE")
