# Fases do Desenvolvimento, Controle e Governança

## O que é hardening

Hardening é a fase de tornar o produto robusto para uso profissional. Não é uma feature específica; é o conjunto de ajustes que reduz fragilidade operacional.

Inclui, por exemplo:

- empacotamento e instalação previsíveis
- validações mais fortes
- observabilidade
- testes de regressão
- segurança de configuração
- documentação operacional

## Fases

### Fase 0 — Fundamentos e contrato

- definir limites do produto
- definir linguagem de domínio
- definir contrato de estudo

### Fase 1 — Núcleo analítico mínimo

- baseline
- cenário manual
- persistência

### Fase 2 — Dataset de desenvolvimento e laboratório manual

- estudo demo robusto
- filtros
- biblioteca de regras
- comparação e exportação

### Fase 3 — Criação e combinação de regras

- matriz exploratória
- criação visual de regras
- persistência de regras novas

### Fase 4 — Otimização automática governada

- objetivos mais ricos
- restrições explícitas
- estratégias mais fortes

### Fase 5 — Hardening e produto profissional

- packaging
- observabilidade
- documentação operacional
- trilhas de auditoria

## Trilhas permanentes de controle

### Mudança estrutural deve atualizar

- código
- markdown de apoio
- notebooks
- estudo demo, se o contrato mudar

### Risco: divergência entre manifesto do estudo e snapshot real

Exemplo:

- o manifesto diz que a coluna histórica se chama `historical_decision`
- mas o snapshot entregue pelo cliente vem com `decision_hist`

Outro exemplo:

- o manifesto diz que `profit_value` existe
- mas o snapshot real não trouxe a coluna

Consequência:

- cálculo incorreto ou silenciosamente incompleto
- leitura errada do estudo

Maneiras de antecipar:

1. validação de schema na carga do estudo
2. validação de tipos
3. validação de colunas obrigatórias por estudo
4. checklist de consistência antes de abrir o estudo na UI

### Risco: desempenho composto mascarar trade-offs reais

Exemplo:

- cenário A:
  - aprovação sobe bastante
  - risco sobe um pouco
  - complexidade sobe muito
- cenário B:
  - aprovação sobe pouco
  - risco cai
  - complexidade fica estável

Se o peso de aprovação estiver alto, o cenário A pode parecer "melhor" no ranking, mesmo que a organização prefira claramente o cenário B por prudência.

Maneiras de antecipar:

1. sempre mostrar métricas individuais ao lado do ranking
2. permitir pesos configuráveis
3. adicionar fronteira de Pareto
4. bloquear recomendações que violem restrições duras

### Risco: UI evoluir sem refletir restrições da engine

Exemplo:

- a UI permite reorder livre
- mas a engine futura exigir que regra com cutoff otimizado fique por último

Mitigação:

- regras de negócio da UI devem ser derivadas das capacidades do núcleo

### Risco: otimização explorar fora do suporte

Mitigação:

- medir `out_of_support_ratio`
- penalizar no desempenho composto
- no futuro, transformar isso também em restrição dura

Status atual:

- essa mitigação já está parcialmente ativa no MVP:
  - o `out_of_support_ratio` já é calculado
  - o desempenho composto já penaliza extrapolação

### Risco: documentação ficar desatualizada

Mitigação:

- gerar notebooks a partir de fontes versionadas
- revisar documentação junto com cada mudança estrutural

Status atual:

- essa mitigação já está ativa:
  - os notebooks são regenerados por script a partir das fontes em `docs/notebook_sources`
  - o fluxo recomendado é editar a fonte e depois executar o refresh

## Validação de contrato do estudo

- como reforço de governança, o carregamento do snapshot agora valida se o schema real respeita o manifesto do estudo
- o produto verifica a existência de:
  - coluna de entidade
  - coluna de decisão histórica
  - colunas declaradas em `outcome_columns`
  - colunas declaradas em `metadata_columns`
  - features usadas na baseline

Consequência prática:

- divergências entre manifesto e snapshot deixam de ficar silenciosas
- o estudo falha cedo com mensagem explícita
- isso reduz o risco de avaliar um estudo com métrica quebrada sem perceber
