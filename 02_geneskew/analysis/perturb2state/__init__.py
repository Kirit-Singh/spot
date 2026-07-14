"""Stage-2 SECONDARY analysis: Perturb2State (plan §6).

Perturb2State is REQUIRED but strictly secondary to the direct measured
perturbation screen (``02_geneskew/analysis/direct/``). Its coefficients are
conditional *reconstruction weights* — never causal effects, treatment effects,
biological p-values, donor validation, or independent confirmation (plan §6.1).

Perturb2StateModel itself is pre-existing upstream MIT software:

    repository: emdann/pert2state_model
    commit:     2c2e30959ffafadecc6af5d4d7b5bde868ab5313
    license:    MIT

spot's contribution here is the Stage-1-selected contrast, the broad
target-signature construction, masking, the frozen stability design, real
execution, verification, and UI integration. The authors' existing Th1/Th2
result is NOT a new spot result (plan §12).
"""
