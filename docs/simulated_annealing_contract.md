# Contrato Funcional da Primeira Estrategia Avancada de Busca

Este documento consolida a proposta funcional para a proxima etapa da otimizacao: adicionar uma estrategia avancada baseada em `simulated annealing` sobre a infraestrutura que ja foi consolidada na fundacao da busca.

## Motivacao

Depois da fundacao da otimizacao, o produto ja consegue:

- operar com `ObjectiveSpec`
- buscar sobre baseline, ultima simulacao manual ou construir do zero
- gerar candidatos mais ricos que um cutoff isolado
- ranquear com desempenho composto, guardrails e Pareto
- transferir sugestoes governadas para o `Laboratorio Manual`

O proximo gargalo deixa de ser estrutural e passa a ser de qualidade de exploracao: precisamos de uma estrategia que consiga escapar de otimos locais e navegar melhor pelo espaco de politicas candidatas.

## Decisao de priorizacao

### Estrategia escolhida

- `simulated_annealing`

### Estrategias nao priorizadas neste momento

- otimizacao bayesiana
  - deixa de ser prioridade
  - pode nem fazer sentido no espaco atual, que mistura thresholds, regras novas, vetos, bundles e policy packs
- varredura parametrica
  - continua existindo como baseline local e explicavel
  - mas deixa de ser a principal aposta para ganho de qualidade

### Estrategias candidatas para depois

- heuristica evolutiva leve
- algoritmos geneticos, se mostrarem ganho incremental real

## Objetivo do ciclo

Adicionar uma primeira estrategia avancada sem quebrar governanca, explicabilidade e performance da UI.

O objetivo nao e substituir `guided_search` e `heuristic_search`. O objetivo e complementar essas estrategias com uma busca que:

- aceite degradacoes temporarias controladas
- explore vizinhancas mais amplas
- encontre politicas candidatas que nao aparecem em buscas locais simples

## Estado da busca

No `simulated annealing`, o estado da busca passa a ser uma `PolicyDefinition` candidata, nao apenas um vetor de thresholds.

Isso e importante porque hoje o espaco de busca ja contem:

- overrides de threshold
- regras simples
- grouped rules
- structured rules
- composite rules
- derived veto
- guarded rules
- rule bundles
- policy packs

## Operadores de vizinhanca

O ciclo deve usar mutacoes governadas, reaproveitando o gerador de candidatos ja existente.

Operadores esperados:

- ajustar threshold de predicado numerico existente
- adicionar regra simples curta
- substituir ou adicionar veto derivado
- propor composite ou structured rule curta
- montar bundles curtos compativeis

Diretriz:

- o annealing deve combinar o que `guided_search` e `heuristic_search` ja sabem gerar
- nao deve abrir um motor paralelo totalmente diferente

## Energia e criterio de aceitacao

O criterio principal continua sendo o score alinhado ao `ObjectiveSpec`.

Elementos usados:

- desempenho composto
- guardrails de preservacao
- penalizacao por violacao de restricao
- complexidade

O Pareto continua como camada de leitura e ordenacao final, nao necessariamente como funcao de energia direta do annealing.

## Parametros governados

No MVP deste ciclo, poucos parametros precisam ser expostos ao usuario.

### Parametros internos

- `annealing_iterations`
- `annealing_initial_temperature`
- `annealing_cooling_rate`
- `annealing_seed_limit`
- `annealing_neighbor_limit`

### Exposicao na UI

A recomendacao e expor pouco no inicio, possivelmente via perfis:

- `Conservador`
- `Balanceado`
- `Exploratorio`

Enquanto isso nao for implementado, os defaults podem ficar declarados em `search_defaults` do estudo.

## Governanca de lineage

Cada candidato vindo de `simulated annealing` deve poder registrar:

- iteracao
- temperatura
- delta de score
- probabilidade de aceitacao
- se a mutacao foi aceita

Isso nao substitui os detalhes tecnicos da composicao do candidato, mas ajuda a explicar como a estrategia navegou o espaco.

## O que entra neste ciclo

- adicionar `simulated_annealing` ao contrato de `SearchStrategy`
- integrar a estrategia a UI da aba de otimizacao
- reutilizar `guided_search` e `heuristic_search` como base de seeds e vizinhancas
- avaliar candidatos reais com a infraestrutura atual do orquestrador
- manter compatibilidade com Pareto, `ObjectiveSpec` e transferencia para o manual

## O que nao entra neste ciclo

- algoritmo genetico completo
- otimizacao bayesiana
- interpretador de objetivo por IA
- reabertura da governanca de transferencia para o `Laboratorio Manual`

## Criterio de sucesso

O ciclo deve ser considerado bem sucedido se:

- `simulated_annealing` gerar candidatas nao triviais e diferentes das locais
- a latencia continuar aceitavel no webapp
- a estrategia permanecer explicavel e auditavel
- as sugestoes continuarem transferiveis para o `Laboratorio Manual`
