# Memo (PROPOSAL — not implemented): the T7b LOMO failure is real construct-fragility evidence; propose a *separate, exploratory* Stage-2 projection-evaluability test — not a selectability bypass

_Stage-1 validation lead → orchestrator. 2026-07-12. Method bundle `stage1-continuous-v3.0.1`._

**Status: PROPOSAL ONLY. Nothing here is applied.** No panel/threshold/control/seed retuned; no
`gate_spec` edited; **no proposal to change the Stage-1 LOMO gate or its consequence**; no T8/selectability
decision; no manufactured pair. The committed T7b artifact (`stage01_validation.json`, raw `1c14cd28…`)
and its sanitized independent-verification record are preserved verbatim. Any change requires orchestrator
approval and a deliberate, separately-reviewed step.

## 1. Established, independently-observed result
- **`stage1_selectable_by_condition = 0/33`** — every program×condition fails the pre-registered
  **cell-level LOMO** gate (ρ≥0.80 AND median|Δ|/IQR≤0.25). Independently reproduced: th1_like|Rest worst
  ρ=**0.764173** (D1), ratio=**0.584872** (exact to 6 dp vs the artifact); cd4_ctl_like|Rest (6-gene) also
  fails independently. **This is a real result, not a bug.**
- `stage2_base_portability` 10/11 pass (th9_like fails); advisory flags empty; 1 separate overlay
  distribution failure; CP10k undefined/descriptive. All integrity + hash checks pass.

## 2. Estimand assessment — the LOMO failure is a genuine finding of *construct fragility*
Reasoning from the estimand and downstream use, not a desired outcome:

- **What cell-level LOMO measures:** whether the *raw panel mean on NTC cells* preserves its per-cell
  ranking when one marker is deleted (controls fixed). This probes whether the panel mean behaves as one
  coherent latent construct.
- **High stability is not a bad thing, and the failure has a bounded reading.** Reliable composite
  measurements often *intentionally* combine correlated indicators; robustness to dropping one indicator is
  a normal property of a coherent construct. With only **3–6 sparse markers, finite panel size and
  detection sparsity are plausible contributors** to the observed instability, so the failure is not by
  itself a statement about the underlying biology. The **supported** conclusion is narrower and still
  substantive: **under the pre-registered diagnostic this composite has not demonstrated leave-one-marker-out
  stability and is marker-sensitive** (ρ 0.5–0.76, median|Δ|/IQR 0.36–0.58). That is *construct-fragility
  evidence* — it does **not** prove that no coherent latent program exists, only that this composite has
  not demonstrated stability under its own pre-registered perturbation.
- **It is not *identical* to the Stage-2 projection estimand.** Stage-2's decision object is a **DE-space
  target-effect ranking** (which knockdowns shift the A/B axis), not the NTC per-cell ordering.
  Construct fragility at the cell level need not translate one-to-one into instability of that ranking.
  **But non-identity does not erase the Stage-1 finding.** A different downstream test cannot license a
  program whose Stage-1 construct is fragile; at most it adds information.

**Conclusion:** the Stage-1 LOMO result should stand as reported — a construct-fragility finding, gate and
consequence unchanged. What is *missing* is a downstream, projection-level view of marker contribution.

## 3. Proposal — a SEPARATE, exploratory Stage-2 projection-evaluability test (necessary, not sufficient; not a bypass)
Explicitly **not** a mechanism to convert a failed Stage-1 program into a validated or selectable program,
and **not** a change to any Stage-1 gate. It is an additional, exploratory Stage-2 diagnostic with
marker-level contribution reporting.

Runs in **Stage-2** (where the DE-space projection lives), on the **full predefined panel as the scorer of
record** (LOMO here is only a probe of the decision). Per candidate pole `P ∈ {A,B}`, per selected
condition `C`:
1. **Full-panel projection:** with the frozen full-panel P-scorer (panel-minus-control, target-masked into
   the effect universe), project every **evaluable** target's DE effect → `toward_b` (and for the A pole,
   `away_from_A`), **kept strictly separate — never combined into `balanced_skew`**; rank each arm.
2. **Leave-one-marker-out projection:** for each *measured* panel marker `m`, recompute the P-scorer with
   `panel∖{m}` (matched frozen controls held fixed), re-project, re-rank — again each arm separately.
3. **Marker-level contribution reporting (the primary output):** for each removed `m`, report per arm the
   top-K set stability (Jaccard, full vs `panel∖{m}`) and full-ranking Spearman ρ over the evaluable set —
   i.e. *how much each marker drives the downstream ranking*. This is exploratory characterization, not a
   pass/fail that licenses identity.
4. **Denominators — to be fixed BEFORE viewing target identities, NOT specified here:** the eligible-target
   universe and the contributing-guide mapping are **unresolved** and must be frozen with a stated
   calibration/simulation rationale; **guide replication is a *separate* support dimension and must not
   silently define this projection denominator**; donor stratification stated explicitly; top-K frozen with
   rationale.
5. **Consequence (bounded):** this test can be a **necessary** input to Stage-2 evaluability (a pole whose
   ranking collapses under a single-marker deletion is not projection-evaluable). It is **not sufficient**:
   passing it does **not** override the Stage-1 construct-fragility finding, does **not** make a program
   `stage1_selectable`, and does **not** license a biological identity. A program that failed Stage-1 LOMO
   remains a fragile construct regardless of this test.

**Frozen values are deliberately NOT proposed here.** The exact eligible-target universe, the top-K, and
the stability thresholds are unresolved, and the contributing-guide mapping is not established. The future
Stage-2 spec must freeze the universe / K / thresholds / denominators **with a stated calibration or
simulation rationale, before any target identities or ranks are viewed** — no unmotivated defaults, no
post-hoc tuning.

**Placement:** part of the deferred Stage-2 remediation (needs `DE_stats`, the target-masked projection,
and guide/eligibility denominators — none in Stage-1). Stage-1 is unchanged.

## 4. What I did / did NOT do
- **DID (allowed):** preserved `stage01_validation.json` + a sanitized `stage01_validation_independent_check.json`
  (zero host/user/path/session/workspace identifiers; independent recompute labeled
  `independently_observed_not_reproducible_from_release` with a proposed verifier follow-up).
- **DID NOT:** propose changing any Stage-1 gate/consequence; edit any threshold/panel/control/seed; run
  T8; declare any selectable program; merge/push/tag/publish/update HF; touch Stage-2 branches/worktrees.

## 5. Requested decision
Approve/adjust the *exploratory* Stage-2 projection-evaluability test above (marker-level contribution
reporting, necessary-not-sufficient, non-licensing). **The Stage-1 LOMO gate, consequence, and the 0/33
outcome stand unchanged.** I am stopping here for your review; nothing further is implemented.
