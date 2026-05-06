from __future__ import annotations

from typing import Any

import polars as pl
from dash import dcc, html

from policy_lab.domain import (
    DecisionRuleDefinition,
    DerivedFeatureDefinition,
    ScenarioResult,
    StudyContext,
)

from .formatting import (
    delta_text,
    delta_text_optional,
    format_by_kind,
    format_delta_by_kind,
    format_optional_money,
    format_optional_number,
    format_optional_pct,
)
from .runtime import feature_repository
from .services import (
    _is_numeric_dtype,
    baseline_asset_id,
    custom_asset_id,
    custom_entry_predicate_handle,
    custom_rule_member_payloads,
    feature_asset_id,
    next_variant_name,
    normalize_predicate_editor_state,
    predicate_value_from_editor_state,
    ui_predicate_handle,
)


def build_info_tooltip(text: str | None) -> html.Span:
    return html.Span(
        className="tooltip-wrap",
        children=[
            html.Button(
                "?",
                className="icon-button",
                type="button",
                **{"aria-label": "Exibir descricao"},
            ),
            html.Span(
                text or "Sem descricao cadastrada.",
                className="tooltip-text",
            ),
        ],
    )


def build_chip_tooltip(label: str, text: str) -> html.Span:
    return html.Span(
        className="tooltip-wrap",
        children=[
            html.Div(label, className="rule-order-chip"),
            html.Span(text, className="tooltip-text"),
        ],
    )


def build_icon_button(
    label: str,
    *,
    button_id: Any,
    title: str,
    class_name: str = "icon-button",
) -> html.Button:
    return html.Button(
        label,
        id=button_id,
        n_clicks=0,
        className=class_name,
        title=title,
        type="button",
    )


def wrap_draggable_card(
    *,
    asset_id: str,
    panel: str,
    class_name: str,
    children: list[Any],
) -> html.Div:
    return html.Div(
        className=f"{class_name} dnd-card",
        draggable="true",
        **{
            "data-asset-id": asset_id,
            "data-panel": panel,
        },
        children=children,
    )


def build_rule_tooltip(rule: DecisionRuleDefinition) -> str:
    lines: list[str] = []
    if rule.description:
        lines.extend(["Descricao:", rule.description, ""])

    lines.extend(
        [
            "Decisao quando a regra dispara:",
            rule.decision,
            "",
            f"Combinacao dos blocos: {rule.block_combiner.value}",
            "Predicados:",
        ]
    )
    for block in rule.blocks:
        lines.append(f"- {block.name} ({block.logical_operator.value})")
        for predicate in block.predicates:
            lines.append(
                f"  {predicate.field} {predicate.operator.value} "
                f"{format_predicate_value(predicate.value)}"
            )

    return "\n".join(lines)


def build_feature_tooltip(feature: DerivedFeatureDefinition) -> str:
    lines: list[str] = []
    if feature.description:
        lines.extend(["Descricao:", feature.description, ""])

    lines.extend(["Expressao:", feature.expression])
    if feature.dependencies:
        lines.extend(["", "Dependencias:", ", ".join(feature.dependencies)])
    lines.extend(["", f"Modo: {feature.mode.value}", f"Tipo: {feature.data_type}"])
    return "\n".join(lines)


def custom_entry_summary(entry: dict[str, Any]) -> str:
    source_type = entry.get("source_type")
    if source_type == "baseline_rule_variant":
        origin_name = str(entry.get("origin_rule_name") or "baseline")
        version = entry.get("version")
        version_text = f"v{version}" if version else "variante"
        return f"Variante de {origin_name} | {version_text}"
    if source_type == "optimization_transfer":
        return optimization_candidate_label(entry)
    rules = custom_entry_rules(entry)
    decision_count = len({rule.decision for rule in rules})
    cell_count = len(entry.get("cell_decisions") or entry.get("selected_cells") or [])
    parts: list[str] = []
    if rules:
        parts.append(f"{len(rules)} regra(s)")
    if decision_count:
        parts.append(f"{decision_count} decisao(oes)")
    if cell_count:
        parts.append(f"{cell_count} celula(s)")
    return " | ".join(parts) if parts else "Ativo criado na matriz"


def format_predicate_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def build_asset_editor_empty_state() -> html.Div:
    return html.Div(
        className="editor-empty-state",
        children=(
            "Selecione um ativo na biblioteca para inspecionar ou editar seus detalhes."
        ),
    )


def build_rule_editor_content(
    study: StudyContext,
    rule: DecisionRuleDefinition,
    snapshot: pl.DataFrame,
    predicate_editor_state: dict[str, Any] | None,
    current_cutoff_handle: str | None,
    custom_rule_entries: list[dict[str, Any]] | None = None,
) -> html.Div:
    normalized_state = normalize_predicate_editor_state(study, predicate_editor_state)
    existing_names = {
        str(entry.get("rule_name"))
        for entry in custom_rule_entries or []
        if entry.get("rule_name")
    }
    existing_names.add(rule.name)
    suggested_variant_name = next_variant_name(rule.name, existing_names)
    current_target_text = (
        "Predicado-alvo atual desta regra: ativo."
        if current_cutoff_handle and current_cutoff_handle.startswith(f"{rule.rule_id}:")
        else "Nenhum predicado desta regra esta marcado como alvo no momento."
    )
    predicate_controls: list[html.Div] = []
    for block_index, block in enumerate(rule.blocks):
        block_children: list[html.Div] = [
            html.Div(block.name, className="editor-section-subtitle"),
            html.Div(
                f"Operador logico do bloco: {block.logical_operator.value}",
                className="editor-copy",
            ),
        ]
        for predicate_index, predicate in enumerate(block.predicates):
            handle = ui_predicate_handle(
                rule.rule_id,
                block_index,
                predicate_index,
                predicate.field,
                predicate.operator.value,
            )
            editable = predicate.field in snapshot.columns and _is_numeric_dtype(
                snapshot.schema.get(predicate.field)
            )
            current_value = predicate_value_from_editor_state(
                study,
                normalized_state,
                handle,
            )
            if editable:
                control: Any = dcc.Input(
                    id={"type": "editor-predicate-input", "handle": handle},
                    type="number",
                    value=current_value,
                    className="rule-input",
                )
            else:
                control = html.Div(
                    f"Valor fixo: {format_predicate_value(current_value)}",
                    className="rule-fixed-value",
                )
            predicate_actions: list[Any] = []
            if editable:
                predicate_actions.append(
                    html.Button(
                        "Ativo" if handle == current_cutoff_handle else "Corte",
                        id={"type": "select-cutoff-handle", "handle": handle},
                        n_clicks=0,
                        className=(
                            "small-button secondary-button"
                            if handle != current_cutoff_handle
                            else "small-button"
                        ),
                        title="Usar este predicado como alvo do ponto de corte",
                    )
                )
            block_children.append(
                html.Div(
                    className="editor-predicate-row",
                    children=[
                        html.Div(
                            f"{predicate.field} {predicate.operator.value}",
                            className="rule-label",
                        ),
                        control,
                        html.Div(
                            className="editor-predicate-actions",
                            children=predicate_actions,
                        ),
                    ],
                )
            )
        predicate_controls.append(
            html.Div(className="editor-section", children=block_children)
        )

    return html.Div(
        className="asset-editor-content",
        children=[
            html.Div(rule.name, className="asset-editor-title"),
            html.Div("Regra baseline", className="asset-editor-badge"),
            html.Div(rule.description or "Sem descricao cadastrada.", className="editor-copy"),
            html.Div(
                f"Decisao quando dispara: {rule.decision}",
                className="editor-copy",
            ),
            html.Div(
                f"Combinacao dos blocos: {rule.block_combiner.value}",
                className="editor-copy",
            ),
            html.Div(
                "Edite os thresholds numericos abaixo. Campos nao numericos "
                "permanecem apenas para consulta nesta primeira fase.",
                className="info-banner compact-banner",
            ),
            html.Div(
                "Para o otimizador singular, selecione o predicado-alvo no proprio editor. "
                "A busca considera o pool de ancoragem imediatamente antes da regra hospedeira.",
                className="info-banner compact-banner",
            ),
            html.Div(
                "Alteracoes neste editor nao sobrescrevem a regra baseline do estudo. "
                "Ao salvar, o DPL cria uma variante governada e opcionalmente substitui "
                "a baseline atual na politica candidata.",
                className="info-banner compact-banner",
            ),
            html.Div(current_target_text, className="editor-copy"),
            html.Div(className="editor-sections", children=predicate_controls),
            html.Div(
                className="editor-section governance-section",
                children=[
                    html.Div("Governanca da variante", className="editor-section-subtitle"),
                    html.Div(
                        "Escolha o nome da variante e se ela deve substituir a baseline "
                        "na politica candidata atual.",
                        className="editor-copy",
                    ),
                    dcc.Input(
                        id="variant-rule-name",
                        type="text",
                        value=suggested_variant_name,
                        className="rule-input",
                    ),
                    dcc.Checklist(
                        id="variant-replace-policy",
                        options=[
                            {
                                "label": "Substituir a regra baseline atual na politica candidata",
                                "value": "replace",
                            }
                        ],
                        value=["replace"],
                        className="editor-checklist",
                    ),
                ],
            ),
        ],
    )


def build_variant_rule_editor_content(
    entry: dict[str, Any],
    rule: DecisionRuleDefinition,
    snapshot: pl.DataFrame,
) -> html.Div:
    predicate_controls: list[html.Div] = []
    for block_index, block in enumerate(rule.blocks):
        block_children: list[html.Div] = [
            html.Div(block.name, className="editor-section-subtitle"),
            html.Div(
                f"Operador logico do bloco: {block.logical_operator.value}",
                className="editor-copy",
            ),
        ]
        for predicate_index, predicate in enumerate(block.predicates):
            handle = ui_predicate_handle(
                str(entry.get("origin_rule_id") or rule.rule_id),
                block_index,
                predicate_index,
                predicate.field,
                predicate.operator.value,
            )
            editable = predicate.field in snapshot.columns and _is_numeric_dtype(
                snapshot.schema.get(predicate.field)
            )
            control: Any
            if editable:
                control = dcc.Input(
                    id={"type": "editor-predicate-input", "handle": handle},
                    type="number",
                    value=predicate.value,
                    className="rule-input",
                )
            else:
                control = html.Div(
                    f"Valor fixo: {format_predicate_value(predicate.value)}",
                    className="rule-fixed-value",
                )
            block_children.append(
                html.Div(
                    className="editor-predicate-row",
                    children=[
                        html.Div(
                            f"{predicate.field} {predicate.operator.value}",
                            className="rule-label",
                        ),
                        control,
                    ],
                )
            )
        predicate_controls.append(
            html.Div(className="editor-section", children=block_children)
        )

    return html.Div(
        className="asset-editor-content",
        children=[
            html.Div(rule.name, className="asset-editor-title"),
            html.Div("Variante governada", className="asset-editor-badge"),
            html.Div(
                "Esta variante deriva da baseline "
                f"'{entry.get('origin_rule_name') or entry.get('origin_rule_id') or 'baseline'}'.",
                className="editor-copy",
            ),
            html.Div(
                "Nesta fase, editar a variante atualiza o proprio ativo criado no estudo, "
                "sem reabrir o fluxo da baseline original.",
                className="info-banner compact-banner",
            ),
            html.Div(
                style={"display": "none"},
                children=[
                    dcc.Input(id="variant-rule-name", type="text", value=rule.name),
                    dcc.Checklist(
                        id="variant-replace-policy",
                        options=[{"label": "replace", "value": "replace"}],
                        value=[],
                    ),
                ],
            ),
            html.Div(className="editor-sections", children=predicate_controls),
        ],
    )


def build_feature_editor_content(feature: DerivedFeatureDefinition) -> html.Div:
    dependency_text = ", ".join(feature.dependencies) if feature.dependencies else "Nenhuma"
    return html.Div(
        className="asset-editor-content",
        children=[
            html.Div(feature.name, className="asset-editor-title"),
            html.Div("Feature derivada", className="asset-editor-badge"),
            html.Div(feature.description or "Sem descricao cadastrada.", className="editor-copy"),
            html.Div(f"Expressao: {feature.expression}", className="editor-copy"),
            html.Div(f"Dependencias: {dependency_text}", className="editor-copy"),
            html.Div(f"Modo: {feature.mode.value}", className="editor-copy"),
            html.Div(f"Tipo: {feature.data_type}", className="editor-copy"),
            html.Div(
                "Nesta fase, features derivadas ainda sao inspecionadas no drawer, "
                "mas nao possuem editor profundo equivalente ao das regras baseline.",
                className="info-banner compact-banner",
            ),
        ],
    )


def build_optimization_transfer_editor_content(
    entry: dict[str, Any],
    rules: list[DecisionRuleDefinition],
    snapshot: pl.DataFrame,
) -> html.Div:
    sections: list[html.Div] = []
    asset_id = str(entry.get("rule_id") or "")
    for rule_index, rule in enumerate(rules):
        predicate_controls: list[html.Div] = []
        for block_index, block in enumerate(rule.blocks):
            block_children: list[html.Div] = [
                html.Div(block.name, className="editor-section-subtitle"),
                html.Div(
                    f"Operador logico do bloco: {block.logical_operator.value}",
                    className="editor-copy",
                ),
            ]
            for predicate_index, predicate in enumerate(block.predicates):
                handle = custom_entry_predicate_handle(
                    asset_id,
                    rule_index,
                    block_index,
                    predicate_index,
                )
                editable = predicate.field in snapshot.columns and _is_numeric_dtype(
                    snapshot.schema.get(predicate.field)
                )
                control: Any
                if editable:
                    control = dcc.Input(
                        id={"type": "editor-predicate-input", "handle": handle},
                        type="number",
                        value=predicate.value,
                        className="rule-input",
                    )
                else:
                    control = html.Div(
                        f"Valor fixo: {format_predicate_value(predicate.value)}",
                        className="rule-fixed-value",
                    )
                block_children.append(
                    html.Div(
                        className="editor-predicate-row",
                        children=[
                            html.Div(
                                f"{predicate.field} {predicate.operator.value}",
                                className="rule-label",
                            ),
                            control,
                        ],
                    )
                )
            predicate_controls.append(
                html.Div(className="editor-section", children=block_children)
            )
        sections.append(
            html.Div(
                className="editor-section governance-section",
                children=[
                    html.Div(rule.name, className="asset-editor-title"),
                    html.Div(
                        f"Decisao quando dispara: {rule.decision}",
                        className="editor-copy",
                    ),
                    html.Div(className="editor-sections", children=predicate_controls),
                ],
            )
        )

    return html.Div(
        className="asset-editor-content",
        children=[
            html.Div(
                str(entry.get("rule_name") or "Sugestao otimizada"),
                className="asset-editor-title",
            ),
            html.Div("Sugestao otimizada", className="asset-editor-badge"),
            html.Div(
                "Este ativo veio da busca automatica. Nesta fase, podemos renomear "
                "o pacote e ajustar predicados numericos das regras encapsuladas.",
                className="info-banner compact-banner",
            ),
            html.Div(
                f"Estrategia: {entry.get('search_strategy') or 'N/A'} | "
                f"Base: {entry.get('search_base') or 'N/A'} | "
                f"Tipo: {entry.get('candidate_kind') or 'N/A'}",
                className="editor-copy",
            ),
            dcc.Input(
                id="variant-rule-name",
                type="text",
                value=str(entry.get("rule_name") or "Sugestao otimizada"),
                className="rule-input",
            ),
            dcc.Checklist(
                id="variant-replace-policy",
                options=[{"label": "replace", "value": "replace"}],
                value=[],
                style={"display": "none"},
            ),
            *sections,
        ],
    )


def build_rule_library(
    study: StudyContext,
    rule_state: dict[str, Any],
    snapshot: pl.DataFrame,
    custom_rule_entries: list[dict[str, Any]] | None = None,
) -> tuple[list[html.Div], list[dict[str, str]]]:
    baseline_rules = {rule.rule_id: rule for rule in study.manifest.baseline_policy.rules}
    custom_entry_map = {
        str(entry.get("rule_id")): dict(entry)
        for entry in custom_rule_entries or []
        if entry.get("rule_id")
    }
    all_features = {feature.feature_id: feature for feature in feature_repository.load(study)}
    used_rule_ids = rule_state["used_rule_ids"]
    used_custom_rule_ids = rule_state.get("used_custom_rule_ids", [])
    selected_feature_ids = rule_state["selected_feature_ids"]
    cutoff_options = build_numeric_handle_options(study, snapshot, used_rule_ids)

    used_cards: list[html.Div] = []
    ordered_index = 1
    for asset_id in rule_state.get("used_asset_ids", []):
        kind, raw_id = str(asset_id).split(":", maxsplit=1)
        if kind == "baseline" and raw_id in baseline_rules:
            used_cards.append(
                build_used_rule_card(study, baseline_rules[raw_id], snapshot, order=ordered_index)
            )
            ordered_index += 1
        elif kind == "custom":
            entry = custom_entry_map.get(raw_id)
            if entry is not None:
                used_cards.append(build_used_custom_rule_card(entry))
        elif kind == "feature" and raw_id in all_features:
            used_cards.append(build_selected_feature_card(all_features[raw_id]))

    available_cards: list[html.Div] = []
    for rule in study.manifest.baseline_policy.rules:
        if rule.rule_id in used_rule_ids:
            continue
        available_cards.append(build_available_rule_card(rule))

    for entry in custom_rule_entries or []:
        entry_id = str(entry.get("rule_id") or "")
        if not entry_id or entry_id in used_custom_rule_ids:
            continue
        available_cards.append(build_available_custom_rule_card(entry))

    for feature in feature_repository.load(study):
        if feature.feature_id in selected_feature_ids:
            continue
        available_cards.append(build_available_feature_card(feature))

    used_panel_children: list[Any] = [
        html.Div(className="library-title", children="Ativos em uso"),
        html.Div(
            className="library-copy",
            children=(
                "Reorganize os ativos e abra o editor lateral para detalhes."
            ),
        ),
    ]
    if used_cards:
        used_panel_children.extend(used_cards)
    else:
        used_panel_children.append(
            html.Div(
                "Nenhuma regra ou feature esta em uso.",
                className="info-copy",
            )
        )

    available_panel_children: list[Any] = [
        html.Div(className="library-title", children="Ativos disponiveis"),
        html.Div(
            className="library-copy",
            children=(
                "Regras baseline, features derivadas e ativos criados no estudo."
            ),
        ),
    ]
    if available_cards:
        available_panel_children.extend(available_cards)
    else:
        available_panel_children.append(
            html.Div(
                "Nao ha ativos disponiveis fora da politica corrente.",
                className="info-copy",
            )
        )

    children = [
        html.Div(
            className="rule-library-panels",
            children=[
                html.Div(
                    className="library-panel dnd-dropzone",
                    id="rule-library-used-panel",
                    children=used_panel_children,
                    **{"data-panel": "used"},
                ),
                html.Div(
                    className="library-panel dnd-dropzone",
                    id="rule-library-available-panel",
                    children=available_panel_children,
                    **{"data-panel": "available"},
                ),
            ],
        )
    ]
    return children, cutoff_options


def _legacy_build_used_rule_card(
    study: StudyContext,
    rule,
    snapshot: pl.DataFrame,
    *,
    order: int,
) -> html.Div:
    return html.Div(
        className="rule-library-card compact-rule-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(str(order), className="rule-order-chip"),
                    html.Div(
                        [
                            html.Div(rule.name, className="rule-title"),
                            html.Div("Baseline", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_rule_tooltip(rule)),
                            html.Button(
                                "✎",
                                id={"type": "open-rule-editor", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Editar regra",
                            ),
                            html.Button(
                                "↑",
                                id={"type": "move-up-rule", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Mover para cima",
                            ),
                            html.Button(
                                "↓",
                                id={"type": "move-down-rule", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Mover para baixo",
                            ),
                            html.Button(
                                "-",
                                id={"type": "remove-rule", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button icon-button-danger",
                                title="Remover da politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _legacy_build_available_rule_card(rule) -> html.Div:
    return html.Div(
        className="rule-library-card compact-rule-card available-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(rule.name, className="rule-title"),
                            html.Div("Baseline", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_rule_tooltip(rule)),
                            html.Button(
                                "✎",
                                id={"type": "open-rule-editor", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Inspecionar e editar regra",
                            ),
                            html.Button(
                                "+",
                                id={"type": "add-rule", "rule_id": rule.rule_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Adicionar a politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def custom_entry_rules(entry: dict[str, Any]) -> list[DecisionRuleDefinition]:
    rules: list[DecisionRuleDefinition] = []
    for payload in custom_rule_member_payloads(entry):
        try:
            rules.append(DecisionRuleDefinition.from_dict(payload))
        except (KeyError, TypeError, ValueError):
            continue
    return rules


def optimization_candidate_label(entry: dict[str, Any]) -> str:
    candidate_kind = str(entry.get("candidate_kind") or "").strip()
    if candidate_kind == "derived_veto":
        return "Derived veto"
    if candidate_kind == "simple_rule_candidate":
        return "Add rule"
    if candidate_kind == "grouped_rule_candidate":
        return "Grouped rule"
    if candidate_kind == "layered_rule_candidate":
        return "Structured rule"
    if candidate_kind == "guarded_rule_candidate":
        return "Guarded rule"
    if candidate_kind == "composite_rule_candidate":
        return "Composite rule"
    if candidate_kind == "signal_bundle_candidate":
        return "Signal bundle"
    if candidate_kind == "rule_bundle_candidate":
        return "Rule bundle"
    if candidate_kind == "policy_pack_candidate":
        return "Policy pack"
    if candidate_kind == "mixed_candidate":
        return "Heuristic mix"
    if candidate_kind == "threshold_pair":
        return "Guided pair"
    if candidate_kind == "threshold_override":
        return "Threshold override"
    return "Sugestao otimizada"


def custom_entry_tooltip(entry: dict[str, Any]) -> str:
    source_type = entry.get("source_type")
    if source_type == "baseline_rule_variant":
        lines = [
            "Variante governada criada a partir de uma regra baseline.",
            f"Origem: {entry.get('origin_rule_name') or entry.get('origin_rule_id') or 'baseline'}",
            f"Versao: {entry.get('version') or 1}",
        ]
        payload = entry.get("rule")
        if isinstance(payload, dict):
            try:
                rule = DecisionRuleDefinition.from_dict(payload)
            except (KeyError, TypeError, ValueError):
                rule = None
            if rule is not None:
                lines.extend(["", build_rule_tooltip(rule)])
        return "\n".join(lines)
    if source_type == "optimization_transfer":
        rules = custom_entry_rules(entry)
        lines = [
            "Politica sugerida pela otimização automatica.",
            f"Estrategia: {entry.get('search_strategy') or 'N/A'}",
            f"Base da busca: {entry.get('search_base') or 'N/A'}",
            f"Tipo do candidato: {entry.get('candidate_kind') or 'N/A'}",
            f"Regras no pacote: {len(rules)}",
        ]
        summary = str(entry.get("search_summary") or "").strip()
        if summary:
            lines.extend(["", "Composicao:", summary.replace(";", ";\n")])
        objective_spec = entry.get("objective_spec")
        if isinstance(objective_spec, dict):
            lines.extend(
                [
                    "",
                    "Objetivo estruturado:",
                    (
                        f"{objective_spec.get('direction', 'maximize')} "
                        f"{objective_spec.get('primary_metric', 'approval')}"
                    ),
                ]
            )
            preserve_metric = objective_spec.get("preserve_metric")
            if preserve_metric not in (None, "", "none"):
                lines.append(
                    "Preservar "
                    f"{preserve_metric} com tolerancia de "
                    f"{objective_spec.get('max_degradation')}"
                )
        return "\n".join(lines)
    rules = custom_entry_rules(entry)
    lines = [
        "Ativo criado na matriz.",
        f"Regras geradas: {len(rules)}",
    ]
    if entry.get("description"):
        lines.extend(["", str(entry.get("description"))])
    for rule in rules[:3]:
        lines.extend(
            [
                "",
                f"- {rule.name}",
                f"  decisao: {rule.decision}",
                f"  blocos: {len(rule.blocks)}",
            ]
        )
    if len(rules) > 3:
        lines.append("")
        lines.append(f"... +{len(rules) - 3} regras")
    return "\n".join(lines)


def custom_entry_note(entry: dict[str, Any]) -> str:
    if entry.get("source_type") == "baseline_rule_variant":
        return (
            "Variante governada de uma regra baseline. "
            "Use Adicionar para ativa-la ou substituir manualmente a baseline na politica."
        )
    rules = custom_entry_rules(entry)
    decisions = []
    for rule in rules:
        if rule.decision not in decisions:
            decisions.append(rule.decision)
    if not rules:
        return "Ativo criado na matriz."
    if len(rules) == 1:
        return (
            "Regra criada pela matriz. Use 'Editar na matriz' para reabrir o contexto salvo."
        )
    decision_text = ", ".join(decisions)
    return (
        "Composicao multicategoria criada pela matriz. "
        f"Decisoes presentes: {decision_text}. "
        "Use 'Editar na matriz' para reabrir o contexto salvo."
    )


def _legacy_build_used_custom_rule_card(entry: dict[str, Any]) -> html.Div:
    entry_id = str(entry.get("rule_id") or "")
    title = str(entry.get("rule_name") or entry_id or "Ativo criado na matriz")
    return html.Div(
        className="rule-library-card compact-rule-card matrix-rule-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div("M", className="rule-order-chip"),
                    html.Div(
                        [
                            html.Div(title, className="rule-title"),
                            html.Div(custom_entry_summary(entry), className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(custom_entry_tooltip(entry)),
                            html.Button(
                                "I",
                                id={"type": "open-custom-editor", "rule_id": entry_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Inspecionar ativo criado",
                            ),
                            html.Button(
                                "M",
                                id={
                                    "type": "edit-custom-rule",
                                    "rule_id": entry_id,
                                },
                                n_clicks=0,
                                className="icon-button",
                                title="Editar na matriz",
                            ),
                            html.Button(
                                "-",
                                id={
                                    "type": "remove-custom-rule",
                                    "rule_id": entry_id,
                                },
                                n_clicks=0,
                                className="icon-button icon-button-danger",
                                title="Remover da politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _legacy_build_available_custom_rule_card(entry: dict[str, Any]) -> html.Div:
    entry_id = str(entry.get("rule_id") or "")
    title = str(entry.get("rule_name") or entry_id or "Ativo criado na matriz")
    return html.Div(
        className="rule-library-card compact-rule-card matrix-rule-card available-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(title, className="rule-title"),
                            html.Div(custom_entry_summary(entry), className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(custom_entry_tooltip(entry)),
                            html.Button(
                                "I",
                                id={"type": "open-custom-editor", "rule_id": entry_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Inspecionar ativo criado",
                            ),
                            html.Button(
                                "M",
                                id={"type": "edit-custom-rule", "rule_id": entry_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Editar na matriz",
                            ),
                            html.Button(
                                "+",
                                id={"type": "add-custom-rule", "rule_id": entry_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Adicionar a politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _legacy_build_selected_feature_card(feature: DerivedFeatureDefinition) -> html.Div:
    return html.Div(
        className="rule-library-card compact-rule-card feature-card active-feature-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(feature.name, className="rule-title"),
                            html.Div("Feature derivada", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_feature_tooltip(feature)),
                            html.Button(
                                "✎",
                                id={
                                    "type": "open-feature-editor",
                                    "feature_id": feature.feature_id,
                                },
                                n_clicks=0,
                                className="icon-button",
                                title="Inspecionar feature derivada",
                            ),
                            html.Button(
                                "-",
                                id={"type": "remove-feature", "feature_id": feature.feature_id},
                                n_clicks=0,
                                className="icon-button icon-button-danger",
                                title="Remover da politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _legacy_build_available_feature_card(feature: DerivedFeatureDefinition) -> html.Div:
    return html.Div(
        className="rule-library-card compact-rule-card feature-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(feature.name, className="rule-title"),
                            html.Div("Feature derivada", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_feature_tooltip(feature)),
                            html.Button(
                                "✎",
                                id={
                                    "type": "open-feature-editor",
                                    "feature_id": feature.feature_id,
                                },
                                n_clicks=0,
                                className="icon-button",
                                title="Inspecionar feature derivada",
                            ),
                            html.Button(
                                "+",
                                id={"type": "add-feature", "feature_id": feature.feature_id},
                                n_clicks=0,
                                className="icon-button",
                                title="Adicionar a politica",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_used_rule_card(
    study: StudyContext,
    rule,
    snapshot: pl.DataFrame,
    *,
    order: int,
) -> html.Div:
    _ = study, snapshot
    return wrap_draggable_card(
        asset_id=baseline_asset_id(rule.rule_id),
        panel="used",
        class_name="rule-library-card compact-rule-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    build_chip_tooltip(
                        str(order),
                        f"Regra baseline na ordem {order} da politica candidata.",
                    ),
                    html.Div(
                        [
                            html.Div(rule.name, className="rule-title"),
                            html.Div("Regra baseline", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_rule_tooltip(rule)),
                            build_icon_button(
                                "E",
                                button_id={"type": "open-rule-editor", "rule_id": rule.rule_id},
                                title="Editar regra",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_available_rule_card(rule) -> html.Div:
    return wrap_draggable_card(
        asset_id=baseline_asset_id(rule.rule_id),
        panel="available",
        class_name="rule-library-card compact-rule-card available-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(rule.name, className="rule-title"),
                            html.Div("Baseline", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_rule_tooltip(rule)),
                            build_icon_button(
                                "E",
                                button_id={"type": "open-rule-editor", "rule_id": rule.rule_id},
                                title="Inspecionar e editar regra",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_used_custom_rule_card(entry: dict[str, Any]) -> html.Div:
    entry_id = str(entry.get("rule_id") or "")
    title = str(entry.get("rule_name") or entry_id or "Ativo criado na matriz")
    source_type = entry.get("source_type")
    is_variant = source_type == "baseline_rule_variant"
    is_optimization = source_type == "optimization_transfer"
    chip = "V" if is_variant else "O" if is_optimization else "M"
    chip_text = (
        "Variante governada de baseline."
        if is_variant
        else "Sugestao transferida do otimizador."
        if is_optimization
        else "Regra ou composicao criada na matriz."
    )
    card_class = (
        "rule-library-card compact-rule-card available-card"
        if is_variant
        else "rule-library-card compact-rule-card optimization-rule-card available-card"
        if is_optimization
        else "rule-library-card compact-rule-card matrix-rule-card"
    )
    return wrap_draggable_card(
        asset_id=custom_asset_id(entry_id),
        panel="used",
        class_name=card_class,
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    build_chip_tooltip(chip, chip_text),
                    html.Div(
                        [
                            html.Div(title, className="rule-title"),
                            html.Div(custom_entry_summary(entry), className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(custom_entry_tooltip(entry)),
                            *(
                                [
                                    build_icon_button(
                                        "E",
                                        button_id={
                                            "type": "open-custom-editor",
                                            "rule_id": entry_id,
                                        },
                                        title="Editar variante",
                                    )
                                ]
                                if is_variant
                                else [
                                    build_icon_button(
                                        "E",
                                        button_id={
                                            "type": "open-custom-editor",
                                            "rule_id": entry_id,
                                        },
                                        title="Editar sugestao",
                                    )
                                ]
                                if is_optimization
                                else [
                                    build_icon_button(
                                        "M",
                                        button_id={"type": "edit-custom-rule", "rule_id": entry_id},
                                        title="Editar na matriz",
                                    )
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_available_custom_rule_card(entry: dict[str, Any]) -> html.Div:
    entry_id = str(entry.get("rule_id") or "")
    title = str(entry.get("rule_name") or entry_id or "Ativo criado na matriz")
    source_type = entry.get("source_type")
    is_variant = source_type == "baseline_rule_variant"
    is_optimization = source_type == "optimization_transfer"
    chip = "V" if is_variant else "O" if is_optimization else "M"
    chip_text = (
        "Variante governada de baseline."
        if is_variant
        else "Sugestao transferida do otimizador."
        if is_optimization
        else "Regra ou composicao criada na matriz."
    )
    card_class = (
        "rule-library-card compact-rule-card available-card"
        if is_variant
        else "rule-library-card compact-rule-card optimization-rule-card available-card"
        if is_optimization
        else "rule-library-card compact-rule-card matrix-rule-card available-card"
    )
    return wrap_draggable_card(
        asset_id=custom_asset_id(entry_id),
        panel="available",
        class_name=card_class,
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    build_chip_tooltip(chip, chip_text),
                    html.Div(
                        [
                            html.Div(title, className="rule-title"),
                            html.Div(custom_entry_summary(entry), className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(custom_entry_tooltip(entry)),
                            *(
                                [
                                    build_icon_button(
                                        "E",
                                        button_id={
                                            "type": "open-custom-editor",
                                            "rule_id": entry_id,
                                        },
                                        title="Editar variante",
                                    )
                                ]
                                if is_variant
                                else [
                                    build_icon_button(
                                        "E",
                                        button_id={
                                            "type": "open-custom-editor",
                                            "rule_id": entry_id,
                                        },
                                        title="Editar sugestao",
                                    )
                                ]
                                if is_optimization
                                else [
                                    build_icon_button(
                                        "M",
                                        button_id={"type": "edit-custom-rule", "rule_id": entry_id},
                                        title="Editar na matriz",
                                    )
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_selected_feature_card(feature: DerivedFeatureDefinition) -> html.Div:
    return wrap_draggable_card(
        asset_id=feature_asset_id(feature.feature_id),
        panel="used",
        class_name="rule-library-card compact-rule-card feature-card active-feature-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(feature.name, className="rule-title"),
                            html.Div("Feature derivada", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_feature_tooltip(feature)),
                            build_icon_button(
                                "E",
                                button_id={
                                    "type": "open-feature-editor",
                                    "feature_id": feature.feature_id,
                                },
                                title="Inspecionar feature derivada",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_available_feature_card(feature: DerivedFeatureDefinition) -> html.Div:
    return wrap_draggable_card(
        asset_id=feature_asset_id(feature.feature_id),
        panel="available",
        class_name="rule-library-card compact-rule-card feature-card",
        children=[
            html.Div(
                className="rule-card-header",
                children=[
                    html.Div(
                        [
                            html.Div(feature.name, className="rule-title"),
                            html.Div("Feature derivada", className="rule-card-meta"),
                        ]
                    ),
                    html.Div(
                        className="rule-action-row",
                        children=[
                            build_info_tooltip(build_feature_tooltip(feature)),
                            build_icon_button(
                                "E",
                                button_id={
                                    "type": "open-feature-editor",
                                    "feature_id": feature.feature_id,
                                },
                                title="Inspecionar feature derivada",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_numeric_handle_options(
    study: StudyContext,
    snapshot: pl.DataFrame,
    used_rule_ids: list[str],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for rule in study.manifest.baseline_policy.rules:
        if rule.rule_id not in used_rule_ids:
            continue
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                if predicate.field not in snapshot.columns:
                    continue
                if not _is_numeric_dtype(snapshot.schema.get(predicate.field)):
                    continue
                handle = ui_predicate_handle(
                    rule.rule_id,
                    block_index,
                    predicate_index,
                    predicate.field,
                    predicate.operator.value,
                )
                options.append({"label": f"{rule.name} | {predicate.field}", "value": handle})
    return options


def build_study_meta(study: StudyContext, baseline_result: ScenarioResult) -> list[html.Div]:
    return [
        html.Div(study.manifest.name, className="panel-title panel-title-small"),
        html.Div(study.manifest.description, className="meta-copy"),
        html.Div(f"Workspace: {study.manifest.workspace.name}", className="meta-line"),
        html.Div(
            f"Familia de politica: {study.manifest.policy_family.name}",
            className="meta-line",
        ),
        html.Div(f"Versao baseline: {study.manifest.baseline_version}", className="meta-line"),
        html.Div(
            f"Registros avaliados: {baseline_result.metrics.records_evaluated}",
            className="meta-line",
        ),
    ]


def build_metric_cards(
    result: ScenarioResult,
    baseline_result: ScenarioResult | None = None,
    *,
    compact: bool = False,
) -> list[html.Div]:
    metrics = [
        (
            "Aprovacao",
            format_optional_pct(result.metrics.approval_rate),
            delta_text(result.metrics.approval_rate, baseline_result.metrics.approval_rate)
            if baseline_result
            else "",
        ),
        (
            "Lucro esperado",
            format_optional_money(result.metrics.expected_profit),
            delta_text_optional(
                result.metrics.expected_profit,
                baseline_result.metrics.expected_profit,
                scale=1.0,
            )
            if baseline_result
            else "",
        ),
        (
            "Indice de lucro",
            format_optional_number(result.metrics.expected_profit_index),
            delta_text_optional(
                result.metrics.expected_profit_index,
                baseline_result.metrics.expected_profit_index,
                scale=1.0,
            )
            if baseline_result
            else "",
        ),
        (
            "Risco",
            format_optional_pct(result.metrics.risk_estimate),
            delta_text_optional(
                result.metrics.risk_estimate,
                baseline_result.metrics.risk_estimate,
            )
            if baseline_result
            else "",
        ),
        (
            "Churn",
            format_optional_pct(result.metrics.churn_estimate),
            delta_text_optional(
                result.metrics.churn_estimate,
                baseline_result.metrics.churn_estimate,
            )
            if baseline_result
            else "",
        ),
        ("Fora do suporte", format_optional_pct(result.metrics.out_of_support_ratio), ""),
        ("Complexidade", format_optional_number(result.metrics.complexity_score), ""),
        (
            "Incerteza",
            result.metrics.uncertainty_label.title() if result.metrics.uncertainty_label else "N/A",
            "",
        ),
    ]
    card_class = "metric-card metric-card-compact" if compact else "metric-card"
    return [
        html.Div(
            className=card_class,
            children=[
                html.Div(label, className="metric-label"),
                html.Div(value, className="metric-value"),
                html.Div(delta, className="metric-delta"),
            ],
        )
        for label, value, delta in metrics
    ]


def build_comparison_table(
    baseline_result: ScenarioResult,
    scenario_result: ScenarioResult,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows = [
        build_metric_row(
            "Aprovacao",
            baseline_result.metrics.approval_rate,
            scenario_result.metrics.approval_rate,
            kind="pct",
        ),
        build_metric_row(
            "Analise manual",
            baseline_result.metrics.review_rate,
            scenario_result.metrics.review_rate,
            kind="pct",
        ),
        build_metric_row(
            "Rejeicao",
            baseline_result.metrics.rejection_rate,
            scenario_result.metrics.rejection_rate,
            kind="pct",
        ),
        build_metric_row(
            "Lucro esperado",
            baseline_result.metrics.expected_profit,
            scenario_result.metrics.expected_profit,
            kind="money",
        ),
        build_metric_row(
            "Indice de lucro",
            baseline_result.metrics.expected_profit_index,
            scenario_result.metrics.expected_profit_index,
            kind="number",
        ),
        build_metric_row(
            "Risco",
            baseline_result.metrics.risk_estimate,
            scenario_result.metrics.risk_estimate,
            kind="pct",
        ),
        build_metric_row(
            "Churn",
            baseline_result.metrics.churn_estimate,
            scenario_result.metrics.churn_estimate,
            kind="pct",
        ),
        build_metric_row(
            "Fora do suporte",
            baseline_result.metrics.out_of_support_ratio,
            scenario_result.metrics.out_of_support_ratio,
            kind="pct",
        ),
        build_metric_row(
            "Complexidade",
            baseline_result.metrics.complexity_score,
            scenario_result.metrics.complexity_score,
            kind="number",
        ),
    ]
    columns = [
        {"name": "Metrica", "id": "metric"},
        {"name": "Baseline", "id": "baseline"},
        {"name": "Candidata", "id": "candidate"},
        {"name": "Delta", "id": "delta"},
    ]
    return rows, columns


def build_metric_row(
    name: str,
    baseline: float | None,
    candidate: float | None,
    *,
    kind: str,
) -> dict[str, str]:
    return {
        "metric": name,
        "baseline": format_by_kind(baseline, kind),
        "candidate": format_by_kind(candidate, kind),
        "delta": format_delta_by_kind(baseline, candidate, kind),
    }


def build_matrix_summary(
    snapshot: pl.DataFrame,
    event_column: str | None = None,
) -> list[html.Div]:
    if snapshot.is_empty():
        return [
            html.Div(
                className="metric-card metric-card-compact",
                children=[
                    html.Div("Publico elegivel", className="metric-label"),
                    html.Div("0", className="metric-value"),
                    html.Div("Nenhum registro apos regras e filtros", className="metric-delta"),
                ],
            )
        ]

    event_rate = None
    if event_column and event_column in snapshot.columns:
        event_rate = snapshot.select(pl.col(event_column).mean()).item()
    return [
        html.Div(
            className="metric-card metric-card-compact",
            children=[
                html.Div("Publico elegivel", className="metric-label"),
                html.Div(f"{snapshot.height:,}".replace(",", "."), className="metric-value"),
                html.Div("Registros remanescentes apos as regras ativas", className="metric-delta"),
            ],
        ),
        html.Div(
            className="metric-card metric-card-compact",
            children=[
                html.Div("Taxa de evento", className="metric-label"),
                html.Div(format_optional_pct(event_rate), className="metric-value"),
                html.Div("Calculada no publico usado pela matriz", className="metric-delta"),
            ],
        ),
    ]
