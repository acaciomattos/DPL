# Contrato Funcional da Fundacao da Otimizacao

Este documento deixa de descrever um bloco futuro e passa a registrar o estado consolidado da fundacao da otimizacao depois da implementacao e validacao do usuario.

## Resultado consolidado

A fundacao da otimizacao foi concluida com quatro entregas principais:

- arquitetura comum de busca
- ampliacao governada do espaco de candidatos
- objetivo estruturado e ranking auditavel
- base suficiente para transferir sugestoes ao `Laboratorio Manual`

Com isso, a aba de `Otimizacao automatica` deixou de ser apenas um buscador de cortes simples e passou a gerar candidatos mais proximos de regras e pacotes de politica.

## Componentes consolidados

### 1. SearchProblem

O problema de busca passou a ser montado de forma explicita a partir de:

- estudo
- snapshot filtrado
- politica base da busca
- features derivadas resolvidas
- `ObjectiveSpec`
- configuracao do espaco de busca

As bases de busca hoje suportadas sao:

- `Baseline do estudo`
- `Ultima simulacao manual`
- `Construir do zero`

Essa decisao foi importante porque a otimizacao deixou de assumir sempre a baseline institucional como ponto de partida.

### 2. CandidateGenerator

O gerador de candidatos passou a ser independente da estrategia de busca. Hoje ele ja suporta:

- shifts por variavel
- grids por dominio
- quantis
- valores observados
- limites inferiores e superiores por variavel
- regras simples numericas
- regras simples categoricas
- grouped rules
- structured rules
- composite rules
- derived veto
- signal bundles
- guarded rules
- rule bundles
- policy packs

Diretriz consolidada:

- o espaco de busca nao deve ficar preso apenas aos predicados ja presentes na baseline
- a baseline pode orientar a busca, mas nao limitar tudo o que o gerador considera elegivel

### 3. SearchStrategy

As estrategias atuais passaram a compartilhar a mesma infraestrutura:

- `parameter_sweep`
- `guided_search`
- `heuristic_search`

Elas seguem com personalidades diferentes:

- `parameter_sweep`: mais local e explicavel
- `guided_search`: exploracao combinatoria curta e governada
- `heuristic_search`: mistura mais livre e exploratoria

O contrato comum deixou a base pronta para as proximas estrategias avancadas.

### 4. ObjectiveEvaluator

O ranking deixou de depender apenas de uma heuristica fixa. Hoje ele combina:

- `ObjectiveSpec`
- restricoes de preservacao
- filtros de efetividade
- deduplicacao semantica
- frentes de Pareto
- desempenho composto auditavel

As metricas de dominancia usadas na organizacao de Pareto incluem:

- aprovacao
- indice de lucro
- risco
- churn
- out of support
- complexidade

Na UI, isso aparece nas colunas de metricas e na coluna `Pareto`, com `F1`, `F2` e assim por diante.

### 5. SearchResultPackage

Embora ainda nao exista um novo tipo de dominio com esse nome, o produto ja carrega esse pacote logico nos resultados da busca:

- politica/cenario sugerido
- estrategia de origem
- base da busca
- tipo de candidato
- composicao
- metricas agregadas
- desempenho composto
- pareto front
- lineage da busca

Esse pacote foi suficiente para destravar a transferencia governada para o `Laboratorio Manual`.

## Melhorias operacionais consolidadas

### Paralelizacao

- a avaliacao de candidatos passou a rodar com `ThreadPoolExecutor`
- o paralelismo fica configuravel por `search_parallel_workers`
- o snapshot nao e duplicado entre processos como seria num modelo com `ProcessPoolExecutor`

### Reducao de memoria

- a busca deixou de reter frames completos de todos os candidatos
- so o necessario para ranking e transferencia sobrevive ao fim da avaliacao

### Explicabilidade

- a tabela da aba de otimizacao ficou mais informativa
- `Cenario` passou a usar rotulos curtos por tipo de candidato
- `Composicao` passou a carregar a descricao tecnica relevante

## Dependencia que ja foi vencida

Antes, a transferencia para o `Laboratorio Manual` estava explicitamente bloqueada por falta de riqueza no motor. Essa dependencia foi vencida.

O produto agora ja consegue:

- gerar candidatos mais ricos
- explicar sua composicao
- preserva-los com lineage
- transferi-los como ativos governados para o fluxo manual

## O que fica para os proximos ciclos

Com a fundacao concluida, os proximos passos recomendados deixam de ser estruturais e passam a ser de expansao qualitativa:

### 1. Estrategias avancadas de busca

- simulated annealing
- algoritmos geneticos
- busca bayesiana, quando fizer sentido

### 2. Interpretador de objetivo

- enriquecer o contrato estruturado
- permitir que um modulo deterministico ou com IA preencha melhor esse contrato a partir de texto livre

### 3. Promocao e exportacao

- decidir quando uma sugestao transferida deve virar variante baseline, regra simples governada ou composicao promovivel
- preparar exportacao para formatos externos do cliente

## Resultado esperado desta etapa

Ao final da fundacao, o DPL passou a estar preparado para:

- sugerir mais do que um cutoff seco
- operar com mais de uma base de busca
- comparar candidatos de forma multicriterio
- transferir sugestoes governadas ao laboratorio
- suportar, em etapas posteriores, tanto IA interpretativa quanto estrategias avancadas de busca
