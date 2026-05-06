# Estudo Demo, Dataset e Contratos

## Objetivo do estudo demo

O estudo demo foi remodelado para aproximar o desenvolvimento do prompt original:

- 20.000 linhas
- 16.000 aprovações históricas
- 4.000 reprovações históricas
- baseline usando `score1`, `x1..x8`, `w1`, `indicador_potencial1`
- variáveis candidatas para expansão e otimização

## Colunas principais

### Caracterizadoras

- `entity_id`
- `y`
- `date_reference`
- `decisao`
- `historical_decision`

### Baseline do prompt

- `score1`
- `x1` a `x8`
- `w1`
- `indicador_potencial1`

### Candidatas do prompt

- `score2`
- `w2`
- `z1` a `z4`
- `indicador_potencial2`

### Continuidade do primeiro demo

- `credit_score`
- `number_of_protests`
- `recent_income_stability`
- `debt_ratio`
- `ticket_value`
- `profit_value`
- `defaulted`
- `churned`
- `segment`

## Papéis declarados no manifesto

O snapshot pode ter nomes próprios de coluna, mas o produto deve consultar o papel declarado no `study.json`.

- `snapshot.date_column`: aponta para `date_reference`
- `snapshot.analysis_feature_columns`: lista as variáveis elegíveis para matriz, filtros da matriz e criação de regras
- `snapshot.performance_columns.matrix_event`: aponta para `y` no demo
- `snapshot.performance_columns.risk_event`: aponta para `defaulted` no demo
- `snapshot.performance_columns.profit`: aponta para `profit_value` no demo
- `snapshot.performance_columns.churn`: aponta para `churned` no demo
- `snapshot.performance_columns.ticket`: aponta para `ticket_value` no demo

Assim, nomes como `y`, `defaulted` ou `profit_value` são detalhes do estudo demo, não nomes engessados no motor.

## Política baseline do estudo

### Por que existem duas regras baseline

Porque o objetivo não era ter uma única regra monolítica, e sim uma política com mais de um caminho de aprovação dentro da mesma família.

- Regra 1: cobre um perfil resiliente
- Regra 2: cobre um perfil de recuperação estável

Isso é útil para demonstrar:

- múltiplas regras dentro da mesma política
- ordem entre regras
- composição por blocos
- comparação de cenários mais realista

## Hierarquia dos objetos da política

### `DecisionRuleDefinition`

- representa a regra inteira
- sim, cada uma das duas regras baseline é uma `DecisionRuleDefinition`

### `RuleBlockDefinition`

- não é cada variável individual
- é cada bloco lógico dentro da regra
- exemplo:
  - bloco `Resilient thresholds`
  - bloco `Resilient signals`

### `PredicateDefinition`

- é a variável individual com operador e valor
- exemplo:
  - `score1 > 340`
  - `x1 == 0`

## O que significa "veto"

Aqui "veto" quer dizer vetar a proposta, isto é, recusar/rejeitar.

No código atual, o veto derivado simples é uma regra do tipo:

- se `risk_buffer_flag == True`
- então `decision = reject`

## Contrato do estudo

### Manifesto

Arquivo:

- `runtime/studies/demo_lending/study.json`

Ele registra:

- identificação do estudo
- workspace
- família da política
- versão baseline
- contrato do snapshot
- baseline policy
- catálogo de features derivadas
- defaults de busca

### Snapshot

Arquivo:

- `runtime/studies/demo_lending/study_snapshot.csv`

Ele é o recorte congelado usado pelo laboratório.

### Catálogo de features derivadas

Arquivo:

- `runtime/studies/demo_lending/derived_features.json`

### Política baseline isolada

Arquivo:

- `runtime/studies/demo_lending/baseline_policy.json`

## Exemplo de leitura operacional

1. `StudyRepository.load("demo_lending")` lê o manifesto
2. `StudyRepository.load_snapshot(study)` lê o CSV
3. a engine executa a baseline sobre o snapshot
4. features derivadas são acionadas apenas se algum cenário pedir

## Observação importante sobre o notebook

O erro de caminho que você viu vinha do fato de o notebook estar dentro de `docs/notebooks/`. Os snippets agora precisam localizar a raiz do projeto antes de abrir o snapshot.
