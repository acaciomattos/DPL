from __future__ import annotations

# ruff: noqa: E501
import csv
import json
import math
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from refresh_documentation_notebooks import main as refresh_documentation_notebooks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
NOTEBOOKS_DIR = DOCS_DIR / "notebooks"
NOTEBOOK_SOURCE_DIR = DOCS_DIR / "notebook_sources"
STUDY_DIR = PROJECT_ROOT / "runtime" / "studies" / "demo_lending"
SCENARIOS_DIR = STUDY_DIR / "scenarios"
RESULTS_DIR = STUDY_DIR / "results"


def notebook(cells: list[dict], *, title: str) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "title": title,
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def md_cell(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code_cell(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def write_notebook(path: Path, cells: list[dict], *, title: str) -> None:
    path.write_text(
        json.dumps(notebook(cells, title=title), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def markdown_to_notebook(markdown_path: Path, notebook_path: Path, title: str) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    cells = [
        md_cell(f"# {title}\n\nCópia em notebook de `{markdown_path.relative_to(PROJECT_ROOT)}`.\n"),
        md_cell(text),
    ]
    write_notebook(notebook_path, cells, title=title)


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def correlated_pair(
    rng: random.Random,
    mean_a: float,
    sd_a: float,
    mean_b: float,
    sd_b: float,
    corr: float,
) -> tuple[float, float]:
    z1 = rng.gauss(0.0, 1.0)
    z2 = rng.gauss(0.0, 1.0)
    x = z1
    y = corr * z1 + math.sqrt(max(1.0 - corr**2, 0.0)) * z2
    return mean_a + sd_a * x, mean_b + sd_b * y


def sample_binary_vector(
    rng: random.Random,
    probabilities: list[float],
) -> list[int]:
    return [1 if rng.random() < probability else 0 for probability in probabilities]


def choice_by_score(value: float, thresholds: list[tuple[float, str]], fallback: str) -> str:
    for threshold, label in thresholds:
        if value >= threshold:
            return label
    return fallback


def generate_demo_rows(seed: int = 17) -> list[dict[str, object]]:
    rng = random.Random(seed)
    total_rows = 20_000
    approved_count = 16_000
    rejected_count = total_rows - approved_count
    approved_events = int(approved_count * 0.20)
    rejected_events = int(rejected_count * 0.35)

    status_pairs = (
        [("approve", 1)] * approved_events
        + [("approve", 0)] * (approved_count - approved_events)
        + [("reject", 1)] * rejected_events
        + [("reject", 0)] * (rejected_count - rejected_events)
    )
    rng.shuffle(status_pairs)

    start_date = date(2024, 1, 1)
    rows: list[dict[str, object]] = []

    for index, (decision, event_flag) in enumerate(status_pairs, start=1):
        if decision == "approve" and event_flag == 0:
            score1_mean, score1_sd = 600, 150
            score2_mean, score2_sd = 550, 100
            pot1_mean, pot1_sd = 50, 10
            pot2_mean, pot2_sd = 50, 15
            x_prob = [0.05, 0.04, 0.06, 0.05, 0.07, 0.06, 0.05, 0.04]
            z_prob = [0.06, 0.05, 0.08, 0.06]
            w1_shape, w1_scale = 1.6, 1.0
            w2_shape, w2_scale = 2.0, 1.6
            income_alpha, income_beta = 7.0, 2.2
            debt_alpha, debt_beta = 2.5, 7.0
        elif decision == "approve" and event_flag == 1:
            score1_mean, score1_sd = 400, 200
            score2_mean, score2_sd = 450, 50
            pot1_mean, pot1_sd = 30, 15
            pot2_mean, pot2_sd = 35, 10
            x_prob = [0.20, 0.16, 0.18, 0.19, 0.16, 0.18, 0.17, 0.16]
            z_prob = [0.22, 0.16, 0.18, 0.15]
            w1_shape, w1_scale = 2.8, 1.5
            w2_shape, w2_scale = 3.0, 2.2
            income_alpha, income_beta = 3.6, 4.8
            debt_alpha, debt_beta = 4.8, 3.1
        elif decision == "reject" and event_flag == 0:
            score1_mean, score1_sd = 500, 140
            score2_mean, score2_sd = 500, 90
            pot1_mean, pot1_sd = 40, 12
            pot2_mean, pot2_sd = 44, 12
            x_prob = [0.18, 0.15, 0.17, 0.16, 0.14, 0.18, 0.15, 0.14]
            z_prob = [0.17, 0.12, 0.15, 0.13]
            w1_shape, w1_scale = 2.4, 1.7
            w2_shape, w2_scale = 2.6, 2.2
            income_alpha, income_beta = 4.3, 4.0
            debt_alpha, debt_beta = 3.8, 4.1
        else:
            score1_mean, score1_sd = 330, 170
            score2_mean, score2_sd = 410, 70
            pot1_mean, pot1_sd = 22, 14
            pot2_mean, pot2_sd = 28, 11
            x_prob = [0.33, 0.28, 0.31, 0.30, 0.27, 0.29, 0.30, 0.28]
            z_prob = [0.30, 0.22, 0.27, 0.24]
            w1_shape, w1_scale = 3.0, 2.0
            w2_shape, w2_scale = 3.4, 2.6
            income_alpha, income_beta = 2.4, 5.6
            debt_alpha, debt_beta = 5.4, 2.6

        score1, score2 = correlated_pair(
            rng,
            score1_mean,
            score1_sd,
            score2_mean,
            score2_sd,
            0.6,
        )
        potencial1, potencial2 = correlated_pair(
            rng,
            pot1_mean,
            pot1_sd,
            pot2_mean,
            pot2_sd,
            -0.8,
        )

        x_values = sample_binary_vector(rng, x_prob)
        z_values = sample_binary_vector(rng, z_prob)
        w1 = max(1, int(round(rng.gammavariate(w1_shape, w1_scale))))
        w2 = max(1, int(round(rng.gammavariate(w2_shape, w2_scale))))

        recent_income_stability = round(
            clip(rng.betavariate(income_alpha, income_beta), 0.01, 0.99),
            4,
        )
        debt_ratio = round(
            clip(rng.betavariate(debt_alpha, debt_beta), 0.02, 0.98),
            4,
        )

        score1 = int(round(clip(score1, 0, 1000)))
        score2 = int(round(clip(score2, 0, 1000)))
        potencial1 = round(clip(potencial1, 0, 100), 2)
        potencial2 = round(clip(potencial2, 0, 100), 2)

        credit_score = int(round(clip((0.72 * score1) + (0.28 * score2), 0, 1000)))
        number_of_protests = min(w1, 12)
        segment = choice_by_score(
            credit_score,
            [
                (720, "prime"),
                (620, "standard"),
                (540, "near-prime"),
            ],
            "watchlist",
        )

        if decision == "approve" and event_flag == 0:
            ticket_value = clip(rng.gauss(4200, 900), 1500, 9000)
            profit_value = round(ticket_value * rng.uniform(0.028, 0.055), 2)
        elif decision == "approve" and event_flag == 1:
            ticket_value = clip(rng.gauss(3600, 950), 1200, 8500)
            profit_value = round(ticket_value * rng.uniform(-0.032, 0.01), 2)
        else:
            ticket_value = clip(rng.gauss(3000, 850), 1000, 7500)
            profit_value = 0.0

        churn_probability = 0.06
        if decision == "approve":
            churn_probability += 0.18 if event_flag == 1 else 0.07
            churn_probability += 0.06 if segment in {"near-prime", "watchlist"} else 0.0
        churned = 1 if rng.random() < min(churn_probability, 0.92) else 0

        query_date = start_date + timedelta(days=rng.randint(0, 365 - 1))
        row = {
            "entity_id": index,
            "workspace_id": "credit-risk-lab",
            "policy_family_id": "retail-lending-eligibility",
            "policy_version_real": "v1.5",
            "y": event_flag,
            "date_reference": query_date.strftime("%Y%m%d"),
            "decisao": decision,
            "historical_decision": decision,
            "score1": score1,
            "score2": score2,
            "x1": x_values[0],
            "x2": x_values[1],
            "x3": x_values[2],
            "x4": x_values[3],
            "x5": x_values[4],
            "x6": x_values[5],
            "x7": x_values[6],
            "x8": x_values[7],
            "w1": w1,
            "w2": w2,
            "z1": z_values[0],
            "z2": z_values[1],
            "z3": z_values[2],
            "z4": z_values[3],
            "indicador_potencial1": potencial1,
            "indicador_potencial2": potencial2,
            "credit_score": credit_score,
            "number_of_protests": number_of_protests,
            "recent_income_stability": recent_income_stability,
            "debt_ratio": debt_ratio,
            "ticket_value": round(ticket_value, 2),
            "profit_value": profit_value,
            "defaulted": event_flag,
            "churned": churned,
            "segment": segment,
        }
        rows.append(row)

    rows.sort(key=lambda item: item["entity_id"])
    return rows


def study_manifest() -> dict:
    return {
        "study_id": "demo_lending",
        "name": "Retail Lending Eligibility Pilot",
        "description": (
            "Merged development study based on the prompt specification "
            "and the first demo dataset, preserving business-friendly aliases "
            "and the richer feature catalog requested for continued development."
        ),
        "workspace": {
            "workspace_id": "credit-risk-lab",
            "name": "Credit Risk Lab",
            "description": "Pilot workspace for governed policy studies.",
        },
        "policy_family": {
            "policy_family_id": "retail-lending-eligibility",
            "name": "Retail Lending Eligibility",
            "description": "Eligibility policy family for retail lending studies.",
        },
        "baseline_version": "v1.5",
        "snapshot": {
            "file_name": "study_snapshot.csv",
            "format": "csv",
            "entity_id_column": "entity_id",
            "historical_decision_column": "historical_decision",
            "outcome_columns": ["y", "profit_value", "defaulted", "churned"],
            "metadata_columns": ["segment", "date_reference", "ticket_value"],
            "date_column": "date_reference",
            "analysis_feature_columns": [
                "score1",
                "score2",
                "x1",
                "x2",
                "x3",
                "x4",
                "x5",
                "x6",
                "x7",
                "x8",
                "w1",
                "w2",
                "z1",
                "z2",
                "z3",
                "z4",
                "indicador_potencial1",
                "indicador_potencial2",
                "credit_score",
                "number_of_protests",
                "recent_income_stability",
                "debt_ratio",
            ],
            "performance_columns": {
                "matrix_event": "y",
                "profit": "profit_value",
                "risk_event": "y",
                "churn": "churned",
                "ticket": "ticket_value",
            },
        },
        "baseline_policy": baseline_policy(),
        "derived_features": derived_features(),
        "search_defaults": {
            "integer_shifts": [-60, -40, -20, 20, 40],
            "float_shifts": [-0.08, -0.04, 0.04, 0.08],
            "feature_candidates": ["risk-buffer-flag", "thin-file-watch-flag"],
            "heuristic_trials": 8,
            "top_k": 8,
            "seed": 17,
        },
    }


def baseline_policy() -> dict:
    return {
        "policy_id": "eligibility-baseline",
        "name": "Eligibility Baseline",
        "version": "v1.5",
        "decision_column": "simulated_decision",
        "default_decision": "reject",
        "rules": [
            {
                "rule_id": "approve-prime",
                "name": "Approve resilient applicants",
                "decision": "approve",
                "block_combiner": "all",
                "description": (
                    "Baseline rule based on score1, indicator_potencial1, "
                    "w1 and the first set of baseline boolean signals."
                ),
                "blocks": [
                    {
                        "block_id": "approve-prime-thresholds",
                        "name": "Resilient thresholds",
                        "logical_operator": "all",
                        "predicates": [
                            {"field": "score1", "operator": ">", "value": 340},
                            {"field": "indicador_potencial1", "operator": ">", "value": 18.0},
                            {"field": "w1", "operator": "<", "value": 9},
                        ],
                    },
                    {
                        "block_id": "approve-prime-signals",
                        "name": "Resilient signals",
                        "logical_operator": "any",
                        "predicates": [
                            {"field": "x1", "operator": "==", "value": 0},
                            {"field": "x2", "operator": "==", "value": 0},
                            {"field": "x3", "operator": "==", "value": 0},
                            {"field": "x4", "operator": "==", "value": 0},
                        ],
                    }
                ],
            },
            {
                "rule_id": "approve-stable",
                "name": "Approve stable recoveries",
                "decision": "approve",
                "block_combiner": "all",
                "description": (
                    "Second baseline block covering remaining baseline signals "
                    "x5 to x8 together with score1, w1 and indicator_potencial1."
                ),
                "blocks": [
                    {
                        "block_id": "approve-stable-thresholds",
                        "name": "Stable thresholds",
                        "logical_operator": "all",
                        "predicates": [
                            {"field": "score1", "operator": ">", "value": 360},
                            {"field": "indicador_potencial1", "operator": ">", "value": 20.0},
                            {"field": "w1", "operator": "<", "value": 9},
                        ],
                    },
                    {
                        "block_id": "approve-stable-signals",
                        "name": "Stable recovery signals",
                        "logical_operator": "any",
                        "predicates": [
                            {"field": "x5", "operator": "==", "value": 0},
                            {"field": "x6", "operator": "==", "value": 0},
                            {"field": "x7", "operator": "==", "value": 0},
                            {"field": "x8", "operator": "==", "value": 0},
                        ],
                    }
                ],
            },
        ],
        "metadata": {
            "source_adapter": "python",
            "notes": (
                "Prompt-aligned baseline using score1, x1..x8, w1 and "
                "indicador_potencial1. Candidate variables remain available "
                "for manual and automatic policy search."
            ),
        },
    }


def derived_features() -> list[dict]:
    return [
        {
            "feature_id": "risk-buffer-flag",
            "name": "risk_buffer_flag",
            "expression": (
                "(recent_income_stability < 0.38) | (debt_ratio > 0.62) | "
                "(indicador_potencial2 < 28) | (z1 == 1)"
            ),
            "dependencies": [
                "recent_income_stability",
                "debt_ratio",
                "indicador_potencial2",
                "z1",
            ],
            "data_type": "bool",
            "mode": "virtual",
            "description": "Reusable veto for unstable or high-risk applications.",
        },
        {
            "feature_id": "thin-file-watch-flag",
            "name": "thin_file_watch_flag",
            "expression": "(w2 > 8) & ((z2 == 1) | (z3 == 1))",
            "dependencies": ["w2", "z2", "z3"],
            "data_type": "bool",
            "mode": "virtual",
            "description": "Flags thin-file patterns among candidate variables.",
        },
        {
            "feature_id": "blended_quality_flag",
            "name": "blended_quality_flag",
            "expression": (
                "(score2 > 520) & (indicador_potencial2 > 45) & "
                "(recent_income_stability > 0.62) & (debt_ratio < 0.42)"
            ),
            "dependencies": [
                "score2",
                "indicador_potencial2",
                "recent_income_stability",
                "debt_ratio",
            ],
            "data_type": "bool",
            "mode": "virtual",
            "description": "Positive candidate signal built from non-baseline variables.",
        },
    ]


def write_study_files() -> None:
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for directory in (SCENARIOS_DIR, RESULTS_DIR):
        for item in directory.glob("*.json"):
            item.unlink()

    rows = generate_demo_rows()
    fieldnames = list(rows[0].keys())
    with (STUDY_DIR / "study_snapshot.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest = study_manifest()
    (STUDY_DIR / "study.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (STUDY_DIR / "derived_features.json").write_text(
        json.dumps(manifest["derived_features"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (STUDY_DIR / "baseline_policy.json").write_text(
        json.dumps(manifest["baseline_policy"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def convert_docs_to_notebooks() -> None:
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    markdown_to_notebook(
        DOCS_DIR / "architecture.md",
        NOTEBOOKS_DIR / "00_architecture.ipynb",
        "Architecture Notes",
    )
    markdown_to_notebook(
        DOCS_DIR / "mvp_scope.md",
        NOTEBOOKS_DIR / "01_mvp_scope.ipynb",
        "MVP Scope",
    )


def generate_reference_notebooks() -> None:
    files_reference = """
# Repositório e Referência Técnica

Este notebook documenta a base atual do produto arquivo por arquivo, com objetivo, contexto, uso, pontos de extensão e parâmetros relevantes.

## Convenção de leitura

- **Objetivo**: por que o arquivo existe.
- **Uso**: como ele entra no fluxo do produto.
- **Parâmetros**: entradas relevantes para classes, funções ou contratos.
- **Saídas**: estruturas, efeitos persistidos ou artefatos gerados.
- **Evolução sugerida**: onde o arquivo tende a crescer nas próximas fases.

## Arquivos raiz

### `pyproject.toml`
- Objetivo: definir empacotamento, dependências e comando de entrada do app.
- Uso: instala o projeto em modo editável e expõe `policy-lab-dashboard`.
- Parâmetros relevantes:
  - `project.dependencies`: `dash`, `duckdb`, `plotly`, `polars`
  - `project.scripts`: comando de entrada do app
- Evolução sugerida: separar dependências por perfil (`ui`, `engine`, `dev`, `docs`).

### `README.md`
- Objetivo: ponto de entrada humano do repositório.
- Uso: onboarding, visão do escopo e quickstart.
- Evolução sugerida: adicionar screenshots reais do app e um fluxo de importação de estudos.

## Pasta `policy_lab`

### `policy_lab/__init__.py`
- Objetivo: marcar o pacote principal e expor versão.
- Uso: referência institucional do pacote.

### `policy_lab/config.py`
- Objetivo: centralizar caminhos do projeto e do runtime.
- Função principal: `get_settings()`
- Saída: `Settings(project_root, runtime_root, studies_root)`
- Uso: repositórios de estudo usam este contrato para localizar estudos persistidos.

## `policy_lab/domain`

### `policy_lab/domain/models.py`
- Objetivo: definir os objetos canônicos do produto.
- Classes e papéis:
  - `Workspace`: escopo organizacional.
  - `PolicyFamily`: família de política.
  - `StudySnapshotDefinition`: contrato do snapshot congelado.
  - `DerivedFeatureDefinition`: catálogo de feature derivada.
  - `PredicateDefinition`: átomo lógico da regra.
  - `RuleBlockDefinition`: grupo de predicados.
  - `DecisionRuleDefinition`: regra que produz decisão.
  - `PolicyDefinition`: política estruturada.
  - `ScenarioDefinition`: política candidata dentro de um estudo.
  - `SearchRunDefinition`: execução de busca governada.
  - `ScenarioMetrics`: métricas agregadas.
  - `ScenarioResult`: resultado persistível de um cenário.
  - `StudyManifest`: manifesto do estudo.
  - `StudyContext`: manifesto + caminho físico do estudo.
- Parâmetros importantes:
  - `PolicyDefinition.decision_column`: coluna que receberá a decisão simulada.
  - `DerivedFeatureDefinition.expression`: expressão executável em Polars.
  - `ScenarioDefinition.feature_ids`: features derivadas necessárias para o cenário.
- Uso: todos os módulos do produto orbitam este contrato.
- Evolução sugerida: adicionar schemas versionados e validações semânticas.

## `policy_lab/adapters`

### `policy_lab/adapters/base/adapter.py`
- Objetivo: definir o protocolo mínimo de um adapter de política.
- Contrato: `normalize(source: dict[str, Any]) -> PolicyDefinition`
- Uso: desacoplar o núcleo do produto da linguagem de regras de origem.

### `policy_lab/adapters/python/adapter.py`
- Objetivo: adapter demonstrativo para payloads já estruturados em Python/JSON.
- Uso: MVP e testes.
- Evolução sugerida: adicionar adapters para decision tables, SQL e motores proprietários.

## `policy_lab/engine`

### `policy_lab/engine/policy_parser/service.py`
- Objetivo: registrar adapters e aplicar mutações em políticas.
- Classes:
  - `PolicyParser`: seleciona o adapter e normaliza a política.
  - `PolicyBuilder`: clona políticas, gera handles de predicados e aplica overrides.
- Métodos relevantes:
  - `parse(source, adapter_name='python')`
  - `predicate_handle(rule_index, block_index, predicate_index, predicate)`
  - `apply_threshold_overrides(policy, overrides)`
  - `add_reject_rule_from_feature(policy, feature)`
- Uso: manual lab e otimizador usam `PolicyBuilder`.

### `policy_lab/engine/feature_resolution/service.py`
- Objetivo: resolver features derivadas sobre o snapshot congelado.
- Método principal: `resolve(frame, catalog, feature_ids=None)`
- Entradas:
  - `frame`: `polars.DataFrame`
  - `catalog`: lista de `DerivedFeatureDefinition`
  - `feature_ids`: subset de features necessárias para um cenário
- Saída: novo `DataFrame` com colunas derivadas.
- Observação: usa `eval` restrito para compilar expressões Polars.

### `policy_lab/engine/policy_executor/service.py`
- Objetivo: aplicar a política ao dataset.
- Método principal: `execute(frame, policy)`
- Fluxo:
  1. inicializa decisão default
  2. percorre regras na ordem
  3. aplica first-match-wins
  4. devolve frame com decisão simulada e regra que casou
- Evolução sugerida: suportar políticas com múltiplas decisões e árvores mais complexas.

### `policy_lab/engine/counterfactual_engine/service.py`
- Objetivo: resumir transições e distribuições de decisão.
- Métodos:
  - `transitions(frame, from_column, to_column)`
  - `distribution(frame, decision_column)`

### `policy_lab/engine/optimizer/service.py`
- Objetivo: propor cenários candidatos governados.
- Estratégias atuais:
  - `parameter_sweep`
  - `guided_search`
  - `heuristic_search`
- Entradas principais:
  - `policy`
  - `snapshot`
  - `derived_features`
  - `strategy`
  - `search_defaults`
- Saída: lista de `ScenarioDefinition`
- Limites do MVP: trabalha apenas com thresholds numéricos e veto derivado simples.

### `policy_lab/engine/scenario_orchestrator/service.py`
- Objetivo: orquestrar baseline, cenários manuais e busca automática.
- Classe auxiliar: `ScenarioRunBundle(result, frame)`
- Métodos:
  - `run_baseline(study)`
  - `run_scenario(study, scenario, baseline_bundle=None)`
  - `run_search(study, strategy, baseline_bundle=None)`
- Cálculo de score:
  - ganho de aprovação
  - ganho de profit index
  - penalidade de risco
  - penalidade de out-of-support
  - penalidade de complexidade

## `policy_lab/analysis`

### `impact_estimator/service.py`
- Objetivo: calcular aprovação, revisão, rejeição, lucro esperado, profit index, risco e churn.
- Suposição atual:
  - `profit_value`, `defaulted` e `churned` existem no snapshot.
- Evolução sugerida: parametrizar fórmulas por estudo.

### `uncertainty_estimator/service.py`
- Objetivo: medir extrapolação relativa ao suporte observado.
- Método: compara aprovados simulados com a faixa de 5% a 95% dos aprovados históricos.
- Saída:
  - `out_of_support_ratio`
  - label `low`, `medium` ou `high`

### `complexity_estimator/service.py`
- Objetivo: penalizar políticas muito extensas.
- Score atual:
  - regras
  - predicados
  - quantidade de features únicas

## `policy_lab/storage`

### `studies_repository/repository.py`
- Objetivo: listar estudos, carregar manifesto e ler snapshot.
- Métodos:
  - `list_studies()`
  - `load(study_id)`
  - `load_snapshot(study)`

### `feature_repository/repository.py`
- Objetivo: carregar e salvar `derived_features.json`.

### `scenario_repository/repository.py`
- Objetivo: persistir definições de cenário em `runtime/studies/<study>/scenarios`.

### `result_repository/repository.py`
- Objetivo: persistir resultados em `runtime/studies/<study>/results`.

## `policy_lab/apps/simulator_app`

### `app.py`
- Objetivo: camada de apresentação e orquestração do Dash.
- Callbacks:
  - carregamento do estudo
  - execução manual
  - execução de busca
- Funções auxiliares:
  - construção dos controles da política
  - geração de cards de métricas
  - gráficos comparativos e fronteira de recomendação
- Uso: é a interface principal do MVP.

### `assets/style.css`
- Objetivo: linguagem visual do app.
- Direção:
  - dark analytical interface
  - painéis densos
  - cards e gráficos com contraste controlado
- Evolução sugerida: tokens de design por tema e responsividade mais refinada.

## `runtime/studies/demo_lending`

### `study.json`
- Objetivo: manifesto do estudo.
- Uso: define snapshot, baseline, derived features e defaults de busca.

### `baseline_policy.json`
- Objetivo: cópia isolada da política baseline do estudo.
- Uso: facilitar inspeção e exportação.

### `derived_features.json`
- Objetivo: catálogo de features derivadas do estudo.

### `study_snapshot.csv`
- Objetivo: dataset de desenvolvimento do produto.
- Uso: insumo fixo para baseline, cenários e otimização.

## `docs`

### `architecture.md`
- Objetivo: resumo arquitetural conciso.

### `mvp_scope.md`
- Objetivo: delimitar o que já existe e o que ainda está fora.

## `tests`

### `tests/test_policy_lab.py`
- Objetivo: smoke tests do MVP.
- Testes:
  - baseline executa
  - override manual altera a política clonada sem mutar o baseline

## `dev/experiments`

### `generate_demo_assets.py`
- Objetivo: reproduzir dataset, manifesto e notebooks de documentação.
- Quando usar:
  - ao alterar o contrato do estudo demo
  - ao atualizar a documentação em notebook
  - ao limpar cenários e resultados stale
"""

    calculations_reference = """
# Engine, Operações e Cálculos

## Fluxo principal do produto

1. O usuário escolhe um estudo persistido.
2. O manifesto informa qual snapshot congelado usar.
3. Features derivadas são resolvidas sobre o snapshot.
4. A política baseline ou candidata é executada em Polars.
5. O motor analítico calcula métricas, transições, incerteza e complexidade.
6. O resultado pode ser persistido, comparado e usado como entrada para busca.

## Como o executor funciona

### Estratégia
- A política começa com uma decisão default (`reject` no MVP).
- Cada regra é avaliada na ordem.
- A primeira regra que casa em uma linha define a decisão final dessa linha.
- A coluna `_matched_rule` registra qual regra disparou.

### Consequência de design
- Ordem importa.
- O laboratório manual precisa permitir reordenação de regras.
- O cálculo de ponto de corte futuro precisa respeitar essa ordem, como o prompt descreve.

## Cálculos agregados do MVP

### Aprovação, review e rejeição
- São médias booleanas sobre a coluna de decisão simulada.

### Lucro esperado
- Hoje é a média de `profit_value` apenas para linhas aprovadas.
- Rejeitados contam como `0`.
- Isto é simples e explícito, mas futuramente deve ser configurável por contexto de política.

### Profit index
- Fórmula atual:
  - `expected_profit / baseline_expected_profit * 100`
- Interpretação:
  - `100` = igual ao baseline
  - `110` = 10% acima do baseline

### Risco e churn
- São médias de `defaulted` e `churned` apenas entre aprovados simulados.

### Incerteza
- O motor compara os aprovados simulados contra o suporte dos aprovados históricos.
- Para cada feature numérica usada na política:
  - calcula percentis 5% e 95% na população histórica aprovada
  - verifica quantos aprovados simulados caem fora dessa faixa
- O ratio agregado vira `out_of_support_ratio`.

### Complexidade
- Score sintético atual:
  - 12 pontos por regra
  - 4 pontos por predicado
  - 9 pontos por feature única usada
- Papel: evitar ótimos artificiais baseados em políticas excessivamente intrincadas.

## Busca automática no MVP

### `parameter_sweep`
- Varia thresholds numéricos das regras existentes.
- É a estratégia mais segura e mais explicável.

### `guided_search`
- Combina pequenas variações em dois thresholds.
- Serve como etapa intermediária antes de heurísticas mais livres.

### `heuristic_search`
- Sorteia combinações limitadas e pode incluir veto derivado.
- Ainda é uma heurística leve, não um otimizador global.

## Restrições e lacunas ainda abertas

- O desempenho composto ainda e unico e linear.
- Não existe fronteira de Pareto persistida.
- Não existe cálculo de estabilidade temporal.
- Não existe busca sobre estruturas lógicas complexas.
- Ainda não existe etapa explícita de "encontrar ponto de corte" separada do "simular".
"""

    app_reference = """
# App e Fluxos de Usuário

## Papel do app Dash

O app é a camada de apresentação, navegação e orquestração. A lógica de domínio e cálculo fica fora dele.

## O que já existe

### Topbar
- seleção do estudo
- seleção do modo de busca

### Sidebar
- resumo do estudo
- métricas baseline

### Rule Builder
- inputs numéricos para thresholds das regras baseline
- checklist de veto por features derivadas
- botão de execução manual

### Scenario Comparison
- cards de métricas do cenário
- gráfico baseline vs candidato
- matriz de transição baseline -> candidato

### Recommendations
- botão de busca
- tabela com cenários ranqueados
- gráfico tipo fronteira aprovação vs profit index

## Relação com o prompt original

### Já aderente
- abas conceituais de laboratório manual e otimização começam a aparecer no fluxo atual
- baseline e comparação de cenários já existem
- recomendação automática já existe em forma inicial

### Ainda faltando
- reordenação de regras no app
- criação matricial de regras
- botão separado para encontrar ponto de corte
- exportação explícita da política simulada
- filtros de público e data no painel baseline
- visualização do fluxo de subdecisões por regra

## Callbacks principais

### `load_study_view`
- Entrada: `study_id`
- Saídas:
  - metadados do estudo
  - métricas baseline
  - controles das regras
  - opções de features derivadas

### `run_manual_scenario`
- Entradas:
  - clique do botão
  - estudo selecionado
  - valores de thresholds
  - features derivadas selecionadas
- Saídas:
  - cards de comparação
  - gráfico comparativo
  - matriz de transição

### `run_search`
- Entradas:
  - clique do botão
  - estudo
  - estratégia de busca
- Saídas:
  - tabela de recomendações
  - gráfico de fronteira

## Próxima evolução recomendada

1. Separar o app em `layout.py`, `callbacks.py` e `components/`.
2. Adicionar stores Dash para baseline e cenário.
3. Criar abas reais:
   - laboratório manual
   - combinação de regras
   - otimização automática
4. Exportar política para JSON a partir da interface.
"""

    data_reference = """
# Estudo Demo, Dataset e Contratos

## Objetivo do estudo demo

Fornecer uma base de desenvolvimento mais próxima do prompt:
- 20.000 linhas
- 16.000 aprovações históricas
- 4.000 reprovações históricas
- baseline usando `score1`, `x1..x8`, `w1`, `indicador_potencial1`
- variáveis candidatas disponíveis para novas regras e otimização
- alias de negócio do primeiro dataset mantidos para continuidade do desenvolvimento

## Colunas do `study_snapshot.csv`

### Caracterizadoras
- `entity_id`: identificador da entidade
- `y`: evento observado/inferido
- `date_reference`: data de referencia da consulta/proposta em formato `YYYYMMDD`
- `decisao`: decisão histórica da política vigente
- `historical_decision`: alias padronizado usado pela engine

### Features baseline do prompt
- `score1`
- `x1` a `x8`
- `w1`
- `indicador_potencial1`

### Features candidatas do prompt
- `score2`
- `w2`
- `z1` a `z4`
- `indicador_potencial2`

### Features de continuidade do primeiro demo
- `credit_score`
- `number_of_protests`
- `recent_income_stability`
- `debt_ratio`
- `segment`
- `ticket_value`
- `profit_value`
- `defaulted`
- `churned`

## Observações de modelagem

- O prompt original tinha inconsistência na escala de `indicador_potencial1/2`:
  - dizia "0 a 1000"
  - mas descrevia médias `50`, `30`, `35`
- Neste estudo, a escala foi normalizada para `0 a 100` porque ela é coerente com as médias descritas.

## Política baseline do estudo

### Regra 1: `Approve resilient applicants`
- Usa:
  - `score1`
  - `indicador_potencial1`
  - `w1`
  - `x1`, `x2`, `x3`, `x4`

### Regra 2: `Approve stable recoveries`
- Usa:
  - `score1`
  - `indicador_potencial1`
  - `w1`
  - `x5`, `x6`, `x7`, `x8`

### Decisão default
- `reject`

## Features derivadas do estudo

### `risk_buffer_flag`
- Objetivo: veto reutilizável de alto risco.
- Componentes:
  - `recent_income_stability`
  - `debt_ratio`
  - `indicador_potencial2`
  - `z1`

### `thin_file_watch_flag`
- Objetivo: sinalizar perfil com pouca robustez de arquivo e sinais complementares.

### `blended_quality_flag`
- Objetivo: feature positiva combinando variáveis candidatas não baseline.

## Governança implícita do contrato

- O snapshot é congelado por estudo.
- A política baseline é versionada.
- Features derivadas são catalogadas fora do snapshot base.
- Cenários e resultados ficam em pastas próprias do estudo.
"""

    governance_reference = """
# Fases do Desenvolvimento, Controle e Governança

## Princípios de governança

- evolução lenta e explicável
- reprodutibilidade acima de velocidade
- todo estudo precisa ter contrato explícito
- mudanças de engine e UI precisam de documentação correspondente
- artefatos de exemplo não podem ficar stale sem rastreabilidade

## Fase 0 — Fundamentos e contrato

### Objetivo
- definir escopo, limites e linguagem comum do produto

### Entregáveis
- manifesto arquitetural
- contrato do estudo
- esqueleto do repositório

### Critério de saída
- equipe consegue explicar o produto sem ambiguidade entre laboratório e motor de produção

## Fase 1 — Núcleo analítico mínimo

### Objetivo
- reproduzir baseline e simular cenários manuais

### Entregáveis
- modelos de domínio
- parser interno
- executor em Polars
- persistência de estudo, cenário e resultado

### Critério de saída
- baseline roda em snapshot congelado e cenários manuais podem ser comparados

## Fase 2 — Dataset de desenvolvimento e laboratório manual

### Objetivo
- estabilizar um dataset rico para todo o ciclo de desenvolvimento

### Entregáveis
- estudo demo alinhado ao prompt
- baseline policy versionada
- documentação detalhada do dataset
- interface manual mais fiel ao fluxo descrito

### Critério de saída
- o dataset serve de base comum para engine, UI e testes

## Fase 3 — Criação e combinação de regras

### Objetivo
- permitir criação assistida de novas regras a partir de matrizes e faixas

### Entregáveis
- aba específica de combinação de regras
- binning balanceado para contínuas
- persistência de regras criadas no estudo
- reuso dessas regras nas demais abas

### Critério de saída
- uma regra criada visualmente pode ser salva, explicada e reutilizada

## Fase 4 — Otimização automática governada

### Objetivo
- expandir a busca automática com mais controle

### Entregáveis
- objetivos multi-métrica
- restrições explícitas
- recomendação com justificativa
- exportação da política sugerida

### Critério de saída
- o sistema encontra alternativas úteis sem sacrificar explicabilidade

## Fase 5 — Hardening e produto profissional

### Objetivo
- preparar a base para uso profissional em ambientes variados

### Entregáveis
- packaging
- configuração por ambiente
- guias operacionais
- testes de regressão
- observabilidade e auditoria

### Critério de saída
- o produto pode ser entregue e evoluído sem depender de conhecimento tácito

## Trilhas permanentes de controle

### Gestão de mudanças
- toda mudança estrutural deve atualizar:
  - código
  - documentação `.md`
  - notebooks correspondentes
  - contrato do estudo demo quando aplicável

### Qualidade
- smoke tests obrigatórios
- validação do estudo demo após alterações relevantes
- limpeza de artefatos stale quando o contrato muda

### Decisões arquiteturais
- registrar motivação
- registrar alternativas descartadas
- registrar impacto futuro

### Riscos para acompanhar
- divergência entre manifesto do estudo e snapshot real
- UI evoluir sem refletir as restrições da engine
- desempenho composto mascarar trade-offs reais
- otimização explorar regiões fora de suporte
- documentação ficar desatualizada em relação ao código
"""

    notebooks = {
        "02_repository_reference.ipynb": {
            "title": "Repository Reference",
            "markdown": files_reference,
            "code": (
                "from pathlib import Path\n"
                "root = Path.cwd()\n"
                "files = [p.relative_to(root) for p in root.rglob('*') "
                "if p.is_file() and '__pycache__' not in p.parts]\n"
                "files[:80]"
            ),
        },
        "03_engine_operations_and_calculations.ipynb": {
            "title": "Engine Operations and Calculations",
            "markdown": calculations_reference,
            "code": (
                "from policy_lab.storage.studies_repository import StudyRepository\n"
                "from policy_lab.storage.feature_repository import FeatureRepository\n"
                "from policy_lab.storage.result_repository import ResultRepository\n"
                "from policy_lab.storage.scenario_repository import ScenarioRepository\n"
                "from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator\n"
                "study_repo = StudyRepository()\n"
                "orchestrator = ScenarioOrchestrator(study_repo, FeatureRepository(), ScenarioRepository(), ResultRepository())\n"
                "study = study_repo.load('demo_lending')\n"
                "baseline = orchestrator.run_baseline(study)\n"
                "baseline.result.metrics"
            ),
        },
        "04_app_and_user_workflows.ipynb": {
            "title": "App and User Workflows",
            "markdown": app_reference,
            "code": (
                "from pathlib import Path\n"
                "app_path = Path('policy_lab/apps/simulator_app/app.py')\n"
                "print(app_path)\n"
                "print(app_path.read_text(encoding='utf-8')[:2000])"
            ),
        },
        "05_data_study_and_policy_contract.ipynb": {
            "title": "Data Study and Policy Contract",
            "markdown": data_reference,
            "code": (
                "import csv\n"
                "from pathlib import Path\n"
                "snapshot = Path('runtime/studies/demo_lending/study_snapshot.csv')\n"
                "with snapshot.open(encoding='utf-8') as handle:\n"
                "    reader = csv.DictReader(handle)\n"
                "    rows = [next(reader) for _ in range(5)]\n"
                "rows"
            ),
        },
        "06_development_governance_phases.ipynb": {
            "title": "Development Governance and Phases",
            "markdown": governance_reference,
            "code": (
                "from pathlib import Path\n"
                "docs = sorted(Path('docs/notebooks').glob('*.ipynb'))\n"
                "[doc.name for doc in docs]"
            ),
        },
    }

    for file_name, payload in notebooks.items():
        cells = [
            md_cell(payload["markdown"]),
            code_cell(payload["code"]),
        ]
        write_notebook(NOTEBOOKS_DIR / file_name, cells, title=payload["title"])


def notebook_index() -> None:
    index_markdown = """
# Documentação em Notebook

Os notebooks abaixo foram gerados para servir como documentação navegável do produto.

## Ordem sugerida de leitura

1. `00_architecture.ipynb`
2. `01_mvp_scope.ipynb`
3. `02_repository_reference.ipynb`
4. `03_engine_operations_and_calculations.ipynb`
5. `04_app_and_user_workflows.ipynb`
6. `05_data_study_and_policy_contract.ipynb`
7. `06_development_governance_phases.ipynb`
"""
    (NOTEBOOKS_DIR / "README.md").write_text(index_markdown.strip() + "\n", encoding="utf-8")


def validate_dataset(rows: list[dict[str, object]]) -> dict[str, object]:
    decision_counter = Counter(row["decisao"] for row in rows)
    event_by_decision: dict[str, list[int]] = {"approve": [], "reject": []}
    for row in rows:
        event_by_decision[row["decisao"]].append(int(row["y"]))
    return {
        "rows": len(rows),
        "approved": decision_counter["approve"],
        "rejected": decision_counter["reject"],
        "approve_event_rate": sum(event_by_decision["approve"]) / len(event_by_decision["approve"]),
        "reject_event_rate": sum(event_by_decision["reject"]) / len(event_by_decision["reject"]),
    }


def main() -> None:
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate_demo_rows()
    summary = validate_dataset(rows)
    write_study_files()
    refresh_documentation_notebooks()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
