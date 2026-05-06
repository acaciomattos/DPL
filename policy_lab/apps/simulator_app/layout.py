from __future__ import annotations

from dash import dash_table, dcc, html

from policy_lab.domain import SearchStrategy

from .components import build_info_tooltip
from .runtime import default_study_id, load_studies


def build_manual_lab_tab() -> html.Div:
    return html.Div(
        className="content-grid",
        children=[
            html.Div(
                className="sidebar",
                children=[
                    html.Div(className="panel panel-tight", children=[html.Div(id="study-meta")]),
                    html.Div(
                        className="panel panel-tight",
                        children=[
                            html.Div(className="panel-title", children="Baseline e filtros"),
                            html.Div(
                                id="baseline-metrics",
                                className="metric-grid metric-grid-compact",
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Meses do snapshot"),
                                    dcc.Dropdown(
                                        id="month-filter",
                                        multi=True,
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Coluna de segmentacao"),
                                    dcc.Dropdown(
                                        id="segment-field",
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Valores de segmentacao"),
                                    dcc.Dropdown(
                                        id="segment-values",
                                        multi=True,
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="panel panel-tight",
                        children=[
                            html.Div(
                                className="panel-title",
                                children="Resumo de corte e simulacao",
                            ),
                            html.Div(id="cutoff-suggestion", className="info-banner"),
                            html.Div(
                                className="field-group cutoff-objective-group",
                                children=[
                                    html.Label("Predicado-alvo selecionado"),
                                    dcc.Dropdown(
                                        id="cutoff-handle",
                                        disabled=True,
                                        clearable=False,
                                        placeholder="Selecione no editor lateral",
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="info-banner compact-banner",
                                children=[
                                    "Abra uma regra baseline no editor lateral, escolha o "
                                    "predicado numerico alvo e rode a otimizacao singular por la.",
                                ],
                            ),
                            html.Div(
                                className="button-grid",
                                children=[
                                    html.Button(
                                        "Simular",
                                        id="run-scenario",
                                        n_clicks=0,
                                        className="action-button compact-action-button",
                                    ),
                                    html.Button(
                                        "Exportar politica JSON",
                                        id="export-manual-policy",
                                        n_clicks=0,
                                        className="action-button secondary compact-action-button",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(className="panel-title", children="Biblioteca de regras"),
                            html.Div(
                                className="panel-subtitle",
                                children=(
                                    "As regras em uso e os ativos disponiveis ficam "
                                    "concentrados aqui. Arraste entre os paineis para ativar, "
                                    "remover ou reordenar ativos. Editar uma regra baseline gera "
                                    "uma variacao analitica da propria regra."
                                ),
                            ),
                            html.Div(id="rule-library", className="rule-library"),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="main-column",
                children=[
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                className="panel-title",
                                children="Resultados da politica candidata",
                            ),
                            html.Div(
                                className="panel-subtitle",
                                children=(
                                    "A coluna principal fica reservada para desempenho, "
                                    "fluxo de subdecisoes "
                                    "e comparacao com a baseline."
                                ),
                            ),
                            html.Div(id="scenario-metrics", className="metric-grid"),
                        ],
                    ),
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(className="panel-title", children="Fluxo de subdecisoes"),
                            dcc.Graph(id="rule-flow-figure", className="chart"),
                        ],
                    ),
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                className="panel-title",
                                children="Comparacao baseline x candidata",
                            ),
                            dash_table.DataTable(
                                id="comparison-table",
                                style_as_list_view=True,
                                style_table={"overflowX": "auto"},
                                style_header={
                                    "backgroundColor": "#182028",
                                    "color": "#dce6e9",
                                    "border": "none",
                                },
                                style_data={
                                    "backgroundColor": "#10161d",
                                    "color": "#dce6e9",
                                    "border": "none",
                                },
                            ),
                            dcc.Graph(id="comparison-figure", className="chart"),
                            dcc.Graph(id="transition-figure", className="chart"),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_rule_composition_tab() -> html.Div:
    return html.Div(
        className="content-grid single-tab",
        children=[
            html.Div(
                className="panel",
                children=[
                    html.Div(
                        className="panel-header-inline",
                        children=[
                            html.Div(className="panel-title", children="Criacao de regras"),
                            build_info_tooltip(
                                "Escolha a decisao ativa e clique em uma celula para atribui-la. "
                                "Arraste uma area sobre a matriz para atribuir a mesma decisao "
                                "a varias celulas. Clique novamente em uma celula ja marcada "
                                "com a mesma decisao para remove-la. "
                                "O duplo clique nao e usado para selecao nesta tela. "
                                "O publico elegivel mostrado na matriz sempre "
                                "depende da configuracao atual do Laboratorio Manual."
                            ),
                        ],
                    ),
                    html.Div(
                        className="panel-subtitle",
                        children=(
                            "A matriz usa o publico elegivel remanescente da "
                            "configuracao manual atual. Isso deixa explicito como a "
                            "politica em estudo altera o insumo da criacao de novas regras."
                        ),
                    ),
                    html.Div(
                        className="matrix-toolbar matrix-toolbar-filter",
                        children=[
                            html.Div(
                                className="toolbar-section-title",
                                children="Filtro do publico elegivel",
                            ),
                            html.Div(id="matrix-filter-container", className="matrix-filter-list"),
                            html.Div(
                                className="field-group align-end",
                                children=[
                                    html.Label("Filtros"),
                                    html.Button(
                                        "Adicionar filtro",
                                        id="add-matrix-filter",
                                        n_clicks=0,
                                        className="action-button secondary",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="matrix-toolbar matrix-toolbar-variables",
                        children=[
                            html.Div(
                                className="toolbar-section-title",
                                children="Variaveis X e Y",
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Variavel da linha"),
                                    dcc.Dropdown(id="matrix-row-variable"),
                                ],
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Variavel da coluna"),
                                    dcc.Dropdown(id="matrix-column-variable"),
                                ],
                            ),
                            html.Div(
                                className="field-group align-end",
                                children=[
                                    html.Label("Acao"),
                                    html.Button(
                                        "Gerar matriz",
                                        id="generate-matrix",
                                        n_clicks=0,
                                        className="action-button",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(id="matrix-summary", className="metric-grid matrix-summary-grid"),
                    dcc.Graph(
                        id="matrix-figure",
                        className="chart",
                        config={
                            "doubleClick": False,
                            "modeBarButtonsToRemove": ["select2d"],
                        },
                    ),
                    html.Div(id="matrix-selection-summary", className="info-banner"),
                    html.Div(
                        className="rule-save-panel",
                        children=[
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Nome da nova regra"),
                                    dcc.Input(
                                        id="matrix-rule-name",
                                        type="text",
                                        value="Regra criada pela matriz",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group",
                                children=[
                                    html.Label("Decisao ativa na matriz"),
                                    dcc.Dropdown(id="matrix-rule-decision", clearable=False),
                                ],
                            ),
                            html.Div(
                                className="info-banner compact-banner",
                                children=(
                                    "Cada celula pode receber apenas uma decisao. "
                                    "Cores da matriz continuam representando a taxa do evento; "
                                    "as bordas coloridas mostram a decisao atribuida."
                                ),
                            ),
                            html.Div(
                                className="button-row button-row-no-margin",
                                children=[
                                    html.Button(
                                        "Avaliar previa de resultados",
                                        id="preview-matrix-rule",
                                        n_clicks=0,
                                        className="action-button secondary",
                                    ),
                                    html.Button(
                                        "Salvar regra",
                                        id="save-matrix-rule",
                                        n_clicks=0,
                                        className="action-button",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(id="matrix-rule-preview", className="metric-grid"),
                    html.Div(id="matrix-save-status", className="info-banner"),
                ],
            )
        ],
    )


def build_optimization_tab() -> html.Div:
    return html.Div(
        className="content-grid single-tab",
        children=[
            html.Div(
                className="panel",
                children=[
                    html.Div(className="panel-title", children="Otimizacao automatica"),
                    html.Div(
                        className="button-row",
                        children=[
                            html.Div(
                                className="field-group field-group-grow",
                                children=[
                                    html.Label("Estrategia"),
                                    dcc.Dropdown(
                                        id="search-strategy",
                                        options=[
                                            {
                                                "label": "Varredura parametrica",
                                                "value": SearchStrategy.PARAMETER_SWEEP.value,
                                            },
                                            {
                                                "label": "Busca guiada",
                                                "value": SearchStrategy.GUIDED_SEARCH.value,
                                            },
                                            {
                                                "label": "Busca heuristica",
                                                "value": SearchStrategy.HEURISTIC_SEARCH.value,
                                            },
                                            {
                                                "label": "Simulated annealing",
                                                "value": SearchStrategy.SIMULATED_ANNEALING.value,
                                            },
                                        ],
                                        value=SearchStrategy.GUIDED_SEARCH.value,
                                        clearable=False,
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group field-group-grow",
                                children=[
                                    html.Label("Base da busca"),
                                    dcc.Dropdown(
                                        id="search-base",
                                        options=[
                                            {
                                                "label": "Baseline do estudo",
                                                "value": "baseline_study",
                                            },
                                            {
                                                "label": "Ultima simulacao manual",
                                                "value": "last_simulation",
                                            },
                                            {
                                                "label": "Construir do zero",
                                                "value": "from_scratch",
                                            },
                                        ],
                                        value="baseline_study",
                                        clearable=False,
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group action-inline",
                                children=[
                                    html.Label("Acao"),
                                    html.Button(
                                        "Executar busca",
                                        id="run-search",
                                        n_clicks=0,
                                        className="action-button",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="button-row",
                        children=[
                            html.Div(
                                className="field-group field-group-grow",
                                children=[
                                    html.Label("Objetivo principal"),
                                    dcc.Dropdown(
                                        id="search-primary-metric",
                                        options=[
                                            {"label": "Aprovacao", "value": "approval"},
                                            {"label": "Risco", "value": "risk"},
                                            {
                                                "label": "Indice de lucro",
                                                "value": "profit_index",
                                            },
                                            {"label": "Churn", "value": "churn"},
                                            {
                                                "label": "Complexidade",
                                                "value": "complexity",
                                            },
                                        ],
                                        value="approval",
                                        clearable=False,
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group compact",
                                children=[
                                    html.Label("Direcao"),
                                    dcc.Dropdown(
                                        id="search-direction",
                                        options=[
                                            {"label": "Maximizar", "value": "maximize"},
                                            {"label": "Minimizar", "value": "minimize"},
                                        ],
                                        value="maximize",
                                        clearable=False,
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group field-group-grow",
                                children=[
                                    html.Label("Metrica a preservar"),
                                    dcc.Dropdown(
                                        id="search-preserve-metric",
                                        options=[
                                            {"label": "Nenhuma", "value": "none"},
                                            {"label": "Aprovacao", "value": "approval"},
                                            {"label": "Risco", "value": "risk"},
                                            {
                                                "label": "Indice de lucro",
                                                "value": "profit_index",
                                            },
                                            {"label": "Churn", "value": "churn"},
                                            {
                                                "label": "Complexidade",
                                                "value": "complexity",
                                            },
                                        ],
                                        value="risk",
                                        clearable=False,
                                        className="compact-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="field-group compact",
                                children=[
                                    html.Label("Tolerancia maxima"),
                                    dcc.Input(
                                        id="search-max-degradation",
                                        type="number",
                                        value=2,
                                        min=0,
                                        step=0.5,
                                        className="compact-text-input",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="field-group",
                        children=[
                            html.Label("Objetivo em linguagem natural"),
                            dcc.Textarea(
                                id="optimization-objective",
                                value=(
                                    "Aumentar aprovacao sem piorar risco alem de 2pp "
                                    "e sem aumentar muito a complexidade."
                                ),
                                className="objective-textarea",
                            ),
                            html.Div(
                                className="info-banner",
                                children=(
                                    "O interpretador automatico do texto ainda nao foi "
                                    "implementado. "
                                    "Por enquanto, o campo registra o objetivo analitico do estudo."
                                ),
                            ),
                        ],
                    ),
                    dcc.Loading(
                        id="optimization-loading",
                        type="circle",
                        className="optimization-loading-wrapper",
                        custom_spinner=html.Div(
                            className="optimization-loading-indicator",
                            children=[
                                html.Div(
                                    className="optimization-loading-title",
                                    children="Executando busca automatica",
                                ),
                                html.Div(
                                    className="optimization-loading-copy",
                                    children=(
                                        "Gerando e avaliando candidatos para este recorte."
                                    ),
                                ),
                            ],
                        ),
                        children=[
                            dash_table.DataTable(
                                id="recommendation-table",
                                page_size=8,
                                row_selectable="single",
                                selected_rows=[],
                                style_as_list_view=True,
                                style_table={"overflowX": "auto"},
                                style_cell={
                                    "whiteSpace": "normal",
                                    "height": "auto",
                                    "lineHeight": "15px",
                                    "textAlign": "left",
                                    "padding": "8px 10px",
                                },
                                style_cell_conditional=[
                                    {
                                        "if": {"column_id": "composicao"},
                                        "whiteSpace": "pre-line",
                                        "maxWidth": "360px",
                                        "width": "360px",
                                    }
                                ],
                                style_header={
                                    "backgroundColor": "#182028",
                                    "color": "#dce6e9",
                                    "border": "none",
                                },
                                style_data={
                                    "backgroundColor": "#10161d",
                                    "color": "#dce6e9",
                                    "border": "none",
                                },
                            ),
                            html.Div(
                                className="button-row",
                                children=[
                                    html.Button(
                                        "Transferir para o Laboratorio Manual",
                                        id="transfer-search-candidate",
                                        n_clicks=0,
                                        className="action-button secondary",
                                    ),
                                    html.Div(
                                        id="transfer-search-status",
                                        className="info-banner compact-banner",
                                    ),
                                ],
                            ),
                            dcc.Graph(id="recommendation-figure", className="chart"),
                        ],
                    ),
                ],
            )
        ],
    )


def build_app_layout() -> html.Div:
    return html.Div(
        className="app-shell",
        children=[
            dcc.Download(id="policy-download"),
            dcc.Store(id="rule-state-store", storage_type="session"),
            dcc.Store(id="manual-ui-state-store", storage_type="session"),
            dcc.Store(id="predicate-editor-store", storage_type="session"),
            dcc.Store(id="asset-editor-store"),
            dcc.Store(id="cutoff-override-store"),
            dcc.Store(id="matrix-filter-count-store", data=1),
            dcc.Store(id="matrix-config-store", storage_type="session"),
            dcc.Store(id="matrix-selection-store", storage_type="session"),
            dcc.Store(id="custom-rule-store", storage_type="session"),
            dcc.Store(id="manual-config-store", storage_type="session"),
            dcc.Store(id="manual-config-current-store", storage_type="session"),
            dcc.Store(id="pending-matrix-rule-store", storage_type="session"),
            dcc.Store(id="pending-matrix-edit-store", storage_type="session"),
            dcc.Store(id="matrix-editing-rule-store", storage_type="session"),
            dcc.Store(id="last-simulation-store", storage_type="session"),
            dcc.Store(id="search-results-store", storage_type="session"),
            dcc.Input(
                id="rule-library-dnd-payload",
                type="text",
                value="",
                style={"display": "none"},
            ),
            dcc.ConfirmDialog(
                id="overwrite-rule-confirm",
                message=(
                    "Ja existe uma regra com este nome. "
                    "Deseja sobrescrever a regra existente?"
                ),
            ),
            dcc.ConfirmDialog(
                id="matrix-edit-alert",
                message="",
            ),
            html.Div(
                className="topbar",
                children=[
                    html.Div(
                        className="brand",
                        children=[
                            html.Div("Decision Policy Lab", className="brand-title"),
                            html.Div(
                                "Laboratorio governado para reproducao da baseline, "
                                "simulacao manual, criacao de regras e busca automatica.",
                                className="brand-subtitle",
                            ),
                        ],
                    ),
                    html.Div(
                        className="topbar-controls",
                        children=[
                            html.Div(
                                className="field-group topbar-study-group",
                                children=[
                                    html.Label("Estudo"),
                                    dcc.Dropdown(
                                        id="study-dropdown",
                                        options=[
                                            {
                                                "label": study.manifest.name,
                                                "value": study.study_id,
                                            }
                                            for study in load_studies()
                                        ],
                                        value=default_study_id(),
                                        clearable=False,
                                        className="topbar-dropdown",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="panel panel-tight topbar-workspace-panel",
                                children=[
                                    html.Div(
                                        className="panel-title topbar-workspace-title",
                                        children="Workspaces manuais",
                                    ),
                                    html.Div(
                                        className="panel-subtitle topbar-workspace-subtitle",
                                        children=(
                                            "Salve e recarregue configuracoes do "
                                            "Laboratorio Manual para reutilizar o "
                                            "contexto nas tres abas."
                                        ),
                                    ),
                                    html.Div(
                                        className="topbar-workspace-fields",
                                        children=[
                                            html.Div(
                                                className="field-group",
                                                children=[
                                                    html.Label("Workspace salvo"),
                                                    dcc.Dropdown(
                                                        id="manual-config-select",
                                                        placeholder=(
                                                            "Selecione uma configuracao salva"
                                                        ),
                                                        clearable=False,
                                                        className="compact-dropdown",
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className="field-group",
                                                children=[
                                                    html.Label("Nome da configuracao"),
                                                    dcc.Input(
                                                        id="manual-config-name",
                                                        type="text",
                                                        value="Workspace manual",
                                                        className="compact-text-input",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className=(
                                            "button-row button-row-no-margin "
                                            "topbar-workspace-actions"
                                        ),
                                        children=[
                                            html.Button(
                                                "Carregar",
                                                id="load-manual-config",
                                                n_clicks=0,
                                                className=(
                                                    "action-button secondary "
                                                    "compact-action-button"
                                                ),
                                            ),
                                            html.Button(
                                                "Salvar configuracao",
                                                id="save-manual-config",
                                                n_clicks=0,
                                                className="action-button compact-action-button",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        id="manual-config-status",
                                        className=(
                                            "info-banner compact-banner "
                                            "topbar-workspace-status"
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Tabs(
                id="main-tabs",
                value="manual_lab",
                className="app-tabs",
                children=[
                    dcc.Tab(
                        label="Laboratorio manual",
                        value="manual_lab",
                        className="app-tab",
                        selected_className="app-tab-selected",
                    ),
                    dcc.Tab(
                        label="Criacao de regras",
                        value="rule_composition",
                        className="app-tab",
                        selected_className="app-tab-selected",
                    ),
                    dcc.Tab(
                        label="Otimizacao automatica",
                        value="automatic_optimization",
                        className="app-tab",
                        selected_className="app-tab-selected",
                    ),
                ],
            ),
            html.Div(
                id="tabs-body",
                children=[
                    html.Div(id="manual-lab-container", children=[build_manual_lab_tab()]),
                    html.Div(
                        id="rule-composition-container",
                        children=[build_rule_composition_tab()],
                        style={"display": "none"},
                    ),
                    html.Div(
                        id="automatic-optimization-container",
                        children=[build_optimization_tab()],
                        style={"display": "none"},
                    ),
                ],
            ),
            html.Div(
                id="asset-editor-drawer",
                className="asset-editor-drawer",
                children=[
                    html.Div(
                        className="asset-editor-shell",
                        children=[
                            html.Div(
                                className="asset-editor-toolbar",
                                children=[
                                    html.Div(
                                        "Editor de ativo",
                                        id="asset-editor-toolbar-title",
                                        className="asset-editor-toolbar-title",
                                    ),
                                    html.Div(
                                        className="asset-editor-toolbar-actions",
                                        children=[
                                            html.Button(
                                                "Salvar",
                                                id="asset-editor-save",
                                                n_clicks=0,
                                                className="small-button",
                                            ),
                                            html.Button(
                                                "X",
                                                id="asset-editor-close",
                                                n_clicks=0,
                                                className="icon-button",
                                                title="Fechar editor",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                id="asset-cutoff-panel",
                                className="asset-cutoff-panel",
                                children=[
                                    html.Div(
                                        "Otimizacao singular do predicado",
                                        className="panel-title panel-title-small",
                                    ),
                                    html.Div(
                                        className="panel-subtitle",
                                        children=(
                                            "Escolha o predicado-alvo dentro da regra, ajuste o "
                                            "tipo de controle e encontre um ponto de corte "
                                            "usando o pool de ancoragem da propria regra."
                                        ),
                                    ),
                                    html.Div(
                                        className="field-group cutoff-objective-group",
                                        children=[
                                            html.Label("Tipo de controle"),
                                            dcc.RadioItems(
                                                id="cutoff-objective",
                                                options=[
                                                    {
                                                        "label": "Meta de aprovacao",
                                                        "value": "approval",
                                                    },
                                                    {"label": "Meta de risco", "value": "risk"},
                                                    {
                                                        "label": "Corte seco",
                                                        "value": "fixed_cutoff",
                                                    },
                                                ],
                                                value="approval",
                                                className="cutoff-objective",
                                                inputClassName="cutoff-objective-input",
                                                labelClassName="cutoff-objective-label",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="field-group",
                                        children=[
                                            html.Label(
                                                "Meta de aprovacao (%)",
                                                id="cutoff-target-label",
                                            ),
                                            dcc.Input(
                                                id="target-approval-rate",
                                                type="number",
                                                value=80.0,
                                            ),
                                        ],
                                    ),
                                    html.Button(
                                        "Encontrar ponto de corte",
                                        id="find-cutoff",
                                        n_clicks=0,
                                        className="action-button secondary",
                                    ),
                                ],
                            ),
                            html.Div(id="asset-editor-body", className="asset-editor-body"),
                            html.Div(
                                id="asset-editor-status",
                                className="info-banner compact-banner",
                            ),
                        ],
                    )
                ],
            ),
        ],
    )
