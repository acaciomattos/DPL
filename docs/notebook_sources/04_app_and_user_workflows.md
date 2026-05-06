# App e Fluxos de Usuário

## Papel do app

O app Dash é a camada de apresentação e orquestração. Ele não é o motor de política e nem substitui a engine analítica.

## Abas atuais

### 1. Laboratório Manual

Prioriza o fluxo descrito no prompt:

- resumo do estudo
- métricas baseline
- filtros de mês e de segmentação
- workspaces manuais no topo da interface, ao lado da seleção do estudo
- biblioteca de regras concentrada na lateral
- dois painéis na biblioteca:
  - ativos em uso
  - ativos disponíveis
- drag-and-drop completo entre os dois painéis da biblioteca
- reordenação do fluxo por drag-and-drop dentro de `Ativos em uso`
- cada painel da biblioteca com rolagem própria
- cards compactos na biblioteca, com detalhes deslocados para tooltips e editor lateral
- edição de thresholds baseline no `drawer`
- edição governada de baseline com criação de variante
- resumo do predicado-alvo e da sugestão de corte na lateral
- botão de simulação
- exportação da política concorrente em JSON
- visualização do fluxo de subdecisões
- comparação baseline vs candidata
- estado da sessão persistido em `dcc.Store` para filtros, cutoff, regras e última simulação
- persistência governada de workspaces manuais em arquivo próprio do estudo

### 2. Criação de Regras

- seleção de variável de linha
- seleção de variável de coluna
- filtros opcionais dinamicos do público elegível antes da matriz, adicionados pelo botão `Adicionar filtro`
- matriz exploratória com contínuas quebradas em 10 faixas balanceadas
- variáveis numéricas de baixa cardinalidade, como flags `0/1`, tratadas como categorias explícitas
- geração da matriz por botão explícito
- matriz alimentada pelo público elegível remanescente da configuração manual
- variáveis explicativas/predicados presentes no snapshot, incluindo dicotômicas, disponíveis para seleção
- features derivadas virtuais do catálogo resolvidas como colunas booleanas temporárias para uso em filtros, linhas e colunas da matriz
- exclusão de outcomes, performance, decisão e metadados operacionais da lista de variáveis da matriz
- labels de célula com `Vol` para volume percentual e `Tx` para taxa do evento
- seleção múltipla de células da matriz
- paleta de decisão ativa na matriz, com uma decisão explícita por célula
- clique simples para atribuir ou remover a decisão ativa em uma célula
- `lasso-select` para atribuir ou remover a decisão ativa em áreas
- prévia de resultados antes de salvar a regra
- salvamento de regra criada pela matriz como ativo disponível na biblioteca do Laboratório Manual
- a regra salva nasce desmarcada, isto é, disponível mas não ativa automaticamente na política/cenário candidata
- confirmação de sobrescrita quando o usuário tenta salvar uma regra com o mesmo nome de outra regra criada na matriz
- configuração da matriz persistida em `dcc.Store`, incluindo variáveis X/Y e filtros dinâmicos
- persistência governada das regras criadas em `created_rules.json`
- botão `Editar na matriz` para restaurar uma regra criada com seu contexto salvo
- composições multicategoria persistidas como um ativo único de biblioteca, expandido em várias `DecisionRuleDefinition` irmãs no momento da simulação

### Decisão conceitual: matriz cria regra, não feature

Nesta etapa, a aba `Criacao de regras` cria `DecisionRuleDefinition`, não `DerivedFeatureDefinition`.

A distinção adotada é:

- uma feature derivada responde a uma pergunta lógica ou analítica, geralmente booleana, como `thin_file_watch_flag == true`
- uma regra responde a uma decisão de política, como aprovar, rejeitar ou enviar para mesa
- a seleção de células da matriz já nasce associada a uma decisão escolhida pelo usuário
- por isso, o artefato salvo pela matriz é uma regra estruturada, composta por blocos e predicados
- features derivadas podem ser insumo da matriz; quando uma célula com feature derivada é salva, ela vira predicado dentro da regra criada

Exemplo:

- célula selecionada: `score1 em [300, 520)` e `z1 == 1`
- decisão escolhida: `approve`
- resultado salvo: regra com `block_combiner=any`, um bloco `all` para a célula e decisão explícita `approve`

Quando várias células são selecionadas, cada célula vira um bloco `all` e a regra combina esses blocos com `any`. Assim, a regra dispara se qualquer célula selecionada for satisfeita.

### Público elegível e regras baseline

A regra criada na matriz é avaliada sobre o público elegível remanescente da configuração manual atual. Isso não obriga que regras baseline estejam ativas.

Exemplo:

- se as duas regras baseline estiverem ativas, a matriz enxerga quem sobrou depois delas
- se o usuário remover as duas regras baseline e simular, o público elegível passa a ser o pool inicial filtrado
- nesse segundo caso, é possível construir uma política/cenário candidata apenas com regras criadas originalmente na matriz

### Comportamento atual da criação por matriz

- o dropdown de decisão é dinâmico a partir das decisões presentes no manifesto/baseline do estudo
- se o estudo declarar `review` ou outra decisão em alguma regra, essa decisão passa a aparecer como opção
- uma opção explícita de `seguir no fluxo` ainda não existe; no executor atual, seguir no fluxo é representado implicitamente pela não captura do registro por uma regra
- regras criadas pela matriz agora são persistidas em `created_rules.json`
- uma mesma composição pode atribuir decisões diferentes para células diferentes, desde que cada célula tenha apenas uma decisão
- o artefato salvo continua sendo um ativo único da biblioteca, mas registra `rules`, `cell_decisions` e `decision_order`
- na simulação, esse ativo gera um conjunto ordenado de `DecisionRuleDefinition` irmãs, uma por decisão usada na composição
- a edição profunda dessas regras passa a ser feita pela própria aba de criação de regras, não pela exposição de todos os blocos na lateral do laboratório manual
- ao clicar em `Editar na matriz`, o app abre um alerta antes de restaurar o contexto salvo
- o alerta explica que o público elegível também depende da configuração e da última simulação no `Laboratório Manual`
- quando o usuário confirma a restauração, o app realinha também o `pool inicial` e os resultados visuais do `Laboratório Manual`
- a edição reaproveita os mesmos intervalos usados na criação original da regra, registrados em `axis_specs`
- valores que fiquem abaixo ou acima dos limites salvos são absorvidos pela primeira ou pela última faixa, em vez de ficarem sem bucket útil na edição
- a seleção da matriz usa `lasso-select` como padrão, com clique simples para selecionar ou remover uma célula e arraste para selecionar ou desmarcar áreas
- a ajuda dessa mecânica fica exposta ao lado do título do painel
- se o ativo criado pela matriz estiver ativo em `Ativos em uso`, o app bloqueia `Editar na matriz` e exibe um alerta para evitar viés no público elegível

### 3. Otimização Automática

- seleção da estratégia
- seleção da base da busca
- objetivo estruturado mínimo:
  - objetivo principal
  - direção
  - métrica a preservar
  - tolerância máxima
- objetivo em linguagem natural
- execução do buscador
- tabela de recomendações
- leitura de Pareto na tabela (`F1`, `F2`, ...)
- fronteira aprovação x profit index
- transferência governada da candidata selecionada para o `Laboratório Manual`

## O que ainda falta na UI

- exportação nativa para `drools`, `blaze`, `fico`, `sql` e outros formatos
- interpretador do objetivo em linguagem natural para restrições estruturadas

## Por que exportação nativa é importante

Hoje a exportação disponível é para o formato estruturado interno em JSON. Isso é útil para:

- auditoria
- versionamento
- persistência de estudo
- base para adapters de saída

No futuro, o produto deve ter adapters de saída também, para permitir exportar:

- `drools`
- `sql`
- `decision table`
- formatos proprietários do cliente

## Fluxos principais

### Carregar estudo

1. o usuário escolhe o estudo
2. o app lê manifesto, snapshot e catálogo de features
3. o baseline é executado
4. o topo é preenchido com seleção de estudo e workspaces manuais disponíveis
5. a lateral é preenchida com filtros e biblioteca de regras

### Salvar e reutilizar workspace manual

1. o usuário monta o contexto analítico da aba manual
2. informa um nome para a configuração
3. clica em `Salvar configuracao`
4. o app salva um artefato de workspace separado do manifesto do estudo
5. depois, o usuário pode selecionar essa configuração no topo e clicar em `Carregar`

### Regra de governança do salvamento

- o estudo continua sendo a camada imutável
- o workspace manual é um artefato analítico separado
- se o usuário salvar com o mesmo nome da configuração atualmente carregada, no mesmo `workspace_id`, o app atualiza a própria configuração
- se o usuário carregar uma configuração e salvar com outro nome, o app cria um novo workspace derivado
- essa derivação registra vínculo com a configuração anterior por `parent_config_id`

### Simular manualmente

1. o usuário escolhe filtros
2. arrasta ativos entre `Ativos disponíveis` e `Ativos em uso`
3. reordena o fluxo por drag-and-drop dentro de `Ativos em uso`
4. abre a regra baseline no `drawer` e altera thresholds quando necessário
5. opcionalmente adiciona veto por feature derivada
6. executa a simulação
7. o app mostra:
   - métricas
   - tabela comparativa
   - matriz de transição
   - fluxo de subdecisões

### Ajustes implementados e validados

- Ao iniciar o webapp, os painéis de resultado, comparação e fluxo passam a apresentar a política baseline como ponto de partida.
- O corte singular continua com três modos: `Meta de aprovacao`, `Meta de risco` e `Corte seco`.
- Os controles do corte singular foram deslocados do painel global para o `drawer` da regra baseline.
- A lateral do `Laboratório Manual` agora mantém apenas o resumo do predicado-alvo selecionado, a sugestão ativa e os botões de simulação/exportação.
- Quando o usuário busca uma meta de aprovação ou risco, a sugestão passa a ser guardada em estado e aplicada na simulação seguinte.
- Quando o usuário seleciona `Corte seco`, o valor informado é aplicado diretamente na simulação e o banner não tenta apresentar uma sugestão analítica.
- O predicado-alvo do corte singular passa a ser escolhido no próprio editor da regra baseline.
- A mensagem do editor deixa explícito que a busca usa o pool de ancoragem imediatamente antes da regra hospedeira do predicado.
- O gráfico de fluxo de subdecisões passa a apresentar barras empilhadas por etapa e por decisão acumulada, com cores de negócio: verde para aprovados, vermelho para rejeitados e azul para análise/revisão quando houver.
- Cada barra do fluxo soma o pool filtrado. Registros ainda não capturados por uma regra assumem a decisão default do manifesto até serem decididos por uma regra posterior.
- O fluxo passa a terminar em `Pool final`, em vez de criar uma linha separada para a decisão default.
- A biblioteca de regras da lateral foi ajustada para não sobrepor a coluna principal.
- A aba de combinação de regras passou a ordenar visualmente o fluxo como filtro, variáveis X/Y e matriz.
- A matriz agora exibe volume percentual e taxa do evento dentro das células, além da paleta de cores por taxa, com fonte menor e separação visual entre células.
- A matriz aceita filtros dinâmicos do público elegível por botão `Adicionar filtro`.
- A lista de variáveis da matriz inclui variáveis explicativas/predicados presentes no snapshot, inclusive dicotômicas como `x1..x8`, e exclui outcomes, performance, decisão e metadados operacionais.
- A lista de variáveis da matriz passa a ser governada por `snapshot.analysis_feature_columns` no manifesto do estudo.
- A taxa exibida na matriz passa a consultar `snapshot.performance_columns.matrix_event`, evitando dependência de nomes como `y`.
- Labels de eixo da matriz removem `.00` quando o valor é inteiro.
- A aba `Criacao de regras` passou a usar `lasso-select` como modo padrão de seleção múltipla, mantendo clique simples para seleção ou remoção individual.
- A matriz criada pode gerar prévia de resultados antes do salvamento da regra.
- Regras criadas pela matriz passam a ser persistidas em `created_rules.json`, com `source_type="matrix_composition"`, filtros elegíveis, células selecionadas, decisão, autor, versão e carimbo temporal.
- As regras criadas registram também `axis_specs`, de modo que futuras edições reutilizem exatamente as mesmas faixas da criação original.
- Regras multicategoria registram também `rules`, `cell_decisions` e `decision_order`, preservando a atribuição de uma decisão por célula.
- Ao editar uma regra criada, o app abre um alerta para o usuário decidir se quer ou não restaurar o contexto salvo de meses e segmento.
- Se o usuário restaurar esse contexto, o `Laboratório Manual` é atualizado para o mesmo escopo e o `pool inicial` volta a refletir esse contexto.
- Se parte das categorias salvas não existir no snapshot atual, o app avisa isso e faz fallback controlado para os filtros atuais.
- A reedição gera a matriz automaticamente e restaura nome, decisão, filtros, variáveis e células já selecionadas.
- Quando a regra foi criada com várias decisões, a reedição restaura também a decisão atribuída a cada célula.
- Se a regra criada pela matriz estiver ativa na política/cenário usada pela última simulação, `Editar na matriz` é bloqueado por alerta para não contaminar o público elegível da própria edição.
- A aba de otimização automática mantém labels nos pontos do gráfico, mas usa um posicionamento guloso inspirado em `ggrepel` para reduzir colisões entre labels.
- A aba de otimização automática passou a operar com base da busca explícita: baseline, última simulação manual ou construir do zero.
- A UI da otimização agora expõe um `ObjectiveSpec` mínimo com objetivo principal, direção, métrica a preservar e tolerância máxima.
- A tabela da otimização ficou mais explicável, com colunas de tipo, composição e Pareto.
- O motor já organiza os candidatos em frentes de Pareto, exibidas como `F1`, `F2` e assim por diante.
- O produto agora consegue transferir uma candidata selecionada da tabela de otimização para o `Laboratório Manual`.
- A transferência preserva a política ativa quando a base da busca foi a última simulação manual e substitui o fluxo somente quando a base foi `Construir do zero`.
- Sugestões transferidas entram na biblioteca como ativos `optimization_transfer`, com chip `O`, tooltip próprio e abertura no `drawer`.
- Os botões de informação `?` nos cards de regra e feature derivada passam a exibir descrição e estrutura técnica: regras mostram decisão, combinação de blocos e predicados; features derivadas mostram expressão, dependências, modo e tipo.
- O `drawer` foi validado pelo usuário para edição baseline e uso do otimizador singular.
- Alterar uma regra baseline no `drawer` não sobrescreve a baseline do estudo; o app cria uma variante governada.
- A variante pode entrar apenas em `Ativos disponíveis` ou substituir a baseline ativa na mesma posição da política candidata.
- Variantes baseline também podem ser reabertas e reeditadas no `drawer`.
- O `drawer` não abre automaticamente ao iniciar o app; ele depende de ação explícita do usuário.
- A biblioteca do `Laboratório Manual` passou a usar drag-and-drop completo para adicionar, remover e reordenar ativos.
- O placeholder visual foi validado pelo usuário, assim como a movimentação real entre `Ativos disponíveis` e `Ativos em uso`.
- A ordem do fluxo agora segue a ordem visual do painel `Ativos em uso`, inclusive quando houver mistura de regras baseline, variantes, ativos de matriz e features derivadas.
- Com isso, os botões de adicionar, remover e mover ordem deixaram de ser necessários nos cards compactos da biblioteca.
- O quadro `Workspaces manuais` foi movido para o topo da interface, ao lado da seleção do estudo, por também impactar `Criação de regras` e `Otimização automática`.
- O app agora permite salvar e recarregar configurações do `Laboratório Manual` em `manual_configs.json`.
- Ao carregar um workspace manual, o app restaura filtros, cutoff, ativos, ordem do fluxo e recalcula automaticamente os resultados da aba manual.
- O salvamento não contamina o `study.json`; a configuração fica em um artefato próprio de workspace analítico.
- Se o usuário salvar novamente a mesma configuração carregada com o mesmo nome, o app atualiza esse workspace.
- Se o usuário salvar com outro nome a partir de uma configuração carregada, o app cria um novo workspace derivado.

Os itens desta rodada foram aprovados pelo usuário e consolidados na documentação. Novos ajustes visuais devem entrar como novas pendências no radar, se aparecerem em validações futuras.

### Persistência de estado validada

- `rule-state-store` guarda regras em uso, regras disponíveis, features selecionadas e features disponíveis.
- `manual-ui-state-store` guarda meses, segmentação, valores de segmentação e controles de ponto de corte.
- `cutoff-override-store` guarda a sugestão de ponto de corte ou corte seco ativo.
- `matrix-filter-count-store` guarda a quantidade de filtros dinâmicos da matriz.
- `matrix-config-store` guarda variáveis de linha/coluna, filtros da matriz e `last_generated_at` quando o usuário clica em `Gerar matriz`.
- `matrix-selection-store` guarda células selecionadas na matriz.
- `custom-rule-store` espelha em sessão o conteúdo persistido em `created_rules.json`.
- `pending-matrix-rule-store` guarda temporariamente uma regra que aguarda confirmação de sobrescrita.
- `pending-matrix-edit-store` guarda temporariamente o pedido de edição de uma regra criada, até o usuário confirmar no alerta de restauração de contexto.
- `matrix-editing-rule-store` guarda o contexto mínimo da regra que está sendo reaberta para edição.
- `last-simulation-store` guarda a última simulação manual, incluindo filtros, estado de regras, política candidata e resultados.
- `manual-config-store` espelha em sessão o conteúdo persistido em `manual_configs.json`.
- `manual-config-current-store` guarda a configuração manual atualmente carregada.
- O quadro `Baseline e filtros` recalcula as métricas baseline sobre o público filtrado por mês e segmento.
- A validação do usuário confirmou o comportamento da baseline filtrada, da persistência da última matriz gerada, da persistência dos resultados da otimização e dos tooltips de informação.

Essa persistência de sessão continua existindo, mas agora convive com uma persistência governada de workspaces manuais em arquivo próprio do estudo.

### Regra estruturada vs feature derivada na biblioteca

- Regras baseline são `DecisionRuleDefinition`; por isso já abrem seus blocos, predicados, operadores e thresholds editáveis quando aplicável.
- Features derivadas são `DerivedFeatureDefinition`; hoje entram como ativo reutilizável simples e podem ser inspecionadas no `drawer`, mas ainda sem edição profunda.
- Quando uma feature derivada é selecionada hoje, o produto ainda não decide se ela virou uma regra independente, um bloco dentro de outra regra ou apenas um predicado auxiliar editável.
- Ativos criados na matriz continuam fora do `drawer`; sua trilha principal de edição é `Editar na matriz`.
- Essa mecânica foi registrada em `docs/proposals_radar.md` para desenho futuro, porque envolve governança de criação de regra, lineage, variantes e UX de edição.

### Como adicionar e reordenar regras hoje

- adicionar regra:
  - arrastar o card do painel `Ativos disponíveis` para o painel `Ativos em uso`
- remover regra:
  - arrastar o card do painel `Ativos em uso` de volta para `Ativos disponíveis`
- reordenar regra:
  - arrastar o card dentro do próprio painel `Ativos em uso`
- drag-and-drop:
  - já foi implementado e validado pelo usuário
  - governa inclusão, remoção e ordem de execução no mesmo fluxo visual

### Encontrar ponto de corte

1. o usuário abre uma regra baseline no `drawer`
2. escolhe o predicado numérico alvo dentro da própria regra
3. informa `Meta de aprovacao`, `Meta de risco` ou `Corte seco`
4. o app busca um cutoff unidimensional no pool de ancoragem daquele predicado
5. a sugestão é apresentada sem substituir automaticamente a regra

### Otimização automática

1. o usuário escolhe a estratégia
2. escolhe a base da busca e o objetivo estruturado mínimo
3. opcionalmente descreve o objetivo em linguagem natural
4. o buscador gera candidatas
5. a engine executa, ranqueia e organiza por Pareto
6. o app mostra a lista recomendada

### Transferir sugestão otimizada

1. o usuário roda a otimização
2. seleciona uma candidata na tabela
3. clica em `Transferir para o Laboratorio Manual`
4. o app cria ativos governados a partir da sugestão
5. a aba muda para `Laboratório Manual`
6. o cenário é reaplicado e simulado automaticamente

### Regra de governança da transferência

- se a base da busca foi `Ultima simulacao manual`, o app preserva a política que já estava ativa e transfere apenas o delta possível
- se a base da busca foi `Construir do zero`, o app substitui os ativos em uso pela sugestão transferida
- alterações em regras baseline viram variantes baseline
- regras ou pacotes novos viram ativos `optimization_transfer` com chip `O`
- ativos transferidos podem ser reabertos no `drawer`

### `recommendation-figure`

- o gráfico mostra a fronteira de candidatos:
  - eixo x: aprovação
  - eixo y: índice de lucro esperado
- o ponto baseline entra como referência fixa
- as candidatas entram como pontos comparáveis
- a cor representa o desempenho composto usado para ordenação automática
- os labels dos pontos são mantidos no gráfico com pequenos deslocamentos para reduzir colisões visuais

### `optimization-objective`

- no estado atual, o campo ainda não traduz automaticamente o texto em restrições estruturadas
- ele registra o objetivo analítico do estudo
- a evolução proposta para interpretação estruturada está registrada em `docs/proposals_radar.md`

### `ObjectiveSpec` e Pareto

- a otimização já usa um objetivo estruturado mínimo no backend e na UI
- o usuário escolhe:
  - objetivo principal
  - direção
  - métrica a preservar
  - tolerância máxima
- a ordenação final combina:
  - guardrails de efetividade
  - desempenho composto
  - frente de Pareto
- `F1` representa candidatos não dominados
- `F2` representa a segunda frente de candidatos

### IA generativa local/offline no produto

- é tecnicamente possível avaliar um componente de IA generativa local ou auto-hospedado para:
  - interpretar objetivos escritos em linguagem natural
  - transformar objetivos em restrições estruturadas
  - auxiliar manutenção e diagnóstico dentro do produto
  - oferecer um bot offline de suporte ao cliente
- recomendação arquitetural:
  - tratar IA como módulo opcional, não como dependência obrigatória do núcleo
  - manter camada de validação humana antes de qualquer restrição afetar a otimização
  - não permitir que o bot exponha código-fonte sensível
  - registrar prompts, respostas, versão do modelo e decisões aceitas
  - preservar fallback totalmente determinístico sem IA
- riscos a avaliar antes de implementar:
  - peso de instalação
  - consumo de memória e CPU/GPU
  - latência em máquinas do cliente
  - qualidade da interpretação em português e em linguagem de negócio
  - governança de privacidade e auditoria

## Sobre o arquivo de código exibido no notebook

O erro que você viu vinha do caminho relativo assumido no notebook. O código de exemplo agora precisa localizar a raiz do projeto antes de abrir arquivos, porque o notebook fica dentro de `docs/notebooks/`.

## Próximas evoluções recomendadas

1. avaliar e implementar estratégias avançadas de busca, como bayesiana, genética e simulated annealing
2. evoluir o interpretador do objetivo em linguagem natural para preencher melhor o contrato estruturado
3. implementar exportadores por engine de destino
4. evoluir manifesto com mapeamento de decisões e métricas configuráveis por estudo
