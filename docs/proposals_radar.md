# Propostas e Radar de Evolucao

Este documento centraliza propostas abertas que surgiram a partir de questionamentos sobre o produto. A ideia aqui nao e aprovar tudo de uma vez, e sim manter um backlog governado de decisoes de arquitetura e UX para discutirmos juntos antes de mudar o nucleo.

## 1. Reuso entre estudos da mesma familia de politica

### Problema

Dois estudos podem pertencer a mesma familia de politica, usar a mesma baseline em producao e ainda assim operar sobre snapshots diferentes no tempo, com recortes diferentes do publico e com novas variaveis candidatas.

### Proposta

Introduzir um conceito explicito de `policy asset reuse` entre estudos da mesma familia:

- reutilizar opcionalmente politicas/cenarios candidatos de estudos anteriores
- reutilizar opcionalmente regras e features derivadas de estudos anteriores
- permitir clonar uma politica/cenario candidata de um estudo antigo como candidata comparavel em um novo estudo
- nao tratar esse clone como baseline automaticamente
- exigir validacao de compatibilidade antes do reuso

### Condicoes de compatibilidade sugeridas

Uma politica/cenario candidata so pode ser importada de outro estudo se:

- a familia de politica for a mesma
- todas as features usadas pela politica estiverem presentes no novo snapshot ou puderem ser derivadas no novo contexto
- os tipos das colunas forem compativeis
- os valores de decisao e o contrato do estudo forem compativeis
- a baseline de referencia do estudo de destino continuar explicitamente separada da candidata importada

Uma feature derivada so pode ser importada de outro estudo se:

- todas as dependencias estiverem presentes
- a expressao puder ser compilada no novo contexto
- nao houver conflito de `feature_id` ou `name`
- o modo `VIRTUAL` ou `MATERIALIZED` fizer sentido no novo estudo

## 2. Lineage cross-study

### Conceito

Lineage cross-study e a trilha que liga um ativo analitico criado em um estudo a seu reaproveitamento, promocao, importacao ou comparacao em outro estudo.

### Nomes de politicas/cenarios e nomes de regras/features

Uma politica/cenario candidata tambem deve ter nome proprio. Esse nome representa o pacote completo de regras, ordem, decisoes e parametros simulados. Ele nao deve ser confundido com o nome de uma regra individual, bloco logico, predicado ou feature derivada.

Exemplos:

- politica/cenario candidata: `manual-risk-buffer-policy`
- regra individual: `Reject recent protest`
- feature derivada: `has_recent_protest`
- predicado: `months_since_recent_protest <= 6`

### Exemplo

- estudo `eligibility_2026Q1` gera a politica/cenario candidata `manual-risk-buffer-policy`
- estudo `eligibility_2026Q2` importa essa politica/cenario candidata para novo snapshot
- o produto registra:
  - estudo de origem
  - snapshot de origem
  - baseline de origem
  - estudo de destino
  - snapshot de destino
  - baseline de destino
  - compatibilidade validada
  - quem aprovou a importacao

## 3. Manifesto, decisoes canonicas e metricas configuraveis

### Problema

Hoje parte do produto ainda assume um conjunto pequeno de labels e colunas de metricas. Em estudos reais, o snapshot pode usar nomes diferentes para decisao, lucro, evento adverso, churn, ticket, rentabilidade, custo operacional ou outras metricas de performance.

### Proposta

Evoluir o contrato do estudo para declarar explicitamente:

- `historical_decision_mapping`
- `policy_decision_mapping`
- colunas usadas em metricas padrao, como lucro, evento adverso, churn e ticket
- metricas adicionais configuraveis por estudo
- formulas ou agregacoes parametrizaveis por estudo, quando forem seguras e auditaveis

### Diretriz de produto

O produto deve manter um nucleo minimo padronizado de metricas, mas permitir um conjunto extensivel por estudo. Assim o DPL evita engessamento sem perder comparabilidade basica entre cenarios.

### Exemplos

- `Aprovado`, `APPROVED` e `APV` podem mapear para a classe canonica `approve`
- `Recusado`, `DECLINED` e `REJ` podem mapear para `reject`
- `valor_lucro_esperado` pode ser declarado como coluna de lucro em um estudo
- `inadimplente_12m` pode ser declarado como evento adverso em outro estudo

## 4. Arquitetura de otimizacao e estrategias de busca

### Problema

A heuristica atual do MVP e intencionalmente simples: thresholds numericos e veto derivado simples. Ela e explicavel e boa para o inicio, mas pode ficar limitada quando o espaco de busca crescer.

### Proposta

Criar uma arquitetura de otimizacao com estrategias plugaveis:

- interface comum de estrategia de busca
- geracao de candidatos desacoplada da orquestracao
- restricoes e objetivos em formato estruturado
- medicao de custo computacional por estrategia
- medicao de estabilidade das recomendacoes
- comparacao de tecnicas lado a lado no mesmo estudo

### Diagnostico do estado atual

No estado atual do produto, a aba de otimizacao automatica ja saiu do MVP estreito e passou a operar com uma base mais rica e governada:

- `parameter_sweep`, `guided_search` e `heuristic_search` ja rodam sobre uma arquitetura comum de problema de busca
- o espaco de busca agora inclui:
  - overrides de threshold
  - regras simples novas
  - regras agrupadas por categoria
  - regras estruturadas
  - regras compostas
  - vetos derivados
  - bundles curtos de regras
  - policy packs
- a busca pode partir de:
  - `Baseline do estudo`
  - `Ultima simulacao manual`
  - `Construir do zero`
- o ranking ja considera `ObjectiveSpec`, frente de Pareto, guardrails de efetividade e deduplicacao semantica
- a avaliacao dos candidatos ja foi paralelizada e deixou de reter frames desnecessarios em memoria

Com isso, as sugestoes ja deixaram de se concentrar apenas em cortes simples como ajustes em `score1` e passaram a gerar ativos mais proximos de regras e pacotes de politica.

### Reagrupamento recomendado dos proximos ciclos

Para nao antecipar transferencia de politica nem interpretacao por IA antes da hora, a recomendacao consolidada e dividir essa frente em quatro blocos:

- Ciclo A. Fundacao da otimizacao
- Ciclo B. Estrategias avancadas de busca
- Ciclo C. Objetivo estruturado e interpretador
- Ciclo D. Transferencia da sugestao para o Laboratorio Manual

O detalhamento funcional do Ciclo A foi consolidado em `docs/optimization_foundation_contract.md`.

### Evolucoes de geracao de candidatos

- shifts por variavel
- grids orientados por dominio
- candidatos baseados em quantis
- candidatos baseados em valores observados no snapshot
- candidatos categoricos usando `IN` e `NOT_IN`
- controle de limites inferiores e superiores por variavel

### Estrategias futuras

- simulated annealing como primeira estrategia avancada prioritaria
- algoritmos geneticos como evolucao opcional, se trouxerem ganho incremental real
- busca bayesiana apenas como possibilidade secundaria, a ser reavaliada se houver evidencia clara de ganho no espaco de busca do produto

Essas estrategias devem complementar a infraestrutura atual sem perder rastreabilidade e explicabilidade suficientes para uso governado.

### Sequenciamento recomendado

- antes de implementar busca bayesiana, genetica ou simulated annealing, o produto deve separar geracao de candidatos, estrategia e avaliacao do objetivo
- antes de adicionar interpretador por IA, o produto deve ter um contrato estruturado de objetivo e restricoes
- antes de transferir uma politica/cenario sugerido para o `Laboratorio Manual`, o produto deve conseguir gerar recomendacoes mais ricas do que ajustes simples de cutoff

## 5. Biblioteca de regras e laboratorio manual

### Situacao consolidada

O ciclo de evolucao de drag-and-drop da biblioteca foi concluido e aprovado pelo usuario. O produto ja possui:

- dois paineis lado a lado na biblioteca:
  - `Ativos em uso`
  - `Ativos disponiveis`
- rolagem propria em cada painel
- drag-and-drop completo entre painel "em uso" e painel "disponivel"
- reordenacao do fluxo por drag-and-drop dentro de `Ativos em uso`
- remocao dos botoes de adicionar, remover e mover ordem dos cards compactos
- ordem mista governada para regras baseline, variantes baseline, ativos criados na matriz e features derivadas
- respeito automatico a substituicao da baseline de origem quando uma variante baseline e ativada

### Desdobramentos que permanecem no radar

- editor lateral ou popup de regra
- governanca de sobrescrita de regras
- regra baseline editada gera automaticamente uma nova variante
- regra derivada criada pelo usuario pode ser sobrescrita pelo proprio usuario
- persistencia de filtros e estado em `dcc.Store`

### Observacao

Essa evolucao deve ser implementada com consentimento explicito, porque altera a governanca da biblioteca e o fluxo de criacao de ativos.

## 6. Criacao e combinacao de regras

### Situacao consolidada

O ciclo de evolucao de criacao de regras por matriz foi concluido e aprovado pelo usuario. O produto ja possui:

- selecao singular e multipla de celulas, com `lasso-select` como modo padrao
- previa de resultados antes do salvamento
- salvamento governado em `created_rules.json`
- inclusao da regra salva como ativo disponivel no Laboratorio Manual
- sobrescrita confirmada quando o nome ja existe
- botao `Editar na matriz`
- alerta antes de restaurar o contexto salvo da regra
- reaproveitamento das mesmas faixas da criacao original por meio de `axis_specs`
- persistencia de `source_type`, filtros elegiveis, celulas, decisao, versao, autor e datas
- matriz multicategoria com decisao por celula, preservando uma unica decisao por celula e expandindo a composicao em regras irmas no momento da simulacao
- bloqueio de `Editar na matriz` quando o ativo estiver aplicado na ultima simulacao, para evitar vies no publico elegivel

Decisao conceitual consolidada:

- a aba `Criacao de regras` cria regras, nao features derivadas
- uma feature derivada representa um padrao logico/analitico, geralmente booleano
- uma regra representa uma decisao explicita da politica/cenario, como aprovar, rejeitar ou enviar para mesa
- como a matriz associa celulas selecionadas a uma decisao, o artefato salvo e uma regra estruturada

### Desdobramentos que permanecem no radar

- governanca de versao mais rica quando uma regra criada pela matriz for alterada varias vezes
- definicao de quando criar nova variante versionada em vez de sobrescrever a regra existente
- ordenacao manual governada entre regras criadas pela matriz e regras baseline quando o estudo exigir fluxo mais sofisticado
- ordenacao manual governada entre decisoes irmas geradas pela mesma composicao de matriz, quando o estudo exigir fluxo mais sofisticado

### Mecanica entre regras e features derivadas

Ponto para discutirmos com cuidado antes de implementar: uma `DerivedFeatureDefinition` pode ser usada de varias formas dentro de uma politica/cenario candidata, e cada forma tem implicacoes diferentes de UX e governanca.

Possibilidades a desenhar:

- promover uma feature derivada booleana para uma regra simples, por exemplo `se thin_file_watch_flag == true, rejeitar`
- usar uma feature derivada como um predicado dentro de uma regra maior
- combinar duas ou mais features derivadas em um mesmo `RuleBlockDefinition`
- decompor uma expressao de feature derivada em predicados editaveis quando a gramatica for suportada
- manter a feature como ativo analitico fechado quando a expressao for complexa, nao editavel ou materializada
- registrar lineage entre feature original, regra criada, politica/cenario candidata e estudo
- diferenciar claramente "editar a feature", "criar variante da feature" e "criar regra nova baseada na feature"

Esta evolucao tambem deve resolver como os cards da biblioteca exibem e editam ativos derivados: hoje a feature selecionada entra como ativo reutilizavel simples, mas ainda nao abre internamente em campos, operadores e thresholds como uma regra estruturada baseline.

## 7. Otimizacao automatica e transferencia para o laboratorio manual

### Problema

A aba de otimizacao automatica pode sugerir politicas/cenarios, mas o usuario precisa conseguir revisar, comparar e transferir a sugestao para o laboratorio manual.

### Proposta

Evoluir a aba de otimizacao para:

- apresentar politicas/cenarios sugeridos com metricas macro e metricas detalhadas
- permitir comparar recomendacoes lado a lado
- permitir transferir uma politica/cenario sugerida para a aba manual com um clique
- criar automaticamente regras ou thresholds necessarios para representar a sugestao
- manter lineage entre busca automatica, politica/cenario sugerida e simulacao manual posterior

### Estado consolidado

Esta evolucao foi implementada, validada pelo usuario e considerada concluida.

O estado consolidado agora inclui:

- selecao de uma candidata diretamente na tabela da aba de otimizacao
- transferencia governada para o `Laboratorio Manual`
- preservacao da politica ativa quando a base da busca foi `Ultima simulacao manual`, aplicando apenas o delta transferivel
- substituicao completa dos ativos ativos apenas quando a base foi `Construir do zero`
- criacao de:
  - variantes baseline quando a sugestao altera uma regra baseline existente
  - ativos `optimization_transfer` quando a sugestao adiciona regra nova ou pacote novo
- novo chip `O` na biblioteca para sugestoes transferidas
- drawer para inspecionar, renomear e editar predicados numericos de sugestoes transferidas
- lineage da sugestao preservado por estrategia, base da busca, tipo do candidato e objetivo estruturado

### Desdobramentos que permanecem no radar

- decidir quando um `optimization_transfer` deve ser promovido automaticamente a variante baseline ou regra simples governada
- aprofundar a edicao de sugestoes transferidas quando a composicao crescer alem de ajustes simples
- formalizar exportacao ou promocao dessas sugestoes para formatos externos do cliente

## 8. IA generativa local/offline

### Situacao atual

O campo textual da aba de otimizacao registra o objetivo do estudo, mas ainda nao o traduz para restricoes estruturadas.

### Proposta

Avaliar uma arquitetura opcional com modelo generativo local, open-source ou auto-hospedado para:

- interpretar objetivo em linguagem natural
- extrair objetivos e restricoes em formato estruturado
- apoiar um bot de suporte e manutencao offline
- auxiliar diagnostico de erros operacionais sem expor codigo sensivel ao cliente

### Dependencia de arquitetura

O interpretador de objetivo nao deve vir antes da fundacao deterministica da otimizacao.

Sequencia recomendada:

- primeiro, criar um contrato estruturado de objetivo e restricoes
- depois, permitir que um modulo local/offline preencha esse contrato
- por fim, validar essa saida antes da execucao

Assim, a IA nao passa a "inventar" o formato da busca; ela apenas traduz texto livre para um contrato que o motor ja entende.

### Guardrails

- a saida do modelo deve ser validada e editada pelo usuario antes da execucao
- o modelo nao deve executar otimizacao automaticamente a partir de texto livre
- prompts, respostas, versao do modelo e decisoes aceitas devem ser auditaveis
- deve existir fallback deterministico quando o modulo de IA estiver indisponivel
- a avaliacao deve considerar peso de instalacao, consumo de memoria, CPU, GPU, latencia e qualidade em portugues de negocio

### Exemplo

Texto do usuario:

`Aumentar aprovacao sem piorar risco alem de 2pp e mantendo churn abaixo de 8%.`

Saida estruturada esperada:

```json
{
  "objective": "maximize_approval_rate",
  "constraints": [
    {"metric": "risk_estimate", "operator": "<=", "reference": "baseline+0.02"},
    {"metric": "churn_estimate", "operator": "<=", "value": 0.08}
  ]
}
```

## 9. Hall de entrada do estudo

### Problema

Criar um `study.json` manualmente pode ser trabalhoso e propenso a erro para o cliente, principalmente quando o snapshot tem muitas colunas e quando ha necessidade de reaproveitar ativos de estudos anteriores.

### Proposta

Criar uma tela de entrada do estudo para:

- ler o cabecalho do snapshot
- sugerir tipos e papeis de colunas
- selecionar familia de politica
- preencher metadados sensiveis
- gerar a pasta do estudo e o `study.json`
- validar contrato minimo antes de liberar simulacoes
- validar importacao opcional de politicas/cenarios, regras e features derivadas de outros estudos da mesma familia

### Relacao com lineage cross-study

Essa tela deve ser o ponto natural para aplicar as regras de lineage cross-study, porque e nela que o produto conhece o novo snapshot, a familia de politica, a baseline declarada e os ativos que o usuario deseja importar.

## 10. Hall de registro de adapters

### Problema

Clientes podem usar motores diferentes de politica, como Drools, FICO, Blaze, SQL, planilhas governadas ou scripts Python. Sem um cadastro assistido, a traducao para o formato normalizado do Decision Policy Lab tende a depender demais de trabalho tecnico manual.

### Proposta

Criar uma tela ou fluxo de registro de adapters para:

- selecionar o tipo de motor de origem
- anexar ou apontar exemplos de protocolos reais
- associar uma implementacao de adapter
- executar validacoes em amostras pequenas
- versionar o adapter usado em cada estudo
- registrar limites conhecidos da traducao automatica

Esse fluxo deve alimentar o `PolicyParser`, mas o parser em si nao deve adivinhar sozinho o protocolo de origem no MVP. A deteccao automatica pode entrar como evolucao posterior.

## 11. Exportadores nativos para motores de destino

### Problema

Hoje a exportacao mais segura e o JSON interno estruturado. Para clientes reais, pode ser necessario exportar uma politica/cenario aprovada para o formato que o motor de destino entende.

### Proposta

Criar adapters de saida para:

- Drools
- SQL
- Blaze
- FICO
- decision tables
- formatos proprietarios do cliente

### Diretriz de governanca

A exportacao nativa deve preservar rastreabilidade entre politica/cenario no DPL, regras exportadas, versao do adapter e arquivo gerado. A exportacao nao deve substituir validacao tecnica no ambiente do cliente.

## 12. Modularizacao e hardening da interface web

### Situacao

A modularizacao inicial da interface web foi aprovada pelo usuario e esta concluida como evolucao. O antigo `app.py` foi separado em ponto de entrada, layout, callbacks, handlers, componentes, figuras, servicos, runtime e formatacao.

### Estrutura consolidada

- `app.py`: ponto de entrada do Dash
- `layout.py`: estrutura visual das abas
- `callbacks.py`: registro dos callbacks Dash
- `callback_handlers.py`: funcoes executadas pelos callbacks
- `components.py`: cards, tabelas, biblioteca de regras e blocos reutilizaveis
- `figures.py`: graficos Plotly
- `services.py`: filtros, estado, politica candidata e populacao elegivel
- `runtime.py`: repositorios e orquestrador compartilhados pela UI
- `formatting.py`: formatacao de metricas e deltas

### Hardening futuro

Estes pontos deixam de fazer parte da evolucao de modularizacao inicial e passam a ser hardening futuro:

- aprofundar testes de callbacks e handlers da UI
- reduzir dependencias globais gradualmente, quando fizer sentido
- manter novas evolucoes da UI dentro dessa estrutura modular

### Packaging

Embora `dash` e `plotly` estejam em um perfil tecnico separado no `pyproject.toml`, o produto comercial deve ser entregue com a interface web. No hardening e packaging final, o setup padrao do produto deve instalar as dependencias de UI.

## 13. Decisoes visuais da UI ja consolidadas

### Situacao

A validacao do usuario aprovou a rodada de ajustes funcionais e visuais da UI. Estes itens deixam de ser pendencias do radar e passam a compor a documentacao consolidada da interface:

- fluxo de subdecisoes em barras empilhadas por etapa, mantendo leitura vertical desde `Pool inicial`
- fluxo representado por decisao acumulada, com cores de negocio para aprovados, rejeitados e revisao quando existir
- ausencia de linha separada de decisao default; cada barra soma o pool filtrado e registros ainda nao capturados por regra assumem a decisao default declarada no manifesto
- variaveis da matriz governadas por `snapshot.analysis_feature_columns`
- colunas de performance mapeadas por `snapshot.performance_columns`
- labels da matriz com `Vol` para volume e `Tx` para taxa
- filtros dinamicos do publico elegivel adicionados pelo botao `Adicionar filtro`
- labels do grafico de otimizacao mantidos com posicionamento guloso inspirado em `ggrepel`

### Observacao

Se surgirem novos ajustes visuais na proxima validacao, eles devem entrar como nova secao ou item especifico, em vez de reabrir esta rodada ja aprovada.

## 14. Persistencia de estado da UI concluida

### Situacao

A evolucao de persistir estado relevante da UI em `dcc.Store` foi implementada, validada pelo usuario e considerada concluida neste ciclo.

### Pontos validados pelo usuario

- o quadro `Baseline e filtros` recalcula as metricas baseline sobre o publico filtrado por mes e segmento
- `matrix-config-store` registra a ultima geracao da matriz com timestamp e configuracao usada
- a ultima matriz gerada permanece disponivel ao alternar entre abas
- a ultima simulacao manual preserva filtros, regras em uso, cutoff e resultados
- os tooltips dos cards de regras e features derivadas mostram descricao e estrutura tecnica suficiente para validacao inicial

### Estado persistido nesta rodada

- `rule-state-store`: regras em uso, regras disponiveis, features derivadas selecionadas e features disponiveis
- `manual-ui-state-store`: meses, segmentacao, valores de segmentacao e controles de ponto de corte
- `cutoff-override-store`: sugestao ou corte seco ativo para a simulacao manual
- `matrix-filter-count-store`: quantidade de filtros dinamicos da matriz
- `matrix-config-store`: variaveis de linha/coluna, filtros configurados na matriz e timestamp da ultima geracao da matriz
- `last-simulation-store`: ultima simulacao manual, com filtros, estado de regras, politica candidata, resultado baseline e resultado do cenario

### Diretriz

Os stores usam memoria de sessao quando faz sentido preservar estado durante a navegacao do usuario. Eles nao substituem persistencia governada em disco/banco; a persistencia governada de workspaces manuais agora passa a viver em `manual_configs.json`.

## 15. Ordem sugerida de priorizacao

Para evoluirmos uma coisa por vez, a ordem recomendada e:

1. implementar primeira estrategia avancada de busca com `simulated annealing` governado
2. reavaliar necessidade de heuristica evolutiva leve ou algoritmos geneticos
3. evoluir objetivo e restricoes estruturadas para interpretacao mais rica do texto livre
4. avaliar modulo de IA generativa local/offline para interpretador de objetivo e bot de suporte
5. evoluir manifesto com mapeamento de decisoes e registro configuravel de metricas por estudo
6. criar hall de entrada do estudo para gerar `study.json` e validar snapshots
7. criar hall de registro de adapters de entrada
8. criar exportadores nativos por motor de destino

### Registro de encerramento

A evolucao `desenhar a mecanica entre features derivadas, regras novas e regras compostas antes de abrir edicao profunda desses ativos` foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- biblioteca com cards mais enxutos
- `drawer` como editor principal das regras baseline
- inspecao de features derivadas no `drawer`
- ativos criados na matriz mantidos fora do `drawer`, com trilha propria em `Editar na matriz`
- otimizador singular reposicionado para o contexto do predicado-alvo dentro da regra baseline
- uso de `pool de ancoragem` para evitar vies na busca de cutoff singular

A evolucao `implementar editor governado de regra, com criacao de variante quando regra baseline for alterada` tambem foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- baseline do estudo permanece imutavel
- editar baseline no `drawer` cria uma variante governada em `created_rules.json`
- a variante pode substituir a baseline ativa na mesma posicao da politica candidata ou permanecer como ativo disponivel
- variantes baseline podem ser reabertas e reeditadas no proprio `drawer`
- rascunhos nao salvos do editor deixam de contaminar simulacao, exportacao e matriz

A evolucao `implementar drag-and-drop completo entre regras em uso e disponiveis` tambem foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- dois paineis lado a lado na biblioteca do `Laboratorio Manual`
- drag-and-drop entre `Ativos disponiveis` e `Ativos em uso`
- reordenacao do fluxo dentro de `Ativos em uso`
- rolagem propria em cada painel
- ordem mista respeitada para regras baseline, variantes baseline, ativos de matriz e features derivadas
- remocao dos botoes de adicionar, remover e mover ordem dos cards compactos

A evolucao `permitir salvar e reutilizar configuracoes da aba manual` tambem foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- persistencia governada de workspaces manuais em `manual_configs.json`
- separacao entre manifesto do estudo, ativos compartilhados do estudo e workspace analitico do usuario
- painel de `Workspaces manuais` no topo da interface, ao lado da selecao de estudo
- restauro de filtros, cutoff, ativos, ordem do fluxo e resultados da aba manual ao carregar uma configuracao
- regra de governanca em que salvar a mesma configuracao atualiza o artefato, enquanto salvar com outro nome a partir de uma configuracao carregada cria um workspace derivado
- metadados preparados para evolucao futura, incluindo `workspace_id`, `author` e `parent_config_id`

A evolucao `fundacao da otimizacao` tambem foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- arquitetura comum de busca para `parameter_sweep`, `guided_search` e `heuristic_search`
- geracao desacoplada de candidatos e espaco de busca muito mais amplo
- suporte a:
  - overrides de threshold
  - regras simples
  - grouped rules
  - structured rules
  - composite rules
  - derived veto
  - signal bundles
  - guarded rules
  - rule bundles
  - policy packs
- `ObjectiveSpec` estruturado na UI e no backend
- base da busca explicita entre baseline, ultima simulacao manual e construir do zero
- avaliacao paralela dos candidatos com menor retencao de memoria
- ranking com desempenho composto auditavel, deduplicacao semantica e organizacao em frentes de Pareto

A evolucao `implementar transferencia de politica/cenario sugerida da otimizacao para o laboratorio manual` tambem foi implementada, validada pelo usuario e considerada concluida.

Ela deixou como estado consolidado:

- transferencia com um clique da candidata selecionada na tabela do otimizador
- criacao governada de ativos `optimization_transfer`
- preservacao da politica ativa quando a base da busca foi a ultima simulacao manual
- substituicao completa do fluxo apenas quando a base foi construir do zero
- drawer para inspecionar e editar sugestoes transferidas
- chips e tooltips especificos para identificar sugestoes do otimizador na biblioteca
