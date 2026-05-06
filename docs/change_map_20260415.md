# Mapa de Mudancas Consolidado em 2026-04-15

Este arquivo resume o estado consolidado do repositorio apos os ciclos de atualizacao mais recentes, com foco nos pontos que mudaram de fato e em onde eles podem ser encontrados.

## Documentacao-base atualizada

- `docs/notebook_sources/02_repository_reference.md`
  - consolidou perfis de dependencia do `pyproject.toml`
  - explicou `black`, `ruff` e `mypy`
  - explicou por que `dash` e `plotly` estao em dependencia opcional de UI
  - consolidou criterio de classificacao de `FeatureMode`
  - alinhou que enriquecimentos externos devem chegar previamente no snapshot
  - consolidou reuso opcional entre estudos da mesma familia de politica
  - consolidou `lineage cross-study`
  - consolidou identificacao de metricas `None` por ausencia de colunas
  - consolidou observacoes sobre adapters, parser e mapeamento de decisoes
  - consolidou atualizacao estrutural da biblioteca de regras da UI

- `docs/notebook_sources/03_engine_operations_and_calculations.md`
  - consolidou uso analitico de `out_of_support_ratio`
  - deixou explicito que a metrica e uma heuristica propria do produto
  - adicionou referencias conceituais sobre suporte, dataset shift e generalizacao
  - consolidou explicacao do nivel de conforto implicito na formula do desempenho composto

- `docs/notebook_sources/04_app_and_user_workflows.md`
  - removeu a contradicao sobre reorder por input numerico
  - documentou o fluxo atual para adicionar, remover e reordenar regras
  - consolidou biblioteca com dois paineis
  - consolidou edicao de thresholds dentro dos cards
  - consolidou matriz baseada no publico elegivel remanescente
  - consolidou explicacao de `recommendation-figure`
  - consolidou status atual de `optimization-objective`
  - registrou proposta de IA generativa local/offline como modulo opcional futuro

- `docs/notebook_sources/06_development_governance_phases.md`
  - consolidou mitigacao ja ativa para exploracao fora do suporte
  - consolidou mitigacao ja ativa para documentacao versionada
  - consolidou validacao de contrato do estudo no carregamento do snapshot

## Documentos adicionais mantidos

- `docs/study_manifest_contract.md`
  - contrato esperado para `study.json`
  - proposta de hall de entrada do estudo para facilitar criacao do manifesto

- `docs/proposals_radar.md`
  - backlog estruturado de propostas e temas em radar
  - inclui reuso cross-study, adapters, IA local/offline e hall de entrada do estudo
  - agora tambem explicita metricas configuraveis por estudo, estrategias avancadas de otimizacao, criacao de regras por matriz, transferencia da otimizacao para o laboratorio manual, exportadores nativos e ordem sugerida de priorizacao

- `docs/change_map_20260415.md`
  - este mapa consolidado

## Addenda removidos da trilha ativa

Os addenda `07` a `10` deixaram de ser gerados como notebooks ativos. O conteudo relevante foi incorporado nos documentos-base `02`, `03`, `04`, `06`, no contrato do manifesto e no radar de propostas.

Os arquivos fisicos e notebooks antigos de addendum foram removidos para evitar duplicidade e leitura de conteudo desatualizado.

## Codigo alterado nos ciclos recentes

- `pyproject.toml`
  - perfis `ui`, `dev`, `docs`
  - configuracao de `black`, `ruff`, `mypy`

- `policy_lab/storage/studies_repository/repository.py`
  - validacao de schema do snapshot contra o manifesto

- `policy_lab/apps/simulator_app/app.py`
  - reorganizacao da UI em portugues
  - biblioteca de regras com dois paineis
  - edicao de thresholds nos cards
  - cutoff na lateral
  - matriz ligada ao publico elegivel
  - reordenacao por botoes
  - `rule-state-store`
  - handles estaveis de predicados
  - modularizacao inicial aplicada: `app.py` ficou como ponto de entrada e a UI foi separada em layout, callbacks, handlers, componentes, figuras, servicos, runtime e formatacao

- `policy_lab/apps/simulator_app/layout.py`
  - estrutura visual das abas e containers principais

- `policy_lab/apps/simulator_app/callbacks.py`
  - registro declarativo dos callbacks Dash

- `policy_lab/apps/simulator_app/callback_handlers.py`
  - funcoes executadas pelos callbacks

- `policy_lab/apps/simulator_app/components.py`
  - cards, tabelas, biblioteca de regras e componentes reutilizaveis

- `policy_lab/apps/simulator_app/figures.py`
  - construcao dos graficos Plotly

- `policy_lab/apps/simulator_app/services.py`
  - filtros, estado, politica candidata, ponto de corte e populacao elegivel

- `policy_lab/apps/simulator_app/runtime.py`
  - repositorios, orquestrador e servicos compartilhados pela UI

- `policy_lab/apps/simulator_app/formatting.py`
  - formatacao de metricas, moeda, percentuais e deltas

- `policy_lab/apps/simulator_app/assets/style.css`
  - suporte visual para a nova organizacao da UI
  - ajustes para evitar sobreposicao da biblioteca de regras com a coluna principal
  - ajustes para impedir que paineis da coluna principal sejam esticados pela altura da lateral

- `policy_lab/apps/simulator_app/callback_handlers.py`
  - laboratorio manual passa a renderizar baseline como estado inicial
  - ponto de corte passa a aplicar sugestao ou corte seco na politica simulada
  - filtros mensais passam a usar `date_reference` como coluna temporal do snapshot demo

- `policy_lab/apps/simulator_app/figures.py`
  - fluxo de subdecisoes passa a mostrar registros que seguem apos cada regra
  - matriz passa a exibir volume percentual e risco nas celulas
  - grafico de otimizacao reduz sobreposicao de labels

- `runtime/studies/demo_lending/study_snapshot.csv`
  - coluna temporal `dt` renomeada para `date_reference`

- `runtime/studies/demo_lending/study.json`
  - `metadata_columns` atualizado para declarar `date_reference`

- `tests/test_policy_lab.py`
  - teste novo para validacao de schema do snapshot

- `README.md`
  - instalacao com perfis de dependencia

- `dev/experiments/refresh_documentation_notebooks.py`
  - geracao consolidada dos notebooks `00` a `09`

## Regeneracao dos notebooks

Sempre que os arquivos em `docs/notebook_sources/` ou os documentos adicionais mudarem, executar:

```powershell
python dev\experiments\refresh_documentation_notebooks.py
```
