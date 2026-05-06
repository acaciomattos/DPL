# Engine, Operações e Cálculos

## Fluxo principal

1. O usuário escolhe um estudo.
2. O manifesto informa qual snapshot congelado será usado.
3. Filtros de data/segmento podem restringir o público daquele estudo.
4. Features derivadas são resolvidas.
5. A política baseline ou candidata é executada.
6. O sistema calcula métricas, incerteza e complexidade.
7. O resultado pode ser persistido, comparado e ranqueado.

## Estratégia do executor

- A política começa com uma decisão default.
- Cada regra é avaliada na ordem.
- A primeira regra satisfeita define a decisão final da linha.
- Isso implementa um fluxo sequencial e explicável.

### Exemplo ilustrativo

Suponha três propostas:

| entity_id | score1 | indicador_potencial1 | w1 | x1 | x2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 500 | 25 | 2 | 0 | 1 |
| 2 | 280 | 12 | 8 | 1 | 1 |
| 3 | 420 | 30 | 3 | 0 | 0 |

Regra:

- bloco thresholds:
  - `score1 > 340`
  - `indicador_potencial1 > 18`
  - `w1 < 9`
- bloco sinais com `ANY`:
  - `x1 == 0`
  - `x2 == 0`

Resultado:

- entidade 1 aprova
- entidade 2 rejeita por default
- entidade 3 aprova

## Cálculos agregados

### Aprovação, review e rejeição

- médias booleanas da coluna de decisão simulada

### Lucro esperado

- média da coluna declarada em `snapshot.performance_columns.profit` entre aprovados
- rejeitados entram como zero

### Profit index

- `expected_profit / baseline_expected_profit * 100`

### Risco e churn

- médias das colunas declaradas em `snapshot.performance_columns.risk_event` e `snapshot.performance_columns.churn` entre aprovados simulados
- no snapshot de demo, esses papeis apontam para `defaulted` e `churned`, mas o motor consulta o manifesto e não nomes fixos

### Incerteza

- o método usa o suporte empírico dos aprovados históricos
- para cada feature numérica usada na política:
  - calcula percentis 5% e 95%
  - marca aprovados simulados fora dessa faixa
- o `out_of_support_ratio` é a média das linhas aprovadas que ficaram fora do suporte em pelo menos uma feature

### Exemplo ilustrativo de incerteza

Suponha que, entre aprovados históricos:

- `score1` fica entre 300 e 760 no intervalo 5%-95%
- `w1` fica entre 1 e 7 no mesmo intervalo

Se a candidata aprovar 1000 propostas e 180 delas tiverem:

- `score1 < 300` ou `score1 > 760`, ou
- `w1 > 7`

então:

- `out_of_support_ratio = 180 / 1000 = 18%`
- label resultante: `high`

### Como usar `out_of_support_ratio` na análise

- essa métrica ajuda a entender se a política/cenário candidata está aprovando perfis em regiões de domínio pouco representadas entre os aprovados históricos
- na prática, ela pode orientar o analista a investigar quais features explicam a diferença de perfil entre baseline e candidata
- interpretação operacional:
  - a baseline define um território observado para as features usadas
  - a candidata pode ampliar a aprovação para regiões menos conhecidas
  - o `out_of_support_ratio` resume o percentual desses aprovados
- a leitura correta é conjunta com:
  - distribuições das features
  - comparação baseline x candidata
  - métricas de risco e churn
- Natureza do cálculo:
  - a fórmula atual é própria do produto e foi criada como heurística explicável de apoio à análise
  - ela não deve ser tratada como teste estatístico formal nem como prova de instabilidade
  - o raciocínio é simples: se uma política/cenário aprova muitos registros em faixas pouco observadas entre aprovados históricos, a incerteza operacional aumenta
  - por isso, o indicador funciona como alerta de extrapolação, não como decisão automática

### Referências conceituais úteis

As referências abaixo ajudam a contextualizar a ideia de suporte empírico, mudança de distribuição e extrapolação, embora a métrica atual do DPL seja uma heurística própria:

- Quiñonero-Candela, Sugiyama, Schwaighofer and Lawrence, *Dataset Shift in Machine Learning*, MIT Press, 2008. https://mitpress.mit.edu/9780262170055/dataset-shift-in-machine-learning/
- Sugiyama and Kawanabe, *Machine Learning in Non-Stationary Environments*, MIT Press, 2012. https://mitpress.mit.edu/9780262017091/machine-learning-in-non-stationary-environments/
- Hastie, Tibshirani and Friedman, *The Elements of Statistical Learning*, 2nd ed., Springer, 2009. https://link.springer.com/book/10.1007/978-0-387-84858-7
- Breiman, *Statistical Modeling: The Two Cultures*, *Statistical Science*, 2001. DOI: https://doi.org/10.1214/ss/1009213726

## Desempenho composto da otimização

O produto continua exibindo todas as métricas individuais. O desempenho composto existe apenas para ordenar cenários automaticamente.

### Fórmula atual

```text
approval_delta
+ profit_gain
- risk_penalty
- support_penalty
- complexity_penalty
```

### Natureza da fórmula

- é uma heurística operacional do MVP
- não é uma verdade estatística universal
- é uma fórmula própria do produto para ordenar candidatos de forma simples e auditável
- foi desenhada para:
  - premiar ganho de aprovação e rentabilidade
  - punir risco
  - punir extrapolação
  - punir políticas excessivamente complexas
- a segurança do uso vem da transparência:
  - todas as métricas individuais continuam visíveis
  - a fórmula composta serve apenas para triagem e ranking inicial
  - pesos e limiares devem evoluir para configuração por estudo

### Como os multiplicadores foram escolhidos

- `200` em risco:
  - dá peso forte a aumentos de risco acima do nível de conforto implícito do MVP
- `120` em suporte:
  - sinaliza que extrapolar fora do observado é quase tão sensível quanto aumentar risco
- `0.12` em complexidade:
  - complexidade importa, mas não deveria esmagar ganhos de negócio sozinha

### Onde está o nível de conforto implícito

- no código atual, esse conforto implícito aparece quando a penalidade de risco só começa a crescer acima de `5%`
- expressão atual:

```text
max(risk_estimate - 0.05, 0.0) * 200
```

- leitura prática:
  - até `5%`, essa parcela da fórmula não adiciona penalidade
  - acima de `5%`, cada aumento de risco consome pontos do desempenho composto
- esse limiar ainda é heurístico e deveria evoluir para configuração por estudo ou família de política

### Interpretação prática

- o desempenho composto é usado como critério de ranqueamento de cenários na otimização
- ele não substitui a leitura individual de aprovação, churn, risco, profit index etc.

## Por que essa nota única pode mascarar trade-offs

Exemplo:

- cenário A:
  - aprovação +4pp
  - risco +0.2pp
  - complexidade +5
- cenário B:
  - aprovação +1pp
  - risco -1.5pp
  - complexidade igual

Dependendo dos pesos, o cenário A pode ficar acima do B, mesmo que um gestor de risco prefira claramente o B. Por isso:

- a nota composta serve para triagem
- a decisão final deve olhar as métricas individuais

## Métodos de otimização atuais

### `parameter_sweep`

- testa variações controladas em thresholds existentes
- forte em explicabilidade

### `guided_search`

- combina pequenas mudanças em poucos thresholds
- ainda governado e relativamente fácil de explicar

### `heuristic_search`

- usa amostragem controlada e pode adicionar veto derivado
- mais flexível, porém menos sistemático

## Métodos futuros já colocados no radar

- Bayesian Optimization
- Genetic Algorithms
- Simulated Annealing

### Plano inicial para introdução

1. criar uma interface comum de estratégia de busca
2. desacoplar geração de candidatos da orquestração
3. expor restrições e objetivos em formato estruturado
4. medir custo computacional e estabilidade das recomendações
5. comparar técnicas lado a lado no mesmo estudo

### Bibliografia sugerida para futura consulta externa

Como o projeto foi restringido aos arquivos anexados, as referências abaixo entram como bibliografia sugerida, não como citação verificada online nesta rodada.

- Bayesian Optimization:
  - Mockus, J. *Bayesian Approach to Global Optimization*
  - Snoek, Larochelle, Adams. *Practical Bayesian Optimization of Machine Learning Algorithms*
- Genetic Algorithms:
  - Holland, J. *Adaptation in Natural and Artificial Systems*
  - Goldberg, D. *Genetic Algorithms in Search, Optimization and Machine Learning*
- Simulated Annealing:
  - Kirkpatrick, Gelatt, Vecchi. *Optimization by Simulated Annealing*
  - Aarts, Korst. *Simulated Annealing and Boltzmann Machines*

## Complexidade

### Fórmula atual

- 12 por regra
- 4 por predicado
- 9 por feature única

### Racional

- regra extra aumenta custo cognitivo e governança
- predicado extra aumenta leitura e manutenção
- feature extra aumenta dependência de dados e explicabilidade

### Uso prático

- entra como penalidade no desempenho composto
- também pode ser exibida ao analista

### Exemplo

- política A:
  - 2 regras
  - 8 predicados
  - 5 features
- política B:
  - 7 regras
  - 24 predicados
  - 12 features

A segunda tende a ser menos auditável, mais difícil de explicar e mais cara de manter, mesmo que tenha ligeiro ganho de métrica.
