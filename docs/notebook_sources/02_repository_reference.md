# Repositório e Referência Técnica

Este notebook é a referência detalhada da base atual do produto. A ideia aqui é explicar não só "o que o arquivo faz", mas também "por que ele existe", "como entra no fluxo" e "onde ele deve evoluir".

## Convenção de leitura

- Objetivo: por que o arquivo existe.
- Uso: como ele participa do fluxo do produto.
- Entradas e parâmetros: contratos e suposições relevantes.
- Saídas: artefatos, objetos ou efeitos persistidos.
- Exemplo: mini caso ilustrativo.
- Evolução sugerida: próximos passos coerentes com os documentos anexados.

## Exemplo base usado em vários pontos

Usaremos este payload simplificado para ilustrar adapters, parser, builder, executor e resolver:

```python
python_policy_payload = {
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
                    ],
                },
            ],
        }
    ],
}
```

## Arquivos raiz

### `pyproject.toml`

- Objetivo: definir empacotamento, dependências e comando de entrada do app.
- Uso: instalação do projeto em modo editável e exposição do script `policy-lab-dashboard`.
- Entradas relevantes:
  - `project.dependencies`
  - `project.scripts`
- Estado atual:
  - o arquivo já foi atualizado para separar perfis de dependência:
    - base: `polars`, `duckdb`
    - `ui`: `dash`, `plotly`
    - `dev`: `pytest`, `ruff`, `mypy`, `black`
    - `docs`: `ipykernel`, `nbformat`
  - também já existem configurações básicas de lint, typing e formatação
- O que são essas ferramentas:
  - `black`: formatador automático de código Python; reduz discussões de estilo e deixa o código visualmente padronizado
  - `ruff`: ferramenta rápida de lint; identifica imports não usados, padrões arriscados, erros simples e inconsistências de estilo
  - `mypy`: verificador estático de tipos; ajuda a encontrar incompatibilidades de tipo antes da execução
- Por que `dash` e `plotly` estão em um perfil separado:
  - comercialmente, o Decision Policy Lab deve ser entregue com a interface web como parte do produto
  - tecnicamente, o núcleo analítico do DPL deve continuar podendo rodar sem abrir a interface web, por exemplo em testes, jobs de validação, rotinas de CI ou execuções headless
  - por isso, `dash` e `plotly` ficam no perfil técnico `ui`, separado do núcleo analítico, mas o packaging comercial/hardening deve instalar esse perfil por padrão
  - a separação reduz acoplamento arquitetural; não significa que a interface web esteja fora do entregável final

### `README.md`

- Objetivo: onboarding do projeto.
- Uso: visão rápida do produto e quickstart.

## `policy_lab/config.py`

- Objetivo: centralizar caminhos institucionais do projeto.
- Função principal: `get_settings()`
- Saída:
  - `project_root`
  - `runtime_root`
  - `studies_root`
- Uso:
  - repositórios localizam os estudos sem hardcode espalhado

## `policy_lab/domain/models.py`

### `FeatureMode`

- Objetivo: dizer como uma feature derivada é disponibilizada dentro do estudo.
- Valores:
  - `VIRTUAL`: a feature não é gravada como coluna física no snapshot do estudo; sua expressão é reavaliada sob demanda.
  - `MATERIALIZED`: a feature é persistida como coluna ou ativo materializado do workspace do estudo.
- Para que é usado:
  - orientar a estratégia de reuso e custo computacional no `FeatureResolver`
  - documentar se uma feature precisa ser recalculada ou apenas lida
- Critério sugerido de classificação:
  1. começar com `VIRTUAL` como default
  2. medir ou estimar custo de recalculo quando a feature começar a ser usada de forma recorrente
  3. avaliar se a expressão exige join com tabela auxiliar, enriquecimento persistido ou transformação custosa
  4. promover para `MATERIALIZED` quando o custo ou a dependência justificar persistência
- Exemplo:
  - `risk_buffer_flag = (debt_ratio > 0.62) | (z1 == 1)` pode ser `VIRTUAL` porque é simples.
  - uma regra criada na aba de combinação que dependa de uma tabela auxiliar de faixas, matriz ou lookup pode virar `MATERIALIZED` se o produto precisar persistir o resultado para reuso.
- Observação sobre dados externos:
  - como o DPL trabalha sobre snapshot congelado, enriquecimentos externos devem, em regra, já ter sido incorporados ao snapshot antes do estudo
  - portanto, `MATERIALIZED` no contexto do produto não significa buscar dado externo em tempo real; significa persistir um artefato derivado dentro do workspace do estudo
- Estado atual:
  - ainda não existe medidor automático de custo
  - a regra operacional proposta para o MVP é usar `VIRTUAL` por padrão e promover para `MATERIALIZED` quando houver join auxiliar, cálculo caro ou reuso frequente

### `PolicyFamily`

- Como defini:
  - uma família de política é um agrupamento lógico de versões históricas e candidatas do mesmo propósito decisório.
- Exemplo:
  - "Retail Lending Eligibility" é uma família.
  - dentro dela podem existir:
    - baseline `v1.5`
    - candidata manual `manual-20260410`
    - candidata otimizada `opt-run-07`
- Por que isso importa:
  - evita tratar cada versão como se fosse uma política completamente desconectada
  - ajuda a comparar evolução ao longo do tempo sem perder o vínculo com o objetivo de negócio
- Evolução importante no radar:
  - a mesma família pode ter vários estudos em snapshots diferentes ao longo do tempo, mantendo inclusive a mesma baseline em produção
  - por isso, foi colocado no radar o reuso opcional de políticas candidatas e features derivadas entre estudos da mesma família, com validação de compatibilidade e `lineage cross-study`

### `DerivedFeatureDefinition`

- O conceito aparece, sim, nos documentos anexados:
  - o prompt fala explicitamente em "Derived feature catalog"
  - também detalha os modos virtual e materializado
  - e descreve reuso entre cenários dentro do mesmo estudo
- Fluxo de entrada e saída do catálogo:
  1. o estudo já nasce com um catálogo inicial vindo do manifesto ou de `derived_features.json`
  2. o usuário ou processo de busca referencia uma `feature_id`
  3. o `FeatureResolver` resolve dependências e calcula a coluna quando necessário
  4. a feature pode ser reaproveitada em outros cenários do mesmo estudo
- Observação importante:
  - hoje o catálogo é ligado ao estudo, não à família de política
  - portanto, o reuso entre estudos ainda não é automático
  - esse tema ficou explicitamente no radar de evolução
- Informações registradas hoje:
  - `feature_id`
  - `name`
  - `expression`
  - `dependencies`
  - `data_type`
  - `mode`
  - `description`
- Como a feature derivada é criada hoje:
  - no estado atual do produto, a criação é declarativa e governada por arquivo
  - ela pode nascer em `study.json` ou, mais tipicamente, em `runtime/studies/<study_id>/derived_features.json`
  - o DPL ainda não possui uma UI própria para autoria de `DerivedFeatureDefinition`
  - depois de cadastrada, a feature é resolvida pelo `FeatureResolver` e pode virar coluna virtual do snapshot durante a execução
- Implicação importante:
  - a aba de matriz não cria feature derivada; ela usa features derivadas existentes como insumo opcional e salva o resultado como regra
- Exemplo:

```python
{
    "feature_id": "risk-buffer-flag",
    "name": "risk_buffer_flag",
    "expression": "(recent_income_stability < 0.38) | (debt_ratio > 0.62)",
    "dependencies": ["recent_income_stability", "debt_ratio"],
    "data_type": "bool",
    "mode": "virtual",
    "description": "Reusable veto for unstable or high-risk applications."
}
```

### `PredicateDefinition`

- Conceito:
  - é o átomo lógico da regra, isto é, a menor unidade avaliável de condição.
- Exemplo:
  - `score1 > 340`
  - `segment in ["prime", "standard"]`
- Cada `PredicateDefinition` tem:
  - `field`
  - `operator`
  - `value`
  - `description`

### `RuleBlockDefinition`

- Conceito:
  - grupo de predicados combinados por uma lógica comum (`all` ou `any`).
- Exemplo:
  - bloco `Resilient thresholds`
    - `score1 > 340`
    - `indicador_potencial1 > 18`
    - `w1 < 9`
  - como o bloco é `all`, todos precisam ser verdadeiros
- Exemplo alternativo:
  - bloco `Resilient signals`
    - `x1 == 0`
    - `x2 == 0`
  - se o bloco for `any`, basta um deles

### `DecisionRuleDefinition`

- Conceito:
  - regra que, quando satisfeita, produz uma decisão (`approve`, `reject`, `review` etc.).
- Sim, as duas regras baseline do estudo atual entram nesta classe.
- Hierarquia correta:
  - `DecisionRuleDefinition`: a regra inteira
  - `RuleBlockDefinition`: cada bloco dentro da regra
  - `PredicateDefinition`: cada condição individual

### `PolicyDefinition`

- Política estruturada:
  - é a representação normalizada da política em formato interno do produto
  - ela é "estruturada" porque não está como texto solto; está decomposta em regras, blocos, predicados, decisão default e metadados
- Política vigente ou baseline:
  - é a versão que representa a política realmente usada como referência histórica naquele estudo
- Política candidata:
  - é qualquer variação estudada no laboratório, manual ou automática
- Diferença prática:
  - toda baseline e toda candidata são políticas estruturadas
  - "estruturada" é a forma
  - "baseline" e "candidata" são papéis no estudo
- Como uma candidata passa a ser uma política estruturada:
  - na prática, ela já é estruturada quando é convertida para `PolicyDefinition`
  - o que muda depois é seu papel de governança: ela pode ser promovida a baseline de um estudo futuro

### `StudyManifest` e `StudyContext`

- O que inicia um estudo:
  - um snapshot congelado
  - uma baseline definida
  - metadados mínimos de escopo
- Na prática operacional:
  - esses metadados mínimos devem acompanhar o snapshot
  - no produto atual, isso é representado por `study.json`
  - o contrato desse arquivo está documentado em `docs/study_manifest_contract.md`
- Como o `study.json` deve ser criado:
  - no MVP atual, ele é criado como artefato do estudo demo ou preparado manualmente
  - em operação real, não devemos exigir que o cliente edite JSON manualmente como fluxo principal
  - evolução recomendada: criar um hall de entrada do estudo no webapp para ler o cabeçalho do snapshot, selecionar família de política, preencher metadados sensíveis, validar schema e gerar a pasta do estudo com `study.json`
  - esse hall também pode validar importação de políticas/cenários e features derivadas de estudos anteriores da mesma família
- O que encerra um estudo:
  - atualmente não existe flag formal de encerramento no código
  - conceitualmente, o estudo encerra quando aquele snapshot deixa de ser o recorte analítico ativo e os cenários deixam de ser produzidos naquele contexto
- Quantidade de cenários:
  - hoje não há limite técnico explícito no código
  - na prática, o limite é operacional: armazenamento, organização e governança
- Como cenários são manuseados entre estudos:
  - hoje ficam isolados por pasta do estudo
  - não existe ainda promoção automática de cenário entre estudos
  - proposta coerente para evoluir:
    - permitir clonar uma candidata de um estudo antigo como baseline inicial de um novo estudo
    - manter lineage cross-study
- `lineage cross-study`:
  - é a trilha que liga um ativo criado em um estudo a seu reaproveitamento, promoção ou comparação em outro estudo
  - exemplo:
    - uma candidata nasce em `eligibility_2026Q1`
    - depois é importada para `eligibility_2026Q2`
    - o produto registra origem, destino e validação de compatibilidade

### `ScenarioMetrics`

- Papel:
  - encapsular as métricas agregadas de um cenário.
- Ponto importante:
  - algumas métricas podem não existir no snapshot de um estudo.
- Isso está sendo considerado?
  - agora sim de forma parcial no código:
    - métricas como `expected_profit`, `risk_estimate`, `churn_estimate` e `out_of_support_ratio` podem ser `None`
  - isso diferencia "não aplicável/não disponível" de zero real
- Convenção recomendada de linguagem:
  - usar `política/cenário` quando o foco for o ativo avaliado no laboratório
  - usar `política` quando o foco for a estrutura de regra
  - usar `cenário` quando o foco for a execução dessa política dentro do estudo
- Como a ausência é identificada:
  - o manifesto declara os papeis em `snapshot.performance_columns`
  - o `ImpactEstimator` consulta esses papeis, como `profit`, `risk_event` e `churn`
  - se o papel não estiver declarado ou a coluna declarada não existir, a métrica correspondente vira `None`
  - além disso, o `StudyRepository` agora valida o schema declarado no manifesto ao carregar o snapshot
- Próxima evolução recomendada:
  - trocar a estrutura fixa por um registro de métricas configurável por estudo
  - manter um núcleo mínimo padronizado e um conjunto extensível

## `policy_lab/adapters/base/adapter.py`

- Objetivo:
  - definir o protocolo mínimo de qualquer adapter de política.
- Protocolo:

```python
class PolicyAdapter(Protocol):
    adapter_name: str
    def normalize(self, source: dict[str, Any]) -> PolicyDefinition:
        ...
```

- Exemplo conceitual dos adapters futuros:
  - `blaze`: recebe artefato exportado do Blaze e mapeia para `PolicyDefinition`
  - `fico`: converte uma policy set ou tabela equivalente para a estrutura interna
  - `drools`: interpreta DRL ou estrutura intermediária e normaliza
  - `sql`: converte regras SQL para predicados e blocos
  - `decision_table`: mapeia linhas/colunas de tabela de decisão
  - `proprietary`: template para motores internos do cliente
- Exemplos de "antes e depois":
  - Drools:

```text
rule "ApproveResilient"
when
    Application(score1 > 340, indicador_potencial1 > 18.0, w1 < 9)
then
    modify($application) { setDecision("approve") }
end
```

  - SQL:

```sql
CASE
  WHEN score1 > 340
   AND indicador_potencial1 > 18.0
   AND w1 < 9
  THEN 'approve'
  ELSE 'reject'
END AS simulated_decision
```

  - FICO / Blaze:
    - o material público oficial encontrado aponta fortemente para modelagem visual e governança de lógica, mas não expõe uma gramática textual estável equivalente ao DRL
    - por isso, exemplos textuais de FICO/Blaze devem ser tratados como representativos, não autoritativos

## `policy_lab/adapters/python/adapter.py`

- Objetivo:
  - adapter demonstrativo para payloads já estruturados em JSON/Python.
- Exemplo de uso:

```python
adapter = PythonPolicyAdapter()
policy = adapter.normalize(python_policy_payload)
```

- Esse é o formato mais simples porque o payload já está muito próximo da estrutura interna.

## `policy_lab/engine/policy_parser/service.py`

### `PolicyParser`

- Papel:
  - escolher o adapter correto e normalizar o payload de entrada.
- Está preparado para identificar protocolos sozinho?
  - não
  - hoje ele precisa que o adapter seja registrado e o `adapter_name` seja informado
  - detecção automática de formato é uma evolução futura
- Leitura operacional correta:
  - o adapter é o artefato registrado que permite ao `PolicyParser` traduzir um protocolo externo para o formato interno compreendido pelo `PolicyBuilder` e pelo produto
- Evolução recomendada:
  - criar um hall de registro de adapters, semelhante ao hall de criação de estudos
  - esse fluxo ajudaria o usuário a cadastrar origem, tipo de motor, arquivo de exemplo, adapter associado, versão e validações de normalização
  - quanto mais complexo for o motor do cliente, mais importante será reduzir o esforço manual de transcrição para `PolicyDefinition`
- Exemplo:

```python
parser = PolicyParser()
policy = parser.parse(python_policy_payload, adapter_name="python")
```

### `PolicyBuilder`

- Função:
  - utilitário para clonar e transformar políticas já normalizadas.
- Mutações hoje suportadas:
  - override de thresholds
  - inclusão de regra derivada de veto
- O que significa "mutação" aqui:
  - não é mutação da política em produção
  - é mutação de uma cópia analítica da política para construir candidatas dentro do estudo
- Exemplo de override:

```python
handle = PolicyBuilder.predicate_handle(0, 0, 0, policy.rules[0].blocks[0].predicates[0])
candidate = PolicyBuilder.apply_threshold_overrides(policy, {handle: 360})
```

- Situação de uso de override:
  - estudo contrafactual
  - sugestão de ponto de corte
  - busca automática

### `apply_threshold_overrides()`

- O que faz:
  - percorre a política clonada e troca apenas os valores cujos handles estão no dicionário de overrides.
- Exemplo:
  - baseline: `score1 > 340`
  - candidata: `score1 > 360`

### `add_reject_rule_from_feature()`

- O que faz:
  - cria uma nova regra no topo da política que rejeita a proposta quando uma feature derivada booleana é verdadeira.
- Conceito de veto derivado simples:
  - uma regra sintética do tipo "se a feature derivada disparar, rejeita"
  - simples porque:
    - usa uma única feature derivada booleana
    - gera apenas uma decisão de veto
    - entra antes das demais regras
- Exemplo:

```python
candidate = PolicyBuilder.add_reject_rule_from_feature(policy, risk_buffer_feature)
```

## `policy_lab/engine/feature_resolution/service.py`

### `resolve()`

- Papel:
  - resolver features derivadas pedidas por um cenário.
- Exemplo:

```python
resolved = resolver.resolve(frame, feature_catalog, ["risk-buffer-flag"])
```

### `_ordered_features()` e `visit()`

- Papel:
  - ordenar features respeitando dependências.
- Exemplo:
  - `feature_c` depende de `feature_b`
  - `feature_b` depende de `feature_a`
  - a ordem correta precisa ser `a -> b -> c`

### `_compile_expression()`

- Papel:
  - transformar a expressão registrada em uma `pl.Expr`.
- Exemplo:

```python
expression = "(debt_ratio > 0.62) | (z1 == 1)"
compiled = resolver._compile_expression(expression, frame.columns)
```

## `policy_lab/engine/policy_executor/service.py`

- Quantas decisões ele suporta hoje?
  - tecnicamente quantas forem necessárias como labels finais
  - mas o cálculo agregado do MVP foi desenhado pensando em `approve`, `review`, `reject`
- Limite de complexidade atual:
  - suporta regras compostas por blocos `all/any` e predicados simples
  - não suporta árvores arbitrárias, precedência aninhada profunda, short-circuit complexo por segmento, ou grafos decisórios com desvio explícito
- Exemplo de execução:

```python
executed = executor.execute(frame, policy)
```

- Como ler as funções:
  - `_predicate_expression`: traduz um predicado para expressão Polars
  - `_block_expression`: combina predicados de um bloco
  - `_rule_expression`: combina blocos de uma regra
  - `_combine`: aplica `AND` ou `OR`

## `policy_lab/engine/optimizer/service.py`

- O módulo deixou de ser só um MVP de threshold e passou a concentrar a geração desacoplada do espaço de busca.
- Hoje o otimizador já gera:
  - `threshold_override`
  - `threshold_pair`
  - `simple_rule_candidate`
  - `grouped_rule_candidate`
  - `layered_rule_candidate`
  - `composite_rule_candidate`
  - `derived_veto`
  - `signal_bundle_candidate`
  - `guarded_rule_candidate`
  - `rule_bundle_candidate`
  - `policy_pack_candidate`
  - `mixed_candidate`
- Isso significa que o espaço de busca já não está mais restrito às variáveis presentes na baseline nem a cortes simples em uma única coluna.
- `_candidate_thresholds()`:
  - continua sendo o núcleo dos candidatos numéricos
  - hoje já aceita shifts por variável, grids orientados por domínio, quantis, valores observados e limites inferiores/superiores
- Regras categóricas:
  - o motor já consegue gerar candidatos com igualdade e agrupamento por categoria
  - isso aproximou a otimização do que o usuário montaria manualmente na UI
- `ObjectiveSpec`:
  - já influencia o ranking
  - e também já orienta quais candidatos o gerador tende a priorizar
- Paralelização:
  - a geração continua governada no mesmo processo
  - a avaliação foi separada para permitir paralelismo posterior no orquestrador
- Evoluções futuras já colocadas no radar:
  - busca bayesiana
  - algoritmos genéticos
  - simulated annealing

## `policy_lab/engine/scenario_orchestrator/service.py`

- Renomeação conceitual adotada:
  - em vez de "score", a documentação passa a tratar isso como desempenho composto da otimização
- Funções:
  - `run_baseline()`
  - `run_scenario()`
  - `run_search()`
  - `_evaluate_composite_performance()`
- Estado consolidado:
  - `run_search()` já opera com base da busca explícita
  - a avaliação dos candidatos já foi paralelizada
  - a retenção de memória foi reduzida, evitando guardar frames completos de todos os candidatos
  - os resultados já saem enriquecidos com lineage suficiente para transferência ao `Laboratório Manual`
- O valor final:
  - não substitui as métricas individuais
  - serve como critério sintético de ordenação e ranqueamento
- Pareto:
  - o orquestrador agora calcula frentes de Pareto (`F1`, `F2`, ...)
  - essas frentes complementam o desempenho composto e ajudam a filtrar dominância multicritério
- Multiplicadores atuais:
  - foram definidos heurísticamente para o MVP
  - intenção:
    - risco e extrapolação pesam forte
    - complexidade pesa, mas menos
  - ainda não são calibrados por pesquisa operacional formal

## `policy_lab/analysis/impact_estimator/service.py`

- O código quebra se só algumas colunas existirem?
  - não
  - quando os papeis `profit`, `risk_event` ou `churn` não estão declarados em `snapshot.performance_columns`, ou quando a coluna declarada não existe, o estimador devolve `None` para a métrica correspondente
- O que significa "parametrizar fórmulas por estudo"?
  - permitir que cada estudo declare:
    - qual métrica é lucro
    - qual é evento adverso
    - como churn é calculado
    - quais decisões contam em cada KPI
- Coluna de decisão:
  - a decisão simulada é identificada por `policy.decision_column`
  - a decisão histórica é indicada no manifesto do estudo
  - hoje o impacto assume rótulos `approve`, `review` e `reject`
- Observação importante:
  - `snapshot.historical_decision_column` e `baseline_policy.decision_column` não precisam ser iguais
  - a primeira aponta para o histórico real
  - a segunda para a decisão simulada criada pelo executor
- Evolução recomendada:
  - o manifesto deve poder declarar um mapeamento explícito entre labels reais e classes canônicas de decisão
  - também deve permitir parametrizar nomes de colunas usadas em métricas, como lucro, evento adverso, churn, ticket e outras métricas de performance
  - isso reduz engessamento quando passarmos de demo fictícia para estudos reais
- Sobre equivalência entre decisão histórica e baseline simulada:
  - se o snapshot histórico realmente foi produzido por uma única versão da política baseline declarada no estudo, espera-se alta equivalência entre `snapshot.historical_decision_column` e `baseline_policy.decision_column` após executar a baseline
  - divergências nesse caso podem indicar erro de transcrição da política, diferença de versão, dados faltantes ou regra operacional não representada no DPL
  - se a coluna histórica mistura versões de política ou exceções operacionais, a equivalência perfeita não deve ser assumida

## `policy_lab/analysis/uncertainty_estimator/service.py`

- Objetivo:
  - sinalizar quando a política candidata aprova perfis fora da faixa normalmente observada entre os aprovados históricos
- Entrada:
  - `frame`
  - `policy`
  - `reference_decision_column`
- Saída:
  - `out_of_support_ratio`
  - label `low`, `medium` ou `high`
- Exemplo prático:
  - se os aprovados históricos têm `score1` majoritariamente entre 300 e 760
  - e a candidata aprova muita gente com `score1 < 150`
  - o ratio sobe

## `policy_lab/analysis/complexity_estimator/service.py`

- Fórmula atual:
  - 12 por regra
  - 4 por predicado
  - 9 por feature distinta
- Natureza:
  - heurística de governança do MVP, não fórmula acadêmica calibrada
- Uso:
  - entra no desempenho composto da otimização
  - também pode ser mostrado ao usuário como guardrail explicável

## `policy_lab/storage`

### Estrutura usada hoje

```text
runtime/
  studies/
    demo_lending/
      study.json
      baseline_policy.json
      derived_features.json
      study_snapshot.csv
      scenarios/
        <scenario_id>.json
      results/
        <scenario_id>.json
```

### `StudyRepository`

- `list_studies()`: lista todas as pastas com `study.json`
- `load(study_id)`: carrega manifesto e retorna `StudyContext`
- `load_snapshot(study)`: lê o snapshot em CSV ou Parquet
- Exemplo:

```python
repo = StudyRepository()
studies = repo.list_studies()
study = repo.load("demo_lending")
snapshot = repo.load_snapshot(study)
```

### `FeatureRepository`

- Caminho:
  - `runtime/studies/<study_id>/derived_features.json`

### `CreatedRuleRepository`

- Caminho:
  - `runtime/studies/<study_id>/created_rules.json`
- Papel:
  - persistir regras autoradas durante o estudo, especialmente as criadas na aba de criação de regras
- Informações registradas:
  - `rule_id`
  - `rule_name`
  - `rule`
  - `rules`
  - `source_type`
  - `row_variable`
  - `column_variable`
  - `eligible_filters`
  - `axis_specs`
  - `selected_cells`
  - `decision`
  - `cell_decisions`
  - `decision_order`
  - `version`
  - `author`
  - `created_at`
  - `updated_at`
- Observações de governança:
  - `source_type="matrix_composition"` identifica regras nascidas pela matriz
  - `source_type="baseline_rule_variant"` identifica variantes governadas criadas a partir de regras baseline
  - `source_type="optimization_transfer"` identifica sugestões transferidas da aba de otimização para o `Laboratório Manual`
  - `rule` segue existindo por compatibilidade com regras antigas de decisão única; composições multicategoria usam `rules`
  - `axis_specs` guarda as faixas ou categorias usadas na criação para permitir reedição consistente
  - os limites extremos de snapshots futuros passam a cair na primeira ou na última faixa salva
  - no MVP atual, `author` entra como `local_user` porque ainda não existe autenticação no app
  - variantes baseline registram também `origin_rule_id`, `origin_rule_name` e `origin_policy_name`
  - sugestões transferidas registram também metadados de busca, como estratégia, base da busca, tipo do candidato, objetivo estruturado e snapshot de métricas

### `ScenarioRepository`

- Caminho:
  - `runtime/studies/<study_id>/scenarios/<scenario_id>.json`

### `ResultRepository`

- Caminho:
  - `runtime/studies/<study_id>/results/<scenario_id>.json`

## `policy_lab/apps/simulator_app`

- A interface foi reorientada para priorizar o fluxo descrito no prompt:
  - abas explícitas
  - baseline e filtros na lateral
  - biblioteca de regras com drag-and-drop entre ativos em uso e disponíveis
  - ordem das regras pela própria biblioteca, governada visualmente no painel de ativos em uso
  - sugestão de ponto de corte
  - fluxo de subdecisões
  - comparação tabular
  - exportação JSON
- Atualização mais recente:
  - o bloco `rule-controls` foi removido
  - a edição de thresholds baseline foi deslocada para o `drawer`
  - a biblioteca agora trabalha com dois painéis: ativos em uso e ativos disponíveis
  - regras criadas pela matriz passam a ser persistidas em `created_rules.json`
  - essas regras registram `source_type="matrix_composition"` e metadados suficientes para reabrir a edição
  - a aba foi consolidada como `Criacao de regras`
  - a matriz agora suporta decisão por célula e salva composições multicategoria sem criar um novo tipo de objeto de domínio
  - o otimizador singular de ponto de corte foi deslocado para dentro do `drawer` da regra baseline
  - a biblioteca da aba manual passou a usar drag-and-drop completo para adicionar, remover e reordenar ativos
  - o topo da interface passou a concentrar a seleção de estudo e os workspaces manuais
  - a aba de otimização passou a permitir transferir candidatas para o `Laboratório Manual`
- Modularização inicial:
  - `app.py`: ponto de entrada do Dash; cria o app, registra callbacks e aplica o layout
  - `layout.py`: estrutura visual das abas e containers principais
  - `callbacks.py`: registro declarativo dos callbacks Dash
  - `callback_handlers.py`: funções executadas pelos callbacks
  - `components.py`: componentes reutilizáveis da UI, como cards, biblioteca de regras, métricas e tabelas
  - `figures.py`: construção de gráficos Plotly
  - `services.py`: helpers de estado, filtros, montagem de política candidata e população elegível
  - `runtime.py`: repositórios, orquestrador e serviços compartilhados pela UI
  - `formatting.py`: formatação de percentuais, moeda, números e deltas
- Persistência de estado da sessão:
  - `rule-state-store`: ativos em uso/disponíveis, incluindo regras baseline, variantes, ativos de matriz e features derivadas, com ordem mista governada por `used_asset_ids`
  - `manual-ui-state-store`: filtros manuais e controles de cutoff
  - `cutoff-override-store`: sugestão de cutoff ou corte seco ativo
  - `matrix-config-store`: variáveis, filtros da matriz e timestamp da última geração
  - `matrix-selection-store`: células selecionadas na matriz
  - `pending-matrix-rule-store`: regra aguardando confirmação de sobrescrita
  - `pending-matrix-edit-store`: contexto de edição aguardando decisão do usuário no alerta de restauração
  - `matrix-editing-rule-store`: contexto mínimo da regra reaberta para edição
  - `custom-rule-store`: espelho em sessão das regras persistidas em `created_rules.json`
  - `manual-config-store`: espelho em sessão das configurações persistidas em `manual_configs.json`
  - `manual-config-current-store`: metadados mínimos do workspace manual atualmente carregado
  - `last-simulation-store`: última simulação manual com política candidata e resultados
  - `Baseline e filtros`: métricas recalculadas sobre o público filtrado por mês e segmento
- Persistência governada de workspaces manuais:
  - o arquivo `runtime/studies/<study_id>/manual_configs.json` guarda as configurações salvas da aba manual
  - essa persistência é separada de `study.json`, para não misturar manifesto do estudo com workspace analítico
  - cada configuração pode registrar:
    - `config_id`
    - `name`
    - `workspace_id`
    - `author`
    - `parent_config_id`
    - `created_at`
    - `updated_at`
    - `manual_ui_state`
    - `rule_state`
    - `cutoff_override`
  - ao carregar uma configuração, o app restaura filtros, cutoff, ativos/ordem e recalcula automaticamente os resultados da aba manual
  - se a configuração carregada for salva novamente com o mesmo nome, no mesmo workspace, o app atualiza o próprio artefato
  - se for salva com outro nome a partir de uma configuração carregada, o app cria um novo artefato derivado
- Tooltips da biblioteca:
  - cards de regras mostram descrição, decisão, combinação de blocos e predicados
  - cards de features derivadas mostram descrição, expressão, dependências, modo e tipo
  - isso ajuda a validar rapidamente ativos como `thin_file_watch_flag` sem abrir arquivos JSON
- Biblioteca e drag-and-drop:
  - a biblioteca da aba manual trabalha com dois painéis lado a lado: `Ativos em uso` e `Ativos disponíveis`
  - cada painel possui rolagem própria
  - o drag-and-drop entre os painéis governa adicionar e remover ativos da política candidata
  - o drag-and-drop dentro de `Ativos em uso` governa a ordem de execução
  - a mesma mecânica vale para regras baseline, variantes baseline, ativos criados na matriz e features derivadas
  - variantes baseline continuam respeitando a governança de substituir a regra de origem quando aplicável
- Editor lateral de ativos:
  - regras baseline abrem no `drawer` e concentram a edição de thresholds numéricos
  - salvar uma edição baseline no `drawer` cria uma variante governada, sem sobrescrever a baseline do estudo
  - a variante pode substituir a baseline ativa na mesma posição da política candidata ou permanecer apenas como ativo disponível
  - variantes baseline podem ser reabertas e reeditadas no `drawer`
  - features derivadas abrem no `drawer` apenas para inspeção
  - ativos criados na matriz continuam sendo editados pela ação `Editar na matriz`, sem inspeção obrigatória no `drawer`
  - ativos `optimization_transfer` também podem ser abertos no `drawer` para inspeção, renomeação e edição de predicados numéricos
  - o `drawer` também passou a concentrar o corte singular do predicado-alvo da regra baseline
- Transferência da otimização:
  - a tabela de recomendações permite selecionar uma candidata e transferi-la com um clique
  - quando a base da busca é a última simulação manual, a transferência preserva o fluxo atual e aplica apenas o delta transferível
  - quando a base da busca é `Construir do zero`, a transferência substitui os ativos em uso pela sugestão transferida
  - alterações em baseline viram variantes baseline
  - regras ou pacotes novos viram ativos `optimization_transfer`, identificados por chip `O`
- Criação de regras por matriz:
  - a aba `Criacao de regras` salva regras estruturadas de forma governada em `created_rules.json`
  - o snapshot usado pela matriz é enriquecido com as features derivadas virtuais do catálogo
  - por isso, features como `risk_buffer_flag`, `thin_file_watch_flag` e `blended_quality_flag` podem aparecer como variáveis de linha/coluna e filtros
  - cada célula selecionada vira um `RuleBlockDefinition`
  - os predicados da linha e da coluna formam o bloco com `logical_operator=all`
  - células com a mesma decisão são agrupadas em uma mesma `DecisionRuleDefinition` com `block_combiner=any`
  - uma composição multicategoria gera várias `DecisionRuleDefinition` irmãs, uma por decisão usada
  - a decisão ativa é aplicada por clique simples ou por `lasso-select`, e clicar de novo remove a mesma decisão da célula
  - a matriz usa clique simples para selecionar/remover uma célula e `lasso-select` como modo padrão para seleção em área
  - a regra pode ser avaliada por uma prévia de resultados antes do salvamento
  - a regra salva aparece como ativo disponível na biblioteca do Laboratório Manual
  - se o nome informado já existir entre regras criadas na matriz, o app solicita confirmação antes de sobrescrever
  - ao salvar, o app registra também `eligible_filters`, `selected_cells`, `cell_decisions`, `decision_order` e `axis_specs`
  - `axis_specs` preserva as mesmas faixas da criação original para futuras edições
  - se um novo snapshot trouxer valores acima ou abaixo do range salvo, os extremos são absorvidos pela faixa mais baixa ou mais alta
  - o botão `Editar na matriz` abre um alerta antes de restaurar o contexto salvo
  - esse alerta informa que o público elegível também depende da última simulação e que restaurar o contexto afeta o `pool inicial` do `Laboratório Manual`
  - ao confirmar a restauração, o app realinha filtros, resultados do laboratório, variáveis, células, decisão e nome da regra
  - se o ativo criado pela matriz estiver ativo na política/cenário da última simulação, a edição é bloqueada por alerta para evitar viés no público elegível
- Limite atual entre regras e features:
  - uma regra baseline é uma `DecisionRuleDefinition` e já possui blocos e predicados editáveis na UI
  - uma feature derivada é uma `DerivedFeatureDefinition` e hoje entra como ativo reutilizável simples, com inspeção em `drawer`
  - uma regra criada pela matriz continua sendo executada como `DecisionRuleDefinition`, mesmo quando o ativo salvo representa uma composição multicategoria
  - a transformação governada de feature derivada em regra, bloco ou predicado editável está registrada no radar de evolução
- Status de governança:
  - a modularização foi aplicada sem intenção de alterar comportamento
  - foi validada pelo usuário e considerada concluída como evolução
  - a persistência de estado relevante da UI também foi validada pelo usuário e considerada concluída como evolução
  - o editor governado de baseline com criação de variante também foi validado pelo usuário e considerado concluído como evolução
  - próximos ajustes nessa estrutura entram como hardening ou como novas evoluções específicas da UI
- Ponto ainda em evolução:
  - exportação para formatos nativos do motor do cliente (`drools`, `sql`, `blaze`, `fico`) ainda depende dos adapters de saída

## `policy_lab/storage/manual_config_repository/repository.py`

- Objetivo: persistir e recuperar workspaces manuais salvos por estudo.
- Uso:
  - lido no carregamento do app para popular o seletor de `Workspaces manuais`
  - escrito quando o usuário salva uma configuração do `Laboratório Manual`
- Caminho:
  - `runtime/studies/<study_id>/manual_configs.json`
- Contrato atual:
  - `study_id`
  - `configs`: lista de workspaces manuais
- Exemplo de payload:

```json
{
  "study_id": "demo_lending",
  "configs": [
    {
      "config_id": "workspace-manual",
      "name": "Workspace manual",
      "workspace_id": "default",
      "author": "local_user",
      "parent_config_id": null,
      "created_at": "2026-05-04T00:00:00+00:00",
      "updated_at": "2026-05-04T00:00:00+00:00",
      "manual_ui_state": {
        "study_id": "demo_lending",
        "filters": {
          "months": ["202401", "202402"],
          "segment_field": "segmento_cluster",
          "segment_values": ["A", "B"]
        },
        "cutoff": {
          "objective": "approval",
          "handle": "approve-prime:0:0:score1:>",
          "target_value": 82.0
        }
      },
      "rule_state": {
        "study_id": "demo_lending",
        "used_asset_ids": ["baseline:approve-prime", "custom:variant-approve-prime-2"]
      },
      "cutoff_override": null
    }
  ]
}
```

## `tests/test_policy_lab.py`

- Sim:
  - ele existe para validar o núcleo sem precisar abrir a interface web
  - na prática, o app chama os módulos internamente
  - o teste garante que o núcleo continue íntegro independentemente da UI
