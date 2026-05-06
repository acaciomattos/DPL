# Architecture Notes

Decision Policy Lab starts at the analytical handoff boundary defined in the supplied concept documents: a frozen study snapshot plus baseline policy rules. The product is intentionally separated from ETL/ELT and from production decisioning.

## MVP layers

- `policy_lab/adapters`
  - adapter contract and a demonstrative Python adapter for structured payloads
- `policy_lab/domain`
  - canonical entities for workspace, policy family, study, scenario, derived feature and results
- `policy_lab/engine`
  - policy parsing and mutation
  - derived-feature resolution
  - policy execution in `polars`
  - counterfactual comparison
  - bounded candidate generation
  - scenario orchestration
- `policy_lab/analysis`
  - KPI, uncertainty and complexity estimation
- `policy_lab/storage`
  - runtime persistence under `runtime/studies`
- `policy_lab/apps/simulator_app`
  - Dash UI for study review, scenario editing and recommendation review

## Product boundaries preserved in code

- no ETL or source-system querying
- no production execution or deployment hooks
- no dependency on one rule language
- study persistence is local and explicit
- UI is orchestration and presentation, not the core business logic

## Current execution path

1. Load a study manifest and frozen snapshot.
2. Resolve requested derived features on the snapshot.
3. Execute the baseline or candidate policy in `polars`.
4. Estimate KPI impact, uncertainty and complexity.
5. Persist scenarios and results.
6. Surface results in Dash and optionally run bounded search.

