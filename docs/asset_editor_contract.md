# Contrato Funcional do Editor de Ativos

Este documento registra o desenho funcional da evolucao `desenhar a mecanica entre features derivadas, regras novas e regras compostas antes de abrir edicao profunda desses ativos`.

O objetivo e alinhar UX, governanca e calculo antes de aprofundar a refatoracao da interface e da logica analitica.

## 1. Unidade principal de edicao

A unidade principal da biblioteca deixa de ser "o card expandido com todos os campos visiveis" e passa a ser "o ativo editavel".

Um ativo editavel pode ser:

- regra baseline
- regra nova criada manualmente
- regra criada por matriz
- regra composta
- feature derivada

Consequencia de UX:

- o card da biblioteca deve ser enxuto
- a edicao detalhada deve acontecer fora do card
- o editor detalhado passa a ser concentrado em um `drawer`

## 2. Tipos de ativo e comportamento esperado

### 2.1 Regra baseline

- continua sendo uma `DecisionRuleDefinition`
- pode ser inspecionada e editada em profundidade
- thresholds numericos sao editados no editor do ativo
- alteracoes em regra baseline precisam respeitar governanca de variante em etapa posterior

### 2.2 Feature derivada

- continua sendo uma `DerivedFeatureDefinition`
- nao embute decisao de politica
- no estado atual pode funcionar como ativo reutilizavel simples
- no futuro pode ser promovida a predicado ou regra, mas essa promocao deve ser explicita e governada

### 2.3 Regra criada por matriz

- nasce como ativo governado persistido em `created_rules.json`
- pode representar uma regra simples ou uma composicao multicategoria
- sua edicao profunda continua acontecendo pela propria aba `Criacao de regras`
- quando for aberta para edicao, o contexto salvo precisa ser restaurado ou explicitamente rejeitado pelo usuario

### 2.4 Regra composta

- por enquanto e um conceito funcional, nao um novo tipo de objeto de dominio
- pode ser representada por uma ou mais `DecisionRuleDefinition`
- o editor deve deixar claro quais blocos, predicados e decisoes compoem o ativo

## 3. Biblioteca de regras

Diretriz de interface:

- dois paineis lado a lado: `Ativos em uso` e `Ativos disponiveis`
- cada painel deve ter sua propria barra de rolagem
- o painel `Ativos em uso` define ordem operacional
- o painel `Ativos disponiveis` prioriza descoberta e reaproveitamento

Diretriz de conteudo:

- cards devem ser curtos
- nomes longos podem quebrar linha
- texto explicativo detalhado sai do card
- acoes devem usar icones e `title`/tooltip quando possivel

## 4. Drawer como editor unico de ativos

O `drawer` passa a ser o ponto principal de inspecao e edicao detalhada.

Ele deve suportar, conforme o tipo do ativo:

- resumo do ativo
- descricao
- predicados e blocos
- thresholds editaveis
- secoes de governanca e lineage
- acoes contextuais

### 4.1 Conteudo esperado por tipo

#### Regra baseline

- nome
- descricao
- decisao
- blocos e predicados
- edicao de thresholds numericos
- secao de otimizacao singular dentro do proprio `drawer`

#### Feature derivada

- nome
- descricao
- expressao
- dependencias
- modo `VIRTUAL` ou `MATERIALIZED`
- explicacao de como ela entra hoje na politica/cenario

#### Regra criada por matriz

- continua com inspecao principal pela propria biblioteca
- sua edicao profunda acontece na aba `Criacao de regras`
- a acao operacional relevante permanece `Editar na matriz`
- o produto nao precisa abrir esse ativo em inspecao detalhada no `drawer` nesta fase

## 5. Otimizacao singular de ponto de corte

### 5.1 Regra de governanca

O produto nao deve otimizar "uma variavel solta".

Ele deve otimizar um **predicado-alvo**.

Exemplos corretos:

- `score1 > 340` dentro da regra `Approve resilient applicants`
- `indicador_potencial1 > 18` dentro da mesma regra

Exemplos incorretos:

- "otimizar score1" sem indicar em que predicado ou regra

### 5.2 Pool de ancoragem

Para evitar vies, a busca de cutoff deve usar um **pool de ancoragem**:

1. identificar o predicado-alvo
2. identificar a regra hospedeira desse predicado
3. congelar o publico elegivel imediatamente antes da regra hospedeira
4. gerar candidatos de cutoff nesse pool ancorado
5. reexecutar a politica completa para medir o efeito final de cada candidato

### 5.3 Situacao da implementacao

Nesta primeira fase:

- o alvo continua sendo identificado por handle de predicado
- o pool de ancoragem passa a ser calculado antes da regra hospedeira do predicado
- a geracao de candidatos usa esse pool ancorado
- a avaliacao de desempenho continua sendo feita pela execucao completa da politica

Evolucao futura:

- suportar ancoragem ainda mais fina quando a estrutura do ativo exigir granularidade abaixo do nivel da regra

## 6. Relacao entre matriz e analise justa

A mesma preocupacao analitica usada na edicao de regra criada pela matriz tambem se aplica a otimizacao singular:

- o publico elegivel nunca pode ser tratado como neutro quando a propria estrutura da politica ja o alterou
- o sistema precisa deixar claro qual publico esta servindo de base para a sugestao
- a otimizacao nao deve se autojustificar com base em um publico enviesado pelo proprio alvo

## 7. Fatiamento recomendado da implementacao

### Fase 1

- registrar este contrato funcional
- introduzir helpers backend para identificacao do predicado-alvo
- introduzir pool de ancoragem na busca singular
- preparar a biblioteca para migracao de cards expandidos para cards enxutos

### Fase 2

- introduzir `drawer` para regra baseline e feature derivada
- retirar a edicao detalhada de dentro dos cards
- manter a edicao de matriz pela aba `Criacao de regras`

### Fase 3

- migrar o otimizador singular do painel global para o contexto do predicado no `drawer`
- adicionar guardrails e alertas contextuais

### Fase 4

- unificar de forma mais completa regras novas, regras compostas e features derivadas no editor
- conectar essa governanca ao futuro drag-and-drop

## 8. Premissas consolidadas

- nao havera multiplas decisoes na mesma celula da matriz
- drag-and-drop sera tratado em evolucao separada da aba `Laboratorio Manual`
- features derivadas e regras continuam sendo conceitos distintos e complementares
- a ordem de execucao continua sendo parte central da interpretacao do estudo

## 9. Estado atual implementado

Nesta rodada, o produto passou a operar assim:

- a biblioteca usa cards compactos para regras baseline, features derivadas e ativos criados na matriz
- a regra baseline abre no `drawer` e concentra a edicao de thresholds numericos
- a feature derivada abre no `drawer` apenas para inspecao
- o ativo criado por matriz nao depende do `drawer`; sua trilha principal continua sendo `Editar na matriz`
- o predicado-alvo do corte singular e escolhido dentro da propria regra baseline aberta no editor
- os controles de `Meta de aprovacao`, `Meta de risco` e `Corte seco` foram deslocados para o `drawer`
- a lateral do `Laboratorio Manual` ficou com um resumo do predicado-alvo selecionado, sugestao ativa e botoes de simulacao/exportacao

## 10. Evolucao consolidada: editor governado de baseline

O ciclo `implementar editor governado de regra, com criacao de variante quando regra baseline for alterada` foi concluido e validado.

Estado consolidado:

- regra baseline continua sendo a referencia imutavel do estudo
- alterar uma baseline no `drawer` nao sobrescreve a regra original
- o salvamento gera um novo ativo governado com `source_type="baseline_rule_variant"`
- a variante pode:
  - ficar apenas em `Ativos disponiveis`
  - substituir a baseline ativa na politica candidata atual
- quando a substituicao e escolhida, a variante ocupa a mesma posicao operacional da baseline original
- a simulacao manual, a exportacao e a matriz deixam de depender implicitamente de rascunhos nao salvos do editor
- variantes baseline podem ser reabertas e reeditadas no proprio `drawer`
- ativos criados na matriz continuam fora do `drawer`; sua trilha de edicao profunda segue em `Editar na matriz`

Metadados governados da variante:

- `rule_id`
- `rule_name`
- `source_type="baseline_rule_variant"`
- `origin_rule_id`
- `origin_rule_name`
- `origin_policy_name`
- `version`
- `author`
- `created_at`
- `updated_at`

Diretriz conceitual consolidada:

- papel do ativo e modo de edicao permanecem conceitos separados
- uma regra pode ser `baseline` no estudo atual e, ainda assim, precisar de uma trilha de edicao diferente no futuro se sua origem for matricial
- por isso, baseline simples segue no `drawer`, enquanto baseline promovida a partir de matriz deve continuar sendo redirecionada para a propria matriz quando chegarmos nessa evolucao
