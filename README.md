# Decision Policy Lab

Decision Policy Lab is a Dash-based analytical product for simulating, comparing and optimizing business decision policies over frozen study snapshots. It starts at the analytical handoff boundary: a client-prepared study dataset plus baseline policy rules.

This repository implements an MVP aligned to the attached project materials:

- baseline reproduction over a static study snapshot
- manual scenario testing with derived-feature reuse
- local persistence for studies, scenarios and results
- bounded policy search on top of the simulator
- a Dash application for study review, scenario editing and recommendation review

## Product boundaries

- No ETL or ELT
- No external data collection
- No production decisioning
- No deployment of policies to a live engine
- Adapter-first policy normalization so the core product is not tied to a single rule syntax

## Tech choices

- `polars` for analytical execution
- `dash` for the application layer
- `plotly` for charts
- `duckdb` prepared for future execution paths, but the MVP uses `polars` first

## Quick start

1. Create or activate the virtual environment.
2. Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[ui,dev,docs]
```

3. Run the Dash app:

```powershell
.\.venv\Scripts\python.exe -m policy_lab.apps.simulator_app.app
```

4. Open the local address printed by Dash.

## Dependency profiles

- base: `pip install -e .`
- UI: `pip install -e .[ui]`
- development: `pip install -e .[dev]`
- documentation notebooks: `pip install -e .[docs]`
- full local setup: `pip install -e .[ui,dev,docs]`

## Demo study

The repository includes a sample study in [`runtime/studies/demo_lending`](/c:/Users/acaci/Documents/Decision%20Intelligence%20Platform/DPL/runtime/studies/demo_lending) based on the simulation case described in the provided documents. It demonstrates:

- baseline policy reproduction
- threshold changes
- optional use of a reusable derived feature
- comparison against observed outcomes
- recommendation search over bounded numeric thresholds

## Repository shape

The structure follows the architecture described in the supplied materials:

- `policy_lab/adapters`
- `policy_lab/domain`
- `policy_lab/engine`
- `policy_lab/analysis`
- `policy_lab/storage`
- `policy_lab/apps/simulator_app`
- `runtime/studies`
- `docs`
- `tests`
