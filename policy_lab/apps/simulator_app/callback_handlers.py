from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import plotly.graph_objects as go
import polars as pl
from dash import ctx, dcc, html, no_update
from dash.exceptions import MissingCallbackContextException

from policy_lab.domain import (
    DecisionRuleDefinition,
    PolicyDefinition,
    ScenarioDefinition,
    ScenarioResult,
    SearchObjectiveSpec,
    SearchStrategy,
)

from .components import (
    build_asset_editor_empty_state,
    build_comparison_table,
    build_feature_editor_content,
    build_matrix_summary,
    build_metric_cards,
    build_optimization_transfer_editor_content,
    build_rule_editor_content,
    build_rule_library,
    build_study_meta,
    build_variant_rule_editor_content,
)
from .figures import (
    build_comparison_figure,
    build_matrix_preview,
    build_recommendation_figure,
    build_rule_flow_figure,
    build_transition_figure,
    empty_figure,
)
from .formatting import format_optional_number, format_optional_pct
from .runtime import (
    created_rule_repository,
    feature_repository,
    load_study,
    manual_config_repository,
    orchestrator,
    study_repository,
)
from .services import (
    append_rule_to_policy,
    apply_optional_matrix_filter,
    apply_variant_to_rule_state,
    available_matrix_columns,
    available_segment_columns,
    baseline_asset_id,
    build_candidate_policy,
    build_matrix_rule_set,
    custom_asset_id,
    custom_entry_predicate_handle,
    custom_rule_entries_from_store,
    custom_rule_store_payload,
    custom_rules_from_store,
    default_predicate_editor_state,
    default_rule_state,
    enrich_rule_state,
    extract_anchor_population_for_predicate,
    extract_eligible_population,
    feature_asset_id,
    feature_ids_used_by_rules,
    filter_snapshot,
    find_cutoff_suggestion,
    matrix_axis_spec,
    next_variant_name,
    normalize_predicate_editor_state,
    normalize_rule_state,
    parse_asset_id,
    reset_editor_state_for_rule,
    slugify,
    ui_predicate_handle,
    unique_asset_id,
    unique_rule_id,
    value_from_handle,
    variant_entry_from_editor_state,
)

DEFAULT_MANUAL_WORKSPACE_ID = "default"
DEFAULT_MANUAL_AUTHOR = "local_user"


def render_tab(tab_name: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    hidden = {"display": "none"}
    visible = {"display": "block"}
    if tab_name == "rule_composition":
        return hidden, visible, hidden
    if tab_name == "automatic_optimization":
        return hidden, hidden, visible
    return visible, hidden, hidden


def state_for_study(
    state: dict[str, Any] | None,
    study_id: str | None,
) -> dict[str, Any]:
    if not state or not study_id or state.get("study_id") != study_id:
        return {}
    return state


def sanitize_selected_values(
    selected_values: list[Any] | None,
    allowed_values: list[str],
) -> list[str]:
    allowed = {str(value) for value in allowed_values}
    return [str(value) for value in selected_values or [] if str(value) in allowed]


def available_month_values(study, frame: pl.DataFrame | None = None) -> list[str]:
    snapshot = frame if frame is not None else study_repository.load_snapshot(study)
    date_column = study.manifest.snapshot.date_column
    if not date_column or date_column not in snapshot.columns:
        return []
    return sorted(
        snapshot.get_column(date_column).cast(pl.String).str.slice(0, 6).unique().to_list()
    )


def available_segment_values(
    study,
    frame: pl.DataFrame,
    segment_field: str | None,
) -> list[str]:
    if not segment_field or segment_field not in frame.columns:
        return []
    values = frame.get_column(segment_field).drop_nulls().unique().to_list()
    return sorted(str(value) for value in values)


def current_manual_filters(
    study,
    manual_ui_state: dict[str, Any] | None,
) -> dict[str, Any]:
    full_snapshot = study_repository.load_snapshot(study)
    stored_state = state_for_study(manual_ui_state, study.study_id)
    stored_filters = stored_state.get("filters", {})

    available_months = available_month_values(study, full_snapshot)
    resolved_months = (
        sanitize_selected_values(stored_filters.get("months"), available_months)
        or available_months
    )

    segment_columns = available_segment_columns(full_snapshot, study)
    stored_segment_field = stored_filters.get("segment_field")
    if stored_segment_field in segment_columns:
        resolved_segment_field = stored_segment_field
    else:
        resolved_segment_field = segment_columns[0] if segment_columns else None

    month_filtered_snapshot = filter_snapshot(
        full_snapshot,
        months=resolved_months,
        segment_field=None,
        segment_values=None,
        date_column=study.manifest.snapshot.date_column,
    )
    allowed_segment_values = available_segment_values(
        study,
        month_filtered_snapshot,
        resolved_segment_field,
    )
    resolved_segment_values = (
        sanitize_selected_values(
            stored_filters.get("segment_values"),
            allowed_segment_values,
        )
        or allowed_segment_values
    )

    return {
        "months": resolved_months,
        "segment_field": resolved_segment_field,
        "segment_values": resolved_segment_values,
    }


def full_scope_manual_filters(
    study,
    manual_ui_state: dict[str, Any] | None,
) -> dict[str, Any]:
    full_snapshot = study_repository.load_snapshot(study)
    available_months = available_month_values(study, full_snapshot)
    segment_columns = available_segment_columns(full_snapshot, study)
    stored_state = state_for_study(manual_ui_state, study.study_id)
    stored_filters = stored_state.get("filters", {})
    stored_segment_field = stored_filters.get("segment_field")
    if stored_segment_field in segment_columns:
        resolved_segment_field = stored_segment_field
    else:
        resolved_segment_field = segment_columns[0] if segment_columns else None
    resolved_segment_values = available_segment_values(
        study,
        full_snapshot,
        resolved_segment_field,
    )
    return {
        "months": available_months,
        "segment_field": resolved_segment_field,
        "segment_values": resolved_segment_values,
    }


def matrix_edit_alert_message(
    *,
    explicit_months: list[str],
    explicit_segment_field: str | None,
    explicit_segment_values: list[str],
    restored_filters: dict[str, Any],
    used_manual_fallback: bool,
) -> str | None:
    has_explicit_filters = bool(
        explicit_months or explicit_segment_field or explicit_segment_values
    )
    if not has_explicit_filters:
        return None

    if used_manual_fallback:
        return (
            "A regra selecionada para edicao foi criada em um snapshot diferente e "
            "algumas categorias filtradas para periodo (meses) e segmento nao foram "
            "observadas no snapshot atual. Foi mantido os filtros que ja estavam "
            'selecionados na aba de "Laboratorio Manual".'
        )

    month_description = ", ".join(explicit_months) if explicit_months else "todos os meses"
    if explicit_segment_field:
        segment_values = (
            ", ".join(explicit_segment_values)
            if explicit_segment_values
            else ", ".join(restored_filters.get("segment_values", [])) or "todos os valores"
        )
        segment_description = f"{explicit_segment_field} - {segment_values}"
    else:
        segment_description = "sem filtro de segmento"
    return (
        "A regra selecionada para edicao foi criada com filtro nas variaveis:\n"
        f"meses - {month_description}\n"
        "e\n"
        f"segmento - {segment_description}"
    )


def normalized_saved_edit_filters(
    study,
    eligible_filters: dict[str, Any],
    manual_ui_state: dict[str, Any] | None,
) -> dict[str, Any]:
    current_filters = current_manual_filters(study, manual_ui_state)
    full_scope_filters = full_scope_manual_filters(study, manual_ui_state)
    full_snapshot = study_repository.load_snapshot(study)
    available_months = available_month_values(study, full_snapshot)
    explicit_months = [str(month) for month in eligible_filters.get("months", [])]
    explicit_segment_field = eligible_filters.get("segment_field")
    explicit_segment_values = [
        str(value) for value in eligible_filters.get("segment_values", [])
    ]
    has_explicit_filters = bool(
        explicit_months or explicit_segment_field or explicit_segment_values
    )
    if not has_explicit_filters:
        return {
            "has_explicit_filters": False,
            "filters_compatible": True,
            "current_filters": current_filters,
            "full_scope_filters": full_scope_filters,
            "restore_filters": full_scope_filters,
            "explicit_months": explicit_months,
            "explicit_segment_field": explicit_segment_field,
            "explicit_segment_values": explicit_segment_values,
        }

    valid_months = sanitize_selected_values(explicit_months, available_months)
    month_mismatch = bool(explicit_months) and len(valid_months) != len(explicit_months)
    segment_columns = available_segment_columns(full_snapshot, study)
    segment_mismatch = False
    restore_filters = dict(current_filters)
    if explicit_months:
        restore_filters["months"] = valid_months or current_filters["months"]
    if explicit_segment_field:
        if explicit_segment_field not in segment_columns:
            segment_mismatch = True
        else:
            restore_filters["segment_field"] = explicit_segment_field
            segment_snapshot = filter_snapshot(
                full_snapshot,
                months=restore_filters["months"],
                segment_field=None,
                segment_values=None,
                date_column=study.manifest.snapshot.date_column,
            )
            allowed_segment_values = available_segment_values(
                study,
                segment_snapshot,
                explicit_segment_field,
            )
            valid_segment_values = sanitize_selected_values(
                explicit_segment_values,
                allowed_segment_values,
            )
            segment_mismatch = len(valid_segment_values) != len(explicit_segment_values)
            restore_filters["segment_values"] = (
                valid_segment_values or allowed_segment_values
            )

    return {
        "has_explicit_filters": True,
        "filters_compatible": not (month_mismatch or segment_mismatch),
        "current_filters": current_filters,
        "full_scope_filters": full_scope_filters,
        "restore_filters": restore_filters,
        "explicit_months": explicit_months,
        "explicit_segment_field": explicit_segment_field,
        "explicit_segment_values": explicit_segment_values,
    }


def build_matrix_edit_confirmation_message(
    rule_name: str,
    resolution: dict[str, Any],
) -> str:
    policy_notice = (
        "O publico elegivel tambem depende das regras ativas e da configuracao "
        "mais recente simulada no Laboratorio Manual. A escolha abaixo tambem "
        "define qual contexto sera refletido no pool inicial e nos resultados "
        "visuais do Laboratorio Manual."
    )
    if not resolution["has_explicit_filters"]:
        return (
            f"A regra '{rule_name}' nao possui filtros salvos de meses/segmento.\n\n"
            "Se confirmar, a edicao sera aberta com o escopo completo do snapshot atual. "
            "Se cancelar, o DPL mantera os filtros atualmente selecionados no "
            "Laboratorio Manual.\n\n"
            f"{policy_notice}"
        )

    if not resolution["filters_compatible"]:
        return (
            "A regra selecionada para edicao foi criada em um snapshot diferente e "
            "algumas categorias filtradas para periodo (meses) e segmento nao foram "
            "observadas no snapshot atual.\n\n"
            "Se confirmar, a regra sera aberta com os filtros atualmente selecionados "
            'na aba de "Laboratorio Manual". Se cancelar, nenhuma alteracao sera feita.\n\n'
            f"{policy_notice}"
        )

    saved_description = matrix_edit_alert_message(
        explicit_months=resolution["explicit_months"],
        explicit_segment_field=resolution["explicit_segment_field"],
        explicit_segment_values=resolution["explicit_segment_values"],
        restored_filters=resolution["restore_filters"],
        used_manual_fallback=False,
    ) or ""
    return (
        f"{saved_description}\n\n"
        "Os mesmos intervalos usados na criacao da regra serao replicados nesta edicao. "
        "Se confirmar, esse contexto sera restaurado para a edicao. "
        "Se cancelar, o DPL mantera os filtros atualmente selecionados no "
        "Laboratorio Manual.\n\n"
        f"{policy_notice}"
    )


def resolved_manual_filters_for_matrix_edit(
    study,
    eligible_filters: dict[str, Any],
    manual_ui_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    resolution = normalized_saved_edit_filters(study, eligible_filters, manual_ui_state)
    if not resolution["has_explicit_filters"]:
        return resolution["full_scope_filters"], None
    if not resolution["filters_compatible"]:
        return (
            resolution["current_filters"],
            matrix_edit_alert_message(
                explicit_months=resolution["explicit_months"],
                explicit_segment_field=resolution["explicit_segment_field"],
                explicit_segment_values=resolution["explicit_segment_values"],
                restored_filters=resolution["current_filters"],
                used_manual_fallback=True,
            ),
        )
    return (
        resolution["restore_filters"],
        matrix_edit_alert_message(
            explicit_months=resolution["explicit_months"],
            explicit_segment_field=resolution["explicit_segment_field"],
            explicit_segment_values=resolution["explicit_segment_values"],
            restored_filters=resolution["restore_filters"],
            used_manual_fallback=False,
        ),
    )


def current_triggered_id() -> Any:
    try:
        return ctx.triggered_id
    except MissingCallbackContextException:
        return None


def manual_config_payload(
    study_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "study_id": study_id,
        "entries": entries,
    }


def manual_config_entries_from_store(
    study_id: str,
    config_store: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not config_store or config_store.get("study_id") != study_id:
        return []
    entries = config_store.get("entries", [])
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def find_manual_config_entry(
    entries: list[dict[str, Any]],
    config_id: str | None,
) -> dict[str, Any] | None:
    if not config_id:
        return None
    for entry in entries:
        if str(entry.get("config_id") or "") == str(config_id):
            return dict(entry)
    return None


def manual_config_option_label(entry: dict[str, Any]) -> str:
    name = str(entry.get("name") or "Workspace manual")
    workspace_id = str(entry.get("workspace_id") or DEFAULT_MANUAL_WORKSPACE_ID)
    author = str(entry.get("author") or DEFAULT_MANUAL_AUTHOR)
    return f"{name} | {workspace_id} | {author}"


def is_asset_active(
    asset_token: str,
    used_asset_ids: list[str],
    selected_feature_ids: list[str],
) -> bool:
    kind, raw_id = parse_asset_id(asset_token)
    if kind == "feature":
        return raw_id in selected_feature_ids
    return asset_token in used_asset_ids


def remove_asset_from_state_lists(
    asset_token: str,
    used_asset_ids: list[str],
    selected_feature_ids: list[str],
) -> tuple[list[str], list[str]]:
    kind, raw_id = parse_asset_id(asset_token)
    next_used_assets = [item for item in used_asset_ids if item != asset_token]
    if kind == "feature":
        next_selected_features = [
            feature_id for feature_id in selected_feature_ids if feature_id != raw_id
        ]
    else:
        next_selected_features = list(selected_feature_ids)
    return next_used_assets, next_selected_features


def add_asset_to_used_lists(
    asset_token: str,
    *,
    target_asset_id: str | None,
    placement: str,
    used_asset_ids: list[str],
    selected_feature_ids: list[str],
    custom_entry_map: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    kind, raw_id = parse_asset_id(asset_token)
    next_used_assets, next_selected_features = remove_asset_from_state_lists(
        asset_token,
        used_asset_ids,
        selected_feature_ids,
    )

    if kind == "feature":
        if raw_id not in next_selected_features:
            next_selected_features.append(raw_id)
    elif kind == "baseline":
        conflicting_variant_token = None
        for item in next_used_assets:
            item_kind, item_raw_id = parse_asset_id(item)
            if item_kind != "custom":
                continue
            entry = custom_entry_map.get(item_raw_id, {})
            if (
                entry.get("source_type") == "baseline_rule_variant"
                and str(entry.get("origin_rule_id") or "") == raw_id
            ):
                conflicting_variant_token = item
                break
        if conflicting_variant_token is not None:
            next_used_assets = [
                item for item in next_used_assets if item != conflicting_variant_token
            ]
    elif kind == "custom":
        entry = custom_entry_map.get(raw_id, {})
        if entry.get("source_type") == "baseline_rule_variant" and entry.get("origin_rule_id"):
            origin_token = baseline_asset_id(str(entry["origin_rule_id"]))
            if origin_token in next_used_assets:
                origin_index = next_used_assets.index(origin_token)
                next_used_assets[origin_index] = asset_token
                return next_used_assets, next_selected_features

    insert_index = len(next_used_assets)
    if target_asset_id and target_asset_id in next_used_assets:
        target_index = next_used_assets.index(target_asset_id)
        insert_index = target_index + (1 if placement == "after" else 0)

    next_used_assets.insert(insert_index, asset_token)
    return next_used_assets, next_selected_features


def load_custom_rule_store(study_id: str) -> dict[str, Any]:
    if not study_id:
        return {}
    study = load_study(study_id)
    entries = created_rule_repository.load(study)
    return custom_rule_store_payload(study, entries)


def load_manual_config_store(study_id: str) -> dict[str, Any]:
    if not study_id:
        return {}
    study = load_study(study_id)
    entries = manual_config_repository.load(study)
    return manual_config_payload(study.study_id, entries)


def update_rule_state(
    study_id: str,
    _add_rule_clicks: list[int],
    _remove_rule_clicks: list[int],
    _move_up_clicks: list[int],
    _move_down_clicks: list[int],
    _add_custom_rule_clicks: list[int],
    _remove_custom_rule_clicks: list[int],
    _add_feature_clicks: list[int],
    _remove_feature_clicks: list[int],
    custom_rule_state: dict[str, Any] | None,
    current_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not study_id:
        return {}

    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    if not current_state or current_state.get("study_id") != study_id:
        return default_rule_state(
            study,
            custom_rules,
            custom_rule_entries=custom_entries,
        )

    triggered_id = current_triggered_id()
    if triggered_id == "study-dropdown":
        return default_rule_state(
            study,
            custom_rules,
            custom_rule_entries=custom_entries,
        )

    state = normalize_rule_state(
        study,
        current_state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    custom_entry_map = {
        str(entry.get("rule_id")): dict(entry)
        for entry in custom_entries
        if entry.get("rule_id")
    }
    used_asset_ids = list(state.get("used_asset_ids", []))
    selected_feature_ids = list(state["selected_feature_ids"])

    if not isinstance(triggered_id, dict):
        return enrich_rule_state(
            study,
            {
                "study_id": study_id,
                "used_asset_ids": used_asset_ids,
                "selected_feature_ids": selected_feature_ids,
            },
            custom_rules=custom_rules,
            custom_rule_entries=custom_entries,
        )

    item_type = triggered_id.get("type")
    if item_type == "add-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = baseline_asset_id(rule_id)
        if not is_asset_active(asset_token, used_asset_ids, selected_feature_ids):
            used_asset_ids, selected_feature_ids = add_asset_to_used_lists(
                asset_token,
                target_asset_id=None,
                placement="append",
                used_asset_ids=used_asset_ids,
                selected_feature_ids=selected_feature_ids,
                custom_entry_map=custom_entry_map,
            )
    elif item_type == "remove-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = baseline_asset_id(rule_id)
        used_asset_ids, selected_feature_ids = remove_asset_from_state_lists(
            asset_token,
            used_asset_ids,
            selected_feature_ids,
        )
    elif item_type == "move-up-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = baseline_asset_id(rule_id)
        if asset_token in used_asset_ids:
            index = used_asset_ids.index(asset_token)
            if index > 0:
                used_asset_ids[index - 1], used_asset_ids[index] = (
                    used_asset_ids[index],
                    used_asset_ids[index - 1],
                )
    elif item_type == "move-down-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = baseline_asset_id(rule_id)
        if asset_token in used_asset_ids:
            index = used_asset_ids.index(asset_token)
            if index < len(used_asset_ids) - 1:
                used_asset_ids[index + 1], used_asset_ids[index] = (
                    used_asset_ids[index],
                    used_asset_ids[index + 1],
                )
    elif item_type == "add-custom-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = custom_asset_id(rule_id)
        if not is_asset_active(asset_token, used_asset_ids, selected_feature_ids):
            used_asset_ids, selected_feature_ids = add_asset_to_used_lists(
                asset_token,
                target_asset_id=None,
                placement="append",
                used_asset_ids=used_asset_ids,
                selected_feature_ids=selected_feature_ids,
                custom_entry_map=custom_entry_map,
            )
    elif item_type == "remove-custom-rule":
        rule_id = triggered_id["rule_id"]
        asset_token = custom_asset_id(rule_id)
        used_asset_ids, selected_feature_ids = remove_asset_from_state_lists(
            asset_token,
            used_asset_ids,
            selected_feature_ids,
        )
    elif item_type == "add-feature":
        feature_id = triggered_id["feature_id"]
        asset_token = feature_asset_id(feature_id)
        if not is_asset_active(asset_token, used_asset_ids, selected_feature_ids):
            used_asset_ids, selected_feature_ids = add_asset_to_used_lists(
                asset_token,
                target_asset_id=None,
                placement="append",
                used_asset_ids=used_asset_ids,
                selected_feature_ids=selected_feature_ids,
                custom_entry_map=custom_entry_map,
            )
    elif item_type == "remove-feature":
        feature_id = triggered_id["feature_id"]
        used_asset_ids, selected_feature_ids = remove_asset_from_state_lists(
            feature_asset_id(feature_id),
            used_asset_ids,
            selected_feature_ids,
        )

    return enrich_rule_state(
        study,
        {
            "study_id": study_id,
            "used_asset_ids": used_asset_ids,
            "selected_feature_ids": selected_feature_ids,
        },
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )


def apply_rule_library_drag_drop(
    payload_raw: str | None,
    study_id: str | None,
    current_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not payload_raw or not study_id:
        return no_update

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return no_update

    asset_token = str(payload.get("asset_id") or "")
    target_panel = str(payload.get("target_panel") or "")
    target_asset_id = payload.get("target_asset_id")
    placement = str(payload.get("placement") or "append")
    if not asset_token or target_panel not in {"used", "available"}:
        return no_update

    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    state = normalize_rule_state(
        study,
        current_state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    custom_entry_map = {
        str(entry.get("rule_id")): dict(entry)
        for entry in custom_entries
        if entry.get("rule_id")
    }
    used_asset_ids = list(state.get("used_asset_ids", []))
    selected_feature_ids = list(state.get("selected_feature_ids", []))

    if target_panel == "available":
        used_asset_ids, selected_feature_ids = remove_asset_from_state_lists(
            asset_token,
            used_asset_ids,
            selected_feature_ids,
        )
    else:
        used_asset_ids, selected_feature_ids = add_asset_to_used_lists(
            asset_token,
            target_asset_id=str(target_asset_id) if target_asset_id else None,
            placement=placement,
            used_asset_ids=used_asset_ids,
            selected_feature_ids=selected_feature_ids,
            custom_entry_map=custom_entry_map,
        )

    return enrich_rule_state(
        study,
        {
            "study_id": study_id,
            "used_asset_ids": used_asset_ids,
            "selected_feature_ids": selected_feature_ids,
        },
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )


def load_filter_controls(
    study_id: str,
    manual_state: dict[str, Any] | None,
) -> tuple[Any, ...]:
    if not study_id:
        empty = []
        return empty, empty, empty, None

    study = load_study(study_id)
    full_snapshot = study_repository.load_snapshot(study)
    available_months = available_month_values(study, full_snapshot)
    segment_columns = available_segment_columns(full_snapshot, study)
    stored_state = state_for_study(manual_state, study_id)
    stored_filters = stored_state.get("filters", {})
    selected_months = (
        sanitize_selected_values(stored_filters.get("months"), available_months)
        if stored_state
        else available_months
    )
    selected_segment_field = stored_filters.get("segment_field")
    if selected_segment_field not in segment_columns:
        selected_segment_field = segment_columns[0] if segment_columns else None
    return (
        [{"label": month, "value": month} for month in available_months],
        selected_months,
        [{"label": column, "value": column} for column in segment_columns],
        selected_segment_field,
    )


def load_manual_config_controls(
    study_id: str,
    config_store: dict[str, Any] | None,
    current_config_state: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], str | None, str]:
    if not study_id:
        return [], None, "Workspace manual"
    entries = manual_config_entries_from_store(study_id, config_store)
    options = [
        {
            "label": manual_config_option_label(entry),
            "value": str(entry.get("config_id") or ""),
        }
        for entry in entries
        if entry.get("config_id")
    ]
    current_config_id = None
    current_name = "Workspace manual"
    if current_config_state and current_config_state.get("study_id") == study_id:
        current_config_id = current_config_state.get("config_id")
        if current_config_state.get("name"):
            current_name = str(current_config_state["name"])
    entry = find_manual_config_entry(entries, current_config_id)
    if entry is not None:
        current_name = str(entry.get("name") or current_name)
        return options, str(entry.get("config_id") or ""), current_name
    return options, None, current_name


def update_baseline_context(
    study_id: str,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
) -> tuple[Any, list[html.Div]]:
    if not study_id:
        return "Nenhum estudo encontrado.", []

    study = load_study(study_id)
    full_snapshot = study_repository.load_snapshot(study)
    filtered_snapshot = filter_snapshot(
        full_snapshot,
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    filtered_baseline_bundle = orchestrator.run_baseline_with_snapshot(
        study,
        snapshot_override=filtered_snapshot,
    )
    return (
        build_study_meta(study, filtered_baseline_bundle.result),
        build_metric_cards(filtered_baseline_bundle.result, compact=True),
    )


def persist_manual_ui_state(
    study_id: str,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    cutoff_objective: str | None,
    cutoff_handle: str | None,
    target_value: float | None,
    current_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not study_id:
        return current_state or {}
    return {
        "study_id": study_id,
        "filters": {
            "months": months or [],
            "segment_field": segment_field,
            "segment_values": segment_values or [],
        },
        "cutoff": {
            "objective": cutoff_objective or "approval",
            "handle": cutoff_handle,
            "target_value": target_value,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_segment_values(
    study_id: str,
    segment_field: str | None,
    months: list[str] | None,
    manual_state: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], list[str]]:
    if not study_id or not segment_field:
        return [], []

    study = load_study(study_id)
    snapshot = filter_snapshot(
        study_repository.load_snapshot(study),
        months=months,
        segment_field=None,
        segment_values=None,
        date_column=study.manifest.snapshot.date_column,
    )
    values = sorted(snapshot.get_column(segment_field).drop_nulls().unique().to_list())
    value_options = [str(value) for value in values]
    stored_state = state_for_study(manual_state, study_id)
    stored_filters = stored_state.get("filters", {})
    stored_values = (
        stored_filters.get("segment_values")
        if stored_filters.get("segment_field") == segment_field
        else []
    )
    selected_values = (
        sanitize_selected_values(stored_values, value_options)
        if stored_filters.get("segment_field") == segment_field
        else value_options
    )
    return [{"label": value, "value": value} for value in value_options], selected_values


def restore_cutoff_controls(
    study_id: str,
    manual_state: dict[str, Any] | None,
) -> tuple[str, str | None, float]:
    stored_state = state_for_study(manual_state, study_id)
    cutoff = stored_state.get("cutoff", {})
    return (
        cutoff.get("objective") or "approval",
        cutoff.get("handle"),
        cutoff.get("target_value") if cutoff.get("target_value") is not None else 80.0,
    )


def save_manual_config(
    n_clicks: int,
    study_id: str,
    config_name: str | None,
    current_config_state: dict[str, Any] | None,
    manual_ui_state: dict[str, Any] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if not n_clicks or not study_id:
        return no_update, no_update, ""

    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    normalized_rule_state = normalize_rule_state(
        study,
        rule_state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    normalized_manual_state = state_for_study(manual_ui_state, study_id) or {
        "study_id": study_id,
        "filters": {
            "months": [],
            "segment_field": None,
            "segment_values": [],
        },
        "cutoff": {
            "objective": cutoff_objective or "approval",
            "handle": cutoff_handle,
            "target_value": cutoff_value if cutoff_value is not None else 80.0,
        },
    }
    active_cutoff_override = resolve_active_cutoff_override(
        study_id,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
    )
    persisted_entries = manual_config_repository.load(study)
    requested_name = (config_name or "").strip() or "Workspace manual"
    loaded_entry = None
    if current_config_state and current_config_state.get("study_id") == study_id:
        loaded_entry = find_manual_config_entry(
            persisted_entries,
            str(current_config_state.get("config_id") or ""),
        )

    now = datetime.now(timezone.utc).isoformat()
    can_update_loaded = (
        loaded_entry is not None
        and str(loaded_entry.get("workspace_id") or DEFAULT_MANUAL_WORKSPACE_ID)
        == DEFAULT_MANUAL_WORKSPACE_ID
        and requested_name == str(loaded_entry.get("name") or "")
    )

    if can_update_loaded:
        updated_entry = dict(loaded_entry)
        updated_entry["name"] = requested_name
        updated_entry["updated_at"] = now
        updated_entry["manual_ui_state"] = normalized_manual_state
        updated_entry["rule_state"] = normalized_rule_state
        updated_entry["cutoff_override"] = active_cutoff_override
        next_entries = [
            updated_entry
            if str(entry.get("config_id") or "") == str(updated_entry["config_id"])
            else dict(entry)
            for entry in persisted_entries
        ]
        manual_config_repository.save(study, next_entries)
        current_payload = {
            "study_id": study_id,
            "config_id": updated_entry["config_id"],
            "name": updated_entry["name"],
            "workspace_id": updated_entry["workspace_id"],
            "author": updated_entry["author"],
        }
        return (
            manual_config_payload(study_id, next_entries),
            current_payload,
            f"Workspace manual '{requested_name}' atualizado com sucesso.",
        )

    config_slug = slugify(requested_name) or "workspace-manual"
    next_config_id = unique_rule_id(
        config_slug,
        {
            str(entry.get("config_id") or "")
            for entry in persisted_entries
            if entry.get("config_id")
        },
    )
    new_entry = {
        "config_id": next_config_id,
        "name": requested_name,
        "workspace_id": DEFAULT_MANUAL_WORKSPACE_ID,
        "author": DEFAULT_MANUAL_AUTHOR,
        "parent_config_id": str(loaded_entry.get("config_id") or "")
        if loaded_entry is not None
        else None,
        "created_at": now,
        "updated_at": now,
        "manual_ui_state": normalized_manual_state,
        "rule_state": normalized_rule_state,
        "cutoff_override": active_cutoff_override,
    }
    next_entries = [*persisted_entries, new_entry]
    manual_config_repository.save(study, next_entries)
    current_payload = {
        "study_id": study_id,
        "config_id": new_entry["config_id"],
        "name": new_entry["name"],
        "workspace_id": new_entry["workspace_id"],
        "author": new_entry["author"],
    }
    derivation_message = (
        " Um novo workspace derivado foi criado a partir da configuracao carregada."
        if loaded_entry is not None
        else ""
    )
    return (
        manual_config_payload(study_id, next_entries),
        current_payload,
        f"Workspace manual '{requested_name}' salvo com sucesso.{derivation_message}",
    )


def load_manual_config(
    n_clicks: int,
    study_id: str,
    selected_config_id: str | None,
    config_store: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any],
    list[str],
    str | None,
    list[str],
    str,
    str | None,
    float,
    Any,
    list[dict[str, Any]],
    list[dict[str, str]],
    go.Figure,
    go.Figure,
    go.Figure,
    dict[str, Any],
    str,
]:
    if not n_clicks or not study_id or not selected_config_id:
        return (no_update,) * 18

    study = load_study(study_id)
    entries = manual_config_entries_from_store(study_id, config_store)
    entry = find_manual_config_entry(entries, selected_config_id)
    if entry is None:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            "Workspace manual selecionado nao foi encontrado.",
        )

    saved_manual_state = dict(entry.get("manual_ui_state") or {})
    resolved_filters = current_manual_filters(study, saved_manual_state)
    cutoff = dict(saved_manual_state.get("cutoff") or {})
    cutoff_objective = cutoff.get("objective") or "approval"
    cutoff_handle = cutoff.get("handle")
    cutoff_target_value = (
        cutoff.get("target_value") if cutoff.get("target_value") is not None else 80.0
    )
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    normalized_rule_state = normalize_rule_state(
        study,
        entry.get("rule_state"),
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    results = manual_scenario_outputs(
        n_clicks=1,
        study_id=study_id,
        months=resolved_filters["months"],
        segment_field=resolved_filters["segment_field"],
        segment_values=resolved_filters["segment_values"],
        rule_state=normalized_rule_state,
        custom_rule_state=custom_rule_state,
        cutoff_override=entry.get("cutoff_override"),
        cutoff_handle=cutoff_handle,
        cutoff_objective=cutoff_objective,
        cutoff_value=cutoff_target_value,
        predicate_editor_state=None,
    )
    current_payload = {
        "study_id": study_id,
        "config_id": str(entry.get("config_id") or ""),
        "name": str(entry.get("name") or "Workspace manual"),
        "workspace_id": str(entry.get("workspace_id") or DEFAULT_MANUAL_WORKSPACE_ID),
        "author": str(entry.get("author") or DEFAULT_MANUAL_AUTHOR),
    }
    refreshed_manual_state = {
        "study_id": study_id,
        "filters": resolved_filters,
        "cutoff": {
            "objective": cutoff_objective,
            "handle": cutoff_handle,
            "target_value": cutoff_target_value,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return (
        refreshed_manual_state,
        normalized_rule_state,
        entry.get("cutoff_override"),
        current_payload,
        resolved_filters["months"],
        resolved_filters["segment_field"],
        resolved_filters["segment_values"],
        cutoff_objective,
        cutoff_handle,
        cutoff_target_value,
        results[0],
        results[1],
        results[2],
        results[3],
        results[4],
        results[5],
        results[6],
        f"Workspace manual '{current_payload['name']}' carregado com sucesso.",
    )


def render_rule_library(
    study_id: str,
    state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
) -> tuple[list[html.Div], list[dict[str, str]]]:
    if not study_id:
        return [], []

    study = load_study(study_id)
    snapshot = matrix_base_snapshot(study)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    rule_state = normalize_rule_state(
        study,
        state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    library_children, cutoff_options = build_rule_library(
        study,
        rule_state,
        snapshot,
        custom_entries,
    )
    return library_children, cutoff_options


def load_predicate_editor_state(study_id: str) -> dict[str, Any]:
    if not study_id:
        return {}
    study = load_study(study_id)
    return default_predicate_editor_state(study)


def update_asset_editor_state(
    study_id: str,
    _open_rule_clicks: list[int],
    _open_feature_clicks: list[int],
    _open_custom_clicks: list[int],
    close_clicks: int,
    current_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not study_id:
        return {}

    triggered_id = current_triggered_id()
    triggered_value = None
    try:
        if ctx.triggered:
            triggered_value = ctx.triggered[0].get("value")
    except MissingCallbackContextException:
        triggered_value = None
    base_state = {
        "study_id": study_id,
        "open": False,
    }
    if triggered_id == "asset-editor-close" and close_clicks:
        return base_state
    if (
        isinstance(triggered_id, dict)
        and triggered_id.get("type") == "open-rule-editor"
        and triggered_value
    ):
        return {
            "study_id": study_id,
            "open": True,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "asset_type": "rule",
            "rule_id": triggered_id.get("rule_id"),
        }
    if (
        isinstance(triggered_id, dict)
        and triggered_id.get("type") == "open-feature-editor"
        and triggered_value
    ):
        return {
            "study_id": study_id,
            "open": True,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "asset_type": "feature",
            "feature_id": triggered_id.get("feature_id"),
        }
    if (
        isinstance(triggered_id, dict)
        and triggered_id.get("type") == "open-custom-editor"
        and triggered_value
    ):
        study = load_study(study_id)
        custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
        entry = find_entry_by_rule_id(custom_entries, triggered_id.get("rule_id"))
        if entry and entry.get("source_type") == "baseline_rule_variant":
            return {
                "study_id": study_id,
                "open": True,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "asset_type": "variant_rule",
                "rule_id": triggered_id.get("rule_id"),
            }
        if entry and entry.get("source_type") == "optimization_transfer":
            return {
                "study_id": study_id,
                "open": True,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "asset_type": "optimization_transfer",
                "rule_id": triggered_id.get("rule_id"),
            }
    return base_state


def render_asset_editor(
    study_id: str,
    asset_editor_state: dict[str, Any] | None,
    predicate_editor_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    current_cutoff_handle: str | None,
) -> tuple[str, Any, str, bool, dict[str, str], str, dict[str, str]]:
    hidden_save = {"display": "none"}
    visible_save = {"display": "inline-flex"}
    hidden_cutoff = {"display": "none"}
    visible_cutoff = {"display": "grid"}
    if not study_id:
        return (
            "asset-editor-drawer",
            build_asset_editor_empty_state(),
            "",
            True,
            hidden_save,
            "Editor de ativo",
            hidden_cutoff,
        )
    if not asset_editor_state or asset_editor_state.get("study_id") != study_id:
        return (
            "asset-editor-drawer",
            build_asset_editor_empty_state(),
            "",
            True,
            hidden_save,
            "Editor de ativo",
            hidden_cutoff,
        )
    if not asset_editor_state.get("open"):
        return (
            "asset-editor-drawer",
            build_asset_editor_empty_state(),
            "",
            True,
            hidden_save,
            "Editor de ativo",
            hidden_cutoff,
        )
    if not asset_editor_state.get("opened_at"):
        return (
            "asset-editor-drawer",
            build_asset_editor_empty_state(),
            "",
            True,
            hidden_save,
            "Editor de ativo",
            hidden_cutoff,
        )

    study = load_study(study_id)
    snapshot = matrix_base_snapshot(study)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    asset_type = asset_editor_state.get("asset_type")
    if asset_type == "rule":
        rule_id = asset_editor_state.get("rule_id")
        rule = next(
            (
                item
                for item in study.manifest.baseline_policy.rules
                if item.rule_id == rule_id
            ),
            None,
        )
        if rule is None:
            return (
                "asset-editor-drawer open",
                html.Div("Regra nao encontrada.", className="editor-empty-state"),
                "",
                True,
                hidden_save,
                "Editor de regra",
                hidden_cutoff,
            )
        return (
            "asset-editor-drawer open",
            build_rule_editor_content(
                study,
                rule,
                snapshot,
                predicate_editor_state,
                current_cutoff_handle,
                custom_entries,
            ),
            "",
            False,
            visible_save,
            "Editor de regra",
            visible_cutoff,
        )
    if asset_type == "feature":
        feature_id = asset_editor_state.get("feature_id")
        feature = next(
            (item for item in feature_repository.load(study) if item.feature_id == feature_id),
            None,
        )
        if feature is None:
            return (
                "asset-editor-drawer open",
                html.Div("Feature nao encontrada.", className="editor-empty-state"),
                "",
                True,
                hidden_save,
                "Inspecao de feature derivada",
                hidden_cutoff,
            )
        return (
            "asset-editor-drawer open",
            build_feature_editor_content(feature),
            "Feature derivada em modo de inspecao. Edicao profunda ficara para a proxima fatia.",
            True,
            hidden_save,
            "Inspecao de feature derivada",
            hidden_cutoff,
        )
    if asset_type == "variant_rule":
        entry = find_entry_by_rule_id(custom_entries, asset_editor_state.get("rule_id"))
        payload = entry.get("rule") if entry else None
        try:
            rule = DecisionRuleDefinition.from_dict(payload) if isinstance(payload, dict) else None
        except (KeyError, TypeError, ValueError):
            rule = None
        if entry is None or rule is None:
            return (
                "asset-editor-drawer open",
                html.Div("Variante nao encontrada.", className="editor-empty-state"),
                "",
                True,
                hidden_save,
                "Editor de variante",
                hidden_cutoff,
            )
        return (
            "asset-editor-drawer open",
            build_variant_rule_editor_content(entry, rule, snapshot),
            "",
            False,
            visible_save,
            "Editor de variante",
            hidden_cutoff,
        )
    if asset_type == "optimization_transfer":
        entry = find_entry_by_rule_id(custom_entries, asset_editor_state.get("rule_id"))
        rules = custom_entry_rules_for_editor(entry) if entry else []
        if entry is None or not rules:
            return (
                "asset-editor-drawer open",
                html.Div("Sugestao otimizada nao encontrada.", className="editor-empty-state"),
                "",
                True,
                hidden_save,
                "Editor de sugestao",
                hidden_cutoff,
            )
        return (
            "asset-editor-drawer open",
            build_optimization_transfer_editor_content(entry, rules, snapshot),
            "",
            False,
            visible_save,
            "Editor de sugestao",
            hidden_cutoff,
        )
    return (
        "asset-editor-drawer",
        build_asset_editor_empty_state(),
        "",
        True,
        hidden_save,
        "Editor de ativo",
        hidden_cutoff,
    )


def save_asset_editor_values(
    n_clicks: int,
    study_id: str,
    asset_editor_state: dict[str, Any] | None,
    input_ids: list[dict[str, str]],
    input_values: list[Any],
    current_editor_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    rule_state: dict[str, Any] | None,
    variant_rule_name: str | None,
    variant_replace_policy: list[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
    if not n_clicks or not study_id:
        return no_update, no_update, no_update, no_update, ""
    if not asset_editor_state or asset_editor_state.get("study_id") != study_id:
        return no_update, no_update, no_update, no_update, ""
    if asset_editor_state.get("asset_type") not in {
        "rule",
        "variant_rule",
        "optimization_transfer",
    }:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            "Nada para salvar neste ativo nesta fase.",
        )

    study = load_study(study_id)
    editor_state = normalize_predicate_editor_state(study, current_editor_state)
    values = dict(editor_state.get("values", {}))
    for descriptor, value in zip(input_ids, input_values, strict=False):
        handle = descriptor.get("handle")
        if not handle or handle not in values:
            continue
        baseline_value = value_from_handle(study, handle)
        if value is None:
            values[handle] = baseline_value
        elif isinstance(baseline_value, int) and not isinstance(baseline_value, bool):
            values[handle] = int(value)
        elif isinstance(baseline_value, float):
            values[handle] = float(value)
        else:
            values[handle] = value
    updated_editor_state = {
        "study_id": study_id,
        "values": values,
    }
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    persisted_entries = created_rule_repository.load(study)
    base_entries = persisted_entries or custom_entries
    closed_drawer = {"study_id": study_id, "open": False}

    if asset_editor_state.get("asset_type") == "rule":
        rule_id = str(asset_editor_state.get("rule_id") or "")
        try:
            variant_entry = variant_entry_from_editor_state(
                study,
                rule_id,
                updated_editor_state,
                base_entries,
                variant_name=variant_rule_name,
            )
        except ValueError as error:
            return updated_editor_state, no_update, no_update, no_update, str(error)

        updated_entries = upsert_rule_entry(base_entries, variant_entry)
        created_rule_repository.save(study, updated_entries)
        updated_custom_store = custom_rule_store_payload(study, updated_entries)
        replace_current = "replace" in (variant_replace_policy or [])
        updated_rule_state = apply_variant_to_rule_state(
            study,
            rule_state,
            variant_asset_id=str(variant_entry["rule_id"]),
            origin_rule_id=str(variant_entry["origin_rule_id"]),
            replace_current=replace_current,
            custom_rule_entries=updated_entries,
        )
        reset_state = reset_editor_state_for_rule(study, updated_editor_state, rule_id)
        replace_message = (
            " A variante substituiu a baseline atual na politica candidata."
            if replace_current
            else " A variante foi adicionada a Ativos disponiveis."
        )
        return (
            reset_state,
            updated_custom_store,
            updated_rule_state,
            closed_drawer,
            (
                f"Variante '{variant_entry['rule_name']}' criada com sucesso."
                f"{replace_message}"
            ),
        )

    if asset_editor_state.get("asset_type") == "optimization_transfer":
        entry = find_entry_by_rule_id(base_entries, str(asset_editor_state.get("rule_id") or ""))
        if entry is None:
            return no_update, no_update, no_update, no_update, "Sugestao nao encontrada."
        rules = custom_entry_rules_for_editor(entry)
        if not rules:
            return no_update, no_update, no_update, no_update, "Sugestao sem regras editaveis."
        input_value_by_handle = {
            descriptor.get("handle"): value
            for descriptor, value in zip(input_ids, input_values, strict=False)
        }
        changed = False
        for rule_index, rule in enumerate(rules):
            for block_index, block in enumerate(rule.blocks):
                for predicate_index, predicate in enumerate(block.predicates):
                    handle = custom_entry_predicate_handle(
                        str(entry.get("rule_id") or ""),
                        rule_index,
                        block_index,
                        predicate_index,
                    )
                    if handle not in input_value_by_handle:
                        continue
                    raw_value = input_value_by_handle[handle]
                    new_value = predicate.value if raw_value is None else raw_value
                    coerced_value = (
                        int(new_value)
                        if isinstance(predicate.value, int)
                        and not isinstance(predicate.value, bool)
                        else float(new_value)
                        if isinstance(predicate.value, float)
                        else new_value
                    )
                    if coerced_value != predicate.value:
                        changed = True
                    predicate.value = coerced_value
        resolved_name = (
            variant_rule_name.strip()
            if variant_rule_name and variant_rule_name.strip()
            else str(entry.get("rule_name") or "Sugestao otimizada")
        )
        if resolved_name != str(entry.get("rule_name") or ""):
            changed = True
        if not changed:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                "Nenhuma alteracao real foi detectada na sugestao otimizada.",
            )
        updated_entry = dict(entry)
        updated_entry["rule_name"] = resolved_name
        updated_entry["rules"] = [rule.to_dict() for rule in rules]
        updated_entry["rule"] = (
            updated_entry["rules"][0]
            if len(updated_entry["rules"]) == 1
            else None
        )
        updated_entry["version"] = int(entry.get("version") or 1) + 1
        updated_entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated_entries = upsert_rule_entry(base_entries, updated_entry)
        created_rule_repository.save(study, updated_entries)
        updated_custom_store = custom_rule_store_payload(study, updated_entries)
        refreshed_rule_state = enrich_rule_state(
            study,
            rule_state or {"study_id": study_id},
            custom_rule_entries=updated_entries,
        )
        return (
            no_update,
            updated_custom_store,
            refreshed_rule_state,
            closed_drawer,
            f"Sugestao otimizada '{resolved_name}' atualizada com sucesso.",
        )

    entry = find_entry_by_rule_id(base_entries, str(asset_editor_state.get("rule_id") or ""))
    payload = entry.get("rule") if entry else None
    if entry is None or not isinstance(payload, dict):
        return no_update, no_update, no_update, no_update, "Variante nao encontrada."
    try:
        variant_rule = DecisionRuleDefinition.from_dict(payload)
    except (KeyError, TypeError, ValueError):
        return no_update, no_update, no_update, no_update, "Variante invalida para edicao."

    input_value_by_handle = {
        descriptor.get("handle"): value
        for descriptor, value in zip(input_ids, input_values, strict=False)
    }
    changed = False
    for block_index, block in enumerate(variant_rule.blocks):
        for predicate_index, predicate in enumerate(block.predicates):
            handle = ui_predicate_handle(
                str(entry.get("origin_rule_id") or variant_rule.rule_id),
                block_index,
                predicate_index,
                predicate.field,
                predicate.operator.value,
            )
            if handle not in input_value_by_handle:
                continue
            raw_value = input_value_by_handle[handle]
            new_value = predicate.value if raw_value is None else raw_value
            coerced_value = (
                int(new_value)
                if isinstance(predicate.value, int) and not isinstance(predicate.value, bool)
                else float(new_value)
                if isinstance(predicate.value, float)
                else new_value
            )
            if coerced_value != predicate.value:
                changed = True
            predicate.value = coerced_value
    if not changed:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            "Nenhuma alteracao real foi detectada na variante.",
        )

    updated_entry = dict(entry)
    updated_entry["rule"] = variant_rule.to_dict()
    updated_entry["rule_name"] = variant_rule.name
    updated_entry["version"] = int(entry.get("version") or 1) + 1
    updated_entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated_entries = upsert_rule_entry(base_entries, updated_entry)
    created_rule_repository.save(study, updated_entries)
    updated_custom_store = custom_rule_store_payload(study, updated_entries)
    refreshed_rule_state = enrich_rule_state(
        study,
        rule_state or {"study_id": study_id},
        custom_rule_entries=updated_entries,
    )
    return (
        updated_editor_state,
        updated_custom_store,
        refreshed_rule_state,
        closed_drawer,
        f"Variante '{variant_rule.name}' atualizada com sucesso.",
    )


def select_cutoff_target(
    _target_clicks: list[int],
    study_id: str,
) -> tuple[str | Any, str]:
    triggered_id = current_triggered_id()
    if not study_id or not isinstance(triggered_id, dict):
        return no_update, ""
    if triggered_id.get("type") != "select-cutoff-handle":
        return no_update, ""
    handle = triggered_id.get("handle")
    if not handle:
        return no_update, ""
    study = load_study(study_id)
    try:
        baseline_value = format_optional_number(value_from_handle(study, handle))
    except KeyError:
        baseline_value = "N/A"
    return (
        handle,
        (
            "Predicado-alvo selecionado para o ponto de corte. "
            f"Valor atual de referencia: {baseline_value}. "
            "Use o painel de otimizacao singular no editor lateral para buscar o novo corte."
        ),
    )


def load_matrix_rule_decisions(study_id: str) -> tuple[list[dict[str, str]], str | None]:
    if not study_id:
        return [], None
    study = load_study(study_id)
    decisions = {
        study.manifest.baseline_policy.default_decision,
        *[rule.decision for rule in study.manifest.baseline_policy.rules],
    }
    ordered_decisions = sorted(decisions, key=decision_sort_key)
    options = [
        {"label": decision_label(decision), "value": decision}
        for decision in ordered_decisions
    ]
    default_value = "approve" if "approve" in decisions else ordered_decisions[0]
    return options, default_value


def decision_label(decision: str) -> str:
    labels = {
        "approve": "Aprovar",
        "reject": "Rejeitar",
        "review": "Enviar para mesa",
    }
    return labels.get(decision, decision)


def decision_sort_key(decision: str) -> tuple[int, str]:
    order = {"approve": 0, "review": 1, "reject": 2}
    return order.get(decision, 9), decision


def matrix_base_snapshot(study) -> pl.DataFrame:
    snapshot = study_repository.load_snapshot(study)
    features = orchestrator.feature_repository.load(study)
    feature_ids = [feature.feature_id for feature in features]
    return orchestrator.feature_resolver.resolve(snapshot, features, feature_ids)


def merge_feature_ids(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for feature_id in group:
            if feature_id not in merged:
                merged.append(feature_id)
    return merged


def update_matrix_filter_count(
    study_id: str,
    add_clicks: int,
    current_count: int | None,
    matrix_state: dict[str, Any] | None,
) -> int:
    triggered_id = current_triggered_id()
    if triggered_id in (None, "study-dropdown"):
        stored_state = state_for_study(matrix_state, study_id)
        return max(1, int(stored_state.get("filter_count") or 1))
    if not study_id:
        return 1
    return max(1, int(current_count or 1) + (1 if add_clicks else 0))


def render_matrix_filters(
    study_id: str,
    filter_count: int | None,
    matrix_state: dict[str, Any] | None,
) -> list[html.Div]:
    if not study_id:
        return []
    study = load_study(study_id)
    snapshot = matrix_base_snapshot(study)
    stored_state = state_for_study(matrix_state, study_id)
    stored_filters = stored_state.get("filters", [])
    options = [
        {"label": column, "value": column}
        for column in available_matrix_columns(snapshot, study)
    ]
    operator_options = [
        {"label": "<", "value": "<"},
        {"label": "<=", "value": "<="},
        {"label": ">", "value": ">"},
        {"label": ">=", "value": ">="},
    ]
    rows: list[html.Div] = []
    for index in range(max(1, int(filter_count or 1))):
        suffix = "" if index == 0 else f" {index + 1}"
        stored_filter = stored_filters[index] if index < len(stored_filters) else {}
        rows.append(
            html.Div(
                className="matrix-filter-row",
                children=[
                    html.Div(
                        className="field-group",
                        children=[
                            html.Label(f"Variavel{suffix}"),
                            dcc.Dropdown(
                                id={"type": "matrix-filter-variable", "index": index},
                                options=options,
                                value=stored_filter.get("variable"),
                            ),
                        ],
                    ),
                    html.Div(
                        className="field-group",
                        children=[
                            html.Label(f"Operador{suffix}"),
                            dcc.Dropdown(
                                id={"type": "matrix-filter-operator", "index": index},
                                options=operator_options,
                                value=stored_filter.get("operator") or "<",
                                clearable=False,
                            ),
                        ],
                    ),
                    html.Div(
                        className="field-group",
                        children=[
                            html.Label(f"Valor{suffix}"),
                            dcc.Input(
                                id={"type": "matrix-filter-value", "index": index},
                                type="number",
                                value=stored_filter.get("value"),
                            ),
                        ],
                    ),
                ],
            )
        )
    return rows


def persist_matrix_config(
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    filter_count: int | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
    current_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not study_id:
        return current_state or {}
    stored_state = dict(state_for_study(current_state, study_id) or {"study_id": study_id})
    filters = [
        {
            "variable": variable,
            "operator": operator,
            "value": value,
        }
        for variable, operator, value in zip(
            filter_variables,
            filter_operators,
            filter_values,
            strict=False,
        )
    ]
    last_generated = stored_state.get("last_generated_config", {})
    keep_axis_specs = (
        last_generated.get("row_variable") == row_variable
        and last_generated.get("column_variable") == column_variable
        and last_generated.get("filters", []) == filters
    )
    return {
        "study_id": study_id,
        "row_variable": row_variable,
        "column_variable": column_variable,
        "filter_count": max(1, int(filter_count or 1)),
        "filters": filters,
        "axis_specs": stored_state.get("axis_specs", {}) if keep_axis_specs else {},
        "last_generated_config": stored_state.get("last_generated_config", {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_matrix_variable_options(
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not study_id:
        return [], []
    study = load_study(study_id)
    snapshot = matrix_base_snapshot(study)
    options = available_matrix_columns(snapshot, study)
    row_options = [
        {"label": column, "value": column}
        for column in options
        if column != column_variable
    ]
    column_options = [
        {"label": column, "value": column}
        for column in options
        if column != row_variable
    ]
    return row_options, column_options


def restore_matrix_variables(
    study_id: str,
    _matrix_trigger: dict[str, Any] | None,
    matrix_state: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    if not study_id:
        return None, None
    study = load_study(study_id)
    snapshot = matrix_base_snapshot(study)
    options = set(available_matrix_columns(snapshot, study))
    stored_state = state_for_study(matrix_state, study_id)
    row_variable = stored_state.get("row_variable")
    column_variable = stored_state.get("column_variable")
    if row_variable not in options:
        row_variable = None
    if column_variable not in options or column_variable == row_variable:
        column_variable = None
    return row_variable, column_variable


def update_cutoff_target_label(cutoff_objective: str | None) -> str:
    if cutoff_objective == "risk":
        return "Meta de risco (%)"
    if cutoff_objective == "fixed_cutoff":
        return "Valor do corte seco"
    return "Meta de aprovacao (%)"


def suggest_cutoff(
    n_clicks: int,
    study_id: str,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    predicate_editor_state: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    target_approval_rate: float | None,
) -> tuple[str, dict[str, Any] | None]:
    if not n_clicks or not study_id or not cutoff_handle:
        return "A sugestao de ponto de corte aparecera aqui.", None

    if cutoff_objective == "fixed_cutoff":
        if target_approval_rate is None:
            return "", None
        return "", {
            "study_id": study_id,
            "handle": cutoff_handle,
            "value": target_approval_rate,
            "metric": "fixed_cutoff",
            "source": "fixed_cutoff",
        }

    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    snapshot = filter_snapshot(
        matrix_base_snapshot(study),
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    policy = build_candidate_policy(
        study,
        rule_state=normalize_rule_state(
            study,
            rule_state,
            custom_rules=custom_rules,
            custom_rule_entries=custom_entries,
        ),
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    target_metric = "risk" if cutoff_objective == "risk" else "approval"
    target_value = (target_approval_rate or 80.0) / 100.0
    suggestion = find_cutoff_suggestion(
        policy,
        snapshot,
        cutoff_handle,
        target_metric,
        target_value,
        performance_columns=study.manifest.snapshot.performance_columns,
        candidate_source_snapshot=extract_anchor_population_for_predicate(
            snapshot,
            policy,
            cutoff_handle,
        ),
    )
    override = suggestion["override"]
    if override is not None:
        override["study_id"] = study_id
    return suggestion["message"], override


def run_manual_scenario(
    n_clicks: int,
    study_id: str,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
) -> tuple[
    Any,
    list[dict[str, Any]],
    list[dict[str, str]],
    go.Figure,
    go.Figure,
    go.Figure,
    dict[str, Any],
]:
    return manual_scenario_outputs(
        n_clicks=n_clicks,
        study_id=study_id,
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        rule_state=rule_state,
        custom_rule_state=custom_rule_state,
        cutoff_override=cutoff_override,
        cutoff_handle=cutoff_handle,
        cutoff_objective=cutoff_objective,
        cutoff_value=cutoff_value,
        predicate_editor_state=predicate_editor_state,
    )


def manual_scenario_outputs(
    *,
    n_clicks: int,
    study_id: str,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
) -> tuple[
    Any,
    list[dict[str, Any]],
    list[dict[str, str]],
    go.Figure,
    go.Figure,
    go.Figure,
    dict[str, Any],
]:
    if not study_id:
        return (
            [],
            [],
            [],
            empty_figure("Execute uma simulacao para comparar com a baseline."),
            empty_figure("A matriz de transicao aparecera aqui."),
            empty_figure("O fluxo de subdecisoes aparecera aqui."),
            {},
        )

    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    normalized_state = normalize_rule_state(
        study,
        rule_state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
    )
    filtered_snapshot = filter_snapshot(
        study_repository.load_snapshot(study),
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    baseline_bundle = orchestrator.run_baseline_with_snapshot(
        study,
        snapshot_override=filtered_snapshot,
    )
    active_cutoff_override = resolve_active_cutoff_override(
        study_id,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
    )
    policy = build_candidate_policy(
        study,
        rule_state=normalized_state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
        cutoff_override=active_cutoff_override,
    )
    if not n_clicks and not active_cutoff_override:
        scenario_result = baseline_bundle.result
        rule_flow_frame = baseline_bundle.frame
        rule_flow_policy = study.manifest.baseline_policy
    else:
        feature_ids = merge_feature_ids(
            normalized_state["selected_feature_ids"],
            feature_ids_used_by_rules(study, policy.rules),
        )
        scenario = ScenarioDefinition(
            scenario_id=f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            name="Cenario manual",
            description=f"Cenario manual sobre {study.manifest.name}.",
            policy=policy,
            feature_ids=feature_ids,
            tags=["manual"],
        )
        scenario_bundle = orchestrator.run_scenario(
            study,
            scenario,
            baseline_bundle=baseline_bundle,
            snapshot_override=filtered_snapshot,
        )
        scenario_result = scenario_bundle.result
        rule_flow_frame = scenario_bundle.frame
        rule_flow_policy = policy
    comparison_data, comparison_columns = build_comparison_table(
        baseline_bundle.result,
        scenario_result,
    )
    return (
        build_metric_cards(scenario_result, baseline_bundle.result),
        comparison_data,
        comparison_columns,
        build_comparison_figure(baseline_bundle.result, scenario_result),
        build_transition_figure(
            scenario_result.transitions,
            title="Transicao baseline x candidata",
        ),
        build_rule_flow_figure(rule_flow_frame, rule_flow_policy),
        {
            "study_id": study_id,
            "simulated_at": datetime.now(timezone.utc).isoformat(),
            "n_clicks": n_clicks,
            "filters": {
                "months": months or [],
                "segment_field": segment_field,
                "segment_values": segment_values or [],
            },
            "rule_state": normalized_state,
            "custom_rules": [rule.to_dict() for rule in custom_rules],
            "cutoff_override": active_cutoff_override,
            "policy": policy.to_dict(),
            "baseline_result": baseline_bundle.result.to_dict(),
            "scenario_result": scenario_result.to_dict(),
        },
    )


def export_manual_policy(
    n_clicks: int,
    study_id: str,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
):
    if not n_clicks or not study_id:
        return None
    study = load_study(study_id)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    policy = build_candidate_policy(
        study,
        rule_state=normalize_rule_state(
            study,
            rule_state,
            custom_rules=custom_rules,
            custom_rule_entries=custom_entries,
        ),
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
        cutoff_override=resolve_active_cutoff_override(
            study_id,
            cutoff_override,
            cutoff_handle,
            cutoff_objective,
            cutoff_value,
        ),
    )
    payload = json.dumps(policy.to_dict(), indent=2, ensure_ascii=False)
    return dcc.send_string(payload, f"{study_id}-manual-policy.json")


def run_search(
    n_clicks: int,
    study_id: str,
    search_strategy: str,
    search_base: str,
    search_primary_metric: str,
    search_direction: str,
    search_preserve_metric: str | None,
    search_max_degradation: float | None,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    last_simulation_state: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], go.Figure, dict[str, Any]]:
    if not n_clicks or not study_id:
        return (
            [],
            [],
            empty_figure("Execute a busca automatica para gerar recomendacoes."),
            {},
        )

    study = load_study(study_id)
    filtered_snapshot = filter_snapshot(
        study_repository.load_snapshot(study),
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    base_policy = _resolve_search_base_policy(
        study,
        search_base,
        last_simulation_state,
    )
    objective_spec = SearchObjectiveSpec(
        primary_metric=search_primary_metric or "approval",
        direction=search_direction or "maximize",
        preserve_metric=(
            None if search_preserve_metric in (None, "", "none") else search_preserve_metric
        ),
        max_degradation=(
            float(search_max_degradation)
            if search_max_degradation not in (None, "")
            else None
        ),
    )
    study_baseline_bundle = orchestrator.run_baseline_with_snapshot(
        study,
        snapshot_override=filtered_snapshot,
    )
    search_base_bundle = _resolve_search_base_bundle(
        study,
        base_policy=base_policy,
        filtered_snapshot=filtered_snapshot,
        baseline_bundle=study_baseline_bundle,
        last_simulation_state=last_simulation_state,
    )
    constraint_reference_bundle = (
        study_baseline_bundle
        if search_base == "from_scratch"
        else search_base_bundle
    )
    results = orchestrator.run_search(
        study,
        strategy=SearchStrategy(search_strategy),
        baseline_bundle=study_baseline_bundle,
        search_reference_bundle=search_base_bundle,
        constraint_reference_bundle=constraint_reference_bundle,
        snapshot_override=filtered_snapshot,
        base_policy=base_policy,
        objective_spec=objective_spec,
    )
    table_data = [
        {
            "cenario": _format_search_scenario_name(result),
            "pareto": _format_pareto_front(result),
            "tipo": result.lineage.get("search_details", {}).get("candidate_kind", "N/A"),
            "composicao": _format_search_composition(
                result.lineage.get("search_details", {}).get("summary", "N/A")
            ),
            "aprovacao": format_optional_pct(result.metrics.approval_rate),
            "indice_lucro": format_optional_number(result.metrics.expected_profit_index),
            "risco": format_optional_pct(result.metrics.risk_estimate),
            "incerteza": result.metrics.uncertainty_label or "N/A",
            "desempenho_composto": format_optional_number(
                result.lineage.get("objective_performance")
            ),
        }
        for result in results
    ]
    columns = [
        {"name": "Cenario", "id": "cenario"},
        {"name": "Pareto", "id": "pareto"},
        {"name": "Tipo", "id": "tipo"},
        {"name": "Composicao", "id": "composicao"},
        {"name": "Aprovacao", "id": "aprovacao"},
        {"name": "Indice de lucro", "id": "indice_lucro"},
        {"name": "Risco", "id": "risco"},
        {"name": "Incerteza", "id": "incerteza"},
        {"name": "Desempenho composto", "id": "desempenho_composto"},
    ]
    return (
        table_data,
        columns,
        build_recommendation_figure(
            results,
            search_base_bundle.result,
            reference_label=_search_base_reference_label(search_base),
        ),
        build_search_results_store_payload(
            study_id,
            search_strategy,
            search_base,
            objective_spec,
            results,
        ),
    )


def _format_search_scenario_name(result: ScenarioResult) -> str:
    search_details = result.lineage.get("search_details", {})
    candidate_kind = search_details.get("candidate_kind")
    threshold_overrides = search_details.get("threshold_overrides", [])
    if candidate_kind == "derived_veto":
        return "Derived Veto"
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
    if candidate_kind in {"threshold_override", "threshold_pair"} and isinstance(
        threshold_overrides,
        list,
    ):
        rule_names: list[str] = []
        for item in threshold_overrides:
            if not isinstance(item, dict):
                continue
            rule_name = str(item.get("rule_name") or "").strip()
            if rule_name and rule_name not in rule_names:
                rule_names.append(rule_name)
        if len(rule_names) == 1:
            return rule_names[0]
        if len(rule_names) > 1:
            return " + ".join(rule_names)
    return result.scenario_name


def _format_search_composition(summary: str) -> str:
    if not isinstance(summary, str):
        return "N/A"
    return ";\n".join(part.strip() for part in summary.split(";") if part.strip())


def _format_pareto_front(result: ScenarioResult) -> str:
    front = result.lineage.get("pareto_front")
    if front in (None, ""):
        return "N/A"
    return f"F{front}"


def build_search_results_store_payload(
    study_id: str,
    search_strategy: str,
    search_base: str,
    objective_spec: SearchObjectiveSpec,
    results: list[ScenarioResult],
) -> dict[str, Any]:
    payload_results: list[dict[str, Any]] = []
    for result in results:
        candidate_scenario = result.lineage.get("candidate_scenario")
        if not isinstance(candidate_scenario, dict):
            continue
        payload_results.append(
            {
                "scenario": candidate_scenario,
                "result": result.to_dict(),
                "search_strategy": search_strategy,
                "search_base": search_base,
                "objective_spec": objective_spec.to_dict(),
            }
        )
    return {
        "study_id": study_id,
        "results": payload_results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def custom_entry_rules_for_editor(entry: dict[str, Any] | None) -> list[DecisionRuleDefinition]:
    if not isinstance(entry, dict):
        return []
    rules: list[DecisionRuleDefinition] = []
    payloads = entry.get("rules")
    if isinstance(payloads, list):
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            try:
                rules.append(DecisionRuleDefinition.from_dict(payload))
            except (KeyError, TypeError, ValueError):
                continue
        return rules
    payload = entry.get("rule")
    if isinstance(payload, dict):
        try:
            rules.append(DecisionRuleDefinition.from_dict(payload))
        except (KeyError, TypeError, ValueError):
            return []
    return rules


def _search_base_reference_label(search_base: str) -> str:
    if search_base == "last_simulation":
        return "Base da busca"
    if search_base == "from_scratch":
        return "Pool inicial"
    return "Baseline"


def _resolve_search_base_policy(
    study,
    search_base: str,
    last_simulation_state: dict[str, Any] | None,
) -> PolicyDefinition:
    if search_base == "from_scratch":
        return PolicyDefinition(
            policy_id=f"{study.manifest.baseline_policy.policy_id}-scratch-search",
            name="Scratch search base",
            version=study.manifest.baseline_policy.version,
            decision_column=study.manifest.baseline_policy.decision_column,
            default_decision=study.manifest.baseline_policy.default_decision,
            rules=[],
            metadata={
                **study.manifest.baseline_policy.metadata,
                "search_base": "from_scratch",
            },
        )

    if (
        search_base == "last_simulation"
        and isinstance(last_simulation_state, dict)
        and last_simulation_state.get("study_id") == study.study_id
    ):
        policy_payload = (
            last_simulation_state.get("candidate_policy")
            or last_simulation_state.get("policy")
        )
        if isinstance(policy_payload, dict):
            try:
                candidate_policy = PolicyDefinition.from_dict(policy_payload)
                candidate_policy.metadata = {
                    **candidate_policy.metadata,
                    "search_base": "last_simulation",
                }
                return candidate_policy
            except (KeyError, TypeError, ValueError):
                pass

    baseline_policy = PolicyDefinition.from_dict(study.manifest.baseline_policy.to_dict())
    baseline_policy.metadata = {
        **baseline_policy.metadata,
        "search_base": "baseline_study",
    }
    return baseline_policy


def transfer_search_candidate_to_manual_lab(
    n_clicks: int,
    study_id: str,
    selected_rows: list[int] | None,
    search_results_store: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    rule_state: dict[str, Any] | None,
    last_simulation_state: dict[str, Any] | None,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    predicate_editor_state: dict[str, Any] | None,
) -> tuple[Any, ...]:
    if not n_clicks or not study_id:
        return (no_update,) * 10 + ("",)

    selected_index = (selected_rows or [None])[0]
    if selected_index is None:
        return (no_update,) * 10 + (
            "Selecione uma linha da tabela de otimização para transferir.",
        )

    store_state = state_for_study(search_results_store, study_id)
    results_payload = store_state.get("results", [])
    if (
        not isinstance(results_payload, list)
        or selected_index < 0
        or selected_index >= len(results_payload)
    ):
        return (no_update,) * 10 + (
            "O candidato selecionado nao esta mais disponivel. Execute a busca novamente.",
        )

    candidate_payload = results_payload[selected_index]
    scenario_payload = candidate_payload.get("scenario")
    if not isinstance(scenario_payload, dict):
        return (no_update,) * 10 + (
            "Nao foi possivel recuperar a politica sugerida desta linha.",
        )

    try:
        scenario = ScenarioDefinition.from_dict(scenario_payload)
    except (KeyError, TypeError, ValueError):
        return (no_update,) * 10 + (
            "A sugestao selecionada esta inconsistente e nao pode ser transferida.",
        )

    study = load_study(study_id)
    persisted_entries = created_rule_repository.load(study)
    session_entries = custom_rule_entries_from_store(study, custom_rule_state)
    merged_entries = merge_custom_entries_for_transfer(persisted_entries, session_entries)
    transferred_entry = build_optimization_transfer_entry(
        study,
        scenario=scenario,
        candidate_payload=candidate_payload,
        existing_entries=merged_entries,
        last_simulation_state=last_simulation_state,
    )
    updated_entries = [
        entry
        for entry in merged_entries
        if str(entry.get("rule_id") or "") not in transferred_entry_ids(transferred_entry)
    ]
    updated_entries.extend(transferred_entries_payload(transferred_entry))
    created_rule_repository.save(study, updated_entries)
    updated_custom_store = custom_rule_store_payload(study, updated_entries)
    updated_rule_state = build_transfer_rule_state(
        study,
        transfer_payload=transferred_entry,
        custom_rule_entries=updated_entries,
        last_simulation_state=last_simulation_state,
    )
    manual_outputs = manual_scenario_outputs(
        n_clicks=1,
        study_id=study_id,
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        rule_state=updated_rule_state,
        custom_rule_state=updated_custom_store,
        cutoff_override=None,
        cutoff_handle=None,
        cutoff_objective=None,
        cutoff_value=None,
        predicate_editor_state=predicate_editor_state,
    )
    return (
        updated_custom_store,
        updated_rule_state,
        *manual_outputs,
        "manual_lab",
        (
            f"Politica sugerida '{transferred_entry['rule_name']}' "
            "transferida para o Laboratorio Manual."
        ),
    )


def merge_custom_entries_for_transfer(
    persisted_entries: list[dict[str, Any]],
    session_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_by_id: dict[str, dict[str, Any]] = {}
    for entry in persisted_entries + session_entries:
        entry_id = str(entry.get("rule_id") or "").strip()
        if not entry_id:
            continue
        merged_by_id[entry_id] = dict(entry)
    return list(merged_by_id.values())


def build_optimization_transfer_entry(
    study,
    *,
    scenario: ScenarioDefinition,
    candidate_payload: dict[str, Any],
    existing_entries: list[dict[str, Any]],
    last_simulation_state: dict[str, Any] | None,
    author: str = DEFAULT_MANUAL_AUTHOR,
) -> dict[str, Any]:
    search_base = str(candidate_payload.get("search_base") or "baseline_study")
    objective_spec = candidate_payload.get("objective_spec")
    base_policy = _resolve_search_base_policy(
        study,
        search_base,
        last_simulation_state,
    )
    transfer_payload = derive_transfer_payload_from_candidate(
        study,
        scenario=scenario,
        base_policy=base_policy,
        existing_entries=existing_entries,
        search_base=search_base,
        objective_spec=objective_spec,
        candidate_payload=candidate_payload,
        author=author,
    )
    return transfer_payload


def derive_transfer_payload_from_candidate(
    study,
    *,
    scenario: ScenarioDefinition,
    base_policy: PolicyDefinition,
    existing_entries: list[dict[str, Any]],
    search_base: str,
    objective_spec: dict[str, Any] | None,
    candidate_payload: dict[str, Any],
    author: str,
) -> dict[str, Any]:
    candidate_rules = [
        DecisionRuleDefinition.from_dict(rule.to_dict())
        for rule in scenario.policy.rules
    ]
    if search_base == "from_scratch":
        return {
            "mode": "full_policy",
            "search_base": search_base,
            "rule_name": build_optimization_transfer_name(
                scenario.name,
                existing_entries,
                candidate_payload,
            ),
            "entry": build_optimization_transfer_package_entry(
                study,
                rules=candidate_rules,
                existing_entries=existing_entries,
                scenario=scenario,
                candidate_payload=candidate_payload,
                objective_spec=objective_spec,
                author=author,
                rule_name=build_optimization_transfer_name(
                    scenario.name,
                    existing_entries,
                    candidate_payload,
                ),
            ),
        }

    baseline_rule_ids = {rule.rule_id for rule in study.manifest.baseline_policy.rules}
    base_rules_by_id = {rule.rule_id: rule for rule in base_policy.rules}
    modified_baseline_rules: list[DecisionRuleDefinition] = []
    added_rules: list[DecisionRuleDefinition] = []
    requires_full_policy = False
    for rule in candidate_rules:
        base_rule = base_rules_by_id.get(rule.rule_id)
        if base_rule is None:
            added_rules.append(rule)
            continue
        if rule.to_dict() == base_rule.to_dict():
            continue
        if rule.rule_id in baseline_rule_ids:
            modified_baseline_rules.append(rule)
        else:
            requires_full_policy = True

    if requires_full_policy:
        return {
            "mode": "full_policy",
            "search_base": search_base,
            "rule_name": build_optimization_transfer_name(
                scenario.name,
                existing_entries,
                candidate_payload,
            ),
            "entry": build_optimization_transfer_package_entry(
                study,
                rules=candidate_rules,
                existing_entries=existing_entries,
                scenario=scenario,
                candidate_payload=candidate_payload,
                objective_spec=objective_spec,
                author=author,
                rule_name=build_optimization_transfer_name(
                    scenario.name,
                    existing_entries,
                    candidate_payload,
                ),
            ),
        }

    variant_entries = [
        optimization_variant_entry_from_rule(
            study,
            modified_rule=rule,
            existing_entries=existing_entries,
            author=author,
        )
        for rule in modified_baseline_rules
    ]
    package_entry = (
        build_optimization_transfer_package_entry(
            study,
            rules=added_rules,
            existing_entries=[
                *existing_entries,
                *variant_entries,
            ],
            scenario=scenario,
            candidate_payload=candidate_payload,
            objective_spec=objective_spec,
            author=author,
            rule_name=build_optimization_transfer_name(
                scenario.name,
                [*existing_entries, *variant_entries],
                candidate_payload,
            ),
        )
        if added_rules
        else None
    )
    return {
        "mode": "delta",
        "search_base": search_base,
        "rule_name": (
            str(package_entry.get("rule_name"))
            if isinstance(package_entry, dict)
            else (
                str(variant_entries[0].get("rule_name"))
                if len(variant_entries) == 1
                else build_optimization_transfer_name(
                    scenario.name,
                    existing_entries,
                    candidate_payload,
                )
            )
        ),
        "variant_entries": variant_entries,
        "package_entry": package_entry,
    }


def build_optimization_transfer_name(
    scenario_name: str,
    existing_entries: list[dict[str, Any]],
    candidate_payload: dict[str, Any] | None = None,
) -> str:
    base_name = optimization_transfer_base_name(
        scenario_name,
        candidate_payload,
    )
    existing_names = [
        str(entry.get("rule_name"))
        for entry in existing_entries
        if entry.get("rule_name")
    ]
    pattern = re.compile(rf"^{re.escape(base_name)} (\d+)$")
    used_numbers = [
        int(match.group(1))
        for name in existing_names
        if (match := pattern.match(name))
    ]
    next_number = max(used_numbers, default=0) + 1
    return f"{base_name} {next_number}"


def optimization_transfer_base_name(
    scenario_name: str,
    candidate_payload: dict[str, Any] | None,
) -> str:
    if not isinstance(candidate_payload, dict):
        return scenario_name or "Optimization transfer"
    result_payload = candidate_payload.get("result")
    result_lineage = (
        result_payload.get("lineage", {})
        if isinstance(result_payload, dict)
        else {}
    )
    search_details = (
        result_lineage.get("search_details", {})
        if isinstance(result_lineage, dict)
        else {}
    )
    candidate_kind = str(search_details.get("candidate_kind") or "").strip()
    if candidate_kind == "derived_veto":
        return "Derived Veto"
    if candidate_kind == "simple_rule_candidate":
        return "Add Rule"
    if candidate_kind == "grouped_rule_candidate":
        return "Grouped Rule"
    if candidate_kind == "layered_rule_candidate":
        return "Structured Rule"
    if candidate_kind == "guarded_rule_candidate":
        return "Guarded Rule"
    if candidate_kind == "composite_rule_candidate":
        return "Composite Rule"
    if candidate_kind == "signal_bundle_candidate":
        return "Signal Bundle"
    if candidate_kind == "rule_bundle_candidate":
        return "Rule Bundle"
    if candidate_kind == "policy_pack_candidate":
        return "Policy Pack"
    if candidate_kind == "mixed_candidate":
        return "Heuristic Mix"
    if candidate_kind == "threshold_pair":
        return "Guided Pair"
    if candidate_kind == "threshold_override":
        threshold_overrides = search_details.get("threshold_overrides", [])
        rule_names: list[str] = []
        if isinstance(threshold_overrides, list):
            for item in threshold_overrides:
                if not isinstance(item, dict):
                    continue
                rule_name = str(item.get("rule_name") or "").strip()
                if rule_name and rule_name not in rule_names:
                    rule_names.append(rule_name)
        if rule_names:
            return " + ".join(rule_names)
    return scenario_name or "Optimization Transfer"


def build_optimization_transfer_package_entry(
    study,
    *,
    rules: list[DecisionRuleDefinition],
    existing_entries: list[dict[str, Any]],
    scenario: ScenarioDefinition,
    candidate_payload: dict[str, Any],
    objective_spec: dict[str, Any] | None,
    author: str,
    rule_name: str,
) -> dict[str, Any]:
    existing_entry_ids = {
        str(entry.get("rule_id"))
        for entry in existing_entries
        if entry.get("rule_id")
    }
    asset_id = unique_asset_id(
        slugify(rule_name) or slugify(scenario.name) or "sugestao-otimizacao",
        existing_entry_ids,
        prefix="optimization",
    )
    result_payload = candidate_payload.get("result", {})
    result_lineage = (
        result_payload.get("lineage", {})
        if isinstance(result_payload, dict)
        else {}
    )
    result_metrics = (
        result_payload.get("metrics", {})
        if isinstance(result_payload, dict)
        else {}
    )
    now = datetime.now(timezone.utc).isoformat()
    policy_rules = [rule.to_dict() for rule in rules]
    return {
        "rule_id": asset_id,
        "rule_name": rule_name,
        "rules": policy_rules,
        "rule": policy_rules[0] if len(policy_rules) == 1 else None,
        "source_type": "optimization_transfer",
        "scenario_id": scenario.scenario_id,
        "scenario_name": scenario.name,
        "scenario_description": scenario.description,
        "candidate_kind": result_lineage.get("search_details", {}).get("candidate_kind"),
        "search_summary": result_lineage.get("search_details", {}).get("summary"),
        "search_strategy": candidate_payload.get("search_strategy"),
        "search_base": candidate_payload.get("search_base"),
        "objective_spec": candidate_payload.get("objective_spec"),
        "metrics_snapshot": {
            "approval_rate": result_metrics.get("approval_rate"),
            "expected_profit_index": result_metrics.get("expected_profit_index"),
            "risk_estimate": result_metrics.get("risk_estimate"),
            "uncertainty_label": result_metrics.get("uncertainty_label"),
            "complexity_score": result_metrics.get("complexity_score"),
            "pareto_front": result_lineage.get("pareto_front"),
            "objective_performance": result_lineage.get("objective_performance"),
        },
        "author": author,
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }


def optimization_variant_entry_from_rule(
    study,
    *,
    modified_rule: DecisionRuleDefinition,
    existing_entries: list[dict[str, Any]],
    author: str,
) -> dict[str, Any]:
    origin_rule = next(
        (
            rule
            for rule in study.manifest.baseline_policy.rules
            if rule.rule_id == modified_rule.rule_id
        ),
        None,
    )
    if origin_rule is None:
        raise KeyError(f"Unknown baseline rule '{modified_rule.rule_id}'")
    existing_entry_ids = {
        str(entry.get("rule_id"))
        for entry in existing_entries
        if entry.get("rule_id")
    }
    existing_names = {
        str(entry.get("rule_name"))
        for entry in existing_entries
        if entry.get("rule_name")
    }
    existing_names.add(origin_rule.name)
    resolved_name = next_variant_name(origin_rule.name, existing_names)
    origin_versions = [
        int(entry.get("version") or 1)
        for entry in existing_entries
        if entry.get("source_type") == "baseline_rule_variant"
        and entry.get("origin_rule_id") == origin_rule.rule_id
    ]
    version = max(origin_versions, default=0) + 1
    now = datetime.now(timezone.utc).isoformat()
    updated_rule = DecisionRuleDefinition.from_dict(modified_rule.to_dict())
    updated_rule.name = resolved_name
    updated_rule.description = (
        f"Variante governada da regra baseline '{origin_rule.name}'. "
        f"Origem: {origin_rule.rule_id}. Versao: {version}."
    )
    asset_id = unique_asset_id(
        slugify(resolved_name) or slugify(origin_rule.name) or "variante-regra",
        existing_entry_ids,
        prefix="variant",
    )
    return {
        "rule_id": asset_id,
        "rule_name": resolved_name,
        "rule": updated_rule.to_dict(),
        "source_type": "baseline_rule_variant",
        "origin_rule_id": origin_rule.rule_id,
        "origin_rule_name": origin_rule.name,
        "version": version,
        "author": author,
        "created_at": now,
        "updated_at": now,
    }


def transferred_entry_ids(transfer_payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for entry in transferred_entries_payload(transfer_payload):
        entry_id = str(entry.get("rule_id") or "")
        if entry_id:
            ids.add(entry_id)
    return ids


def transferred_entries_payload(transfer_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if transfer_payload.get("mode") == "full_policy":
        entry = transfer_payload.get("entry")
        return [dict(entry)] if isinstance(entry, dict) else []
    entries = [dict(entry) for entry in transfer_payload.get("variant_entries", [])]
    package_entry = transfer_payload.get("package_entry")
    if isinstance(package_entry, dict):
        entries.append(dict(package_entry))
    return entries


def build_transfer_rule_state(
    study,
    *,
    transfer_payload: dict[str, Any],
    custom_rule_entries: list[dict[str, Any]],
    last_simulation_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if transfer_payload.get("mode") == "full_policy":
        entry = transfer_payload.get("entry", {})
        return enrich_rule_state(
            study,
            {
                "study_id": study.study_id,
                "used_asset_ids": [custom_asset_id(str(entry.get("rule_id") or ""))],
                "selected_feature_ids": [],
            },
            custom_rule_entries=custom_rule_entries,
        )

    search_base = transfer_payload.get("search_base") or "baseline_study"
    if search_base == "last_simulation":
        base_state = normalize_rule_state(
            study,
            (
                last_simulation_state.get("rule_state")
                if isinstance(last_simulation_state, dict)
                else None
            ),
            custom_rule_entries=custom_rule_entries,
        )
    else:
        base_state = default_rule_state(study, custom_rule_entries=custom_rule_entries)

    updated_state = base_state
    for entry in transfer_payload.get("variant_entries", []):
        updated_state = apply_variant_to_rule_state(
            study,
            updated_state,
            variant_asset_id=str(entry.get("rule_id") or ""),
            origin_rule_id=str(entry.get("origin_rule_id") or ""),
            replace_current=True,
            custom_rule_entries=custom_rule_entries,
        )
    package_entry = transfer_payload.get("package_entry")
    if isinstance(package_entry, dict) and package_entry.get("rule_id"):
        used_asset_ids = list(updated_state.get("used_asset_ids", []))
        package_token = custom_asset_id(str(package_entry["rule_id"]))
        if package_token not in used_asset_ids:
            used_asset_ids.append(package_token)
        updated_state = enrich_rule_state(
            study,
            {
                "study_id": study.study_id,
                "used_asset_ids": used_asset_ids,
                "selected_feature_ids": updated_state.get("selected_feature_ids", []),
            },
            custom_rule_entries=custom_rule_entries,
        )
    return updated_state


def _resolve_search_base_bundle(
    study,
    *,
    base_policy: PolicyDefinition,
    filtered_snapshot: pl.DataFrame,
    baseline_bundle,
    last_simulation_state: dict[str, Any] | None,
):
    if base_policy.policy_id == study.manifest.baseline_policy.policy_id and (
        base_policy.rules == study.manifest.baseline_policy.rules
    ):
        return baseline_bundle

    manual_selected_features: list[str] = []
    if (
        isinstance(last_simulation_state, dict)
        and last_simulation_state.get("study_id") == study.study_id
    ):
        manual_rule_state = last_simulation_state.get("rule_state")
        normalized_rule_state = state_for_study(manual_rule_state, study.study_id) or {}
        manual_selected_features = list(
            normalized_rule_state.get("selected_feature_ids", [])
        )

    feature_ids = merge_feature_ids(
        manual_selected_features,
        feature_ids_used_by_rules(study, base_policy.rules),
    )
    base_scenario = ScenarioDefinition(
        scenario_id=f"{study.study_id}-search-base",
        name="Base da busca",
        description="Referencia analitica da busca automatica.",
        policy=base_policy,
        feature_ids=feature_ids,
        tags=["search_base"],
    )
    return orchestrator.run_scenario(
        study,
        base_scenario,
        baseline_bundle=baseline_bundle,
        snapshot_override=filtered_snapshot,
    )


def render_matrix_preview(
    n_clicks: int,
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
    matrix_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], go.Figure, list[html.Div], dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    if not n_clicks or not study_id or not row_variable or not column_variable:
        updated_matrix_state = update_matrix_generated_state(
            study_id,
            row_variable,
            column_variable,
            filter_variables,
            filter_operators,
            filter_values,
            None,
            matrix_state,
            generated_at,
        )
        return (
            updated_matrix_state,
            empty_figure("Selecione as variaveis e gere a matriz."),
            [],
            matrix_selection_payload(study_id, row_variable, column_variable, []),
        )

    study = load_study(study_id)
    eligible_snapshot = matrix_eligible_snapshot(
        study,
        months,
        segment_field,
        segment_values,
        rule_state,
        custom_rule_state,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
        predicate_editor_state,
        filter_variables,
        filter_operators,
        filter_values,
    )
    axis_specs = {
        "row": matrix_axis_spec(eligible_snapshot, row_variable),
        "column": matrix_axis_spec(eligible_snapshot, column_variable),
    }
    updated_matrix_state = update_matrix_generated_state(
        study_id,
        row_variable,
        column_variable,
        filter_variables,
        filter_operators,
        filter_values,
        axis_specs,
        matrix_state,
        generated_at,
    )
    event_column = study.manifest.snapshot.performance_columns.get("matrix_event")
    return (
        updated_matrix_state,
        build_matrix_preview(
            eligible_snapshot,
            row_variable,
            column_variable,
            event_column,
            interaction_token=generated_at,
            axis_specs=axis_specs,
        ),
        build_matrix_summary(eligible_snapshot, event_column),
        matrix_selection_payload(study_id, row_variable, column_variable, []),
    )


def update_matrix_generated_state(
    study_id: str | None,
    row_variable: str | None,
    column_variable: str | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
    axis_specs: dict[str, Any] | None,
    matrix_state: dict[str, Any] | None,
    generated_at: str,
) -> dict[str, Any]:
    if not study_id:
        return matrix_state or {}
    base_state = dict(state_for_study(matrix_state, study_id) or {"study_id": study_id})
    filters = [
        {
            "variable": variable,
            "operator": operator,
            "value": value,
        }
        for variable, operator, value in zip(
            filter_variables,
            filter_operators,
            filter_values,
            strict=False,
        )
    ]
    base_state.update(
        {
            "study_id": study_id,
            "row_variable": row_variable,
            "column_variable": column_variable,
            "filter_count": max(1, len(filter_variables) or 1),
            "filters": filters,
            "last_generated_at": generated_at,
            "last_generated_config": {
                "row_variable": row_variable,
                "column_variable": column_variable,
                "filters": filters,
                "axis_specs": axis_specs or {},
            },
            "axis_specs": axis_specs or {},
            "updated_at": generated_at,
        }
    )
    return base_state


def matrix_selection_payload(
    study_id: str | None,
    row_variable: str | None,
    column_variable: str | None,
    cells: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "study_id": study_id,
        "row_variable": row_variable,
        "column_variable": column_variable,
        "cells": cells,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_matrix_selection(
    click_data: dict[str, Any] | None,
    selected_data: dict[str, Any] | None,
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    active_decision: str | None,
    selection_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not study_id or not row_variable or not column_variable:
        return matrix_selection_payload(study_id, row_variable, column_variable, [])
    stored = state_for_study(selection_state, study_id)
    if (
        stored.get("row_variable") != row_variable
        or stored.get("column_variable") != column_variable
    ):
        assignments: list[dict[str, str]] = []
    else:
        assignments = [
            {
                "row": str(cell.get("row")),
                "column": str(cell.get("column")),
                "decision": str(cell.get("decision")),
            }
            for cell in stored.get("cells", [])
            if cell.get("row") is not None
            and cell.get("column") is not None
            and cell.get("decision")
        ]

    if not active_decision:
        return matrix_selection_payload(
            study_id,
            row_variable,
            column_variable,
            assignments,
        )

    assignment_map = {
        (item["row"], item["column"]): item["decision"] for item in assignments
    }

    triggered_prop_ids = list(ctx.triggered_prop_ids)
    if "matrix-figure.selectedData" in triggered_prop_ids and selected_data:
        dragged_cells: list[dict[str, str]] = []
        for point in selected_data.get("points", []):
            cell = matrix_cell_from_point(point)
            if cell not in dragged_cells:
                dragged_cells.append(cell)
        if dragged_cells:
            targeted = [(cell["row"], cell["column"]) for cell in dragged_cells]
            if all(assignment_map.get(cell_key) == active_decision for cell_key in targeted):
                for cell_key in targeted:
                    assignment_map.pop(cell_key, None)
            else:
                for cell_key in targeted:
                    assignment_map[cell_key] = active_decision
        return matrix_selection_payload(
            study_id,
            row_variable,
            column_variable,
            [
                {"row": row, "column": column, "decision": decision}
                for (row, column), decision in assignment_map.items()
            ],
        )

    if not click_data or not click_data.get("points"):
        return selection_state or matrix_selection_payload(
            study_id,
            row_variable,
            column_variable,
            [],
        )

    point = click_data["points"][0]
    cell = matrix_cell_from_point(point)
    cell_key = (cell["row"], cell["column"])
    if assignment_map.get(cell_key) == active_decision:
        assignment_map.pop(cell_key, None)
    else:
        assignment_map[cell_key] = active_decision
    return matrix_selection_payload(
        study_id,
        row_variable,
        column_variable,
        [
            {"row": row, "column": column, "decision": decision}
            for (row, column), decision in assignment_map.items()
        ],
    )


def matrix_cell_from_point(point: dict[str, Any]) -> dict[str, str]:
    customdata = point.get("customdata")
    if isinstance(customdata, dict):
        row_value = customdata.get("row", point.get("y"))
        column_value = customdata.get("column", point.get("x"))
    else:
        row_value = point.get("y")
        column_value = point.get("x")
    return {"row": str(row_value), "column": str(column_value)}


def matrix_cell_decisions_from_state(
    selection_state: dict[str, Any] | None,
    study_id: str | None,
    row_variable: str | None,
    column_variable: str | None,
) -> list[dict[str, str]]:
    stored = state_for_study(selection_state, study_id)
    if (
        not stored
        or stored.get("row_variable") != row_variable
        or stored.get("column_variable") != column_variable
    ):
        return []
    return [
        {
            "row": str(cell.get("row")),
            "column": str(cell.get("column")),
            "decision": str(cell.get("decision")),
        }
        for cell in stored.get("cells", [])
        if cell.get("row") is not None
        and cell.get("column") is not None
        and cell.get("decision")
    ]


def entry_cell_decisions(entry: dict[str, Any]) -> list[dict[str, str]]:
    if isinstance(entry.get("cell_decisions"), list):
        return [
            {
                "row": str(cell.get("row")),
                "column": str(cell.get("column")),
                "decision": str(cell.get("decision")),
            }
            for cell in entry.get("cell_decisions", [])
            if cell.get("row") is not None
            and cell.get("column") is not None
            and cell.get("decision")
        ]
    decision = str(entry.get("decision") or "").strip()
    return [
        {"row": str(cell.get("row")), "column": str(cell.get("column")), "decision": decision}
        for cell in entry.get("selected_cells", [])
        if cell.get("row") is not None and cell.get("column") is not None and decision
    ]


def infer_axis_specs_from_selected_cells(entry: dict[str, Any]) -> dict[str, Any]:
    stored_axis_specs = entry.get("axis_specs")
    if isinstance(stored_axis_specs, dict) and stored_axis_specs:
        return stored_axis_specs
    cell_decisions = entry_cell_decisions(entry)
    return {
        "row": infer_axis_spec_from_labels(
            [str(cell.get("row")) for cell in cell_decisions]
        ),
        "column": infer_axis_spec_from_labels(
            [str(cell.get("column")) for cell in cell_decisions]
        ),
    }


def infer_axis_spec_from_labels(labels: list[str]) -> dict[str, Any]:
    unique_labels: list[str] = []
    for label in labels:
        if label and label not in unique_labels:
            unique_labels.append(label)
    intervals: list[tuple[float, float, str]] = []
    for label in unique_labels:
        parsed = parse_interval_label(label)
        if parsed is None:
            intervals = []
            break
        lower, upper = parsed
        intervals.append((lower, upper, label))
    if intervals:
        intervals.sort(key=lambda item: (item[0], item[1]))
        interval_boundaries: list[float] = [intervals[0][0]]
        interval_labels: list[str] = []
        for lower, upper, label in intervals:
            if lower > interval_boundaries[-1]:
                interval_boundaries.append(lower)
            if upper > interval_boundaries[-1]:
                interval_boundaries.append(upper)
            interval_labels.append(label)
        return {"type": "binned", "boundaries": interval_boundaries, "labels": interval_labels}
    return {"type": "discrete", "labels": unique_labels}


def parse_interval_label(label: str) -> tuple[float, float] | None:
    if not label.startswith("[") or "," not in label:
        return None
    core = label[1:-1]
    lower_raw, upper_raw = core.split(",", maxsplit=1)
    try:
        return float(lower_raw.strip()), float(upper_raw.strip())
    except ValueError:
        return None


def render_selected_matrix(
    selection_state: dict[str, Any] | None,
    editing_state: dict[str, Any] | None,
    matrix_state: dict[str, Any] | None,
    study_id: str,
    active_decision: str | None,
    row_variable: str | None,
    column_variable: str | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
) -> tuple[go.Figure, list[html.Div], str]:
    cell_decisions = matrix_cell_decisions_from_state(
        selection_state,
        study_id,
        row_variable,
        column_variable,
    )
    figure, summary = build_current_matrix_artifacts(
        study_id,
        row_variable,
        column_variable,
        filter_variables,
        filter_operators,
        filter_values,
        months,
        segment_field,
        segment_values,
        rule_state,
        custom_rule_state,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
        predicate_editor_state,
        cell_decisions,
        (state_for_study(matrix_state, study_id) or {}).get("axis_specs")
        or (
            editing_state.get("axis_specs")
            if editing_state and editing_state.get("study_id") == study_id
            else {}
        ),
    )
    return figure, summary, matrix_selection_summary(cell_decisions, active_decision)


def build_current_matrix_artifacts(
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
    cell_decisions: list[dict[str, str]],
    axis_specs: dict[str, Any] | None = None,
) -> tuple[go.Figure, list[html.Div]]:
    if not study_id or not row_variable or not column_variable:
        return empty_figure("Selecione as variaveis e gere a matriz."), []
    study = load_study(study_id)
    eligible_snapshot = matrix_eligible_snapshot(
        study,
        months,
        segment_field,
        segment_values,
        rule_state,
        custom_rule_state,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
        predicate_editor_state,
        filter_variables,
        filter_operators,
        filter_values,
    )
    event_column = study.manifest.snapshot.performance_columns.get("matrix_event")
    interaction_token = datetime.now(timezone.utc).isoformat()
    return (
        build_matrix_preview(
            eligible_snapshot,
            row_variable,
            column_variable,
            event_column,
            cell_decisions,
            interaction_token=interaction_token,
            axis_specs=axis_specs,
        ),
        build_matrix_summary(eligible_snapshot, event_column),
    )


def matrix_eligible_snapshot(
    study,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
    filter_variables: list[str | None],
    filter_operators: list[str | None],
    filter_values: list[float | None],
) -> pl.DataFrame:
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    filtered_snapshot = filter_snapshot(
        matrix_base_snapshot(study),
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    policy = build_candidate_policy(
        study,
        rule_state=normalize_rule_state(
            study,
            rule_state,
            custom_rules=custom_rules,
            custom_rule_entries=custom_entries,
        ),
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
        cutoff_override=resolve_active_cutoff_override(
            study.study_id,
            cutoff_override,
            cutoff_handle,
            cutoff_objective,
            cutoff_value,
        ),
    )
    eligible_snapshot = extract_eligible_population(filtered_snapshot, policy)
    for filter_variable, filter_operator, filter_value in zip(
        filter_variables,
        filter_operators,
        filter_values,
        strict=False,
    ):
        eligible_snapshot = apply_optional_matrix_filter(
            eligible_snapshot,
            filter_variable,
            filter_operator,
            filter_value,
        )
    return eligible_snapshot


def matrix_selection_summary(
    cell_decisions: list[dict[str, str]],
    active_decision: str | None = None,
) -> str:
    if not cell_decisions:
        decision_hint = (
            f"Decisao ativa: {decision_label(active_decision)}. "
            if active_decision
            else ""
        )
        return (
            f"{decision_hint}"
            "Clique em uma celula para atribuir a decisao ativa. "
            "Para varias de uma vez, arraste uma area sobre a matriz. "
            "Clique novamente em uma celula ja marcada com a mesma decisao para remove-la."
        )
    decisions: dict[str, list[dict[str, str]]] = {}
    for cell in cell_decisions:
        decisions.setdefault(cell["decision"], []).append(cell)
    decision_parts = [
        f"{decision_label(decision)}: {len(cells)}"
        for decision, cells in sorted(
            decisions.items(),
            key=lambda item: decision_sort_key(item[0]),
        )
    ]
    preview_cells = "; ".join(
        (
            f"{decision_label(cell['decision'])} -> "
            f"linha {cell['row']} | coluna {cell['column']}"
        )
        for cell in cell_decisions[:4]
    )
    suffix = "" if len(cell_decisions) <= 4 else f"; +{len(cell_decisions) - 4} celulas"
    active_hint = (
        f" Decisao ativa para novos cliques: {decision_label(active_decision)}."
        if active_decision
        else ""
    )
    return (
        f"Atribuicoes atuais ({len(cell_decisions)} celulas): "
        f"{', '.join(decision_parts)}. {preview_cells}{suffix}.{active_hint}"
    )


def matrix_decision_order(
    study,
    cell_decisions: list[dict[str, str]] | None = None,
) -> list[str]:
    if cell_decisions:
        return sorted(
            {
                str(cell.get("decision"))
                for cell in cell_decisions
                if cell.get("decision")
            },
            key=decision_sort_key,
        )
    declared_decisions = {
        study.manifest.baseline_policy.default_decision,
        *[rule.decision for rule in study.manifest.baseline_policy.rules],
    }
    return sorted(declared_decisions, key=decision_sort_key)


def build_matrix_rules_from_context(
    snapshot: pl.DataFrame,
    row_variable: str,
    column_variable: str,
    cell_decisions: list[dict[str, str]],
    rule_name: str | None,
    study,
    custom_rules: list[DecisionRuleDefinition],
) -> list[DecisionRuleDefinition]:
    existing_rule_ids = {
        *[rule.rule_id for rule in study.manifest.baseline_policy.rules],
        *[rule.rule_id for rule in custom_rules],
    }
    return build_matrix_rule_set(
        snapshot=snapshot,
        row_variable=row_variable,
        column_variable=column_variable,
        cell_decisions=cell_decisions,
        name=(rule_name or "").strip() or "Regra criada pela matriz",
        existing_rule_ids=existing_rule_ids,
        decision_order=matrix_decision_order(study, cell_decisions),
    )


def preview_matrix_rule(
    n_clicks: int,
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    selection_state: dict[str, Any] | None,
    decision: str | None,
    rule_name: str | None,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
) -> list[html.Div]:
    if not n_clicks:
        return []
    if not study_id or not row_variable or not column_variable:
        return [
            html.Div(
                "Preencha as variaveis da matriz antes de avaliar a previa.",
                className="info-copy",
            )
        ]

    study = load_study(study_id)
    snapshot = study_repository.load_snapshot(study)
    custom_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    cell_decisions = matrix_cell_decisions_from_state(
        selection_state,
        study_id,
        row_variable,
        column_variable,
    )
    try:
        matrix_rules = build_matrix_rules_from_context(
            snapshot,
            row_variable,
            column_variable,
            cell_decisions,
            rule_name,
            study,
            custom_rules,
        )
    except ValueError as error:
        return [html.Div(str(error), className="info-copy")]

    filtered_snapshot = filter_snapshot(
        study_repository.load_snapshot(study),
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        date_column=study.manifest.snapshot.date_column,
    )
    baseline_bundle = orchestrator.run_baseline_with_snapshot(
        study,
        snapshot_override=filtered_snapshot,
    )
    base_policy = build_candidate_policy(
        study,
        rule_state=normalize_rule_state(
            study,
            rule_state,
            custom_rules=custom_rules,
            custom_rule_entries=custom_entries,
        ),
        custom_rules=custom_rules,
        custom_rule_entries=custom_entries,
        cutoff_override=resolve_active_cutoff_override(
            study_id,
            cutoff_override,
            cutoff_handle,
            cutoff_objective,
            cutoff_value,
        ),
    )
    preview_policy = base_policy
    for matrix_rule in matrix_rules:
        preview_policy = append_rule_to_policy(preview_policy, matrix_rule)
    preview_result = evaluate_policy_preview(
        study,
        preview_policy,
        baseline_bundle,
        filtered_snapshot,
        feature_ids=merge_feature_ids(
            normalize_rule_state(
                study,
                rule_state,
                custom_rules=custom_rules,
                custom_rule_entries=custom_entries,
            )["selected_feature_ids"],
            feature_ids_used_by_rules(study, preview_policy.rules),
        ),
    )
    cards = build_metric_cards(preview_result, baseline_bundle.result, compact=True)
    cards.insert(
        0,
        html.Div(
            className="metric-card metric-card-compact",
            children=[
                html.Div("Regras geradas", className="metric-label"),
                html.Div(str(len(matrix_rules)), className="metric-value"),
                html.Div(
                    ", ".join(decision_label(rule.decision) for rule in matrix_rules),
                    className="metric-delta",
                ),
            ],
        ),
    )
    return cards


def save_matrix_rule(
    n_clicks: int,
    study_id: str,
    row_variable: str | None,
    column_variable: str | None,
    selection_state: dict[str, Any] | None,
    decision: str | None,
    rule_name: str | None,
    custom_rule_state: dict[str, Any] | None,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    rule_state: dict[str, Any] | None,
    matrix_filter_variables: list[str | None],
    matrix_filter_operators: list[str | None],
    matrix_filter_values: list[float | None],
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
    editing_rule_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, bool, dict[str, Any] | None]:
    if not study_id:
        return custom_rule_state or {}, "Nenhum estudo selecionado.", False, None
    study = load_study(study_id)
    custom_rules = custom_rules_from_store(study, custom_rule_state)
    persisted_entries = created_rule_repository.load(study)
    store_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_entries = persisted_entries or store_entries
    if not n_clicks:
        return (
            custom_rule_store_payload(study, custom_entries),
            "A regra salva aparecera em Ativos disponiveis na biblioteca.",
            False,
            None,
        )
    if not row_variable or not column_variable:
        return (
            custom_rule_store_payload(study, custom_entries),
            "Preencha as variaveis da matriz antes de salvar.",
            False,
            None,
        )
    cell_decisions = matrix_cell_decisions_from_state(
        selection_state,
        study_id,
        row_variable,
        column_variable,
    )
    eligible_snapshot = matrix_eligible_snapshot(
        study,
        months,
        segment_field,
        segment_values,
        rule_state,
        custom_rule_state,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
        predicate_editor_state,
        matrix_filter_variables,
        matrix_filter_operators,
        matrix_filter_values,
    )
    axis_specs = {
        "row": matrix_axis_spec(eligible_snapshot, row_variable),
        "column": matrix_axis_spec(eligible_snapshot, column_variable),
    }
    try:
        matrix_rules = build_matrix_rules_from_context(
            eligible_snapshot,
            row_variable,
            column_variable,
            cell_decisions,
            rule_name,
            study,
            custom_rules,
        )
    except ValueError as error:
        return custom_rule_store_payload(study, custom_entries), str(error), False, None

    normalized_rule_name = (rule_name or "").strip() or "Regra criada pela matriz"
    decision_order = matrix_decision_order(study, cell_decisions)

    editing_rule_id = (
        editing_rule_state.get("rule_id")
        if editing_rule_state and editing_rule_state.get("study_id") == study_id
        else None
    )
    editing_entry = find_entry_by_rule_id(custom_entries, editing_rule_id)
    if editing_entry is not None and editing_entry.get("rule_name") == normalized_rule_name:
        existing_entry = editing_entry
    else:
        existing_entry = None
    duplicate_entry = find_entry_by_name(custom_entries, normalized_rule_name)
    if duplicate_entry is not None:
        pending_entry = build_created_rule_entry(
            study,
            matrix_rules,
            asset_id=resolve_asset_id(custom_entries, normalized_rule_name, duplicate_entry),
            rule_name=normalized_rule_name,
            row_variable=row_variable,
            column_variable=column_variable,
            cell_decisions=cell_decisions,
            decision_order=decision_order,
            months=months,
            segment_field=segment_field,
            segment_values=segment_values,
            matrix_filters=matrix_filters_payload(
                matrix_filter_variables,
                matrix_filter_operators,
                matrix_filter_values,
            ),
            axis_specs=axis_specs,
            existing_entry=duplicate_entry,
            author=resolve_rule_author(existing_entry),
        )
        return (
            custom_rule_store_payload(study, custom_entries),
            (
                f"Ja existe uma regra chamada '{normalized_rule_name}'. "
                "Confirme se deseja sobrescrever."
            ),
            True,
            {"study_id": study_id, "entry": pending_entry},
        )

    new_entry = build_created_rule_entry(
        study,
        matrix_rules,
        asset_id=resolve_asset_id(custom_entries, normalized_rule_name, existing_entry),
        rule_name=normalized_rule_name,
        row_variable=row_variable,
        column_variable=column_variable,
        cell_decisions=cell_decisions,
        decision_order=decision_order,
        months=months,
        segment_field=segment_field,
        segment_values=segment_values,
        matrix_filters=matrix_filters_payload(
            matrix_filter_variables,
            matrix_filter_operators,
            matrix_filter_values,
        ),
        axis_specs=axis_specs,
        existing_entry=existing_entry,
        author=resolve_rule_author(existing_entry),
    )
    updated_entries = upsert_rule_entry(custom_entries, new_entry)
    created_rule_repository.save(study, updated_entries)
    return (
        custom_rule_store_payload(study, updated_entries),
        (
            f"Regra '{normalized_rule_name}' salva como ativo disponivel. "
            f"Foram geradas {len(matrix_rules)} regra(s) para as decisoes da composicao. "
            "Use Adicionar na biblioteca do Laboratorio Manual para ativa-la. "
            "As faixas usadas nesta regra serao replicadas em futuras edicoes."
        ),
        False,
        None,
    )


def confirm_overwrite_matrix_rule(
    submit_clicks: int,
    study_id: str,
    pending_rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, None]:
    if (
        not submit_clicks
        or not study_id
        or not pending_rule_state
        or pending_rule_state.get("study_id") != study_id
):
        study = load_study(study_id) if study_id else None
        entries = (
            custom_rule_entries_from_store(study, custom_rule_state) if study else []
        )
        payload = (
            custom_rule_store_payload(study, entries)
            if study
            else custom_rule_state or {}
        )
        return payload, "Sobrescrita cancelada ou indisponivel.", None

    study = load_study(study_id)
    persisted_entries = created_rule_repository.load(study)
    store_entries = custom_rule_entries_from_store(study, custom_rule_state)
    custom_entries = persisted_entries or store_entries
    replacement = dict(pending_rule_state["entry"])
    updated_entries = upsert_rule_entry(custom_entries, replacement)
    created_rule_repository.save(study, updated_entries)
    return (
        custom_rule_store_payload(study, updated_entries),
        (
            "Regra "
            f"'{replacement.get('rule_name', 'Regra criada pela matriz')}' "
            "sobrescrita com sucesso."
        ),
        None,
    )


def prepare_custom_rule_matrix_edit(
    _edit_clicks: list[int],
    study_id: str,
    custom_rule_state: dict[str, Any] | None,
    manual_ui_state: dict[str, Any] | None,
    rule_state: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str, bool]:
    triggered_id = current_triggered_id()
    triggered_value = None
    try:
        if ctx.triggered:
            triggered_value = ctx.triggered[0].get("value")
    except MissingCallbackContextException:
        triggered_value = None

    if not isinstance(triggered_id, dict) or not triggered_value:
        return no_update, "", False

    if not study_id:
        return no_update, "", False

    study = load_study(study_id)
    entries = custom_rule_entries_from_store(study, custom_rule_state)

    entry = find_entry_by_rule_id(entries, triggered_id.get("rule_id"))
    if entry is None:
        return no_update, "", False

    normalized_rule_state = normalize_rule_state(
        study,
        rule_state,
        custom_rule_entries=entries,
    )
    if str(entry.get("rule_id")) in normalized_rule_state.get("used_custom_rule_ids", []):
        rule_name = entry.get("rule_name") or (entry.get("rule") or {}).get(
            "name",
            "Regra criada pela matriz",
        )
        return (
            None,
            (
                f"A regra '{rule_name}' esta ativa na configuracao atual do Laboratorio Manual. "
                "Para edita-la na matriz sem viesar o publico elegivel, remova-a dos ativos "
                "em uso e execute Simular novamente antes de abrir a edicao."
            ),
            True,
        )

    resolution = normalized_saved_edit_filters(
        study,
        entry.get("eligible_filters", {}),
        manual_ui_state,
    )
    pending_state = {
        "study_id": study_id,
        "entry": entry,
        "current_filters": resolution["current_filters"],
        "restore_filters": resolution["restore_filters"],
        "restore_mode": (
            "ask_restore"
            if resolution["filters_compatible"]
            else "current_only"
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    message = build_matrix_edit_confirmation_message(
        entry.get("rule_name") or (entry.get("rule") or {}).get("name", "Regra criada pela matriz"),
        resolution,
    )
    return pending_state, message, True


def apply_custom_rule_matrix_edit(
    submit_clicks: int,
    cancel_clicks: int,
    study_id: str,
    pending_edit_state: dict[str, Any] | None,
    rule_state: dict[str, Any] | None,
    custom_rule_state: dict[str, Any] | None,
    cutoff_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
    predicate_editor_state: dict[str, Any] | None,
) -> tuple[
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
]:
    triggered_prop_ids = list(ctx.triggered_prop_ids)
    if (
        not study_id
        or not pending_edit_state
        or pending_edit_state.get("study_id") != study_id
    ):
        return (no_update,) * 25

    if "matrix-edit-alert.submit_n_clicks" not in triggered_prop_ids and (
        "matrix-edit-alert.cancel_n_clicks" not in triggered_prop_ids
    ):
        return (no_update,) * 25

    if (
        "matrix-edit-alert.cancel_n_clicks" in triggered_prop_ids
        and pending_edit_state.get("restore_mode") == "current_only"
    ):
        return (no_update,) * 25

    entry = pending_edit_state.get("entry", {})
    matrix_filters = entry.get("eligible_filters", {}).get("matrix_filters", [])
    axis_specs = infer_axis_specs_from_selected_cells(entry)
    selected_filters = (
        pending_edit_state.get("restore_filters", {})
        if "matrix-edit-alert.submit_n_clicks" in triggered_prop_ids
        else pending_edit_state.get("current_filters", {})
    )
    manual_payload = {
        "study_id": study_id,
        "filters": selected_filters,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    matrix_config = {
        "study_id": study_id,
        "row_variable": entry.get("row_variable"),
        "column_variable": entry.get("column_variable"),
        "filter_count": max(1, len(matrix_filters) or 1),
        "filters": matrix_filters,
        "axis_specs": axis_specs,
        "last_generated_at": datetime.now(timezone.utc).isoformat(),
        "last_generated_config": {
            "row_variable": entry.get("row_variable"),
            "column_variable": entry.get("column_variable"),
            "filters": matrix_filters,
            "axis_specs": axis_specs,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    restored_cell_decisions = entry_cell_decisions(entry)
    selection_state = matrix_selection_payload(
        study_id,
        entry.get("row_variable"),
        entry.get("column_variable"),
        restored_cell_decisions,
    )
    editing_state = {
        "study_id": study_id,
        "rule_id": entry.get("rule_id"),
        "version": entry.get("version"),
        "source_type": entry.get("source_type"),
        "axis_specs": axis_specs,
    }
    restored_matrix_figure, restored_matrix_summary = build_current_matrix_artifacts(
        study_id,
        entry.get("row_variable"),
        entry.get("column_variable"),
        [item.get("variable") for item in matrix_filters],
        [item.get("operator") for item in matrix_filters],
        [item.get("value") for item in matrix_filters],
        selected_filters.get("months"),
        selected_filters.get("segment_field"),
        selected_filters.get("segment_values"),
        rule_state,
        custom_rule_state,
        cutoff_override,
        cutoff_handle,
        cutoff_objective,
        cutoff_value,
        predicate_editor_state,
        restored_cell_decisions,
        axis_specs,
    )
    decision_order = entry.get("decision_order") or [
        cell["decision"] for cell in restored_cell_decisions if cell.get("decision")
    ]
    active_decision = (
        decision_order[0]
        if decision_order
        else (restored_cell_decisions[0]["decision"] if restored_cell_decisions else "approve")
    )
    manual_outputs = manual_scenario_outputs(
        n_clicks=1,
        study_id=study_id,
        months=selected_filters.get("months"),
        segment_field=selected_filters.get("segment_field"),
        segment_values=selected_filters.get("segment_values"),
        rule_state=rule_state,
        custom_rule_state=custom_rule_state,
        cutoff_override=cutoff_override,
        cutoff_handle=cutoff_handle,
        cutoff_objective=cutoff_objective,
        cutoff_value=cutoff_value,
        predicate_editor_state=predicate_editor_state,
    )
    return (
        "rule_composition",
        manual_payload,
        selected_filters.get("months"),
        selected_filters.get("segment_field"),
        selected_filters.get("segment_values"),
        entry.get("row_variable"),
        entry.get("column_variable"),
        matrix_config,
        max(1, len(matrix_filters) or 1),
        selection_state,
        entry.get("rule_name", "Regra criada pela matriz"),
        active_decision,
        f"Regra '{entry.get('rule_name', '')}' carregada para edicao na matriz.",
        editing_state,
        None,
        restored_matrix_figure,
        restored_matrix_summary,
        matrix_selection_summary(restored_cell_decisions, active_decision),
        *manual_outputs,
    )


def find_entry_by_name(
    entries: list[dict[str, Any]],
    name: str,
) -> dict[str, Any] | None:
    normalized_name = name.strip().casefold()
    for entry in entries:
        entry_name = str(
            entry.get("rule_name") or (entry.get("rule") or {}).get("name", "")
        ).strip()
        if entry_name.casefold() == normalized_name:
            return entry
    return None


def find_entry_by_rule_id(
    entries: list[dict[str, Any]],
    rule_id: str | None,
) -> dict[str, Any] | None:
    if not rule_id:
        return None
    for entry in entries:
        if entry.get("rule_id") == rule_id:
            return entry
        payload = entry.get("rule")
        if isinstance(payload, dict) and payload.get("rule_id") == rule_id:
            return entry
        if any(
            payload.get("rule_id") == rule_id
            for payload in entry.get("rules", [])
            if isinstance(payload, dict)
        ):
            return entry
    return None


def upsert_rule_entry(
    entries: list[dict[str, Any]],
    replacement: dict[str, Any],
) -> list[dict[str, Any]]:
    updated_entries = [
        replacement if entry.get("rule_id") == replacement.get("rule_id") else entry
        for entry in entries
    ]
    if all(entry.get("rule_id") != replacement.get("rule_id") for entry in entries):
        updated_entries.append(replacement)
    return updated_entries


def matrix_filters_payload(
    variables: list[str | None],
    operators: list[str | None],
    values: list[float | None],
) -> list[dict[str, Any]]:
    return [
        {
            "variable": variable,
            "operator": operator,
            "value": value,
        }
        for variable, operator, value in zip(variables, operators, values, strict=False)
        if variable
    ]


def resolve_rule_author(existing_entry: dict[str, Any] | None) -> str:
    if existing_entry and existing_entry.get("author"):
        return str(existing_entry["author"])
    return "local_user"


def resolve_asset_id(
    entries: list[dict[str, Any]],
    rule_name: str,
    existing_entry: dict[str, Any] | None,
) -> str:
    if existing_entry and existing_entry.get("rule_id"):
        return str(existing_entry["rule_id"])
    existing_ids = {
        str(entry.get("rule_id"))
        for entry in entries
        if entry.get("rule_id")
    }
    return unique_rule_id(f"asset-{slugify(rule_name) or 'regra-matriz'}", existing_ids)


def build_created_rule_entry(
    study,
    rules: list[DecisionRuleDefinition],
    *,
    asset_id: str,
    rule_name: str,
    row_variable: str,
    column_variable: str,
    cell_decisions: list[dict[str, str]],
    decision_order: list[str],
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    matrix_filters: list[dict[str, Any]],
    axis_specs: dict[str, Any] | None,
    existing_entry: dict[str, Any] | None,
    author: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    created_at = existing_entry.get("created_at") if existing_entry else now
    previous_version = int(existing_entry.get("version", 0)) if existing_entry else 0
    return {
        "rule_id": asset_id,
        "rule_name": rule_name,
        "rules": [rule.to_dict() for rule in rules],
        "rule": rules[0].to_dict() if len(rules) == 1 else None,
        "source_type": "matrix_composition",
        "row_variable": row_variable,
        "column_variable": column_variable,
        "eligible_filters": {
            "months": months or [],
            "segment_field": segment_field,
            "segment_values": segment_values or [],
            "matrix_filters": matrix_filters,
        },
        "axis_specs": axis_specs or {},
        "selected_cells": [
            {"row": cell["row"], "column": cell["column"]} for cell in cell_decisions
        ],
        "cell_decisions": cell_decisions,
        "decision": rules[0].decision if len(rules) == 1 else None,
        "decision_order": decision_order,
        "version": previous_version + 1,
        "author": author,
        "created_at": created_at,
        "updated_at": now,
    }


def evaluate_policy_preview(
    study,
    policy: PolicyDefinition,
    baseline_bundle,
    snapshot: pl.DataFrame,
    *,
    feature_ids: list[str],
) -> ScenarioResult:
    features = orchestrator.feature_repository.load(study)
    enriched = orchestrator.feature_resolver.resolve(snapshot, features, feature_ids)
    executed = orchestrator.policy_executor.execute(enriched, policy)
    metrics = orchestrator.impact_estimator.estimate(
        executed,
        policy,
        baseline_expected_profit=baseline_bundle.result.metrics.expected_profit,
        performance_columns=study.manifest.snapshot.performance_columns,
    )
    out_of_support, uncertainty = orchestrator.uncertainty_estimator.estimate(
        executed,
        policy,
        reference_decision_column=study.manifest.snapshot.historical_decision_column,
    )
    metrics.out_of_support_ratio = out_of_support
    metrics.uncertainty_label = uncertainty
    metrics.complexity_score = orchestrator.complexity_estimator.estimate(policy)
    entity_id = study.manifest.snapshot.entity_id_column
    comparison_frame = baseline_bundle.frame.select(
        [entity_id, study.manifest.baseline_policy.decision_column]
    ).join(
        executed.select([entity_id, policy.decision_column]),
        on=entity_id,
        suffix="_candidate",
    )
    return ScenarioResult(
        scenario_id="matrix-preview",
        scenario_name="Previa da regra criada pela matriz",
        policy_id=policy.policy_id,
        study_id=study.study_id,
        metrics=metrics,
        transitions=orchestrator.counterfactual_engine.transitions(
            comparison_frame,
            study.manifest.baseline_policy.decision_column,
            f"{policy.decision_column}_candidate",
        ),
        decision_distribution=orchestrator.counterfactual_engine.distribution(
            executed,
            policy.decision_column,
        ),
        lineage={"type": "matrix_rule_preview"},
    )


def resolve_active_cutoff_override(
    study_id: str,
    stored_override: dict[str, Any] | None,
    cutoff_handle: str | None,
    cutoff_objective: str | None,
    cutoff_value: float | None,
) -> dict[str, Any] | None:
    if cutoff_objective == "fixed_cutoff":
        if cutoff_handle and cutoff_value is not None:
            return {
                "study_id": study_id,
                "handle": cutoff_handle,
                "value": cutoff_value,
                "metric": "fixed_cutoff",
                "source": "fixed_cutoff",
            }
        return None
    if (
        stored_override
        and stored_override.get("study_id") == study_id
        and stored_override.get("handle") == cutoff_handle
        and stored_override.get("metric") == (cutoff_objective or "approval")
    ):
        return stored_override
    return None
