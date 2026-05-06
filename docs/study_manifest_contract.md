# Contrato do Manifesto do Estudo

Este documento descreve o arquivo que deve acompanhar o snapshot quando um time upstream entregar um estudo para o Decision Policy Lab.

## Papel do manifesto

O snapshot sozinho nao basta. Para o laboratorio funcionar de forma governada, o produto precisa de um arquivo de metadados que declare:

- o identificador do estudo
- a familia da politica
- o contrato do snapshot
- a baseline vigente naquele recorte
- o catalogo inicial de features derivadas

No produto atual, esse arquivo e o `study.json`.

## Quem deve gerar

No demo atual, o manifesto ja existe como `runtime/studies/demo_lending/study.json` e e mantido manualmente pelo proprio produto durante o desenvolvimento.

Em um fluxo real, ha tres possibilidades:

- o time que prepara o snapshot entrega tambem o manifesto completo
- o time que prepara o snapshot entrega apenas os insumos minimos e o time analitico completa o manifesto
- o Decision Policy Lab oferece uma tela de entrada do estudo para ler o cabecalho do snapshot, orientar o preenchimento e gerar o `study.json`

A terceira alternativa e a preferida como evolucao de produto, porque reduz atrito para o cliente e evita que a criacao do estudo dependa de edicao manual de JSON.

## Hall de entrada do estudo

O hall de entrada do estudo e uma proposta de interface para criar um estudo de forma governada. Ele deve:

- receber ou localizar o arquivo de snapshot
- ler o cabecalho e inferir tipos basicos das colunas
- permitir selecionar a familia de politica
- apontar coluna de entidade e coluna de decisao historica
- declarar colunas de resultado, segmentacao, data e metadados
- declarar variaveis analiticas elegiveis para criacao de regras e matriz
- mapear colunas de performance por papel de negocio, como evento, lucro, churn e ticket
- registrar a baseline vigente e sua versao
- validar se as features usadas pela baseline existem no snapshot
- criar a pasta do estudo e o `study.json`
- oferecer importacao opcional de politicas/cenarios, regras e features derivadas de estudos anteriores da mesma familia

Essa tela tambem deve executar as validacoes necessarias para lineage cross-study antes de permitir o reuso de ativos analiticos entre estudos.

## Estrutura minima

```json
{
  "study_id": "eligibility_2026q2",
  "name": "Eligibility Q2 2026",
  "description": "Snapshot congelado para simulacao de politica.",
  "workspace": {
    "workspace_id": "credit-risk-lab",
    "name": "Credit Risk Lab"
  },
  "policy_family": {
    "policy_family_id": "retail-lending-eligibility",
    "name": "Retail Lending Eligibility"
  },
  "baseline_version": "v1.5",
  "snapshot": {
    "file_name": "study_snapshot.csv",
    "format": "csv",
    "entity_id_column": "proposal_id",
    "historical_decision_column": "historical_decision",
    "outcome_columns": ["profit_value", "defaulted", "churned"],
    "metadata_columns": ["segment", "date_reference"],
    "date_column": "date_reference",
    "analysis_feature_columns": ["score1", "score2", "x1", "x2"],
    "performance_columns": {
      "matrix_event": "defaulted",
      "risk_event": "defaulted",
      "profit": "profit_value",
      "churn": "churned",
      "ticket": "ticket_value"
    }
  },
  "baseline_policy": {},
  "derived_features": [],
  "search_defaults": {}
}
```

## Campos que ja sao obrigatorios para o produto atual

- `study_id`
- `name`
- `workspace`
- `policy_family`
- `baseline_version`
- `snapshot.file_name`
- `snapshot.format`
- `snapshot.entity_id_column`
- `snapshot.historical_decision_column`
- `baseline_policy`

## Campos que o produto usa na validacao do snapshot

Ao carregar o snapshot, o produto agora valida se existem:

- a coluna de entidade
- a coluna de decisao historica
- as colunas declaradas em `outcome_columns`
- as colunas declaradas em `metadata_columns`
- a coluna declarada em `date_column`, quando informada
- as colunas declaradas em `analysis_feature_columns`
- as colunas declaradas em `performance_columns`
- todas as features usadas na politica baseline

## Variaveis elegiveis para matriz e criacao de regras

O produto nao deve decidir sozinho que uma coluna chamada `y`, `defaulted`, `ticket_value` ou qualquer outro nome especifico pertence a um papel de negocio. Essa decisao deve vir do manifesto.

Para a aba de combinacao de regras, `snapshot.analysis_feature_columns` define explicitamente quais colunas podem aparecer nas opcoes de variavel de linha, variavel de coluna e filtros do publico elegivel. Isso evita engessar a UI no snapshot de demo e permite que cada cliente declare seu proprio conjunto de variaveis explicativas.

Se o campo estiver vazio, o produto ainda consegue operar em modo tolerante usando colunas tecnicamente compativeis e excluindo papeis ja declarados no manifesto. Para uso profissional, entretanto, a recomendacao e sempre preencher `analysis_feature_columns`.

## Mapeamento de performance

`snapshot.performance_columns` declara o papel de cada coluna usada nos calculos e visualizacoes:

- `matrix_event`: coluna usada como taxa exibida na matriz da aba de combinacao de regras
- `risk_event`: coluna usada para estimativa de risco entre aprovados
- `profit`: coluna usada para lucro esperado
- `churn`: coluna usada para estimativa de churn
- `ticket`: coluna usada como valor/ticket quando aplicavel

No snapshot de demo, esses papeis apontam para nomes como `y`, `defaulted`, `profit_value` e `churned`, mas esses nomes sao apenas dados da demo. O codigo passa a consultar os papeis declarados no manifesto.

## Campos recomendados para evolucao futura

- `historical_decision_mapping`
- `policy_decision_mapping`
- `snapshot_period`
- `population_scope`
- `schema_version`
- `source_systems`
- `cross_study_imports`

## Observacao sobre baseline e coluna historica

`snapshot.historical_decision_column` e `baseline_policy.decision_column` nao precisam ser iguais:

- a primeira aponta para a decisao historica real que veio no snapshot
- a segunda aponta para a coluna simulada que sera criada pelo executor

No demo atual elas sao diferentes de proposito:

- historica: `historical_decision`
- simulada: `simulated_decision`
